"""GeoAI pipeline endpoint — score + queue + explain"""
from __future__ import annotations
import os, logging, time, json
from uuid import UUID
from typing import Optional

import asyncpg
from fastapi import APIRouter, HTTPException, BackgroundTasks

from geoai.models.risk_models import score_assets_batch, MODEL_VERSION
from geoai.inspections.anomaly_detection import detect_zscore, detect_rolling_drop
from reasoning.ollama_client import generate, OllamaUnavailableError
from reasoning.reasoning_service import explain

router = APIRouter()
logger = logging.getLogger("jisp.geoai")
DB_URL = os.getenv("DATABASE_URL","postgresql://jisp:jisp_secret@localhost:5432/jisp")

async def _conn(): return await asyncpg.connect(DB_URL)

async def _run_pipeline(region: Optional[str] = None):
    conn = await _conn()
    try:
        where = f"WHERE is_active=TRUE" + (f" AND region_code='{region}'" if region else "")
        rows = await conn.fetch(
            f"SELECT asset_id,region_code,asset_class,material,diameter_mm,install_year,"
            f"condition_score,is_critical,depth_m,last_inspected FROM assets {where}")
        if not rows:
            logger.warning("No assets found for pipeline")
            return {"scored": 0, "queued": 0}

        asset_dicts = [dict(r) for r in rows]
        results = score_assets_batch(asset_dicts)

        # ── Run anomaly detection on observations ─────────────────────
        anomaly_map = {}  # asset_id -> list of anomaly results
        obs_rows = await conn.fetch(
            """SELECT asset_id::text, metric,
                      array_agg(value ORDER BY time) AS values
               FROM observations
               WHERE quality_flag < 2
               GROUP BY asset_id, metric
               HAVING count(*) >= 5""")

        for obs in obs_rows:
            aid = obs["asset_id"]
            vals = list(obs["values"])
            metric = obs["metric"]
            z = detect_zscore(aid, metric, vals)
            d = detect_rolling_drop(aid, metric, vals)
            for det in [z, d]:
                if det.anomaly_flag:
                    anomaly_map.setdefault(aid, []).append(det)

        # Insert alerts for new anomalies
        async with conn.transaction():
            for aid, detections in anomaly_map.items():
                for det in detections:
                    await conn.execute(
                        """INSERT INTO asset_alerts
                               (asset_id, alert_type, severity, message, metric, value, threshold)
                           VALUES ($1::uuid, $2, $3, $4, $5, $6, $7)""",
                        aid, det.anomaly_type,
                        4 if "spike" in det.anomaly_type else 3,
                        det.message, det.metric, det.value, det.threshold)

        # Write risk scores + update asset risk_tier
        async with conn.transaction():
            for r in results:
                has_anomaly = r.asset_id in anomaly_map
                anomaly_types = [d.anomaly_type for d in anomaly_map.get(r.asset_id, [])]
                await conn.execute(
                    """INSERT INTO risk_scores (asset_id,risk_score,risk_tier,model_version,shap_values,features_used,anomaly_flag,anomaly_types)
                       VALUES ($1::uuid,$2,$3,$4,$5::jsonb,$6::jsonb,$7,$8)""",
                    r.asset_id, r.risk_score, r.risk_tier, MODEL_VERSION,
                    json.dumps(r.shap_values), json.dumps(r.features_used),
                    has_anomaly, anomaly_types)
                await conn.execute(
                    "UPDATE assets SET risk_tier=$1 WHERE asset_id=$2::uuid",
                    r.risk_tier, r.asset_id)

        # Build inspection queue (clear old pending, insert ranked)
        region_clause = f"AND a.region_code='{region}'" if region else ""
        await conn.execute(f"DELETE FROM inspection_queue WHERE status='pending' {region_clause.replace('a.','')} ")

        scored_sorted = sorted(results, key=lambda x: -x.risk_score)
        async with conn.transaction():
            for rank, r in enumerate(scored_sorted, 1):
                reasons = []
                if r.risk_score >= 75: reasons.append("critical_score")
                if r.anomaly_flag:     reasons.append("anomaly_detected")
                await conn.execute(
                    """INSERT INTO inspection_queue (asset_id,region_code,priority_rank,priority_score,risk_tier,reason_codes)
                       SELECT $1::uuid, region_code, $2, $3, $4, $5 FROM assets WHERE asset_id=$1::uuid""",
                    r.asset_id, rank, r.risk_score, r.risk_tier,
                    reasons or ["scheduled_review"])

        logger.info(f"Pipeline complete: {len(results)} scored, {len(scored_sorted)} queued")
        return {"scored": len(results), "queued": len(scored_sorted)}
    finally:
        await conn.close()

@router.post("/geoai/run")
async def run_pipeline(background_tasks: BackgroundTasks, region: Optional[str] = None):
    background_tasks.add_task(_run_pipeline, region)
    return {"status": "pipeline_started", "region": region or "all"}

@router.get("/geoai/run-sync")
async def run_pipeline_sync(region: Optional[str] = None):
    result = await _run_pipeline(region)
    return {"status": "complete", **result}

@router.get("/geoai/inspection-queue")
async def inspection_queue(region: Optional[str] = None, limit: int = 50):
    conn = await _conn()
    try:
        where = f"AND iq.region_code='{region}'" if region else ""
        rows = await conn.fetch(
            f"""SELECT iq.queue_id::text, iq.asset_id::text, iq.priority_rank, iq.priority_score,
                       iq.risk_tier, iq.reason_codes, iq.recommended_date::text,
                       a.name, a.asset_class, a.region_code,
                       ST_X(ST_Centroid(a.geometry)) AS lon, ST_Y(ST_Centroid(a.geometry)) AS lat,
                       a.material, a.install_year, a.last_inspected::text
                FROM inspection_queue iq JOIN assets a ON a.asset_id=iq.asset_id
                WHERE iq.status='pending' {where}
                ORDER BY iq.priority_rank LIMIT $1""", limit)
        return {"count": len(rows), "queue": [dict(r) for r in rows]}
    finally:
        await conn.close()

@router.get("/geoai/explain/{asset_id}")
async def explain_asset(asset_id: UUID):
    conn = await _conn()
    t0 = time.time()
    try:
        row = await conn.fetchrow(
            """SELECT a.asset_id::text, a.name, a.asset_class, a.region_code, a.material,
                      a.install_year, a.condition_score, a.diameter_mm, a.depth_m,
                      a.is_critical, a.last_inspected::text,
                      rs.risk_score, rs.risk_tier, rs.shap_values, rs.anomaly_flag, rs.anomaly_types
               FROM assets a
               LEFT JOIN LATERAL (
                   SELECT risk_score,risk_tier,shap_values,anomaly_flag,anomaly_types
                   FROM risk_scores WHERE asset_id=a.asset_id ORDER BY scored_at DESC LIMIT 1
               ) rs ON TRUE
               WHERE a.asset_id=$1""", asset_id)
        if not row: raise HTTPException(404, "Asset not found")
        ctx = dict(row)
        ctx["asset_id"] = str(ctx["asset_id"])

        try:
            exp = explain(subject=ctx["name"], template="asset_risk", context=ctx)
            explanation_text = exp.explanation
        except OllamaUnavailableError:
            explanation_text = (
                f"Asset {ctx['name']} ({ctx['asset_class']}) — Risk: {ctx.get('risk_tier','unknown')} "
                f"(score {ctx.get('risk_score','N/A')}). "
                f"LLM explanation unavailable (Ollama offline). "
                f"Top risk factors: {ctx.get('shap_values','N/A')}."
            )

        latency = int((time.time()-t0)*1000)
        await conn.execute(
            """INSERT INTO explanation_log (asset_id,template,context,explanation,model,latency_ms)
               VALUES ($1::uuid,$2,$3::jsonb,$4,$5,$6)""",
            asset_id, "asset_risk", json.dumps(ctx), explanation_text,
            os.getenv("OLLAMA_MODEL","llama3.2"), latency)

        return {"asset_id": str(asset_id), "name": ctx["name"],
                "risk_score": ctx.get("risk_score"), "risk_tier": ctx.get("risk_tier"),
                "shap_values": ctx.get("shap_values"), "anomaly_flag": ctx.get("anomaly_flag"),
                "explanation": explanation_text, "model": os.getenv("OLLAMA_MODEL","llama3.2"),
                "latency_ms": latency}
    finally:
        await conn.close()
