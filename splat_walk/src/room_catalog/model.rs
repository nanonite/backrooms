use super::runtime_model::RuntimeMeasurements;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Catalog {
    pub schema_version: u32,
    pub modules: Vec<Module>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Module {
    pub id: String,
    pub display_name: String,
    pub kind: String,
    pub admission_status: String,
    pub source: SourceProvenance,
    pub assets: ModuleAssets,
    pub coordinate_frame: CoordinateFrame,
    pub floor_ceiling: FloorCeiling,
    pub observed_openings: Vec<ObservedOpening>,
    pub connector_sockets: Vec<ConnectorSocket>,
    pub tested_connectors: Vec<TestedConnector>,
    pub boundary_rules: Vec<BoundaryRule>,
    pub shared_controller: ControllerReference,
    pub validation_evidence: Vec<FileEvidence>,
    pub runtime_measurements: RuntimeMeasurements,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SourceProvenance {
    pub video: FileReference,
    pub frames: Vec<SourceFrame>,
    pub camera_metadata: FileReference,
    pub inventory_catalog: FileReference,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SourceFrame {
    pub frame_id: u32,
    pub zero_based_index: u32,
    pub timestamp_seconds: f64,
    pub image: FileReference,
    pub usage: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModuleAssets {
    pub visual: AssetReference,
    pub collision: AssetReference,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AssetReference {
    pub path: String,
    pub sha256: String,
    pub role: String,
    pub transform: AssetTransform,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AssetTransform {
    pub status: String,
    pub translation_m: [f64; 3],
    pub rotation_xyzw: [f64; 4],
    pub scale: [f64; 3],
    pub note: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CoordinateFrame {
    pub id: String,
    pub units: String,
    pub handedness: String,
    pub up_axis: String,
    pub transform_status: String,
    pub registration_accepted: bool,
    pub scale_calibrated: bool,
    pub scale_basis: String,
    pub transform_evidence: FileReference,
    pub registration_evidence: Option<FileReference>,
    pub scale_evidence: Option<FileReference>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FloorCeiling {
    pub floor: SurfaceAssumption,
    pub ceiling: SurfaceAssumption,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SurfaceAssumption {
    pub status: String,
    pub origin: String,
    pub elevation_m: Option<f64>,
    pub assumed_clear_height_m: Option<f64>,
    pub basis: String,
    pub collision_role: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ObservedOpening {
    pub id: String,
    pub inventory_catalog_id: String,
    pub frame_start: u32,
    pub frame_end: u32,
    pub description: String,
    pub traversability: String,
    pub module_relation: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ConnectorSocket {
    pub id: String,
    pub status: String,
    pub description: String,
    pub clear_width_m: f64,
    pub clear_height_m: f64,
    pub local_transform: RigidTransform,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RigidTransform {
    pub translation_m: [f64; 3],
    pub rotation_xyzw: [f64; 4],
    pub scale: [f64; 3],
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TestedConnector {
    pub id: String,
    pub from_socket_id: String,
    pub target_module_id: String,
    pub target_socket_id: String,
    pub evidence: FileEvidence,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BoundaryRule {
    pub id: String,
    pub kind: String,
    pub origin: String,
    pub description: String,
    pub collision_node: String,
    pub evidence: FileEvidence,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ControllerReference {
    pub profile_id: String,
    pub source_files: Vec<FileReference>,
    pub tnua_version: String,
    pub avian3d_version: String,
    pub capsule_radius_m: f64,
    pub capsule_height_m: f64,
    pub max_slope_degrees: f64,
    pub per_module_overrides: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FileEvidence {
    pub path: String,
    pub sha256: String,
    pub purpose: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FileReference {
    pub path: String,
    pub sha256: String,
}
