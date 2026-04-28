"""File upload — ZIP/SHP/GPKG/GeoJSON → PostGIS assets"""
from __future__ import annotations
import os, logging, tempfile, shutil, zipfile, json
from pathlib import Path

import asyncpg
import geopandas as gpd
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()
logger = logging.getLogger("jisp.upload")
DB_URL = os.getenv("DATABASE_URL","postgresql://jisp:jisp_secret@localhost:5432/jisp")
ALLOWED = {".zip",".shp",".gpkg",".geojson",".json"}

@router.post("/import/upload")
async def upload_gis_file(
    file: UploadFile = File(...),
    region_code: str = "US",
    asset_class: str = "PIPE_W",
):
    suffix = Path(file.filename or "upload.geojson").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(400, f"Unsupported format {suffix}. Use: {ALLOWED}")

    tmpdir = tempfile.mkdtemp()
    try:
        fpath = Path(tmpdir) / (file.filename or f"upload{suffix}")
        with open(fpath, "wb") as f:
            f.write(await file.read())

        # Unzip if needed
        read_path = str(fpath)
        if suffix == ".zip":
            with zipfile.ZipFile(fpath, "r") as z:
                z.extractall(tmpdir)
            shp_files = list(Path(tmpdir).rglob("*.shp"))
            if shp_files:
                read_path = str(shp_files[0])
            else:
                gpkg = list(Path(tmpdir).rglob("*.gpkg"))
                if gpkg: read_path = str(gpkg[0])
                else:
                    geoj = list(Path(tmpdir).rglob("*.geojson")) + list(Path(tmpdir).rglob("*.json"))
                    if geoj: read_path = str(geoj[0])
                    else: raise HTTPException(400, "No spatial file found in ZIP")

        gdf = gpd.read_file(read_path)
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        conn = await asyncpg.connect(DB_URL)
        imported = 0
        try:
            async with conn.transaction():
                for _, row in gdf.iterrows():
                    geom = row.geometry
                    if geom is None or geom.is_empty: continue
                    geojson_str = json.dumps(row.geometry.__geo_interface__)
                    name = str(row.get("name") or row.get("NAME") or row.get("id") or f"Imported_{imported+1}")
                    await conn.execute(
                        """INSERT INTO assets (region_code,asset_class,name,geometry,source)
                           VALUES ($1,$2,$3,ST_SetSRID(ST_GeomFromGeoJSON($4),4326),$5)
                           ON CONFLICT DO NOTHING""",
                        region_code, asset_class, name, geojson_str, f"upload:{file.filename}")
                    imported += 1
        finally:
            await conn.close()

        logger.info(f"Imported {imported} features from {file.filename}")
        return {"status":"imported","file":file.filename,"features":imported,
                "region":region_code,"asset_class":asset_class}
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(500, f"Import error: {e}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
