use std::{fs, path::PathBuf, time::SystemTime};

use serde_json::{Value, json};

use super::{files, model::Catalog, validate_structure};

const CATALOG_JSON: &str = include_str!("../../room_catalog/catalog.json");
const SCHEMA_JSON: &str = include_str!("../../room_catalog/catalog.schema.json");

fn sample_value() -> Value {
    serde_json::from_str(CATALOG_JSON).expect("checked-in catalog JSON parses")
}

fn connector_socket() -> Value {
    json!({
        "id": "west-socket",
        "status": "proposed",
        "description": "Local test socket",
        "clear_width_m": 1.0,
        "clear_height_m": 2.0,
        "local_transform": {
            "translation_m": [0.0, 0.0, 0.0],
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
            "scale": [1.0, 1.0, 1.0]
        }
    })
}

fn connector_with_missing_target() -> Value {
    json!({
        "id": "west-to-missing",
        "from_socket_id": "west-socket",
        "target_module_id": "milestone-video-to-walkable-working",
        "target_socket_id": "missing-socket",
        "evidence": {
            "path": "evidence.json",
            "sha256": "0".repeat(64),
            "purpose": "Invalid test endpoint"
        }
    })
}

fn unique_temp_root(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .expect("clock is after UNIX epoch")
        .as_nanos();
    std::env::temp_dir().join(format!(
        "room-catalog-{label}-{}-{nanos}",
        std::process::id()
    ))
}

#[test]
fn reference_catalog_is_structurally_valid_and_unregistered() {
    let catalog: Catalog = serde_json::from_value(sample_value()).expect("catalog model parses");
    validate_structure(&catalog).expect("reference catalog validates");
    let module = &catalog.modules[0];
    assert!(!module.coordinate_frame.registration_accepted);
    assert!(!module.coordinate_frame.scale_calibrated);
    assert_eq!(module.observed_openings.len(), 1);
    assert!(module.tested_connectors.is_empty());
}

#[test]
fn schema_and_catalog_are_valid_json_documents() {
    let schema: Value = serde_json::from_str(SCHEMA_JSON).expect("schema JSON parses");
    let catalog = sample_value();
    assert_eq!(
        schema["$schema"],
        "https://json-schema.org/draft/2020-12/schema"
    );
    assert_eq!(catalog["schema_version"], 1);
}

#[test]
fn duplicate_module_ids_are_rejected() {
    let mut value = sample_value();
    let duplicate = value["modules"][0].clone();
    value["modules"]
        .as_array_mut()
        .expect("module array")
        .push(duplicate);
    let catalog: Catalog = serde_json::from_value(value).expect("duplicate catalog parses");
    assert!(validate_structure(&catalog).is_err());
}

#[test]
fn unnormalized_connector_transform_is_rejected() {
    let mut value = sample_value();
    value["modules"][0]["connector_sockets"] = json!([{
        "id": "west-socket",
        "status": "proposed",
        "description": "Test-only invalid transform",
        "clear_width_m": 1.0,
        "clear_height_m": 2.0,
        "local_transform": {
            "translation_m": [0.0, 0.0, 0.0],
            "rotation_xyzw": [0.0, 0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0]
        }
    }]);
    let catalog: Catalog = serde_json::from_value(value).expect("invalid transform parses");
    assert!(validate_structure(&catalog).is_err());
}

#[test]
fn tested_connector_target_socket_must_exist() {
    let mut value = sample_value();
    value["modules"][0]["connector_sockets"] = json!([connector_socket()]);
    value["modules"][0]["tested_connectors"] = json!([connector_with_missing_target()]);
    let catalog: Catalog = serde_json::from_value(value).expect("connector record parses");
    assert!(validate_structure(&catalog).is_err());
}

#[test]
fn contradictory_calibration_flags_are_rejected() {
    let mut value = sample_value();
    value["modules"][0]["coordinate_frame"]["scale_calibrated"] = json!(true);
    let catalog: Catalog = serde_json::from_value(value).expect("flag combination parses");
    assert!(validate_structure(&catalog).is_err());
}

#[test]
fn observed_opening_cannot_hide_a_connector_transform() {
    let mut value = sample_value();
    value["modules"][0]["observed_openings"][0]["transform"] = json!({
        "translation_m": [0.0, 0.0, 0.0],
        "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
        "scale": [1.0, 1.0, 1.0]
    });
    assert!(serde_json::from_value::<Catalog>(value).is_err());
}

#[test]
fn missing_files_and_path_traversal_are_rejected() {
    let root = unique_temp_root("missing");
    fs::create_dir_all(&root).expect("temporary root created");
    let missing = super::model::FileReference {
        path: "not-present.glb".to_owned(),
        sha256: "0".repeat(64),
    };
    assert!(files::verify_reference(&root, &missing).is_err());
    let traversal = super::model::FileReference {
        path: "../outside.glb".to_owned(),
        sha256: "0".repeat(64),
    };
    assert!(files::verify_reference(&root, &traversal).is_err());
    fs::remove_dir_all(root).expect("temporary test root removed");
}

#[test]
fn modified_asset_hash_is_rejected() {
    let root = unique_temp_root("hash");
    fs::create_dir_all(&root).expect("temporary root created");
    fs::write(root.join("asset.glb"), b"changed asset").expect("temporary asset written");
    let reference = super::model::FileReference {
        path: "asset.glb".to_owned(),
        sha256: "0".repeat(64),
    };
    assert!(files::verify_reference(&root, &reference).is_err());
    fs::remove_dir_all(root).expect("temporary test root removed");
}
