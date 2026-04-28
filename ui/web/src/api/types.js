/**
 * @file Shared API type definitions (JSDoc only — runs as-is, no compiler).
 *
 * Mirrors the server-side Pydantic models in `api/schemas/payloads.py`.
 * If the backend schema changes, update this file in lockstep.
 */

/**
 * @typedef {"us"|"uk"|"anz_au"|"anz_nz"|"apac"} RegionCode
 * @typedef {"water_pipe"|"water_treatment_plant"|"pump_station"|"reservoir"|
 *           "valve"|"hydrant"|"sensor"|"dam"|"catchment"|"bridge"} ClassCode
 * @typedef {"di"|"ci"|"steel"|"pvc"|"hdpe"|"mdpe"|"ac"|"conc"|"cu"|"unknown"} MaterialCode
 * @typedef {"excellent"|"good"|"fair"|"poor"|"critical"} ConditionClass
 */

/**
 * @typedef {Object} AssetProperties
 * @property {string}  id
 * @property {string}  [asset_code]
 * @property {RegionCode} region_code
 * @property {string}  region_name
 * @property {ClassCode} class_code
 * @property {string}  class_name
 * @property {MaterialCode|null} [material_code]
 * @property {string|null} [material_name]
 * @property {string|null} [name]
 * @property {number|null} [install_year]
 * @property {number|null} [diameter_mm]
 * @property {number|null} [length_m]
 * @property {Object<string, unknown>} [attributes]
 * @property {number|null} [risk_score]          - 0..1
 * @property {ConditionClass|null} [risk_condition_class]
 * @property {string|null} [risk_computed_at]
 * @property {string} source
 */

/**
 * @typedef {import("geojson").Feature<import("geojson").Geometry, AssetProperties>} AssetFeature
 * @typedef {import("geojson").FeatureCollection<import("geojson").Geometry, AssetProperties>} AssetCollection
 */

/**
 * @typedef {Object} ClusterZoneProperties
 * @property {string} id
 * @property {RegionCode} region_code
 * @property {number} cluster_id
 * @property {number} num_assets
 * @property {number} mean_score
 * @property {string} computed_at
 */

/**
 * @typedef {import("geojson").Feature<import("geojson").Polygon, ClusterZoneProperties>} ClusterZoneFeature
 * @typedef {import("geojson").FeatureCollection<import("geojson").Polygon, ClusterZoneProperties>} ClusterZoneCollection
 */

/**
 * @typedef {Object} ListAssetsFilters
 * @property {RegionCode[]} [regions]
 * @property {ClassCode[]} [classes]
 * @property {[number,number,number,number]} [bbox]   - [minLon,minLat,maxLon,maxLat]
 * @property {boolean} [highRiskOnly]
 * @property {number} [limit]
 */

/**
 * @typedef {Object} ShapDriver
 * @property {string} feature
 * @property {number} value          - signed contribution
 * @property {number} normalized     - 0..1 magnitude for rendering
 */

/**
 * @typedef {Object} ExplainRequest
 * @property {string} subject        - asset id
 * @property {"asset_condition"|"flood_proximity"|"anomaly"|"cluster"} template
 * @property {Object<string, unknown>} [context]
 */

/**
 * @typedef {Object} ExplainResponse
 * @property {string} subject
 * @property {string} template
 * @property {string} explanation
 * @property {ShapDriver[]} drivers
 * @property {Object} meta
 * @property {string} meta.model
 * @property {number} meta.latency_ms
 * @property {number} [meta.tokens_in]
 * @property {number} [meta.tokens_out]
 * @property {string} meta.created_at
 */

/**
 * @typedef {Object} UploadResponse
 * @property {string} upload_id
 * @property {string} filename
 * @property {number} bytes
 * @property {"queued"|"processing"|"complete"|"error"} status
 * @property {number} [feature_count]
 * @property {string} [message]
 */

/**
 * @typedef {Object} ObservationPoint
 * @property {string} time         - ISO timestamp
 * @property {number} value
 * @property {string} [unit]
 */

/**
 * @typedef {Object} ObservationsResponse
 * @property {string} asset_id
 * @property {string} metric
 * @property {string} [unit]
 * @property {ObservationPoint[]} points
 */

export {};   // Make this an ES module so consumers can `import "./types.js"`.
