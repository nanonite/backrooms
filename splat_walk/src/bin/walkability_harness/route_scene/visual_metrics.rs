use anyhow::Result;
use bevy::prelude::Vec3;
use serde::Serialize;

use crate::walkability_harness::scenarios::AuthoredRouteAsset;

use super::geometry_query::{VisualQueryMesh, capsule_penetration_m, floor_gap_m};

const ROUTE_SAMPLE_COUNT: usize = 1536;
const WORST_SAMPLE_LIMIT: usize = 10;

#[derive(Serialize, Clone)]
pub struct DistanceDistribution {
    pub sample_count: usize,
    pub median_m: Option<f32>,
    pub q90_m: Option<f32>,
    pub max_m: Option<f32>,
}

#[derive(Serialize, Clone)]
pub struct WorstStation {
    pub sample_index: usize,
    pub position_m: [f32; 3],
    pub distance_from_frame_141_m: f32,
    pub signed_floor_gap_m: Option<f32>,
    pub capsule_penetration_m: Option<f32>,
}

#[derive(Serialize, Clone)]
pub struct DistanceBand {
    pub band: &'static str,
    pub sample_count: usize,
    pub floor_gap_signed_m: DistanceDistribution,
    pub floor_gap_abs_m: DistanceDistribution,
    pub holes_below_floor: usize,
    pub visual_holes: usize,
}

#[derive(Serialize, Clone)]
pub struct VisualAlignmentMetrics {
    pub query_method: &'static str,
    pub visual_mesh_triangle_counts: Vec<(String, usize)>,
    pub route_sample_count: usize,
    pub floor_gap_signed_m: DistanceDistribution,
    pub floor_gap_abs_m: DistanceDistribution,
    pub no_floor_within_0_5m_below_count: usize,
    pub visual_hole_count: usize,
    pub visual_hole_fraction: f32,
    pub capsule_intersection_count: usize,
    pub capsule_intersection_fraction: f32,
    pub capsule_penetration_m: DistanceDistribution,
    pub worst_floor_gap_stations: Vec<WorstStation>,
    pub worst_capsule_intersection_stations: Vec<WorstStation>,
    pub hole_stations: Vec<WorstStation>,
    pub by_distance_from_frame_141: Vec<DistanceBand>,
}

struct SampleMetrics {
    sample_index: usize,
    position: Vec3,
    camera_distance_m: f32,
    floor_gap_m: Option<f32>,
    capsule_penetration_m: Option<f32>,
}

pub fn analyze_visual_alignment(
    route: &AuthoredRouteAsset,
    camera_origin: Vec3,
    visual_meshes: &[VisualQueryMesh],
    capsule_radius_m: f32,
    capsule_stem_m: f32,
) -> Result<VisualAlignmentMetrics> {
    let mut samples = Vec::with_capacity(ROUTE_SAMPLE_COUNT);
    for sample_index in 0..ROUTE_SAMPLE_COUNT {
        samples.push(sample_station(
            sample_index,
            route,
            camera_origin,
            visual_meshes,
            capsule_radius_m,
            capsule_stem_m,
        )?);
    }
    Ok(summarize_samples(&samples, visual_meshes))
}

fn sample_station(
    sample_index: usize,
    route: &AuthoredRouteAsset,
    camera_origin: Vec3,
    visual_meshes: &[VisualQueryMesh],
    capsule_radius_m: f32,
    capsule_stem_m: f32,
) -> Result<SampleMetrics> {
    let angle = std::f32::consts::TAU * sample_index as f32 / ROUTE_SAMPLE_COUNT as f32;
    let position = Vec3::new(
        route.center_xz[0] + route.radius_m * angle.cos(),
        route.floor_y + 0.7,
        route.center_xz[1] + route.radius_m * angle.sin(),
    );
    Ok(SampleMetrics {
        sample_index,
        position,
        camera_distance_m: position.distance(camera_origin),
        floor_gap_m: floor_gap_m(visual_meshes, position, route.floor_y),
        capsule_penetration_m: capsule_penetration_m(
            visual_meshes,
            position,
            capsule_radius_m,
            capsule_stem_m,
        )?,
    })
}

fn summarize_samples(
    samples: &[SampleMetrics],
    visual_meshes: &[VisualQueryMesh],
) -> VisualAlignmentMetrics {
    let gaps: Vec<f32> = samples
        .iter()
        .filter_map(|sample| sample.floor_gap_m)
        .collect();
    let absolute_gaps: Vec<f32> = gaps.iter().map(|gap| gap.abs()).collect();
    let penetrations: Vec<f32> = samples
        .iter()
        .filter_map(|sample| sample.capsule_penetration_m)
        .collect();
    let intersecting_count = samples
        .iter()
        .filter(|sample| sample.capsule_penetration_m.is_some())
        .count();
    let holes = samples
        .iter()
        .filter(|sample| !has_floor_nearby(sample.floor_gap_m))
        .count();
    VisualAlignmentMetrics {
        query_method: "CPU-only Parry BVH queries over temporary visual-mesh copies; no Hunyuan Avian collider is created or registered",
        visual_mesh_triangle_counts: visual_meshes
            .iter()
            .map(|mesh| (mesh.name.clone(), mesh.triangle_count))
            .collect(),
        route_sample_count: samples.len(),
        floor_gap_signed_m: distribution(&gaps),
        floor_gap_abs_m: distribution(&absolute_gaps),
        no_floor_within_0_5m_below_count: samples
            .iter()
            .filter(|sample| !has_floor_below(sample.floor_gap_m))
            .count(),
        visual_hole_count: holes,
        visual_hole_fraction: holes as f32 / samples.len() as f32,
        capsule_intersection_count: intersecting_count,
        capsule_intersection_fraction: intersecting_count as f32 / samples.len() as f32,
        capsule_penetration_m: distribution(&penetrations),
        worst_floor_gap_stations: worst_floor_gaps(samples),
        worst_capsule_intersection_stations: worst_capsule_intersections(samples),
        hole_stations: samples
            .iter()
            .filter(|sample| !has_floor_nearby(sample.floor_gap_m))
            .take(WORST_SAMPLE_LIMIT)
            .map(|sample| station_report(sample, None))
            .collect(),
        by_distance_from_frame_141: distance_bands(samples),
    }
}

fn has_floor_below(gap: Option<f32>) -> bool {
    gap.is_some_and(|value| (-0.5..=0.0).contains(&value))
}

fn has_floor_nearby(gap: Option<f32>) -> bool {
    gap.is_some_and(|value| (-0.5..=0.5).contains(&value))
}

fn worst_floor_gaps(samples: &[SampleMetrics]) -> Vec<WorstStation> {
    let mut ordered: Vec<_> = samples
        .iter()
        .filter(|sample| sample.floor_gap_m.is_some())
        .collect();
    ordered.sort_by(|first, second| {
        second
            .floor_gap_m
            .unwrap_or_default()
            .abs()
            .total_cmp(&first.floor_gap_m.unwrap_or_default().abs())
    });
    ordered
        .into_iter()
        .take(WORST_SAMPLE_LIMIT)
        .map(|sample| station_report(sample, None))
        .collect()
}

fn worst_capsule_intersections(samples: &[SampleMetrics]) -> Vec<WorstStation> {
    let mut ordered: Vec<_> = samples
        .iter()
        .filter(|sample| sample.capsule_penetration_m.is_some())
        .collect();
    ordered.sort_by(|first, second| {
        second
            .capsule_penetration_m
            .unwrap_or_default()
            .total_cmp(&first.capsule_penetration_m.unwrap_or_default())
    });
    ordered
        .into_iter()
        .take(WORST_SAMPLE_LIMIT)
        .map(|sample| station_report(sample, sample.capsule_penetration_m))
        .collect()
}

fn distance_bands(samples: &[SampleMetrics]) -> Vec<DistanceBand> {
    [
        ("0-3m", 0.0, 3.0),
        ("3-6m", 3.0, 6.0),
        ("6-10m", 6.0, 10.0),
        (">10m", 10.0, f32::INFINITY),
    ]
    .into_iter()
    .map(|(band, minimum, maximum)| {
        let in_band: Vec<_> = samples
            .iter()
            .filter(|sample| (minimum..maximum).contains(&sample.camera_distance_m))
            .collect();
        let gaps: Vec<_> = in_band
            .iter()
            .filter_map(|sample| sample.floor_gap_m)
            .collect();
        let absolute_gaps: Vec<_> = gaps.iter().map(|gap| gap.abs()).collect();
        DistanceBand {
            band,
            sample_count: in_band.len(),
            floor_gap_signed_m: distribution(&gaps),
            floor_gap_abs_m: distribution(&absolute_gaps),
            holes_below_floor: in_band
                .iter()
                .filter(|sample| !has_floor_below(sample.floor_gap_m))
                .count(),
            visual_holes: in_band
                .iter()
                .filter(|sample| !has_floor_nearby(sample.floor_gap_m))
                .count(),
        }
    })
    .collect()
}

fn station_report(sample: &SampleMetrics, penetration: Option<f32>) -> WorstStation {
    WorstStation {
        sample_index: sample.sample_index,
        position_m: sample.position.to_array(),
        distance_from_frame_141_m: sample.camera_distance_m,
        signed_floor_gap_m: sample.floor_gap_m,
        capsule_penetration_m: penetration,
    }
}

fn distribution(values: &[f32]) -> DistanceDistribution {
    if values.is_empty() {
        return DistanceDistribution {
            sample_count: 0,
            median_m: None,
            q90_m: None,
            max_m: None,
        };
    }
    let mut ordered = values.to_vec();
    ordered.sort_by(f32::total_cmp);
    let median = if ordered.len().is_multiple_of(2) {
        let upper = ordered.len() / 2;
        (ordered[upper - 1] + ordered[upper]) * 0.5
    } else {
        ordered[ordered.len() / 2]
    };
    let q90_index = ((ordered.len() as f32 * 0.9).ceil() as usize)
        .saturating_sub(1)
        .min(ordered.len() - 1);
    DistanceDistribution {
        sample_count: ordered.len(),
        median_m: Some(median),
        q90_m: Some(ordered[q90_index]),
        max_m: ordered.last().copied(),
    }
}

#[cfg(test)]
mod tests {
    use super::{has_floor_below, has_floor_nearby};

    #[test]
    fn floor_above_collision_plane_is_offset_not_a_hole() {
        assert!(!has_floor_below(Some(0.001)));
        assert!(has_floor_nearby(Some(0.001)));
        assert!(!has_floor_nearby(None));
    }
}
