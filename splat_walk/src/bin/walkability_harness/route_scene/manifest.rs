use std::{
    fs::File,
    io::Read,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result, bail};
use serde::Deserialize;
use sha2::{Digest, Sha256};

const MANIFEST_PATH: &str =
    "godot_walk/evidence/2026-10-13-hunyuan-track-a/hunyuan_route_scene_manifest.json";
const ISSUE147_MANIFEST_PATH: &str =
    "godot_walk/evidence/2026-10-20-issue-147/module_manifest.json";
const ISSUE150_MANIFEST_PATH: &str =
    "godot_walk/evidence/2026-10-20-issue-150/module_manifest.json";

#[derive(Deserialize)]
pub struct SceneManifest {
    pub issue: u32,
    pub label: String,
    pub registration_accepted: bool,
    pub scale_calibrated: bool,
    pub transform: SceneTransform,
    pub assets: SceneAssets,
    #[serde(default)]
    pub source_evidence: Vec<AssetRecord>,
    pub locked_traversal_gate: TraversalGate,
    #[serde(default)]
    pub route_report_path: Option<String>,
    #[serde(default)]
    pub route_report_sha256: Option<String>,
    #[serde(default)]
    pub output_report_path: Option<String>,
    #[serde(default)]
    pub capture_poses_path: Option<String>,
    #[serde(default)]
    pub capture_poses_sha256: Option<String>,
    #[serde(default)]
    pub capture_output_path: Option<String>,
}

#[derive(Deserialize)]
pub struct SceneTransform {
    pub transform_status: String,
    pub scale_m_per_hunyuan_unit: f32,
    pub scale_sensitivity_range_m_per_hunyuan_unit: [f32; 2],
    #[serde(alias = "registered_frame_141_camera_anchor_world_m")]
    pub camera_anchor_world_m: [f32; 3],
    pub plane_aligned_translation_world_m: [f32; 3],
    pub camera_anchor_shift_y_m: f32,
    pub declared_collision_floor_y_m: f32,
}

#[derive(Deserialize)]
pub struct SceneAssets {
    pub visual: AssetRecord,
    pub collision: AssetRecord,
    pub camera_metadata: AssetRecord,
}

#[derive(Deserialize)]
pub struct AssetRecord {
    pub path: String,
    pub sha256: String,
}

#[derive(Deserialize)]
pub struct TraversalGate {
    pub outbound_progress_fraction_min: f32,
    pub inbound_progress_fraction_min: f32,
    pub moving_support_fraction_min: f32,
    pub safety_net_contacts_max: usize,
    pub max_vertical_step_m: f32,
}

pub fn load_manifest(root: &Path) -> Result<SceneManifest> {
    load_manifest_from(root, MANIFEST_PATH)
}

pub fn load_issue147_manifest(root: &Path) -> Result<SceneManifest> {
    load_manifest_from(root, ISSUE147_MANIFEST_PATH)
}

pub fn load_issue150_manifest(root: &Path) -> Result<SceneManifest> {
    load_manifest_from(root, ISSUE150_MANIFEST_PATH)
}

fn load_manifest_from(root: &Path, relative_path: &str) -> Result<SceneManifest> {
    let manifest_path = root.join(relative_path);
    let manifest: SceneManifest = serde_json::from_slice(
        &std::fs::read(&manifest_path)
            .with_context(|| format!("cannot read manifest {}", manifest_path.display()))?,
    )
    .context("route-scene manifest is invalid JSON")?;
    if ![137, 147, 150].contains(&manifest.issue)
        || manifest.label != "uncalibrated"
        || manifest.registration_accepted
        || manifest.scale_calibrated
        || manifest.transform.transform_status != "uncalibrated_convention"
    {
        bail!("route-scene manifest has invalid issue or calibration status");
    }
    if manifest.issue != 137
        && (manifest.route_report_path.is_none()
            || manifest.route_report_sha256.is_none()
            || manifest.output_report_path.is_none()
            || manifest.capture_poses_path.is_none()
            || manifest.capture_poses_sha256.is_none()
            || manifest.capture_output_path.is_none()
            || manifest.source_evidence.len() < 2)
    {
        bail!("#147 module manifest is missing route or capture paths");
    }
    if manifest.assets.visual.path.is_empty()
        || manifest.assets.collision.path.is_empty()
        || manifest.transform.scale_m_per_hunyuan_unit <= 0.0
        || manifest
            .transform
            .scale_sensitivity_range_m_per_hunyuan_unit[0]
            > manifest.transform.scale_m_per_hunyuan_unit
        || manifest
            .transform
            .scale_sensitivity_range_m_per_hunyuan_unit[1]
            < manifest.transform.scale_m_per_hunyuan_unit
    {
        bail!("route-scene manifest has an invalid asset path or convention scale");
    }
    verify_hash(root, &manifest.assets.visual)?;
    verify_hash(root, &manifest.assets.collision)?;
    verify_hash(root, &manifest.assets.camera_metadata)?;
    for source in &manifest.source_evidence {
        verify_hash(root, source)?;
    }
    if let (Some(path), Some(sha256)) = (
        manifest.route_report_path.as_ref(),
        manifest.route_report_sha256.as_ref(),
    ) {
        verify_hash(
            root,
            &AssetRecord {
                path: path.clone(),
                sha256: sha256.clone(),
            },
        )?;
    }
    if let (Some(path), Some(sha256)) = (
        manifest.capture_poses_path.as_ref(),
        manifest.capture_poses_sha256.as_ref(),
    ) {
        verify_hash(
            root,
            &AssetRecord {
                path: path.clone(),
                sha256: sha256.clone(),
            },
        )?;
    }
    Ok(manifest)
}

pub fn repo_root() -> Result<PathBuf> {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(Path::to_path_buf)
        .context("crate has no workspace root")
}

fn verify_hash(root: &Path, asset: &AssetRecord) -> Result<()> {
    let path = root.join(&asset.path);
    let actual = sha256_file(&path)?;
    if actual != asset.sha256 {
        bail!(
            "asset hash mismatch for {}: expected {}, got {actual}",
            path.display(),
            asset.sha256
        );
    }
    Ok(())
}

fn sha256_file(path: &Path) -> Result<String> {
    let mut file = File::open(path).with_context(|| format!("cannot open {}", path.display()))?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let read_count = file
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
