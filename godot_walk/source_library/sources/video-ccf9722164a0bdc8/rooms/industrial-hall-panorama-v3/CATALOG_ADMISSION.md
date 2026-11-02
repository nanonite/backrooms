# Catalog admission — industrial hall room v1

The operator explicitly approved adding this room to the playable room library. This is a catalog admission of the existing accepted design, not a new visual revision.

- Catalog: `godot_walk/room_catalog/catalog.json`, version `0.3.0`.
- Module: `godot_gopro_industrial_hall_frame1097_v1`, version `1`.
- Candidate record: [`adaptation_catalog_v1.json`](adaptation_catalog_v1.json), candidate identity `175a52589ca162c12726583ea2e60792637d871e175947b5a601331e27ab131f`.
- Admission decision: [`catalog_admission_decision.json`](catalog_admission_decision.json), SHA-256 `d56badbff2898ebbf26dceeb6a68c17fb36c71e72e9a5de92f4beafb61748d48`.
- Prior reviewed record and decision remain preserved at [`adaptation_candidate_pre_catalog_admission.json`](adaptation_candidate_pre_catalog_admission.json) and [`operator_review.json`](operator_review.json).
- Frozen contract/catalog baseline `godot_psx_room_kit-0.2.0` remains unchanged. The new live catalog snapshot is `godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.3.0.json`.
- Live catalog SHA-256: `31bec038c5e6721976c039b72df5906975b40be8f6741bd3813634ef06d04c5a`.
- Catalog snapshot SHA-256: `31bec038c5e6721976c039b72df5906975b40be8f6741bd3813634ef06d04c5a` (byte-identical to the live catalog at admission).

The module is a standalone authored bounded room. Its `16×13` footprint and `0–4.78` vertical bounds are uncalibrated design units, not meters. Registration and scale calibration remain false. All four walls are closed; there are no authored sockets. The partial source-frame gap remains an observation, not a connector. The module is marked `layout_eligible=false`, so the seeded connector-layout generator will not place it until a separate compatible connector adaptation is authored and tested.

The 512×256 Hunyuan panorama was accepted as a broad hall/post/roof layout reference. Resolution work is deferred until the room library grows; any higher-resolution design should be a later room version and must not replace this accepted v1 record. The playable scene uses explicit geometry and separate collision, with direct source-frame crops for the floor and far window cue.

The current #149 layout-generator input snapshot, including file hashes and runtime dependencies, is preserved at `catalog_generator_snapshot_v0.3.0.json`. It records the new module as a library entry while excluding it from connector-generated layouts.

This admission does not set `registration_accepted` or `scale_calibrated`, and it makes no source-connectivity claim.

## Verify and run

From the workspace root:

```sh
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/adaptation_catalog_v1.json
godot4 --path godot_walk res://source_library/sources/video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v3/room.tscn
```
