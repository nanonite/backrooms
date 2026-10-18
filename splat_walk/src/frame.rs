use std::{fs, path::Path};

use anyhow::{Context, Result, bail};
use bevy::prelude::{Mat3, Quat, Transform, Vec3};
use serde_json::Value;

pub struct FrameCamera {
    pub origin: Vec3,
    pub forward: Vec3,
    pub up: Vec3,
    pub right: Vec3,
    pub vertical_fov_radians: f32,
}

impl FrameCamera {
    pub fn from_json(path: &Path) -> Result<Self> {
        let contents = fs::read_to_string(path)
            .with_context(|| format!("cannot read camera metadata {}", path.display()))?;
        let document: Value =
            serde_json::from_str(&contents).context("invalid camera metadata JSON")?;
        let camera = document
            .get("camera")
            .context("camera metadata has no camera object")?;
        let origin = vector3(camera, "camera_center_godot_world_m")?;
        let forward = vector3(camera, "forward_godot_world")?.normalize_or_zero();
        let source_up = vector3(camera, "up_godot_world")?.normalize_or_zero();
        if forward.length_squared() < 0.99 || source_up.length_squared() < 0.99 {
            bail!("camera forward or up vector has invalid length");
        }

        let right = forward.cross(source_up).normalize_or_zero();
        let up = right.cross(forward).normalize_or_zero();
        if right.length_squared() < 0.99 || up.length_squared() < 0.99 {
            bail!("camera forward and up vectors are parallel");
        }
        let vertical_fov_radians = camera
            .get("approx_vertical_fov_degrees")
            .and_then(Value::as_f64)
            .context("camera metadata has no vertical field of view")?
            as f32;
        if !(0.1..179.0).contains(&vertical_fov_radians) {
            bail!("camera vertical field of view is outside (0.1, 179) degrees");
        }

        Ok(Self {
            origin,
            forward,
            up,
            right,
            vertical_fov_radians: vertical_fov_radians.to_radians(),
        })
    }

    pub fn transform(&self) -> Transform {
        let model_basis = Mat3::from_cols(-self.forward, self.right, self.up);
        Transform::from_translation(self.origin).with_rotation(Quat::from_mat3(&model_basis))
    }

    pub fn camera_transform(&self) -> Transform {
        Transform::from_translation(self.origin).looking_to(self.forward, self.up)
    }
}

fn vector3(document: &Value, key: &str) -> Result<Vec3> {
    let values = document
        .get(key)
        .and_then(Value::as_array)
        .with_context(|| format!("camera metadata has no {key} array"))?;
    if values.len() != 3 {
        bail!("camera vector {key} must have exactly 3 values");
    }
    let components: Vec<f32> = values
        .iter()
        .map(|value| {
            value
                .as_f64()
                .map(|number| number as f32)
                .filter(|number| number.is_finite())
                .with_context(|| format!("camera vector {key} contains a non-finite value"))
        })
        .collect::<Result<_>>()?;
    Ok(Vec3::new(components[0], components[1], components[2]))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn godot_hunyuan_axes_align_to_registered_frame() {
        let forward = Vec3::new(-0.528622, 0.001250, -0.848856).normalize();
        let up = Vec3::new(0.003274, 0.999994, -0.000566).normalize();
        let right = forward.cross(up).normalize();
        let corrected_up = right.cross(forward).normalize();
        let camera = FrameCamera {
            origin: Vec3::ZERO,
            forward,
            up: corrected_up,
            right,
            vertical_fov_radians: 1.0,
        };
        let transform = camera.transform();

        assert!((transform.rotation * -Vec3::X).abs_diff_eq(forward, 1e-4));
        assert!((transform.rotation * Vec3::Y).abs_diff_eq(right, 1e-4));
        assert!((transform.rotation * Vec3::Z).abs_diff_eq(corrected_up, 1e-4));
        let camera_transform = camera.camera_transform();
        assert!((camera_transform.rotation * -Vec3::Z).abs_diff_eq(forward, 1e-4));
        assert!((camera_transform.rotation * Vec3::Y).abs_diff_eq(corrected_up, 1e-4));
    }
}
