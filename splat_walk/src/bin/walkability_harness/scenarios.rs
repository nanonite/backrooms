use std::{
    fs,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result, bail};
use bevy::prelude::{Resource, Vec3};
use serde::Deserialize;

const LINE_SAMPLES: usize = 120;
pub const AUTHORED_LATERAL_PUSH_TICKS: usize = 120;
pub const AUTHORED_LATERAL_RELEASE_TICKS: usize = 60;

#[derive(Clone)]
pub enum SyntheticGeometry {
    Flat,
    Slope {
        degrees: f32,
    },
    SeparatedSlope {
        degrees: f32,
    },
    Step {
        rise_m: f32,
    },
    Gap {
        width_m: f32,
    },
    BlockingWall,
    ClearedOpening,
    OpenLedge {
        strip_width_m: f32,
    },
    LowCeiling,
    AuthoredRoute,
    AuthoredColumnProbe {
        floor_y_m: f32,
    },
    AuthoredLateralPush {
        station: String,
        center_xz: [f32; 2],
        outward_direction_xz: [f32; 2],
        boundary_side: String,
    },
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

pub fn is_authored_lateral_push(name: &str) -> bool {
    name.starts_with("authored_loop_lateral_push_")
}

#[derive(Clone, Resource)]
pub struct AuthoredRouteAsset {
    pub issue: u32,
    pub directory: PathBuf,
    pub file_name: String,
    pub floor_y: f32,
    pub center_xz: [f32; 2],
    pub radius_m: f32,
    pub width_m: f32,
    pub column_lower_xz: [f32; 2],
    pub column_upper_xz: [f32; 2],
    pub column_height_m: f32,
    pub floor_triangles: usize,
    pub column_triangles: usize,
    pub inner_boundary_triangles: usize,
    pub outer_boundary_triangles: usize,
    pub boundary_height_m: f32,
    pub room_layout: Option<AuthoredRoomLayout>,
}

#[derive(Clone)]
pub struct AuthoredRoomLayout {
    pub lower_xz: [f32; 2],
    pub upper_xz: [f32; 2],
    pub boundary_thickness_m: f32,
    pub boundary_triangles: [usize; 4],
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
    issue: u32,
    plane: PlaneReport,
    route: RouteGeometry,
    column_obstacle: ColumnObstacle,
    edge_boundaries: EdgeBoundaryReport,
    export: RouteExport,
    #[serde(default)]
    room_layout: Option<RoomLayoutReport>,
}

#[derive(Deserialize)]
struct RoomLayoutReport {
    bounds_lower_xz_m: [f32; 2],
    bounds_upper_xz_m: [f32; 2],
    boundary_thickness_m: f32,
    walk_loop_centerline_xz_m: Vec<[f32; 2]>,
    boundary_triangles: [usize; 4],
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
    height_m: f32,
}

#[derive(Deserialize)]
struct RouteExport {
    path: String,
    floor_triangles: usize,
    column_triangles: usize,
    inner_edge_boundary_triangles: usize,
    outer_edge_boundary_triangles: usize,
}

#[derive(Deserialize)]
struct EdgeBoundaryReport {
    height_m: f32,
}

pub fn authored_route_config(report_path: &Path) -> Result<(HarnessSpec, AuthoredRouteAsset)> {
    let report = fs::read(report_path).context("cannot read authored route report")?;
    let route: RouteReport =
        serde_json::from_slice(&report).context("authored route report is invalid JSON")?;
    if let Some(layout) = route.room_layout.as_ref() {
        validate_room_layout(layout, route.edge_boundaries.height_m)?;
    }
    let route_directory = report_path
        .parent()
        .context("authored route report path has no parent directory")?
        .to_path_buf();
    let floor_center_y = route.plane.height_m + 0.7;
    let center = Vec3::new(
        route.route.center_xz_m[0],
        floor_center_y,
        route.route.center_xz_m[1],
    );
    let orbit: Vec<Vec3> = route.room_layout.as_ref().map_or_else(
        || {
            (0..128)
                .map(|index| {
                    let angle = std::f32::consts::TAU * index as f32 / 128.0;
                    Vec3::new(
                        center.x + route.route.radius_m * angle.cos(),
                        center.y,
                        center.z + route.route.radius_m * angle.sin(),
                    )
                })
                .collect()
        },
        |layout| {
            layout
                .walk_loop_centerline_xz_m
                .iter()
                .map(|point| Vec3::new(point[0], center.y, point[1]))
                .collect()
        },
    );
    if orbit.len() < 4 {
        anyhow::bail!("authored room route needs at least four loop points");
    }
    let mut waypoints = vec![orbit[0]];
    waypoints.extend(orbit.iter().skip(1).copied());
    waypoints.push(orbit[0]);
    let waypoint_split = waypoints.len();
    waypoints.extend(orbit.iter().skip(1).rev().copied());
    if route.room_layout.is_some() {
        waypoints.push(orbit[0]);
    }
    let spec = HarnessSpec {
        name: "authored_route_outbound_inbound".to_owned(),
        geometry: SyntheticGeometry::AuthoredRoute,
        start: orbit[0],
        waypoints,
        waypoint_split: Some(waypoint_split),
        max_updates: if route.room_layout.is_some() {
            3600
        } else {
            2700
        },
        speed_scale: 1.0,
        blocking: true,
    };
    let asset = AuthoredRouteAsset {
        issue: route.issue,
        directory: route_directory,
        file_name: route.export.path,
        floor_y: route.plane.height_m,
        center_xz: route.route.center_xz_m,
        radius_m: route.route.radius_m,
        width_m: route.route.width_m,
        column_lower_xz: route.column_obstacle.footprint_lower_xz_m,
        column_upper_xz: route.column_obstacle.footprint_upper_xz_m,
        column_height_m: route.column_obstacle.height_m,
        floor_triangles: route.export.floor_triangles,
        column_triangles: route.export.column_triangles,
        inner_boundary_triangles: route.export.inner_edge_boundary_triangles,
        outer_boundary_triangles: route.export.outer_edge_boundary_triangles,
        boundary_height_m: route.edge_boundaries.height_m,
        room_layout: route.room_layout.map(|layout| AuthoredRoomLayout {
            lower_xz: layout.bounds_lower_xz_m,
            upper_xz: layout.bounds_upper_xz_m,
            boundary_thickness_m: layout.boundary_thickness_m,
            boundary_triangles: layout.boundary_triangles,
        }),
    };
    Ok((spec, asset))
}

fn validate_room_layout(layout: &RoomLayoutReport, boundary_height_m: f32) -> Result<()> {
    let [lower_x, lower_z] = layout.bounds_lower_xz_m;
    let [upper_x, upper_z] = layout.bounds_upper_xz_m;
    let bounds_are_valid = [
        lower_x,
        lower_z,
        upper_x,
        upper_z,
        layout.boundary_thickness_m,
    ]
    .iter()
    .all(|value| value.is_finite());
    if !bounds_are_valid
        || lower_x >= upper_x
        || lower_z >= upper_z
        || layout.boundary_thickness_m <= 0.0
        || !boundary_height_m.is_finite()
        || boundary_height_m <= 0.0
        || layout.walk_loop_centerline_xz_m.len() < 4
        || layout
            .walk_loop_centerline_xz_m
            .iter()
            .flatten()
            .any(|value| !value.is_finite())
    {
        bail!("authored room layout has invalid bounds, route, height or boundary meshes");
    }
    Ok(())
}

pub fn authored_lateral_push_specs(route: &AuthoredRouteAsset) -> Vec<HarnessSpec> {
    if let Some(layout) = &route.room_layout {
        return authored_room_boundary_push_specs(route, layout);
    }
    let mut stations: Vec<_> = (0..8)
        .map(|index| {
            let angle = std::f32::consts::TAU * index as f32 / 8.0;
            station_record(route, format!("even_{index}"), angle)
        })
        .collect();
    let nearest_angle = (0..128)
        .map(|index| std::f32::consts::TAU * index as f32 / 128.0)
        .min_by(|first, second| {
            point_to_column_distance(route, *first)
                .total_cmp(&point_to_column_distance(route, *second))
        })
        .unwrap_or(0.0);
    stations.push(station_record(
        route,
        "nearest_column".to_owned(),
        nearest_angle,
    ));

    stations
        .into_iter()
        .flat_map(|(station, center_xz, outward)| {
            [(-1.0_f32, "inner"), (1.0_f32, "outer")].into_iter().map(
                move |(direction, boundary_side)| {
                    let start = Vec3::new(center_xz[0], route.floor_y + 0.7, center_xz[1]);
                    HarnessSpec {
                        name: format!("authored_loop_lateral_push_{station}_{boundary_side}"),
                        geometry: SyntheticGeometry::AuthoredLateralPush {
                            station: station.clone(),
                            center_xz,
                            outward_direction_xz: outward,
                            boundary_side: boundary_side.to_owned(),
                        },
                        start,
                        waypoints: vec![start],
                        waypoint_split: None,
                        max_updates: 300,
                        speed_scale: direction,
                        blocking: true,
                    }
                },
            )
        })
        .collect()
}

fn authored_room_boundary_push_specs(
    route: &AuthoredRouteAsset,
    layout: &AuthoredRoomLayout,
) -> Vec<HarnessSpec> {
    let center_x = (layout.lower_xz[0] + layout.upper_xz[0]) * 0.5;
    let center_z = (layout.lower_xz[1] + layout.upper_xz[1]) * 0.5;
    [
        ("west", [layout.lower_xz[0] + 0.4, center_z], [-1.0, 0.0]),
        ("east", [layout.upper_xz[0] - 0.4, center_z], [1.0, 0.0]),
        ("south", [center_x, layout.lower_xz[1] + 0.4], [0.0, -1.0]),
        ("north", [center_x, layout.upper_xz[1] - 0.4], [0.0, 1.0]),
    ]
    .into_iter()
    .map(|(side, center_xz, outward)| {
        let start = Vec3::new(center_xz[0], route.floor_y + 0.7, center_xz[1]);
        HarnessSpec {
            name: format!("authored_loop_lateral_push_room_{side}"),
            geometry: SyntheticGeometry::AuthoredLateralPush {
                station: format!("room_{side}"),
                center_xz,
                outward_direction_xz: outward,
                boundary_side: side.to_owned(),
            },
            start,
            waypoints: vec![start],
            waypoint_split: None,
            max_updates: 300,
            speed_scale: 1.0,
            blocking: true,
        }
    })
    .collect()
}

fn station_record(
    route: &AuthoredRouteAsset,
    name: String,
    angle: f32,
) -> (String, [f32; 2], [f32; 2]) {
    let outward = [angle.cos(), angle.sin()];
    let center_xz = [
        route.center_xz[0] + route.radius_m * outward[0],
        route.center_xz[1] + route.radius_m * outward[1],
    ];
    (name, center_xz, outward)
}

fn point_to_column_distance(route: &AuthoredRouteAsset, angle: f32) -> f32 {
    let point = [
        route.center_xz[0] + route.radius_m * angle.cos(),
        route.center_xz[1] + route.radius_m * angle.sin(),
    ];
    let dx = (route.column_lower_xz[0] - point[0]).max(0.0)
        + (point[0] - route.column_upper_xz[0]).max(0.0);
    let dz = (route.column_lower_xz[1] - point[1]).max(0.0)
        + (point[1] - route.column_upper_xz[1]).max(0.0);
    dx.hypot(dz)
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

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use bevy::prelude::Vec3;

    use super::{
        AuthoredRoomLayout, AuthoredRouteAsset, SyntheticGeometry, authored_lateral_push_specs,
    };

    #[test]
    fn creates_both_edge_pushes_at_nine_fixed_stations() {
        let route = AuthoredRouteAsset {
            issue: 147,
            directory: PathBuf::new(),
            file_name: String::new(),
            floor_y: -1.0,
            center_xz: [0.0, 0.0],
            radius_m: 2.875,
            width_m: 0.8,
            column_lower_xz: [-0.5, -0.5],
            column_upper_xz: [0.5, 0.5],
            column_height_m: 2.4,
            floor_triangles: 512,
            column_triangles: 12,
            inner_boundary_triangles: 2048,
            outer_boundary_triangles: 2048,
            boundary_height_m: 1.4,
            room_layout: None,
        };

        let specs = authored_lateral_push_specs(&route);

        assert_eq!(specs.len(), 18);
        assert_eq!(
            specs
                .iter()
                .filter(|spec| spec.name.contains("even_"))
                .count(),
            16
        );
        assert_eq!(
            specs
                .iter()
                .filter(|spec| spec.name.contains("nearest_column"))
                .count(),
            2
        );
        for spec in specs {
            assert!(spec.blocking);
            assert_eq!(spec.start.y, route.floor_y + 0.7);
            assert_eq!(spec.waypoints, vec![spec.start]);
            let SyntheticGeometry::AuthoredLateralPush {
                center_xz,
                outward_direction_xz,
                boundary_side,
                ..
            } = spec.geometry
            else {
                panic!("lateral push scenario has wrong geometry type");
            };
            let offset = Vec3::new(center_xz[0], 0.0, center_xz[1]);
            assert!((offset.length() - route.radius_m).abs() < 1e-5);
            assert!((outward_direction_xz[0].hypot(outward_direction_xz[1]) - 1.0).abs() < 1e-5);
            assert!(boundary_side == "inner" || boundary_side == "outer");
        }
    }

    #[test]
    fn creates_a_probe_at_each_room_end_with_matching_boundary_labels() {
        let route = AuthoredRouteAsset {
            issue: 150,
            directory: PathBuf::new(),
            file_name: String::new(),
            floor_y: -1.0,
            center_xz: [0.0, 0.0],
            radius_m: 0.0,
            width_m: 0.0,
            column_lower_xz: [-0.5, -0.5],
            column_upper_xz: [0.5, 0.5],
            column_height_m: 2.4,
            floor_triangles: 2,
            column_triangles: 12,
            inner_boundary_triangles: 0,
            outer_boundary_triangles: 48,
            boundary_height_m: 2.4,
            room_layout: Some(AuthoredRoomLayout {
                lower_xz: [-5.0, -6.0],
                upper_xz: [5.0, 6.0],
                boundary_thickness_m: 0.12,
                boundary_triangles: [12; 4],
            }),
        };

        let specs = authored_lateral_push_specs(&route);
        let sides: Vec<_> = specs
            .iter()
            .filter_map(|spec| match &spec.geometry {
                SyntheticGeometry::AuthoredLateralPush { boundary_side, .. } => {
                    Some(boundary_side.as_str())
                }
                _ => None,
            })
            .collect();

        assert_eq!(sides, ["west", "east", "south", "north"]);
        assert!(
            specs
                .iter()
                .all(|spec| spec.blocking && spec.max_updates == 300)
        );
    }
}
