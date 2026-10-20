use std::{fs, path::Path};

use anyhow::{Context, Result};

use super::{CATALOG_PATH, files, model::Catalog, structure};

pub fn validate_catalog(root: &Path) -> Result<Catalog> {
    let path = root.join(CATALOG_PATH);
    let data = fs::read(&path).with_context(|| format!("cannot read {}", path.display()))?;
    let catalog: Catalog = serde_json::from_slice(&data)
        .with_context(|| format!("invalid room catalog JSON: {}", path.display()))?;
    validate_structure(&catalog)?;
    files::verify_catalog(root, &catalog)?;
    Ok(catalog)
}

pub fn validate_structure(catalog: &Catalog) -> Result<()> {
    structure::validate_catalog(catalog)
}
