"""GeoAI Risk Model — weighted feature scoring + SHAP attribution"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, date

logger = logging.getLogger(__name__)
MODEL_VERSION = "v1.0"

@dataclass
class RiskResult:
    asset_id: str
    risk_score: float
    risk_tier: str
    shap_values: dict = field(default_factory=dict)
    features_used: dict = field(default_factory=dict)
    anomaly_flag: bool = False
    anomaly_types: list = field(default_factory=list)

MATERIAL_RISK = {"AC":0.9,"CI":0.7,"CLAY":0.5,"CONC":0.5,"DI":0.3,"STL":0.4,"PVC":0.2,"HDPE":0.15,"GRP":0.2,"UNK":0.6}
CLASS_CRIT = {"WTP":0.95,"WWTP":0.85,"PUMP":0.8,"DAM":0.95,"RESERVOIR":0.85,"PIPE_W":0.6,"PIPE_S":0.5,"PIPE_ST":0.4,"VALVE":0.55,"HYDRANT":0.45,"METER":0.3,"MANHOLE":0.45,"SENSOR":0.3}
WEIGHTS = {"age_years":0.20,"material_risk":0.18,"class_criticality":0.17,"days_since_inspect":0.15,"condition_score":0.20,"diameter_mm_norm":0.04,"depth_m_norm":0.03,"is_critical":0.03}

def _fv(row: dict) -> dict:
    age = max(0.0, float(datetime.now().year - (row.get("install_year") or 1984)))
    mat = MATERIAL_RISK.get(str(row.get("material","UNK")).upper(), 0.6)
    crit = CLASS_CRIT.get(row.get("asset_class","PIPE_W"), 0.5)
    li = row.get("last_inspected")
    if li and hasattr(li, 'year'):
        days = float((date.today() - li).days)
    else:
        days = 1825.0
    cond = float(row.get("condition_score") or 50.0)
    return {
        "age_years": min(age, 120.0) / 120.0,
        "material_risk": mat,
        "class_criticality": crit,
        "days_since_inspect": min(days, 3650.0) / 3650.0,
        "condition_score": (100.0 - cond) / 100.0,
        "diameter_mm_norm": min(float(row.get("diameter_mm") or 150), 1200.0) / 1200.0,
        "depth_m_norm": min(float(row.get("depth_m") or 1.5), 10.0) / 10.0,
        "is_critical": float(row.get("is_critical", False)),
    }

def _tier(s: float) -> str:
    return "critical" if s>=75 else "high" if s>=55 else "medium" if s>=35 else "low"

def score_asset(row: dict) -> RiskResult:
    fv = _fv(row)
    score = round(min(100.0, sum(fv[k]*w for k,w in WEIGHTS.items()) * 100.0), 1)
    shap = {k: round(fv[k]*w*100.0,2) for k,w in WEIGHTS.items()}
    top5 = dict(sorted(shap.items(), key=lambda x:-x[1])[:5])
    return RiskResult(asset_id=str(row.get("asset_id","")), risk_score=score, risk_tier=_tier(score), shap_values=top5, features_used=fv)

def score_assets_batch(rows: list[dict]) -> list[RiskResult]:
    out = []
    for row in rows:
        try: out.append(score_asset(row))
        except Exception as e: logger.warning(f"Skip {row.get('asset_id')}: {e}")
    logger.info(f"Scored {len(out)} assets")
    return out
