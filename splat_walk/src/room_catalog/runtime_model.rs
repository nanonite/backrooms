use serde::Deserialize;

use super::model::FileEvidence;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeMeasurements {
    pub report: FileEvidence,
    pub mode: String,
    pub gpu_used: bool,
    pub scene_total_wall_time_seconds: f64,
    pub route_simulation_wall_time_seconds: f64,
    pub peak_rss_kib: u64,
    pub mean_update_ms: f64,
    pub p90_update_ms: f64,
    pub max_update_ms: f64,
    pub visual_load_seconds: f64,
    pub visual_query_preparation_seconds: f64,
    pub visual_triangle_count: u64,
    pub note: String,
}
