use std::collections::HashSet;

use anyhow::{Result, bail};

use super::super::super::{model::*, primitives::*, runtime_model::RuntimeMeasurements};

pub fn validate(module: &Module) -> Result<()> {
    validate_surfaces(&module.floor_ceiling)?;
    validate_openings(
        &module.observed_openings,
        module.coordinate_frame.registration_accepted,
    )?;
    validate_boundaries(&module.boundary_rules)?;
    validate_controller(&module.shared_controller)?;
    validate_runtime(&module.runtime_measurements)
}

pub fn validate_calibration(frame: &CoordinateFrame) -> Result<()> {
    let expected = calibration_status(frame.registration_accepted, frame.scale_calibrated);
    if frame.transform_status != expected {
        bail!("calibration flags require transform_status={expected}");
    }
    if frame.registration_accepted != frame.registration_evidence.is_some()
        || frame.scale_calibrated != frame.scale_evidence.is_some()
    {
        bail!("calibration flags and their evidence references must agree");
    }
    Ok(())
}

fn calibration_status(registration: bool, scale: bool) -> &'static str {
    match (registration, scale) {
        (false, false) => "uncalibrated_convention",
        (true, false) => "registered_scale_unknown",
        (false, true) => "scale_calibrated_unregistered",
        (true, true) => "calibrated_registered",
    }
}

fn validate_surfaces(surfaces: &FloorCeiling) -> Result<()> {
    validate_surface(&surfaces.floor, "floor")?;
    validate_surface(&surfaces.ceiling, "ceiling")
}

fn validate_surface(surface: &SurfaceAssumption, name: &str) -> Result<()> {
    let fields = [
        (&surface.status, "status"),
        (&surface.origin, "origin"),
        (&surface.basis, "basis"),
        (&surface.collision_role, "collision role"),
    ];
    for (value, label) in fields {
        validate_nonempty(value, &format!("{name} {label}"))?;
    }
    validate_optional_measurements(surface, name)
}

fn validate_optional_measurements(surface: &SurfaceAssumption, name: &str) -> Result<()> {
    for measurement in [surface.elevation_m, surface.assumed_clear_height_m]
        .into_iter()
        .flatten()
    {
        validate_finite(&[measurement], &format!("{name} measurement"))?;
    }
    Ok(())
}

fn validate_openings(openings: &[ObservedOpening], registered: bool) -> Result<()> {
    let mut ids = HashSet::new();
    for opening in openings {
        validate_opening(opening, registered, &mut ids)?;
    }
    Ok(())
}

fn validate_opening<'a>(
    opening: &'a ObservedOpening,
    registered: bool,
    ids: &mut HashSet<&'a str>,
) -> Result<()> {
    validate_stable_id(&opening.id, "opening")?;
    if !ids.insert(opening.id.as_str()) {
        bail!("duplicate observed opening ID: {}", opening.id);
    }
    if opening.frame_start == 0 || opening.frame_end < opening.frame_start {
        bail!("observed opening {} has an invalid frame range", opening.id);
    }
    validate_opening_status(opening, registered)?;
    validate_nonempty(&opening.inventory_catalog_id, "opening inventory ID")?;
    validate_nonempty(&opening.description, "opening description")
}

fn validate_opening_status(opening: &ObservedOpening, registered: bool) -> Result<()> {
    let traversability_valid =
        ["unknown", "visually_open"].contains(&opening.traversability.as_str());
    let relation_valid =
        ["unregistered", "registered_visual_only"].contains(&opening.module_relation.as_str());
    if !traversability_valid || !relation_valid {
        bail!(
            "source opening {} cannot imply tested traversal",
            opening.id
        );
    }
    if opening.module_relation == "registered_visual_only" && !registered {
        bail!(
            "opening {} cannot be registered in an unregistered module",
            opening.id
        );
    }
    Ok(())
}

fn validate_boundaries(boundaries: &[BoundaryRule]) -> Result<()> {
    let mut ids = HashSet::new();
    for boundary in boundaries {
        validate_boundary(boundary, &mut ids)?;
    }
    Ok(())
}

fn validate_boundary<'a>(boundary: &'a BoundaryRule, ids: &mut HashSet<&'a str>) -> Result<()> {
    validate_stable_id(&boundary.id, "boundary rule")?;
    if !ids.insert(boundary.id.as_str()) {
        bail!("duplicate boundary rule ID: {}", boundary.id);
    }
    if !["authored", "observed"].contains(&boundary.origin.as_str()) {
        bail!("boundary {} must be authored or observed", boundary.id);
    }
    validate_boundary_text(boundary)
}

fn validate_boundary_text(boundary: &BoundaryRule) -> Result<()> {
    validate_nonempty(&boundary.kind, "boundary kind")?;
    validate_nonempty(&boundary.description, "boundary description")?;
    validate_nonempty(&boundary.collision_node, "boundary collision node")
}

fn validate_controller(controller: &ControllerReference) -> Result<()> {
    validate_stable_id(&controller.profile_id, "controller profile")?;
    validate_controller_labels(controller)?;
    validate_controller_dimensions(controller)
}

fn validate_controller_labels(controller: &ControllerReference) -> Result<()> {
    if controller.source_files.is_empty() {
        bail!("shared controller source files are required");
    }
    validate_nonempty(&controller.tnua_version, "Tnua version")?;
    validate_nonempty(&controller.avian3d_version, "Avian version")
}

fn validate_controller_dimensions(controller: &ControllerReference) -> Result<()> {
    let values = [
        controller.capsule_radius_m,
        controller.capsule_height_m,
        controller.max_slope_degrees,
    ];
    validate_finite(&values, "controller measurement")?;
    if values.iter().any(|value| *value <= 0.0) || controller.max_slope_degrees >= 90.0 {
        bail!("shared controller dimensions or slope limit are invalid");
    }
    Ok(())
}

fn validate_runtime(measurements: &RuntimeMeasurements) -> Result<()> {
    let values = [
        measurements.scene_total_wall_time_seconds,
        measurements.route_simulation_wall_time_seconds,
        measurements.mean_update_ms,
        measurements.p90_update_ms,
        measurements.max_update_ms,
        measurements.visual_load_seconds,
        measurements.visual_query_preparation_seconds,
    ];
    validate_finite(&values, "runtime/resource measurement")?;
    validate_runtime_values(measurements, &values)
}

fn validate_runtime_values(measurements: &RuntimeMeasurements, values: &[f64]) -> Result<()> {
    let invalid_values = values.iter().any(|value| *value < 0.0);
    if invalid_values || measurements.peak_rss_kib == 0 || measurements.visual_triangle_count == 0 {
        bail!("runtime/resource measurements must be non-negative and non-zero where required");
    }
    validate_runtime_mode(measurements)
}

fn validate_runtime_mode(measurements: &RuntimeMeasurements) -> Result<()> {
    let valid_mode =
        ["cpu_headless", "gpu_rendered", "interactive_walk"].contains(&measurements.mode.as_str());
    if !valid_mode || (measurements.mode == "cpu_headless" && measurements.gpu_used) {
        bail!("runtime mode and GPU-use flag are inconsistent");
    }
    validate_nonempty(&measurements.note, "runtime measurement note")
}
