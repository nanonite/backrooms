mod connectors;
mod module_checks;

use std::collections::HashSet;

use anyhow::{Result, bail};

use super::{model::*, primitives::validate_stable_id};

const SUPPORTED_SCHEMA_VERSION: u32 = 1;

pub fn validate_catalog(catalog: &Catalog) -> Result<()> {
    if catalog.schema_version != SUPPORTED_SCHEMA_VERSION {
        bail!(
            "unsupported catalog schema version {}",
            catalog.schema_version
        );
    }
    if catalog.modules.is_empty() {
        bail!("catalog must contain at least one module");
    }
    let ids = collect_module_ids(&catalog.modules)?;
    validate_modules(&catalog.modules, &ids)?;
    validate_connector_targets(&catalog.modules)
}

fn collect_module_ids(modules: &[Module]) -> Result<HashSet<&str>> {
    let mut ids = HashSet::new();
    for module in modules {
        validate_stable_id(&module.id, "module")?;
        if !ids.insert(module.id.as_str()) {
            bail!("duplicate module ID: {}", module.id);
        }
    }
    Ok(ids)
}

fn validate_modules(modules: &[Module], ids: &HashSet<&str>) -> Result<()> {
    for module in modules {
        module_checks::validate(module)?;
        connectors::validate_module_connectors(module, ids)?;
    }
    Ok(())
}

fn validate_connector_targets(modules: &[Module]) -> Result<()> {
    for module in modules {
        for connector in &module.tested_connectors {
            let target = modules
                .iter()
                .find(|candidate| candidate.id == connector.target_module_id)
                .ok_or_else(|| anyhow::anyhow!("missing connector target module"))?;
            let target_exists = target
                .connector_sockets
                .iter()
                .any(|socket| socket.id == connector.target_socket_id);
            if !target_exists {
                bail!(
                    "connector {} references a missing target socket",
                    connector.id
                );
            }
        }
    }
    Ok(())
}
