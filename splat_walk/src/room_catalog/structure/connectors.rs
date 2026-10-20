use std::collections::HashSet;

use anyhow::{Result, bail};

use super::super::{model::*, primitives::*};

const QUATERNION_TOLERANCE: f64 = 1.0e-3;
const SCALE_TOLERANCE: f64 = 1.0e-4;

pub fn validate_module_connectors(module: &Module, module_ids: &HashSet<&str>) -> Result<()> {
    let socket_ids = validate_sockets(&module.connector_sockets)?;
    validate_tested_connectors(module, module_ids, &socket_ids)
}

fn validate_sockets(sockets: &[ConnectorSocket]) -> Result<HashSet<&str>> {
    let mut ids = HashSet::new();
    for socket in sockets {
        validate_stable_id(&socket.id, "connector socket")?;
        if !ids.insert(socket.id.as_str()) {
            bail!("duplicate connector socket ID: {}", socket.id);
        }
        validate_clearance(socket)?;
        validate_nonempty(&socket.status, "connector socket status")?;
        validate_nonempty(&socket.description, "connector socket description")?;
        validate_rigid_transform(&socket.local_transform)?;
    }
    Ok(ids)
}

fn validate_clearance(socket: &ConnectorSocket) -> Result<()> {
    let clearance = [socket.clear_width_m, socket.clear_height_m];
    validate_finite(&clearance, "connector clearance")?;
    if clearance.iter().any(|value| *value <= 0.0) {
        bail!("connector socket {} has non-positive clearance", socket.id);
    }
    Ok(())
}

fn validate_tested_connectors(
    module: &Module,
    module_ids: &HashSet<&str>,
    socket_ids: &HashSet<&str>,
) -> Result<()> {
    let mut connector_ids = HashSet::new();
    for connector in &module.tested_connectors {
        validate_stable_id(&connector.id, "tested connector")?;
        if !connector_ids.insert(connector.id.as_str()) {
            bail!("duplicate tested connector ID: {}", connector.id);
        }
        if !socket_ids.contains(connector.from_socket_id.as_str()) {
            bail!(
                "connector {} references a missing local socket",
                connector.id
            );
        }
        if !module_ids.contains(connector.target_module_id.as_str()) {
            bail!(
                "connector {} references a missing target module",
                connector.id
            );
        }
        validate_nonempty(&connector.target_socket_id, "target connector socket ID")?;
    }
    Ok(())
}

fn validate_rigid_transform(transform: &RigidTransform) -> Result<()> {
    validate_finite(&transform.translation_m, "connector translation")?;
    validate_finite(&transform.rotation_xyzw, "connector rotation")?;
    validate_finite(&transform.scale, "connector scale")?;
    validate_rotation(transform)?;
    validate_unit_scale(transform)
}

fn validate_rotation(transform: &RigidTransform) -> Result<()> {
    let norm = transform
        .rotation_xyzw
        .iter()
        .map(|value| value * value)
        .sum::<f64>()
        .sqrt();
    if (norm - 1.0).abs() > QUATERNION_TOLERANCE {
        bail!("connector rotation quaternion must be normalized");
    }
    Ok(())
}

fn validate_unit_scale(transform: &RigidTransform) -> Result<()> {
    if transform
        .scale
        .iter()
        .any(|value| (value - 1.0).abs() > SCALE_TOLERANCE)
    {
        bail!("connector transforms must be rigid and use unit scale");
    }
    Ok(())
}
