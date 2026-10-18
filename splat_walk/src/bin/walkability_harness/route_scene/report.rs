use std::path::Path;

use anyhow::{Context, Result};
use serde::Serialize;
use serde_json::Value;

use crate::walkability_harness::{
    route_scene::manifest::SceneManifest, simulation::ScenarioReport,
};

use super::assets::VisualSceneReportData;

#[derive(Serialize)]
pub struct ComparisonSceneReport {
    pub schema_version: u32,
    pub issue: u32,
    pub label: &'static str,
    pub status: &'static str,
    pub registration_accepted: bool,
    pub scale_calibrated: bool,
    pub transform_status: String,
    pub scale_m_per_hunyuan_unit: f32,
    pub scale_sensitivity_range_m_per_hunyuan_unit: [f32; 2],
    pub plane_aligned_translation_world_m: [f32; 3],
    pub model_rotation_xyzw: [f32; 4],
    pub camera_anchor_shift_y_m: f32,
    pub visual_asset_path: String,
    pub visual_asset_sha256: String,
    pub collision_asset_path: String,
    pub collision_asset_sha256: String,
    pub visual_layers_are_avian_colliders: bool,
    pub gpu_used: bool,
    pub rendering_enabled: bool,
    pub traversal_gate: TraversalGateReport,
    pub visual_metric_contract: &'static str,
    pub visual: Option<VisualSceneReportData>,
    pub traversal: ScenarioReport,
    pub baseline_comparison: BaselineComparison,
    pub update_time_ms: UpdateTimeReport,
    pub scene_total_wall_time_seconds: f64,
    pub route_simulation_wall_time_seconds: f64,
    pub peak_rss_kib: Option<u64>,
    pub current_rss_kib: Option<u64>,
}

pub struct SceneRunReportData {
    pub visual: Option<VisualSceneReportData>,
    pub traversal: ScenarioReport,
    pub baseline_comparison: BaselineComparison,
    pub traversal_gate: TraversalGateReport,
    pub model_rotation_xyzw: [f32; 4],
    pub update_time_ms: UpdateTimeReport,
    pub scene_total_wall_time_seconds: f64,
    pub route_simulation_wall_time_seconds: f64,
    pub peak_rss_kib: Option<u64>,
    pub current_rss_kib: Option<u64>,
}

#[derive(Serialize)]
pub struct TraversalGateReport {
    pub source: &'static str,
    pub outbound_progress_fraction_min: f32,
    pub inbound_progress_fraction_min: f32,
    pub moving_support_fraction_min: f32,
    pub safety_net_contacts_max: usize,
    pub max_vertical_step_m: f32,
    pub comparison_rule: &'static str,
}

impl TraversalGateReport {
    pub fn from_manifest(manifest: &SceneManifest) -> Self {
        Self {
            source: "#135 locked authored-route gate",
            outbound_progress_fraction_min: manifest
                .locked_traversal_gate
                .outbound_progress_fraction_min,
            inbound_progress_fraction_min: manifest
                .locked_traversal_gate
                .inbound_progress_fraction_min,
            moving_support_fraction_min: manifest.locked_traversal_gate.moving_support_fraction_min,
            safety_net_contacts_max: manifest.locked_traversal_gate.safety_net_contacts_max,
            max_vertical_step_m: manifest.locked_traversal_gate.max_vertical_step_m,
            comparison_rule: "use the exact #135 collision GLB and shared controller; these values must match the #135 report within 1e-6",
        }
    }
}

#[derive(Serialize)]
pub struct UpdateTimeReport {
    pub sample_count: usize,
    pub mean: Option<f64>,
    pub p90: Option<f64>,
    pub max: Option<f64>,
    pub sample_scope: &'static str,
}

impl UpdateTimeReport {
    pub fn from_samples(samples_seconds: &[f64]) -> Self {
        if samples_seconds.is_empty() {
            return Self {
                sample_count: 0,
                mean: None,
                p90: None,
                max: None,
                sample_scope: "app.update calls after visual-query preparation and route collider installation",
            };
        }
        let mut sorted = samples_seconds.to_vec();
        sorted.sort_by(f64::total_cmp);
        let p90_index = (sorted.len() * 9).div_ceil(10) - 1;
        Self {
            sample_count: sorted.len(),
            mean: Some(sorted.iter().sum::<f64>() / sorted.len() as f64 * 1000.0),
            p90: Some(sorted[p90_index] * 1000.0),
            max: sorted.last().map(|duration| duration * 1000.0),
            sample_scope: "app.update wall time in milliseconds after visual-query preparation and route collider installation",
        }
    }
}

#[derive(Serialize)]
pub struct BaselineComparison {
    pub reference_report: &'static str,
    pub matches_within_1e_6: bool,
    pub outbound_progress_delta: f32,
    pub inbound_progress_delta: f32,
    pub moving_support_delta: f32,
    pub max_vertical_step_delta_m: f32,
    pub safety_net_contact_count_delta: i64,
}

pub fn baseline_comparison(
    traversal: &ScenarioReport,
    report_path: &Path,
) -> Result<BaselineComparison> {
    let document: Value = serde_json::from_slice(
        &std::fs::read(report_path)
            .with_context(|| format!("cannot read #135 report {}", report_path.display()))?,
    )
    .context("#135 walkability report is invalid JSON")?;
    let scenarios = document
        .get("scenarios")
        .and_then(Value::as_array)
        .context("#135 report has no scenario list")?;
    let baseline = scenarios
        .iter()
        .find(|scenario| {
            scenario.get("scenario").and_then(Value::as_str)
                == Some("authored_route_outbound_inbound")
        })
        .context("#135 report has no authored-route traversal result")?;
    let outbound = metric(baseline, "outbound_progress_fraction")?;
    let inbound = metric(baseline, "inbound_progress_fraction")?;
    let support = metric(baseline, "moving_support_fraction")?;
    let vertical_step = metric(baseline, "max_vertical_step")?;
    let safety_contacts = baseline
        .get("safety_net_contact_events")
        .and_then(Value::as_array)
        .context("#135 route report has no SafetyNet events")?
        .len();
    let outbound_delta = traversal.outbound_progress_fraction - outbound;
    let inbound_delta = traversal.inbound_progress_fraction - inbound;
    let support_delta = traversal.moving_support_fraction - support;
    let vertical_step_delta = traversal.max_vertical_step - vertical_step;
    let contact_delta = traversal.safety_net_contact_events.len() as i64 - safety_contacts as i64;
    let matches = [
        outbound_delta,
        inbound_delta,
        support_delta,
        vertical_step_delta,
    ]
    .into_iter()
    .all(|delta| delta.abs() <= 1.0e-6)
        && contact_delta == 0;
    Ok(BaselineComparison {
        reference_report: "collision_proto/avian_tnua_harness/walkability_report.json",
        matches_within_1e_6: matches,
        outbound_progress_delta: outbound_delta,
        inbound_progress_delta: inbound_delta,
        moving_support_delta: support_delta,
        max_vertical_step_delta_m: vertical_step_delta,
        safety_net_contact_count_delta: contact_delta,
    })
}

pub fn scene_report(manifest: &SceneManifest, run: SceneRunReportData) -> ComparisonSceneReport {
    ComparisonSceneReport {
        schema_version: 2,
        issue: manifest.issue,
        label: "uncalibrated",
        status: if run.traversal.pass && run.baseline_comparison.matches_within_1e_6 {
            "cpu_scene_run_complete"
        } else {
            "cpu_scene_run_incomplete_or_failed"
        },
        registration_accepted: manifest.registration_accepted,
        scale_calibrated: manifest.scale_calibrated,
        transform_status: manifest.transform.transform_status.clone(),
        scale_m_per_hunyuan_unit: manifest.transform.scale_m_per_hunyuan_unit,
        scale_sensitivity_range_m_per_hunyuan_unit: manifest
            .transform
            .scale_sensitivity_range_m_per_hunyuan_unit,
        plane_aligned_translation_world_m: manifest.transform.plane_aligned_translation_world_m,
        model_rotation_xyzw: run.model_rotation_xyzw,
        camera_anchor_shift_y_m: manifest.transform.camera_anchor_shift_y_m,
        visual_asset_path: manifest.assets.visual.path.clone(),
        visual_asset_sha256: manifest.assets.visual.sha256.clone(),
        collision_asset_path: manifest.assets.collision.path.clone(),
        collision_asset_sha256: manifest.assets.collision.sha256.clone(),
        visual_layers_are_avian_colliders: false,
        gpu_used: false,
        rendering_enabled: false,
        traversal_gate: run.traversal_gate,
        visual_metric_contract: "visual floor gap is signed Hunyuan hit Y minus authored collision floor Y; directional absence counts samples without an upward-facing hit at or below the collision plane within 0.5 m, while a visual hole requires no hit within the full +/-0.5 m vertical window. Capsule intersection tests the shared 0.30 m radius / 1.20 m height player volume against temporary CPU query BVHs. All visual metrics are descriptive only because the transform is uncalibrated.",
        visual: run.visual,
        traversal: run.traversal,
        baseline_comparison: run.baseline_comparison,
        update_time_ms: run.update_time_ms,
        scene_total_wall_time_seconds: run.scene_total_wall_time_seconds,
        route_simulation_wall_time_seconds: run.route_simulation_wall_time_seconds,
        peak_rss_kib: run.peak_rss_kib,
        current_rss_kib: run.current_rss_kib,
    }
}

fn metric(document: &Value, field: &str) -> Result<f32> {
    document
        .get(field)
        .and_then(Value::as_f64)
        .map(|value| value as f32)
        .with_context(|| format!("#135 report field {field} is missing or invalid"))
}
