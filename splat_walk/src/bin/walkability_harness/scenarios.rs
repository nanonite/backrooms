use std::{
    fs,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result};
use bevy::prelude::{Resource, Vec3};
use serde::Deserialize;

const LINE_SAMPLES: usize = 120;

#[derive(Clone)]
pub enum SyntheticGeometry {
    Flat,
    Slope { degrees: f32 },
    SeparatedSlope { degrees: f32 },
    Step { rise_m: f32 },
    Gap { width_m: f32 },
    BlockingWall,
    ClearedOpening,
    OpenLedge { strip_width_m: f32 },
    LowCeiling,
    AuthoredRoute,
    AuthoredColumnProbe { floor_y_m: f32 },
}

#[derive(Clone, Resource)]
pub struct HarnessSpec {
    pub name: String,
    pub geometry: SyntheticGeometry,
    pub start: Vec3,
    pub waypoints: Vec<Vec3>,
    pub waypoint_split: Option<usize>,
    pub max_updates: usize,
    pub speed_scale: f32,
    pub blocking: bool,
}

pub const STEEP_REJECTION_SCENARIO: &str = "slope_17_degrees_rejection";
const STEEP_REJECTION_DIAGNOSTIC_PREFIX: &str = "steep_rejection_diagnostic_";

/// Scenarios that apply the locked steep-slope rejection gate: the blocking 17 degree control
/// and its non-blocking angle/approach-speed diagnostics.
pub fn is_steep_rejection(name: &str) -> bool {
    name == STEEP_REJECTION_SCENARIO || name.starts_with(STEEP_REJECTION_DIAGNOSTIC_PREFIX)
}

#[derive(Clone, Resource)]
pub struct AuthoredRouteAsset {
    pub directory: PathBuf,
    pub file_name: String,
    pub floor_y: f32,
    pub center_xz: [f32; 2],
    pub radius_m: f32,
    pub width_m: f32,
    pub column_lower_xz: [f32; 2],
    pub column_upper_xz: [f32; 2],
    pub floor_triangles: usize,
    pub column_triangles: usize,
}

pub fn synthetic_specs() -> Vec<HarnessSpec> {
    vec![
        linear(
            "synthetic_flat",
            SyntheticGeometry::Flat,
            -3.0,
            3.0,
            0.7,
            900,
        ),
        slope_scenario("slope_15_degrees", 15.0),
        slope_scenario(STEEP_REJECTION_SCENARIO, 17.0),
        separated_slope_sensor_probe(),
        linear(
            "step_020m",
            SyntheticGeometry::Step { rise_m: 0.2 },
            -3.0,
            3.0,
            0.7,
            900,
        ),
        linear(
            "step_030m_rejection",
            SyntheticGeometry::Step { rise_m: 0.3 },
            -3.0,
            3.0,
            0.7,
            900,
        ),
        linear(
            "hole_030m",
            SyntheticGeometry::Gap { width_m: 0.3 },
            -3.0,
            3.0,
            0.7,
            900,
        ),
        linear(
            "wide_hole_safety_net_contact",
            SyntheticGeometry::Gap { width_m: 4.0 },
            -3.0,
            3.0,
            0.7,
            900,
        ),
        linear(
            "blocking_wall",
            SyntheticGeometry::BlockingWall,
            -3.0,
            3.0,
            0.7,
            900,
        ),
        linear(
            "cleared_opening",
            SyntheticGeometry::ClearedOpening,
            -3.0,
            3.0,
            0.7,
            900,
        ),
        open_ledge_scenario(0.8),
        linear(
            "headroom_ray",
            SyntheticGeometry::LowCeiling,
            -3.0,
            3.0,
            0.7,
            900,
        ),
    ]
}

#[derive(Deserialize)]
struct RouteReport {
    plane: PlaneReport,
    route: RouteGeometry,
    column_obstacle: ColumnObstacle,
    export: RouteExport,
}

#[derive(Deserialize)]
struct PlaneReport {
    height_m: f32,
}

#[derive(Deserialize)]
struct RouteGeometry {
    center_xz_m: [f32; 2],
    radius_m: f32,
    width_m: f32,
}

#[derive(Deserialize)]
struct ColumnObstacle {
    footprint_lower_xz_m: [f32; 2],
    footprint_upper_xz_m: [f32; 2],
}

#[derive(Deserialize)]
struct RouteExport {
    path: String,
    floor_triangles: usize,
    column_triangles: usize,
}

pub fn authored_route_config(report_path: &Path) -> Result<(HarnessSpec, AuthoredRouteAsset)> {
    let report = fs::read(report_path).context("cannot read #139 route report")?;
    let route: RouteReport =
        serde_json::from_slice(&report).context("#139 route report is invalid JSON")?;
    let route_directory = report_path
        .parent()
        .context("#139 report path has no parent directory")?
        .to_path_buf();
    let floor_center_y = route.plane.height_m + 0.7;
    let center = Vec3::new(
        route.route.center_xz_m[0],
        floor_center_y,
        route.route.center_xz_m[1],
    );
    let orbit: Vec<Vec3> = (0..128)
        .map(|index| {
            let angle = std::f32::consts::TAU * index as f32 / 128.0;
            Vec3::new(
                center.x + route.route.radius_m * angle.cos(),
                center.y,
                center.z + route.route.radius_m * angle.sin(),
            )
        })
        .collect();
    let mut waypoints = vec![orbit[0]];
    waypoints.extend(orbit.iter().skip(1).copied());
    waypoints.push(orbit[0]);
    let waypoint_split = waypoints.len();
    waypoints.extend(orbit.iter().skip(1).rev().copied());
    let spec = HarnessSpec {
        name: "authored_route_outbound_inbound".to_owned(),
        geometry: SyntheticGeometry::AuthoredRoute,
        start: orbit[0],
        waypoints,
        waypoint_split: Some(waypoint_split),
        max_updates: 2700,
        speed_scale: 1.0,
        blocking: true,
    };
    let asset = AuthoredRouteAsset {
        directory: route_directory,
        file_name: route.export.path,
        floor_y: route.plane.height_m,
        center_xz: route.route.center_xz_m,
        radius_m: route.route.radius_m,
        width_m: route.route.width_m,
        column_lower_xz: route.column_obstacle.footprint_lower_xz_m,
        column_upper_xz: route.column_obstacle.footprint_upper_xz_m,
        floor_triangles: route.export.floor_triangles,
        column_triangles: route.export.column_triangles,
    };
    Ok((spec, asset))
}

pub fn authored_route_probe(spec: &HarnessSpec) -> HarnessSpec {
    let mut probe = spec.clone();
    probe.name = "authored_route_static_probe".to_owned();
    probe.waypoints = vec![spec.start];
    probe.waypoint_split = None;
    probe.max_updates = 300;
    probe
}

pub fn authored_column_probe(route: &AuthoredRouteAsset) -> HarnessSpec {
    let lower_x = route.column_lower_xz[0];
    let upper_x = route.column_upper_xz[0];
    let center_z = (route.column_lower_xz[1] + route.column_upper_xz[1]) * 0.5;
    let start = Vec3::new(lower_x - 1.0, route.floor_y + 0.7, center_z);
    let end = Vec3::new(upper_x + 1.0, route.floor_y + 0.7, center_z);
    let waypoints = (0..=LINE_SAMPLES)
        .map(|sample| start.lerp(end, sample as f32 / LINE_SAMPLES as f32))
        .collect();
    HarnessSpec {
        name: "authored_column_block".to_owned(),
        geometry: SyntheticGeometry::AuthoredColumnProbe {
            floor_y_m: route.floor_y,
        },
        start,
        waypoints,
        waypoint_split: None,
        max_updates: 1200,
        speed_scale: 1.0,
        blocking: true,
    }
}

fn linear(
    name: &str,
    geometry: SyntheticGeometry,
    start_x: f32,
    end_x: f32,
    y: f32,
    max_updates: usize,
) -> HarnessSpec {
    let start = Vec3::new(start_x, y, 0.0);
    let end = Vec3::new(end_x, y, 0.0);
    let waypoints = (0..=LINE_SAMPLES)
        .map(|sample| start.lerp(end, sample as f32 / LINE_SAMPLES as f32))
        .collect();
    HarnessSpec {
        name: name.to_owned(),
        geometry,
        start,
        waypoints,
        waypoint_split: None,
        max_updates,
        speed_scale: 1.0,
        blocking: true,
    }
}

fn slope_scenario(name: &str, degrees: f32) -> HarnessSpec {
    let max_updates = if is_steep_rejection(name) { 420 } else { 300 };
    linear(
        name,
        SyntheticGeometry::Slope { degrees },
        -3.0,
        3.0,
        0.7,
        max_updates,
    )
}

/// Non-blocking robustness checks for the steep-slope gate: steeper inclines and slower
/// approaches than the locked 17 degree, full-speed control.
pub fn steep_rejection_diagnostics() -> Vec<HarnessSpec> {
    let mut specs = Vec::new();
    for degrees in [17.0_f32, 20.0, 25.0, 30.0] {
        for speed_scale in [0.25_f32, 0.5, 1.0] {
            if degrees == 17.0 && speed_scale == 1.0 {
                continue;
            }
            let name = format!(
                "{STEEP_REJECTION_DIAGNOSTIC_PREFIX}{degrees:.0}deg_speed{:03.0}",
                speed_scale * 100.0
            );
            let mut spec = slope_scenario(&name, degrees);
            spec.speed_scale = speed_scale;
            spec.blocking = false;
            specs.push(spec);
        }
    }
    specs
}

fn open_ledge_scenario(strip_width_m: f32) -> HarnessSpec {
    let start = Vec3::new(0.0, 0.7, 0.0);
    let waypoints = (0..=LINE_SAMPLES)
        .map(|sample| {
            let lateral_offset = 1.5 * sample as f32 / LINE_SAMPLES as f32;
            Vec3::new(start.x, start.y, start.z + lateral_offset)
        })
        .collect();
    HarnessSpec {
        name: "open_ledge_0_8m".to_owned(),
        geometry: SyntheticGeometry::OpenLedge { strip_width_m },
        start,
        waypoints,
        waypoint_split: None,
        max_updates: 900,
        speed_scale: 1.0,
        blocking: true,
    }
}

fn separated_slope_sensor_probe() -> HarnessSpec {
    let start = Vec3::new(-1.505_416_6, 0.764_865_1, 0.0);
    HarnessSpec {
        name: "slope_17_degrees_nonoverlap_probe".to_owned(),
        geometry: SyntheticGeometry::SeparatedSlope { degrees: 17.0 },
        start,
        waypoints: vec![start],
        waypoint_split: None,
        max_updates: 300,
        speed_scale: 1.0,
        blocking: true,
    }
}
