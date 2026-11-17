# Generation record for the issue-265 admission artifacts

The three generated classes of file (catalog bump, immutable snapshot, six
`catalog_admission_decision.json` records) were produced in one deterministic
pass by a one-off helper. It was run from the repository root; its behaviour is
reproduced verbatim below. It was not left as a runnable tool in the repository
because re-running it against the already-bumped 0.6.0 catalog is intentionally
refused by its `assert catalog_version == "0.5.0"` guard.

It reads each room's frozen `adaptation_standalone_accepted_v1.json` and
`operator_review.json`; copies real `candidate_identity`, footprint, clearance,
provenance, dependencies and collision provenance into the new module entry;
converts any `res://` dependency/visual-asset string to a repository-relative
`godot_walk/...` path (required by `issue149_layout_core._catalog_paths`, which
treats those arrays as filesystem paths); computes real SHA-256 digests for the
accepted records and the new snapshot; and writes with
`json.dumps(obj, indent=2, ensure_ascii=False) + "\n"`.

```python
ROOMS = [
    ("video-22909eb734e4d8e2", "slot-canyon-courtyard-v1", 172),
    ("video-d857abe7a94da9d1", "nested-light-corridor-v1", 173),
    ("video-d92fc1fa764aa3a2", "snow-garden-courtyard-v2", 174),
    ("video-102caf53423018b7", "chevron-corridor-v1", 175),
    ("video-2671b32f256a4ee7", "chevron-corridor-v1", 176),
    ("video-61b91dbeb9026dc7", "chevron-cross-corridor-v1", 177),
]
SNAPSHOT_REL = "godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.6.0.json"
DIRECTIVE = (
    "OPERATOR DECISION 2026-11-17 (Chainlink issue 265 comment 646): all six "
    "accepted rooms are admitted to the catalog as STANDALONE modules "
    "(layout_eligible false, no sockets, no tested connector pairs). The slot "
    "canyon and snow garden are open-world stand-ins and stay standalone until "
    "the open-world contract (#267) lands. accept-module-metadata, "
    "decide-integration and any socket decision stay operator-only."
)

# Per room:
#   module_id = f"video_{source_id.removeprefix('video-')}_{room_id.replace('-', '_')}"
#   module = {
#     id, version=1, kind="authored_bounded_room", psx_profile_id=<accepted record>,
#     scene=f"res://source_library/sources/{source_id}/rooms/{room_id}/room.tscn",
#     variant_status="operator_accepted_standalone_room_cataloged",
#     layout_eligible=False, registration_accepted=False, scale_calibrated=False,
#     coordinate_units="uncalibrated_godot_world_units",
#     candidate_identity=<accepted record>,
#     source_provenance=[video path, frame paths, accepted record, operator review, crop manifest],
#     visual_assets=[room.tscn, room.gd, textures/*.png]  # repo-relative,
#     collision_provenance, placement_footprint_xz, visual_placement_envelope_xz,
#     collision_footprint_xz, observed_openings=[], floor_elevation_m,
#     ceiling_elevation_m, closed_unused_sockets=<standalone statement>,
#     dependencies=<accepted record, res:// converted to godot_walk/...>,
#     sockets=[], tested_connectors=[], integration_scope=<standalone statement>,
#     standalone_validation=<status + standalone_test_receipt path>,
#   }
#   decision = {
#     schema_version=1, decision="accepted_standalone_module_admission", issue=265,
#     adaptation_id, candidate_identity,
#     accepted_record_path + accepted_record_sha256,
#     visual_decision_path + visual_decision_sha256,
#     operator_directive=DIRECTIVE,
#     operator_decision={decision_record_path=<operator_review.json>,
#                        decision_sha256=<real digest>},
#     catalog_path, catalog_version="0.6.0", catalog_snapshot_path,
#     catalog_snapshot_sha256=<real digest of 0.6.0 snapshot>,
#     module_id, module_version=1, scope="standalone_only", layout_eligible=False,
#     tested_connector_pairs=[], registration_accepted=False, scale_calibrated=False,
#   }

# catalog["catalog_version"] = "0.6.0"; catalog["modules"].extend(six modules)
# write catalog.json; write snapshot as an exact byte copy of catalog.json;
# fill each decision["catalog_snapshot_sha256"] and write the six decisions.
```

The `operator_decision` citation added to each decision is not in the Bill Viola
template, but is required by `source_decision_artifacts._timestamp_of` so that
`reconcile-historical` emits a `historical_decision_reconciled` event (rather
than a deferred one) that the derive stage accepts as admission proof. It cites
only the existing frozen `operator_review.json` and its real digest; it creates
no new approval.
