"""Anomaly Detection — z-score + IQR on TimescaleDB observations"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class AnomalyResult:
    asset_id: str
    metric: str
    anomaly_flag: bool
    anomaly_type: str = ""
    z_score: float = 0.0
    value: float = 0.0
    threshold: float = 0.0
    message: str = ""

def detect_zscore(asset_id: str, metric: str, values: list[float], z_thresh: float = 3.0) -> AnomalyResult:
    if len(values) < 5:
        return AnomalyResult(asset_id=asset_id, metric=metric, anomaly_flag=False, message="insufficient data")
    arr  = np.array(values, dtype=float)
    mean, std = arr.mean(), arr.std()
    if std < 1e-9:
        return AnomalyResult(asset_id=asset_id, metric=metric, anomaly_flag=False)
    latest_z = abs((arr[-1] - mean) / std)
    flag = latest_z >= z_thresh
    return AnomalyResult(
        asset_id=asset_id, metric=metric, anomaly_flag=flag,
        anomaly_type="z_score_spike" if flag else "",
        z_score=round(float(latest_z), 3), value=float(arr[-1]),
        threshold=float(mean + z_thresh * std),
        message=f"{metric} z={latest_z:.2f} (thresh={z_thresh})" if flag else ""
    )

def detect_rolling_drop(asset_id: str, metric: str, values: list[float], drop_pct: float = 0.15) -> AnomalyResult:
    if len(values) < 10:
        return AnomalyResult(asset_id=asset_id, metric=metric, anomaly_flag=False)
    baseline = float(np.median(values[:-5]))
    recent   = float(np.mean(values[-5:]))
    if baseline < 1e-6:
        return AnomalyResult(asset_id=asset_id, metric=metric, anomaly_flag=False)
    drop = (baseline - recent) / baseline
    flag = drop >= drop_pct
    return AnomalyResult(
        asset_id=asset_id, metric=metric, anomaly_flag=flag,
        anomaly_type="rolling_drop" if flag else "",
        z_score=0.0, value=recent, threshold=baseline * (1 - drop_pct),
        message=f"{metric} dropped {drop*100:.1f}% from baseline" if flag else ""
    )
