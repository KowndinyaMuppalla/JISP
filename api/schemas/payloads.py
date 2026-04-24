"""Pydantic payload schemas for the JISP API.

This module defines request/response contracts for the reasoning and GeoAI layers.
All schemas enforce explanation-only semantics: no prediction, scoring,
or recommendations are permitted in responses.

Core Schemas:
    - ExplainRequest / ExplainResponse: Reasoning layer (LLaMA 3.3 explanations)
    - GeoAI Finding Schemas: Contract for spatial analysis findings
    - Metrics, Geometry, Context: Reusable building blocks

See reasoning/prompt_templates/GEOAI_CONTEXT_GUIDE.md for examples of
expected context structures for each template.

See api/GEOAI_FINDINGS_CONTRACT.md for formal GeoAI output specifications.
"""

from typing import Any, Literal
from datetime import datetime

from pydantic import BaseModel, Field


TemplateName = Literal["asset_risk", "flood_explanation", "anomaly_summary"]
FindingType = Literal[
    "flood_proximity",
    "flood_change_detection",
    "temperature_spike",
    "vegetation_anomaly",
    "elevation_discrepancy",
    "drainage_blockage",
    "sensor_malfunction",
]


class ExplainRequest(BaseModel):
    """Request to explain a GeoAI finding using a specific template.

    Fields:
        subject: Unique identifier (asset ID, event ID, anomaly ID, etc.).
        template: Which reasoning template to use (see reasoning/prompt_templates/).
        context: Optional structured GeoAI findings (metrics, signals, geometry refs).
                 Passed as-is to the reasoning service for interpolation.

    Example:
        {
            "subject": "ASSET-12345",
            "template": "asset_risk",
            "context": {
                "finding_type": "flood_proximity",
                "metrics": {"proximity_km": 2.5},
                "signals": ["Active flood zone within 5 km"]
            }
        }

    Error handling:
        - If template is unknown: 400 Bad Request
        - If Ollama is unreachable: 503 Service Unavailable
    """

    subject: str = Field(
        ...,
        description=(
            "Unique identifier for the entity being explained "
            "(e.g., 'ASSET-12345', 'FLOOD-EVENT-2025-0042', 'ANOMALY-001')."
        ),
        examples=["ASSET-12345", "FLOOD-EVENT-001", "ANOMALY-2025-00891"],
    )
    template: TemplateName = Field(
        default="asset_risk",
        description=(
            "Which reasoning template to use. See reasoning/prompt_templates/ "
            "and reasoning/prompt_templates/GEOAI_CONTEXT_GUIDE.md for expected context."
        ),
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional structured context from GeoAI analysis. "
            "May include: finding_type, severity_raw, metrics, signals, "
            "spatial_context, hydrology, geometry_reference. "
            "See GEOAI_CONTEXT_GUIDE.md for schema by template type."
        ),
        examples=[
            {
                "finding_type": "flood_proximity",
                "severity_raw": 0.78,
                "metrics": {"proximity_km": 2.5, "flood_extent_percent": 15},
                "signals": ["Active flood zone detected within 5 km"],
            },
            {
                "finding_type": "flood_change_detection",
                "metrics": {"change_percent": 8.2, "depth_m": 2.1},
                "hydrology": {"rainfall_mm_72h": 145},
            },
            {
                "finding_type": "temperature_spike",
                "deviation": {"magnitude_std_devs": 5.6},
                "temporal_context": {"cloud_cover_percent": 5},
            },
        ],
    )


class ExplainResponse(BaseModel):
    """Response from the reasoning layer (explanation only).

    Fields:
        subject: Echo of the request subject.
        template: Echo of the template used.
        explanation: Narrative explanation from LLaMA 3.2. Factual, observational.
                     No prediction, no scoring, no recommendations.
        model: Model name (e.g., "llama3.2") for audit purposes.

    Guarantees:
        - Explanation is based only on signals in the input context.
        - No predictions of future events.
        - No risk scores or severity ratings.
        - No recommendations or actions.
        - Plain language, suitable for field operations leads.

    Example:
        {
            "subject": "ASSET-12345",
            "template": "asset_risk",
            "explanation": (
                "Asset ASSET-12345 is 2.5 km from an active flood zone "
                "with current extent of 15%. The asset sits at elevation 12m "
                "in an area where peak water reached 8m, providing a 4m buffer. "
                "Nearby drainage patterns should be confirmed during field inspection."
            ),
            "model": "llama3.3"
        }
    """

    subject: str = Field(
        ...,
        description="Echo of the request subject.",
    )
    template: TemplateName = Field(
        ...,
        description="Echo of the template used.",
    )
    explanation: str = Field(
        ...,
        description=(
            "Plain-language explanation from the reasoning layer (LLaMA 3.3). "
            "Observational only: no prediction, no scoring, no recommendations."
        ),
    )
    model: str | None = Field(
        default=None,
        description="Model name (e.g., 'llama3.3') for audit trail.",
    )


# ============================================================================
# GeoAI Finding Schemas (STEP 4)
# ============================================================================
# These schemas define the contract between GeoAI analysis modules and the
# reasoning layer. They enforce:
#   - Deterministic, observable findings (no prediction)
#   - Structured metrics (raw values, not scores)
#   - Traceable geometry references
#   - Clear finding types (for template routing)


class GeometryReference(BaseModel):
    """Reference to spatial location of a finding.

    Uses WKT (Well-Known Text) or GeoJSON for interoperability with PostGIS.
    Examples:
        - WKT: "POINT(-73.9352 40.7306)"
        - GeoJSON: {"type": "Point", "coordinates": [-73.9352, 40.7306]}
    """

    format: Literal["wkt", "geojson"] = Field(
        default="wkt",
        description="Geometry format: WKT or GeoJSON.",
    )
    value: str | dict[str, Any] = Field(
        ...,
        description=(
            "Geometry in the specified format. "
            "WKT examples: 'POINT(...)' or 'POLYGON(...)'. "
            "GeoJSON: standard GeoJSON object."
        ),
    )


class SeverityRaw(BaseModel):
    """Raw severity/risk value (not a categorical label or prediction).

    Severity_raw represents an observable, derived metric from GeoAI analysis.
    This is NOT a risk score or alarm level—it is a quantifiable measure
    (e.g., distance percentile, sensor deviation magnitude as a fraction of
    baseline) used by reasoning templates to contextualize findings.

    Important: severity_raw is observational. It describes the intensity or
    magnitude of the finding, not the probability or consequence.
    """

    value: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Normalized severity value (0.0–1.0). "
            "0.0 = minimal/baseline, 1.0 = maximum observed. "
            "Example: 0.78 = 78th percentile of historical signals."
        ),
    )
    percentile: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description=(
            "Optional: Historical percentile rank (0–100). "
            "Example: 0.78 value might correspond to 85th percentile."
        ),
    )
    unit_description: str | None = Field(
        default=None,
        description=(
            "Plain-language description of what severity_raw measures. "
            "Example: 'distance to active flood zone as fraction of floodplain width'."
        ),
    )


class FloodProximityFinding(BaseModel):
    """GeoAI finding: Asset or location is in proximity to flood risk.

    Template: asset_risk
    """

    finding_type: Literal["flood_proximity"] = "flood_proximity"
    asset_id: str | None = Field(
        default=None,
        description="Unique identifier for the flagged asset.",
    )
    asset_type: str | None = Field(
        default=None,
        description="Asset classification (e.g., 'infrastructure_bridge').",
    )
    severity_raw: SeverityRaw = Field(
        ...,
        description=(
            "Observable proximity measure. Example: 0.78 = asset is in 78th percentile "
            "of proximity to flood boundary (closer = higher value)."
        ),
    )
    metrics: dict[str, float | str] = Field(
        ...,
        description=(
            "Raw measurements from spatial analysis. "
            "Typically numeric, but can include categorical values (e.g., FEMA zone). "
            "Examples: proximity_km, flood_extent_percent, recurrence_interval_years, "
            "elevation_m, highest_historical_depth_m, fema_zone."
        ),
    )
    signals: list[str] = Field(
        default_factory=list,
        description=(
            "Observable conditions that triggered this finding. "
            "Plain language, factual. Examples: "
            "'Asset in FEMA floodplain boundary (1% annual chance)', "
            "'Active flood zone detected within 5 km'."
        ),
    )
    geometry_reference: GeometryReference | None = Field(
        default=None,
        description="WKT or GeoJSON reference to asset location.",
    )
    timestamp: datetime | None = Field(
        default=None,
        description="When this finding was generated (ISO 8601).",
    )


class FloodChangeFinding(BaseModel):
    """GeoAI finding: Flood extent or depth changed over a time window.

    Template: flood_explanation
    """

    finding_type: Literal["flood_change_detection"] = "flood_change_detection"
    event_id: str | None = Field(
        default=None,
        description="Unique identifier for this flood change event.",
    )
    observation_window: dict[str, str] = Field(
        ...,
        description=(
            "Time range of observation. Keys: 'before' and 'after' (ISO 8601). "
            "Example: {'before': '2025-03-10T00:00:00Z', 'after': '2025-03-15T00:00:00Z'}"
        ),
    )
    severity_raw: SeverityRaw = Field(
        ...,
        description=(
            "Observable intensity of change. Example: 0.82 = change magnitude "
            "is at 82nd percentile of historical variations."
        ),
    )
    metrics: dict[str, float | str | int] = Field(
        ...,
        description=(
            "Raw measurements of change. "
            "Typically numeric, but can include categorical or count values. "
            "Examples: flood_extent_change_sqkm, flood_extent_change_percent, "
            "max_water_depth_m, affected_pixels."
        ),
    )
    spatial_context: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Geographic factors that contextualize the change. "
            "Keys: location, elevation_range_m, land_cover, proximity_to_asset_km."
        ),
    )
    hydrology: dict[str, float | str] = Field(
        default_factory=dict,
        description=(
            "Hydrological drivers. Keys: rainfall_mm_72h, discharge_percentile, "
            "antecedent_soil_moisture."
        ),
    )
    timestamp: datetime | None = Field(
        default=None,
        description="When this finding was generated (ISO 8601).",
    )


class AnomalyFinding(BaseModel):
    """GeoAI finding: Spatial or temporal anomaly in sensor or analytical data.

    Template: anomaly_summary
    """

    finding_type: Literal["temperature_spike", "vegetation_anomaly"] = Field(
        ...,
        description="Type of anomaly detected (extensible).",
    )
    anomaly_id: str | None = Field(
        default=None,
        description="Unique identifier for this anomaly.",
    )
    severity_raw: SeverityRaw = Field(
        ...,
        description=(
            "Observable deviation from baseline. Example: 5.6 standard deviations "
            "from mean (already normalized to fractional scale for consistency)."
        ),
    )
    baseline: dict[str, Any] = Field(
        ...,
        description=(
            "Historical baseline for comparison. Keys: mean, std_dev, "
            "observation_period_days."
        ),
    )
    observed: dict[str, Any] = Field(
        ...,
        description=(
            "Current observation. Keys: peak_value, duration_hours, timestamp."
        ),
    )
    deviation: dict[str, float] = Field(
        ...,
        description=(
            "Magnitude of deviation. Keys: magnitude_std_devs, "
            "change_from_baseline_percent."
        ),
    )
    spatial_context: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Spatial factors. Keys: location, nearby_features, elevation_m."
        ),
    )
    temporal_context: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Environmental factors at time of anomaly. Keys: wind_speed_mps, "
            "cloud_cover_percent, sun_angle_degrees."
        ),
    )
    note: str | None = Field(
        default=None,
        description="Additional context or correlation notes.",
    )
    timestamp: datetime | None = Field(
        default=None,
        description="When this finding was generated (ISO 8601).",
    )


GeoAIFinding = (
    FloodProximityFinding | FloodChangeFinding | AnomalyFinding
)
"""Union type for all supported GeoAI finding types.

Use for validation or routing based on finding_type.
"""
