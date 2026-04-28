#!/usr/bin/env python3
"""Configure GeoServer via REST API — workspace, datastore, layers, vector tiles"""
import os, sys, time
import requests
from requests.auth import HTTPBasicAuth

GS_URL  = os.getenv("GEOSERVER_URL","http://localhost:8080/geoserver")
GS_USER = os.getenv("GEOSERVER_USER","admin")
GS_PASS = os.getenv("GEOSERVER_PASS","geoserver")
PG_HOST = os.getenv("POSTGRES_HOST","db")
PG_DB   = os.getenv("POSTGRES_DB","jisp")
PG_USER = os.getenv("POSTGRES_USER","jisp")
PG_PASS = os.getenv("POSTGRES_PASSWORD","jisp_secret")
WS      = "jisp"
DS      = "jisp_postgis"

auth = HTTPBasicAuth(GS_USER, GS_PASS)
H_JSON = {"Content-Type":"application/json"}
H_XML  = {"Content-Type":"application/xml"}

def gs(method, path, **kwargs):
    url = f"{GS_URL}/rest{path}"
    r = requests.request(method, url, auth=auth, timeout=30, **kwargs)
    return r

def wait_for_geoserver(retries=20):
    print("Waiting for GeoServer...")
    for i in range(retries):
        try:
            r = requests.get(f"{GS_URL}/web/", timeout=5)
            if r.status_code == 200: print("GeoServer ready."); return
        except Exception: pass
        time.sleep(5)
        print(f"  retry {i+1}/{retries}")
    sys.exit("GeoServer not reachable")

def create_workspace():
    r = gs("GET", f"/workspaces/{WS}")
    if r.status_code == 200: print(f"Workspace {WS} exists"); return
    gs("POST", "/workspaces", headers=H_JSON,
       json={"workspace":{"name":WS}})
    print(f"Created workspace: {WS}")

def create_datastore():
    r = gs("GET", f"/workspaces/{WS}/datastores/{DS}")
    if r.status_code == 200: print(f"Datastore {DS} exists"); return
    gs("POST", f"/workspaces/{WS}/datastores", headers=H_JSON, json={
        "dataStore": {
            "name": DS, "type": "PostGIS",
            "connectionParameters": {"entry": [
                {"@key":"host",     "$":PG_HOST},
                {"@key":"port",     "$":"5432"},
                {"@key":"database", "$":PG_DB},
                {"@key":"user",     "$":PG_USER},
                {"@key":"passwd",   "$":PG_PASS},
                {"@key":"dbtype",   "$":"postgis"},
                {"@key":"schema",   "$":"public"},
                {"@key":"Expose primary keys","$":"true"},
            ]}
        }
    })
    print(f"Created datastore: {DS}")

def publish_layer(view: str, title: str, srs: str = "EPSG:4326"):
    r = gs("GET", f"/workspaces/{WS}/datastores/{DS}/featuretypes/{view}")
    if r.status_code == 200: print(f"Layer {view} exists"); return
    gs("POST", f"/workspaces/{WS}/datastores/{DS}/featuretypes", headers=H_JSON, json={
        "featureType": {
            "name": view, "nativeName": view, "title": title,
            "srs": srs, "projectionPolicy": "FORCE_DECLARED",
            "enabled": True,
            "metadata": {"entry": [
                {"@key":"time","$":{"enabled":True,"attribute":"created_at"}}
            ]}
        }
    })
    # Enable vector tiles (pbf + mvt)
    gs("PUT", f"/workspaces/{WS}/layers/{view}", headers=H_JSON, json={
        "layer": {"defaultStyle": {"name":"jisp:risk_style"},
                  "metadata": {"entry": [{"@key":"cacheLeafLayerInMemory","$":"true"}]}}
    })
    print(f"Published layer: {view} ({title})")

LAYERS = [
    ("v_assets_us",   "JISP US Assets"),
    ("v_assets_uk",   "JISP UK Assets"),
    ("v_assets_anz",  "JISP ANZ Assets"),
    ("v_assets_apac", "JISP APAC Assets"),
    ("v_assets_with_risk", "JISP Assets with Risk"),
    ("v_inspection_queue_full", "JISP Inspection Queue"),
    ("cluster_zones", "JISP Cluster Zones"),
]

def create_risk_style():
    sld = """<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0" xmlns="http://www.opengis.net/sld">
<NamedLayer><Name>jisp:risk_style</Name><UserStyle><Title>JISP Risk Style</Title>
<FeatureTypeStyle><Rule>
  <Name>critical</Name><Filter><PropertyIsEqualTo><PropertyName>risk_tier</PropertyName><Literal>critical</Literal></PropertyIsEqualTo></Filter>
  <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName><Fill><CssParameter name="fill">#E74C3C</CssParameter></Fill></Mark><Size>12</Size></Graphic></PointSymbolizer>
</Rule><Rule>
  <Name>high</Name><Filter><PropertyIsEqualTo><PropertyName>risk_tier</PropertyName><Literal>high</Literal></PropertyIsEqualTo></Filter>
  <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName><Fill><CssParameter name="fill">#F7941D</CssParameter></Fill></Mark><Size>10</Size></Graphic></PointSymbolizer>
</Rule><Rule>
  <Name>medium</Name><Filter><PropertyIsEqualTo><PropertyName>risk_tier</PropertyName><Literal>medium</Literal></PropertyIsEqualTo></Filter>
  <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName><Fill><CssParameter name="fill">#F1C40F</CssParameter></Fill></Mark><Size>8</Size></Graphic></PointSymbolizer>
</Rule><Rule>
  <Name>low</Name>
  <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName><Fill><CssParameter name="fill">#00A896</CssParameter></Fill></Mark><Size>6</Size></Graphic></PointSymbolizer>
</Rule></FeatureTypeStyle></UserStyle></NamedLayer></StyledLayerDescriptor>"""
    r = gs("GET", f"/workspaces/{WS}/styles/risk_style")
    if r.status_code == 200: print("Risk style exists"); return
    gs("POST", f"/workspaces/{WS}/styles", headers=H_JSON,
       json={"style":{"name":"risk_style","filename":"risk_style.sld"}})
    gs("PUT", f"/workspaces/{WS}/styles/risk_style", headers=H_XML, data=sld)
    print("Created risk_style SLD")

if __name__ == "__main__":
    wait_for_geoserver()
    create_workspace()
    create_datastore()
    create_risk_style()
    for view, title in LAYERS:
        try: publish_layer(view, title)
        except Exception as e: print(f"  WARN: {view}: {e}")
    print("\nGeoServer setup complete.")
    print(f"WMS: {GS_URL}/{WS}/wms")
    print(f"VTile: {GS_URL}/gwc/service/tms/1.0.0/{WS}:v_assets_with_risk@EPSG:900913@pbf/{{z}}/{{x}}/{{y}}.pbf")
