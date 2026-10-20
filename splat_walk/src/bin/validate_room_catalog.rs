use std::path::PathBuf;

use anyhow::{Context, Result, bail};
use hunyuan_bevy_fixture::room_catalog::{CATALOG_PATH, validate_catalog};

fn main() -> Result<()> {
    let root = parse_root()?;
    let catalog = validate_catalog(&root)?;
    println!(
        "validated {} module(s) from {}",
        catalog.modules.len(),
        root.join(CATALOG_PATH).display()
    );
    for module in catalog.modules {
        println!(
            "{}: {} [{}], registration_accepted={}, scale_calibrated={}, observed_openings={}, tested_connectors={}",
            module.id,
            module.display_name,
            module.admission_status,
            module.coordinate_frame.registration_accepted,
            module.coordinate_frame.scale_calibrated,
            module.observed_openings.len(),
            module.tested_connectors.len()
        );
    }
    Ok(())
}

fn parse_root() -> Result<PathBuf> {
    let mut arguments = std::env::args_os().skip(1);
    let Some(root) = arguments.next() else {
        return PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .map(PathBuf::from)
            .context("crate manifest has no workspace parent");
    };
    if arguments.next().is_some() {
        bail!("usage: validate_room_catalog [workspace-root]");
    }
    Ok(PathBuf::from(root))
}
