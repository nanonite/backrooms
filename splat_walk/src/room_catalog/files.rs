use std::{
    fs::File,
    io::{BufReader, Read},
    path::{Component, Path, PathBuf},
};

use anyhow::{Context, Result, bail};
use sha2::{Digest, Sha256};

use super::model::{Catalog, FileEvidence, FileReference, Module};

pub fn verify_catalog(root: &Path, catalog: &Catalog) -> Result<()> {
    for module in &catalog.modules {
        verify_module(root, module)?;
    }
    Ok(())
}

fn verify_module(root: &Path, module: &Module) -> Result<()> {
    verify_source_files(root, module)?;
    verify_asset_files(root, module)?;
    verify_evidence_files(root, module)
}

fn verify_source_files(root: &Path, module: &Module) -> Result<()> {
    verify_reference(root, &module.source.video)?;
    verify_reference(root, &module.source.camera_metadata)?;
    verify_reference(root, &module.source.inventory_catalog)?;
    for frame in &module.source.frames {
        verify_reference(root, &frame.image)?;
    }
    Ok(())
}

fn verify_asset_files(root: &Path, module: &Module) -> Result<()> {
    verify_asset(
        root,
        &module.assets.visual.path,
        &module.assets.visual.sha256,
    )?;
    verify_asset(
        root,
        &module.assets.collision.path,
        &module.assets.collision.sha256,
    )?;
    verify_reference(root, &module.coordinate_frame.transform_evidence)?;
    verify_optional_reference(root, module.coordinate_frame.registration_evidence.as_ref())?;
    verify_optional_reference(root, module.coordinate_frame.scale_evidence.as_ref())
}

fn verify_asset(root: &Path, path: &str, sha256: &str) -> Result<()> {
    verify_reference(
        root,
        &FileReference {
            path: path.to_owned(),
            sha256: sha256.to_owned(),
        },
    )
}

fn verify_evidence_files(root: &Path, module: &Module) -> Result<()> {
    for evidence in &module.validation_evidence {
        verify_evidence(root, evidence)?;
    }
    for boundary in &module.boundary_rules {
        verify_evidence(root, &boundary.evidence)?;
    }
    for connector in &module.tested_connectors {
        verify_evidence(root, &connector.evidence)?;
    }
    for source in &module.shared_controller.source_files {
        verify_reference(root, source)?;
    }
    verify_evidence(root, &module.runtime_measurements.report)
}

fn verify_optional_reference(root: &Path, reference: Option<&FileReference>) -> Result<()> {
    if let Some(reference) = reference {
        verify_reference(root, reference)?;
    }
    Ok(())
}

pub fn verify_reference(root: &Path, reference: &FileReference) -> Result<()> {
    verify_hash(root, &reference.path, &reference.sha256)
}

pub fn verify_evidence(root: &Path, evidence: &FileEvidence) -> Result<()> {
    verify_hash(root, &evidence.path, &evidence.sha256)
}

fn verify_hash(root: &Path, relative: &str, expected: &str) -> Result<()> {
    validate_sha256(expected)?;
    let path = resolve_repo_file(root, relative)?;
    let actual = sha256_file(&path)?;
    if actual != expected {
        bail!("SHA-256 mismatch for {relative}: expected {expected}, got {actual}");
    }
    Ok(())
}

fn resolve_repo_file(root: &Path, relative: &str) -> Result<PathBuf> {
    let relative_path = Path::new(relative);
    if relative_path.as_os_str().is_empty()
        || relative_path
            .components()
            .any(|part| !matches!(part, Component::Normal(_)))
    {
        bail!("catalog file path must be a non-empty repository-relative path: {relative}");
    }
    let canonical_root = root
        .canonicalize()
        .with_context(|| format!("cannot resolve repository root {}", root.display()))?;
    let path = canonical_root.join(relative_path);
    let canonical_path = path
        .canonicalize()
        .with_context(|| format!("catalog file is missing: {relative}"))?;
    if !canonical_path.starts_with(&canonical_root) || !canonical_path.is_file() {
        bail!("catalog file must be a regular file inside the repository: {relative}");
    }
    Ok(canonical_path)
}

fn validate_sha256(value: &str) -> Result<()> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        bail!("invalid lowercase SHA-256 digest: {value}");
    }
    Ok(())
}

fn sha256_file(path: &Path) -> Result<String> {
    let file = File::open(path).with_context(|| format!("cannot open {}", path.display()))?;
    let mut reader = BufReader::new(file);
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let read_count = reader
            .read(&mut buffer)
            .with_context(|| format!("cannot hash {}", path.display()))?;
        if read_count == 0 {
            break;
        }
        digest.update(&buffer[..read_count]);
    }
    Ok(digest
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}
