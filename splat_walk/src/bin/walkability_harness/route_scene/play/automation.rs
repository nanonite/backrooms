use std::{
    path::PathBuf,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

use anyhow::{Context, Result, bail};
use bevy::prelude::{
    App, AppExit, Last, MessageReader, MessageWriter, Res, ResMut, Resource, Update,
};

use crate::walkability_harness::{
    route_collision::SceneAssetReadiness,
    simulation::{PlayerResetEvents, ScenarioReport},
};

use super::{
    metrics::{self, PlaySessionMetrics, PlaySessionReport},
    resources::ResourcePreflight,
};

#[derive(Resource)]
struct PlayAutomation {
    started_at: Instant,
    timeout: Option<Duration>,
    report_path: PathBuf,
    preflight: ResourcePreflight,
    report: Arc<Mutex<Option<PlaySessionReport>>>,
    exit_requested: bool,
}

pub struct PlayReportHandle(Arc<Mutex<Option<PlaySessionReport>>>);

pub fn configure(
    app: &mut App,
    report_path: PathBuf,
    preflight: ResourcePreflight,
    timeout: Option<Duration>,
) -> PlayReportHandle {
    let report = Arc::new(Mutex::new(None));
    app.insert_resource(PlayAutomation {
        started_at: Instant::now(),
        timeout,
        report_path,
        preflight,
        report: Arc::clone(&report),
        exit_requested: false,
    })
    .add_systems(Update, request_exit_after_timeout)
    .add_systems(Last, save_report_on_exit);
    PlayReportHandle(report)
}

pub fn timeout_from_args() -> Result<Option<Duration>> {
    let seconds = std::env::args().find_map(|argument| {
        argument
            .strip_prefix("--play-timeout-seconds=")
            .map(str::to_owned)
    });
    let Some(seconds) = seconds else {
        return Ok(None);
    };
    let seconds = seconds
        .parse::<u64>()
        .context("--play-timeout-seconds must be an integer from 1 to 3600")?;
    if !(1..=3600).contains(&seconds) {
        bail!("--play-timeout-seconds must be an integer from 1 to 3600");
    }
    Ok(Some(Duration::from_secs(seconds)))
}

pub fn take_report(handle: PlayReportHandle) -> Result<PlaySessionReport> {
    handle
        .0
        .lock()
        .map_err(|_| anyhow::anyhow!("interactive play report lock was poisoned"))?
        .take()
        .context("interactive scene exited without writing its report")
}

fn request_exit_after_timeout(
    mut automation: ResMut<PlayAutomation>,
    mut app_exit: MessageWriter<AppExit>,
) {
    let Some(timeout) = automation.timeout else {
        return;
    };
    if automation.exit_requested || automation.started_at.elapsed() < timeout {
        return;
    }
    automation.exit_requested = true;
    println!("interactive play timeout reached; writing report and exiting");
    app_exit.write(AppExit::Success);
}

fn save_report_on_exit(
    mut exits: MessageReader<AppExit>,
    automation: Res<PlayAutomation>,
    metrics: Res<PlaySessionMetrics>,
    scenario: Res<ScenarioReport>,
    readiness: Res<SceneAssetReadiness>,
    resets: Res<PlayerResetEvents>,
) {
    if exits.read().next().is_none() {
        return;
    }
    let assets_ready = scenario.collision_asset_loaded && readiness.visual_ready;
    let report = metrics::create_report(
        metrics.clone(),
        automation.preflight.clone(),
        resets.clone(),
        assets_ready,
    );
    if let Err(error) = metrics::write_report(automation.report_path.clone(), &report) {
        eprintln!("cannot write interactive play report: {error:#}");
        return;
    }
    match automation.report.lock() {
        Ok(mut slot) => *slot = Some(report),
        Err(_) => {
            eprintln!("interactive play report lock was poisoned");
        }
    }
}

#[cfg(test)]
mod tests {
    use std::{fs, path::PathBuf};

    use bevy::prelude::App;

    use crate::walkability_harness::{
        route_collision::SceneAssetReadiness,
        simulation::{PlayerResetEvents, ScenarioReport},
    };

    use super::{configure, take_report};
    use crate::walkability_harness::route_scene::play::{
        metrics::PlaySessionMetrics,
        resources::{MINIMUM_AVAILABLE_RAM_KIB, MINIMUM_FREE_VRAM_MIB, ResourcePreflight},
    };

    fn report_path() -> PathBuf {
        std::env::temp_dir().join(format!("hunyuan-play-report-{}.json", std::process::id()))
    }

    #[test]
    fn timeout_writes_report_before_app_exit() -> anyhow::Result<()> {
        let path = report_path();
        let mut app = App::new();
        app.insert_resource(PlaySessionMetrics::default())
            .insert_resource(ScenarioReport::default())
            .insert_resource(SceneAssetReadiness {
                visual_ready: false,
            })
            .insert_resource(PlayerResetEvents::default());
        let preflight = ResourcePreflight {
            available_ram_kib: MINIMUM_AVAILABLE_RAM_KIB,
            minimum_available_ram_kib: MINIMUM_AVAILABLE_RAM_KIB,
            free_vram_mib: MINIMUM_FREE_VRAM_MIB,
            minimum_free_vram_mib: MINIMUM_FREE_VRAM_MIB,
        };
        let handle = configure(
            &mut app,
            path.clone(),
            preflight,
            Some(std::time::Duration::ZERO),
        );
        app.update();

        let report = take_report(handle)?;
        assert!(!report.assets_ready);
        assert!(path.is_file());
        fs::remove_file(path)?;
        Ok(())
    }
}
