mod content;

use anyhow::{Result, bail};

use super::super::{model::*, primitives::*};

pub fn validate(module: &Module) -> Result<()> {
    validate_identity(module)?;
    validate_source(module)?;
    validate_assets(&module.assets)?;
    validate_coordinates(&module.coordinate_frame)?;
    content::validate(module)
}

fn validate_identity(module: &Module) -> Result<()> {
    validate_nonempty(&module.display_name, "display_name")?;
    let valid_kinds = ["bounded_playable_reference_zone", "room", "corridor"];
    if !valid_kinds.contains(&module.kind.as_str()) {
        bail!("unsupported module kind: {}", module.kind);
    }
    let valid_states = ["uncalibrated_reference", "proposed", "standalone_validated"];
    if !valid_states.contains(&module.admission_status.as_str()) {
        bail!(
            "unsupported module admission status: {}",
            module.admission_status
        );
    }
    Ok(())
}

fn validate_source(module: &Module) -> Result<()> {
    if module.source.frames.is_empty() {
        bail!("module {} needs at least one source frame", module.id);
    }
    for frame in &module.source.frames {
        validate_source_frame(module, frame)?;
    }
    Ok(())
}

fn validate_source_frame(module: &Module, frame: &SourceFrame) -> Result<()> {
    if frame.frame_id == 0 || frame.zero_based_index.checked_add(1) != Some(frame.frame_id) {
        bail!("module {} has inconsistent source frame IDs", module.id);
    }
    if !frame.timestamp_seconds.is_finite() || frame.timestamp_seconds < 0.0 {
        bail!("module {} has an invalid source frame timestamp", module.id);
    }
    validate_nonempty(&frame.usage, "source frame usage")
}

fn validate_assets(assets: &ModuleAssets) -> Result<()> {
    if assets.visual.role != "visual_only" || assets.collision.role != "collision_only" {
        bail!("visual and collision asset roles must remain separate");
    }
    validate_asset_transform(&assets.visual.transform)?;
    validate_asset_transform(&assets.collision.transform)
}

fn validate_asset_transform(transform: &AssetTransform) -> Result<()> {
    validate_nonempty(&transform.status, "asset transform status")?;
    validate_finite(&transform.translation_m, "asset translation")?;
    validate_finite(&transform.rotation_xyzw, "asset rotation")?;
    validate_finite(&transform.scale, "asset scale")?;
    validate_rotation(transform)?;
    validate_scale(transform)?;
    validate_nonempty(&transform.note, "asset transform note")
}

fn validate_rotation(transform: &AssetTransform) -> Result<()> {
    let norm = transform
        .rotation_xyzw
        .iter()
        .map(|value| value * value)
        .sum::<f64>()
        .sqrt();
    if (norm - 1.0).abs() > 1.0e-3 {
        bail!("asset rotation quaternion must be normalized");
    }
    Ok(())
}

fn validate_scale(transform: &AssetTransform) -> Result<()> {
    if transform.scale.iter().any(|value| *value <= 0.0) {
        bail!("asset transform scale must be positive");
    }
    Ok(())
}

fn validate_coordinates(frame: &CoordinateFrame) -> Result<()> {
    for (value, label) in [
        (&frame.id, "coordinate frame ID"),
        (&frame.units, "coordinate units"),
        (&frame.handedness, "coordinate handedness"),
        (&frame.up_axis, "coordinate up axis"),
        (&frame.scale_basis, "scale basis"),
    ] {
        validate_nonempty(value, label)?;
    }
    content::validate_calibration(frame)
}
