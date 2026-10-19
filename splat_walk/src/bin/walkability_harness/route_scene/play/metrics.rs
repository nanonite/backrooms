use std::{fs, path::PathBuf, time::Instant};

use anyhow::{Context, Result};
use bevy::prelude::{Res, ResMut, Resource};
use serde::Serialize;

use crate::walkability_harness::{
    route_collision::SceneAssetReadiness,
    route_scene::assets::VisualSceneReport,
    simulation::{PlayerResetEvents, ScenarioReport},
};

use super::resources::ResourcePreflight;

#[derive(Resource, Clone)]
pub struct PlaySessionMetrics {
    started: Instant,
    last_frame: Option<Instant>,
    load_time_seconds: Option<f64>,
    frame_times_ms: Vec<f64>,
}

impl Default for PlaySessionMetrics {
    fn default() -> Self {
        Self {
            started: Instant::now(),
            last_frame: None,
            load_time_seconds: None,
            frame_times_ms: Vec::new(),
        }
    }
}

#[derive(Serialize)]
pub struct PlaySessionReport {
    pub schema_version: u32,
    pub label: &'static str,
    pub fixed_step_hz: u32,
    pub resource_preflight: ResourcePreflight,
    pub assets_ready: bool,
    pub load_time_seconds: Option<f64>,
    pub frame_count: usize,
    pub frame_time_median_ms: Option<f64>,
    pub frame_time_p95_ms: Option<f64>,
    pub peak_rss_kib: Option<u64>,
    pub resets: Vec<crate::walkability_harness::simulation::PlayerResetEvent>,
}

pub fn collect_frame_metrics(
    readiness: Res<SceneAssetReadiness>,
    scenario: Res<ScenarioReport>,
    _visual: Res<VisualSceneReport>,
    mut metrics: ResMut<PlaySessionMetrics>,
) {
    let ready = readiness.visual_ready && scenario.collision_asset_loaded;
    if !ready {
        return;
    }
    let now = Instant::now();
    if metrics.load_time_seconds.is_none() {
        metrics.load_time_seconds = Some(metrics.started.elapsed().as_secs_f64());
        metrics.last_frame = Some(now);
        return;
    }
    if let Some(previous) = metrics.last_frame.replace(now) {
        let elapsed_ms = now.duration_since(previous).as_secs_f64() * 1000.0;
        if elapsed_ms > 0.0 && elapsed_ms < 1000.0 {
            metrics.frame_times_ms.push(elapsed_ms);
        }
    }
}

pub fn create_report(
    metrics: PlaySessionMetrics,
    preflight: ResourcePreflight,
    resets: PlayerResetEvents,
    assets_ready: bool,
) -> PlaySessionReport {
    let mut frame_times = metrics.frame_times_ms;
    frame_times.sort_by(f64::total_cmp);
    PlaySessionReport {
        schema_version: 1,
        label: "uncalibrated",
        fixed_step_hz: 60,
        resource_preflight: preflight,
        assets_ready,
        load_time_seconds: metrics.load_time_seconds,
        frame_count: frame_times.len(),
        frame_time_median_ms: percentile(&frame_times, 0.5),
        frame_time_p95_ms: percentile(&frame_times, 0.95),
        peak_rss_kib: process_peak_rss_kib(),
        resets: resets.0,
    }
}

pub fn write_report(path: PathBuf, report: &PlaySessionReport) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("cannot create play report directory {}", parent.display()))?;
    }
    fs::write(&path, serde_json::to_vec_pretty(report)?)
        .with_context(|| format!("cannot write play report {}", path.display()))
}

fn percentile(sorted: &[f64], fraction: f64) -> Option<f64> {
    if sorted.is_empty() {
        return None;
    }
    let index = ((sorted.len() - 1) as f64 * fraction).ceil() as usize;
    sorted.get(index).copied()
}

fn process_peak_rss_kib() -> Option<u64> {
    fs::read_to_string("/proc/self/status")
        .ok()?
        .lines()
        .find_map(|line| {
            line.strip_prefix("VmHWM:")
                .and_then(|value| value.split_whitespace().next())
                .and_then(|value| value.parse().ok())
        })
}

#[cfg(test)]
mod tests {
    use super::percentile;

    #[test]
    fn reports_nearest_rank_frame_percentiles() {
        assert_eq!(percentile(&[], 0.95), None);
        assert_eq!(percentile(&[1.0, 2.0, 3.0, 4.0], 0.5), Some(3.0));
        assert_eq!(percentile(&[1.0, 2.0, 3.0, 4.0], 0.95), Some(4.0));
    }
}
