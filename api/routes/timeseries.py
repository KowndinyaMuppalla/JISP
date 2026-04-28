"""Timeseries observations endpoint"""
from __future__ import annotations
import os, logging
from uuid import UUID
from typing import Optional

import asyncpg
from fastapi import APIRouter, Query

router = APIRouter()
logger = logging.getLogger("jisp.timeseries")
DB_URL = os.getenv("DATABASE_URL","postgresql://jisp:jisp_secret@localhost:5432/jisp")

@router.get("/assets/{asset_id}/observations")
async def get_observations(
    asset_id: UUID,
    metric: Optional[str] = None,
    from_time: Optional[str] = Query(None, alias="from"),
    to_time:   Optional[str] = Query(None, alias="to"),
    limit: int = 500,
):
    conn = await asyncpg.connect(DB_URL)
    try:
        wheres = ["asset_id=$1"]
        params: list = [asset_id]
        i = 2
        if metric:    wheres.append(f"metric=${i}"); params.append(metric); i+=1
        if from_time: wheres.append(f"time>=${i}::timestamptz"); params.append(from_time); i+=1
        if to_time:   wheres.append(f"time<=${i}::timestamptz"); params.append(to_time); i+=1
        params.append(limit)
        rows = await conn.fetch(
            f"SELECT time::text, metric, value, unit, quality_flag, source "
            f"FROM observations WHERE {' AND '.join(wheres)} ORDER BY time DESC LIMIT ${i}",
            *params)
        return {"asset_id": str(asset_id), "count": len(rows), "observations": [dict(r) for r in rows]}
    finally:
        await conn.close()

@router.get("/assets/{asset_id}/latest")
async def get_latest_readings(asset_id: UUID):
    conn = await asyncpg.connect(DB_URL)
    try:
        rows = await conn.fetch(
            """SELECT DISTINCT ON (metric) metric, value, unit, time::text, quality_flag
               FROM observations WHERE asset_id=$1
               ORDER BY metric, time DESC""", asset_id)
        return {"asset_id": str(asset_id), "latest": [dict(r) for r in rows]}
    finally:
        await conn.close()

@router.post("/assets/{asset_id}/observations", status_code=201)
async def post_observation(asset_id: UUID, body: dict):
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute(
            "INSERT INTO observations (time,asset_id,metric,value,unit,quality_flag,source) "
            "VALUES (now(),$1,$2,$3,$4,$5,$6)",
            asset_id, body["metric"], float(body["value"]),
            body.get("unit"), int(body.get("quality_flag",0)), body.get("source","manual"))
        return {"status": "recorded"}
    finally:
        await conn.close()
