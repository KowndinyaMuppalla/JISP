#!/usr/bin/env python3
"""
JISP Sample Data Seeder — Jacobs Water domain
Seeds ~180 realistic water assets across US, UK, ANZ, APAC
Run: python scripts/seed_sample_data.py
"""
import os, json, random, asyncio
from datetime import date, timedelta
import asyncpg

DB_URL = os.getenv("DATABASE_URL","postgresql://jisp:jisp_secret@localhost:5432/jisp")
random.seed(42)

def rd(a,b): return round(random.uniform(a,b),4)
def ri(a,b): return random.randint(a,b)
def rc(lst): return random.choice(lst)

# ── US Water Assets (Houston, TX area) ───────────────────────────
US_ASSETS = [
    # WTPs
    *[{"region_code":"US","asset_class":"WTP","name":f"Houston WTP-{i}",
       "lon":rd(-95.6,-95.2),"lat":rd(29.6,29.9),"material":"CONC",
       "install_year":ri(1955,1995),"condition_score":rd(45,85),
       "is_critical":True,"owner":"Houston Water","source":"epa_frs"} for i in range(1,5)],
    # Pump stations
    *[{"region_code":"US","asset_class":"PUMP","name":f"PS-{i:03d} Houston",
       "lon":rd(-95.5,-95.1),"lat":rd(29.5,30.0),"material":"STL",
       "install_year":ri(1970,2010),"condition_score":rd(40,90),
       "is_critical":rc([True,False]),"source":"epa_frs"} for i in range(1,12)],
    # Water mains (as point proxies for MVP)
    *[{"region_code":"US","asset_class":"PIPE_W","name":f"WM-{i:04d}",
       "lon":rd(-95.7,-95.0),"lat":rd(29.4,30.1),
       "material":rc(["DI","CI","AC","PVC"]),"diameter_mm":rc([100,150,200,300,450]),
       "install_year":ri(1945,2005),"condition_score":rd(20,95),
       "depth_m":rd(1.2,3.0),"is_critical":False,"source":"gis_export"} for i in range(1,35)],
    # Sensors
    *[{"region_code":"US","asset_class":"SENSOR","name":f"Pressure Sensor US-{i}",
       "lon":rd(-95.6,-95.1),"lat":rd(29.5,29.9),
       "install_year":ri(2010,2023),"condition_score":rd(70,99),"source":"scada"} for i in range(1,9)],
]

# ── UK Water Assets (Thames Valley) ──────────────────────────────
UK_ASSETS = [
    *[{"region_code":"UK","asset_class":"WTP","name":f"Thames WTP {rc(['A','B','C','D'])}{i}",
       "lon":rd(-0.8,0.2),"lat":rd(51.3,51.7),"material":"CONC",
       "install_year":ri(1948,1990),"condition_score":rd(50,88),
       "is_critical":True,"owner":"Thames Water","source":"os_opendata"} for i in range(1,4)],
    *[{"region_code":"UK","asset_class":"PIPE_W","name":f"UK-WM-{i:04d}",
       "lon":rd(-1.0,0.5),"lat":rd(51.2,51.8),
       "material":rc(["CI","AC","DI","PVC"]),"diameter_mm":rc([100,150,225,300]),
       "install_year":ri(1930,2000),"condition_score":rd(15,90),"depth_m":rd(0.9,2.5),
       "source":"os_opendata"} for i in range(1,25)],
    *[{"region_code":"UK","asset_class":"PUMP","name":f"UK Pump Station {i}",
       "lon":rd(-0.9,0.3),"lat":rd(51.3,51.7),"material":"STL",
       "install_year":ri(1965,2015),"condition_score":rd(45,85),"source":"os_opendata"} for i in range(1,8)],
    *[{"region_code":"UK","asset_class":"WWTP","name":f"Thames WWTP {i}",
       "lon":rd(-0.7,0.4),"lat":rd(51.3,51.7),"material":"CONC",
       "install_year":ri(1960,2000),"condition_score":rd(55,80),"is_critical":True,
       "owner":"Thames Water","source":"os_opendata"} for i in range(1,4)],
]

# ── ANZ Water Assets (Sydney, AU) ────────────────────────────────
ANZ_ASSETS = [
    *[{"region_code":"ANZ","asset_class":"RESERVOIR","name":f"Sydney Reservoir {rc(['North','South','East','West'])}-{i}",
       "lon":rd(150.8,151.3),"lat":rd(-34.1,-33.7),"material":"CONC",
       "capacity_ml":rd(50,500),"install_year":ri(1950,2000),
       "condition_score":rd(55,90),"is_critical":True,"owner":"Sydney Water","source":"wsaa"} for i in range(1,5)],
    *[{"region_code":"ANZ","asset_class":"PIPE_W","name":f"ANZ-WM-{i:04d}",
       "lon":rd(150.7,151.4),"lat":rd(-34.2,-33.6),
       "material":rc(["DI","PVC","HDPE","CI"]),"diameter_mm":rc([100,150,200,300]),
       "install_year":ri(1955,2015),"condition_score":rd(30,90),"source":"wsaa"} for i in range(1,22)],
    *[{"region_code":"ANZ","asset_class":"DAM","name":f"Warragamba Dam {i}",
       "lon":rd(150.6,150.9),"lat":rd(-34.0,-33.8),"material":"CONC",
       "install_year":ri(1940,1960),"condition_score":rd(70,90),"is_critical":True,
       "owner":"WaterNSW","source":"wsaa"} for i in range(1,3)],
    *[{"region_code":"ANZ","asset_class":"SENSOR","name":f"ANZ Sensor {i}",
       "lon":rd(150.8,151.2),"lat":rd(-34.0,-33.7),"install_year":ri(2012,2023),
       "condition_score":rd(75,99),"source":"scada"} for i in range(1,7)],
]

# ── APAC Water Assets (Singapore) ────────────────────────────────
APAC_ASSETS = [
    *[{"region_code":"APAC","asset_class":"WTP","name":f"SG Waterworks {rc(['A','B','C'])}{i}",
       "lon":rd(103.7,104.0),"lat":rd(1.28,1.42),"material":"CONC",
       "install_year":ri(1980,2015),"condition_score":rd(60,95),
       "is_critical":True,"owner":"PUB Singapore","source":"pub_sg"} for i in range(1,4)],
    *[{"region_code":"APAC","asset_class":"PIPE_W","name":f"SG-WM-{i:04d}",
       "lon":rd(103.7,104.0),"lat":rd(1.26,1.44),
       "material":rc(["DI","HDPE","PVC"]),"diameter_mm":rc([100,150,200]),
       "install_year":ri(1990,2020),"condition_score":rd(50,95),"source":"pub_sg"} for i in range(1,15)],
    *[{"region_code":"APAC","asset_class":"RESERVOIR","name":f"SG Reservoir {i}",
       "lon":rd(103.75,103.95),"lat":rd(1.30,1.42),"material":"CONC",
       "capacity_ml":rd(100,300),"install_year":ri(1970,2010),
       "condition_score":rd(70,95),"is_critical":True,"owner":"PUB Singapore","source":"pub_sg"} for i in range(1,4)],
]

ALL_ASSETS = US_ASSETS + UK_ASSETS + ANZ_ASSETS + APAC_ASSETS

# ── Synthetic observations ────────────────────────────────────────
def gen_observations(asset_id: str, asset_class: str) -> list[dict]:
    if asset_class not in ("SENSOR","WTP","PUMP","WWTP"): return []
    metrics = {
        "SENSOR": [("pressure_psi",45,75), ("flow_lps",10,80)],
        "WTP":    [("turbidity_ntu",0.1,2.0), ("ph",6.8,7.8), ("flow_lps",100,500)],
        "PUMP":   [("pressure_psi",30,90), ("flow_lps",50,200)],
        "WWTP":   [("flow_lps",50,300), ("ph",6.5,8.0)],
    }.get(asset_class, [])
    obs = []
    for metric, lo, hi in metrics:
        for d in range(30, 0, -1):
            noise = random.gauss(0, (hi-lo)*0.05)
            obs.append({"asset_id":asset_id,"metric":metric,
                         "value":max(lo, min(hi, rd(lo,hi)+noise)),
                         "unit": "psi" if "psi" in metric else "lps" if "lps" in metric else metric.split("_")[-1],
                         "days_ago": d})
    return obs

async def seed():
    conn = await asyncpg.connect(DB_URL)
    print(f"Connected. Seeding {len(ALL_ASSETS)} assets...")
    seeded = 0
    asset_ids = []
    try:
        async with conn.transaction():
            for a in ALL_ASSETS:
                row = await conn.fetchrow(
                    """INSERT INTO assets (region_code,asset_class,name,geometry,material,
                       diameter_mm,install_year,condition_score,capacity_ml,is_critical,
                       depth_m,owner,source)
                       VALUES ($1,$2,$3,ST_SetSRID(ST_MakePoint($4,$5),4326),
                               $6,$7,$8,$9,$10,$11,$12,$13,$14)
                       ON CONFLICT DO NOTHING RETURNING asset_id""",
                    a["region_code"], a["asset_class"], a["name"],
                    a["lon"], a["lat"],
                    a.get("material"), a.get("diameter_mm"), a.get("install_year"), a.get("condition_score"),
                    a.get("capacity_ml"), a.get("is_critical",False),
                    a.get("depth_m"), a.get("owner"), a.get("source","seed"))
                if row:
                    asset_ids.append((str(row["asset_id"]), a["asset_class"]))
                    seeded += 1

        print(f"  ✓ {seeded} assets seeded")

        # Seed observations
        obs_count = 0
        async with conn.transaction():
            for asset_id, asset_class in asset_ids:
                for o in gen_observations(asset_id, asset_class):
                    await conn.execute(
                        "INSERT INTO observations (time,asset_id,metric,value,unit,source) "
                        "VALUES (now()-($1 || ' days')::interval,$2::uuid,$3,$4,$5,$6)",
                        str(o["days_ago"]), asset_id, o["metric"], o["value"], o["unit"], "simulated")
                    obs_count += 1
        print(f"  ✓ {obs_count} observations seeded")

        # ── Inject realistic anomalies into 15% of sensor/WTP assets ──
        anomaly_assets = [a for a in asset_ids if a[1] in ("SENSOR","WTP","PUMP")][:8]
        anomaly_count = 0
        async with conn.transaction():
            for asset_id, asset_class in anomaly_assets:
                metric = "pressure_psi" if asset_class in ("SENSOR","PUMP") else "flow_lps"
                # Insert a spike in last 2 days (3x normal value)
                await conn.execute(
                    "INSERT INTO observations (time,asset_id,metric,value,unit,source) "
                    "VALUES (now()-'1 day'::interval,$1::uuid,$2,$3,$4,$5)",
                    asset_id, metric, 180.0 if "psi" in metric else 850.0,
                    "psi" if "psi" in metric else "lps", "simulated_anomaly")
                await conn.execute(
                    "INSERT INTO observations (time,asset_id,metric,value,unit,source) "
                    "VALUES (now()-'12 hours'::interval,$1::uuid,$2,$3,$4,$5)",
                    asset_id, metric, 195.0 if "psi" in metric else 900.0,
                    "psi" if "psi" in metric else "lps", "simulated_anomaly")
                anomaly_count += 1
        print(f"  ✓ {anomaly_count} anomaly injections seeded")
        print(f"\nSeed complete. Regions: US={sum(1 for a in ALL_ASSETS if a['region_code']=='US')} "
              f"UK={sum(1 for a in ALL_ASSETS if a['region_code']=='UK')} "
              f"ANZ={sum(1 for a in ALL_ASSETS if a['region_code']=='ANZ')} "
              f"APAC={sum(1 for a in ALL_ASSETS if a['region_code']=='APAC')}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(seed())
