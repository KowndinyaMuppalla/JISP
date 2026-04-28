"""Assets CRUD + spatial query"""
from __future__ import annotations
import os, logging
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("jisp.assets")
DB_URL = os.getenv("DATABASE_URL","postgresql://jisp:jisp_secret@localhost:5432/jisp")

async def get_conn():
    return await asyncpg.connect(DB_URL)

class AssetIn(BaseModel):
    region_code: str
    asset_class: str
    name: str
    lon: float; lat: float
    material: Optional[str] = None
    diameter_mm: Optional[float] = None
    install_year: Optional[int] = None
    condition_score: Optional[float] = None
    is_critical: bool = False
    attributes: dict = {}
    source: Optional[str] = "manual"

@router.get("/assets")
async def list_assets(
    region: Optional[str]  = Query(None),
    asset_class: Optional[str] = Query(None),
    risk_tier: Optional[str]   = Query(None),
    bbox: Optional[str]        = Query(None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(200, le=1000),
    offset: int = 0,
):
    conn = await get_conn()
    try:
        wheres = ["a.is_active = TRUE"]
        params: list = []
        i = 1
        if region:      wheres.append(f"a.region_code=${i}"); params.append(region); i+=1
        if asset_class: wheres.append(f"a.asset_class=${i}"); params.append(asset_class); i+=1
        if risk_tier:   wheres.append(f"a.risk_tier=${i}"); params.append(risk_tier); i+=1
        if bbox:
            try:
                mnlon,mnlat,mxlon,mxlat = map(float, bbox.split(","))
                wheres.append(f"ST_Intersects(a.geometry, ST_MakeEnvelope(${i},${i+1},${i+2},${i+3},4326))")
                params += [mnlon,mnlat,mxlon,mxlat]; i+=4
            except ValueError:
                raise HTTPException(400, "bbox must be minLon,minLat,maxLon,maxLat")
        sql = f"""
            SELECT a.asset_id::text, a.region_code, a.asset_class, a.name,
                   ST_X(ST_Centroid(a.geometry)) AS lon, ST_Y(ST_Centroid(a.geometry)) AS lat,
                   a.material, a.diameter_mm, a.install_year, a.condition_score,
                   a.risk_tier, a.is_critical, a.last_inspected::text, a.source,
                   rs.risk_score, rs.anomaly_flag
            FROM assets a
            LEFT JOIN LATERAL (
                SELECT risk_score, anomaly_flag FROM risk_scores
                WHERE asset_id=a.asset_id ORDER BY scored_at DESC LIMIT 1
            ) rs ON TRUE
            WHERE {' AND '.join(wheres)}
            ORDER BY a.name
            LIMIT ${i} OFFSET ${i+1}
        """
        params += [limit, offset]
        rows = await conn.fetch(sql, *params)
        return {"count": len(rows), "assets": [dict(r) for r in rows]}
    finally:
        await conn.close()

@router.get("/assets/{asset_id}")
async def get_asset(asset_id: UUID):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            """SELECT a.*, ST_AsGeoJSON(a.geometry)::json AS geojson,
                      rs.risk_score, rs.risk_tier AS ai_risk_tier, rs.shap_values,
                      rs.anomaly_flag, rs.anomaly_types, rs.scored_at::text
               FROM assets a
               LEFT JOIN LATERAL (
                   SELECT risk_score, risk_tier, shap_values, anomaly_flag, anomaly_types, scored_at
                   FROM risk_scores WHERE asset_id=a.asset_id ORDER BY scored_at DESC LIMIT 1
               ) rs ON TRUE
               WHERE a.asset_id=$1""", asset_id)
        if not row: raise HTTPException(404, "Asset not found")
        d = dict(row)
        d["asset_id"] = str(d["asset_id"])
        return d
    finally:
        await conn.close()

@router.post("/assets", status_code=201)
async def create_asset(asset: AssetIn):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            """INSERT INTO assets (region_code,asset_class,name,geometry,material,diameter_mm,
               install_year,condition_score,is_critical,attributes,source)
               VALUES ($1,$2,$3,ST_SetSRID(ST_MakePoint($4,$5),4326),$6,$7,$8,$9,$10,$11::jsonb,$12)
               RETURNING asset_id::text""",
            asset.region_code, asset.asset_class, asset.name, asset.lon, asset.lat,
            asset.material, asset.diameter_mm, asset.install_year, asset.condition_score,
            asset.is_critical, str(asset.attributes), asset.source)
        return {"asset_id": row["asset_id"], "status": "created"}
    finally:
        await conn.close()

@router.get("/assets/{asset_id}/geojson")
async def asset_geojson(asset_id: UUID):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT ST_AsGeoJSON(geometry)::json AS geom, name, asset_class, risk_tier FROM assets WHERE asset_id=$1",
            asset_id)
        if not row: raise HTTPException(404, "Not found")
        return {"type":"Feature","geometry":row["geom"],
                "properties":{"name":row["name"],"asset_class":row["asset_class"],"risk_tier":row["risk_tier"]}}
    finally:
        await conn.close()
