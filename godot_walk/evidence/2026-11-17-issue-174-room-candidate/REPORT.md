# Issue #174 — stage-6 bounded Godot room candidate

Source: `video-d92fc1fa764aa3a2` ("Angel (Joseph Cornell, 1957).mp4"; 636×480,
29.97003 fps, 6,782 frames, 226.348 s).
Candidate: `snow-garden-courtyard-v1`.
Built from the accepted Hunyuan panorama **attempt-001-retry-001**
(event 14 `hunyuan_operator_feedback`, `improvement: improved`, "all look good other
than the dead end") and the operator-selected direct-source seed **frame_4347**
(145.011533 s, 636×480 native decode, no resize/edit). Both images were viewed
before any authoring:

- panorama: `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/hunyuan/attempt-001-retry-001/panorama/panorama.png` (sha256 `f9c95477644ed77038775ec23a99c3573db78c0d06e991ace76796b5a57b283b`)
- seed: `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/frames/issue174-5s-c/frame_4347.png` (sha256 `ae59a84fb9aa07612b5b100c2ee5b5ab5645836dd5bccc665b862acd51ab500f`)

The panorama shows a blue-tinted snow-covered park/cemetery: a flat snow field,
many leafless trees, a dark tree line, a low stone bench near center and blue sky.
The seed frame shows a blue-stone angel statue in profile against pale sky and
dense leafless branches. No room, doorway, opening or connectivity is visible in
either image.

## 1. What was built

A new, standalone, playable Godot room under
`godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v1/`:
a bounded **20 × 16 design-unit rectangle in XZ, +Y up, uncalibrated**, standing in
for the unbounded outdoor park. It has a flat pale-blue-white snow floor at Y=0,
a closed low dark-green perimeter wall (Y=2.4), eight static leafless trees
(trunks to Y=6.2 with thin branch-cross panels), one low central stone bench, and
the accepted 512×256 panorama as a camera-centered `PanoramaSkyMaterial` visible
above the walls and through the open top. All four perimeter edges are closed and
collidable; `sockets` is `[]`. No doors, entities, moving or animated props, no
hidden rooms and no inferred connectivity. The panorama is **visual only**: it is
not collision geometry and none of its pixels are used as a surface.

Files created (all new, under the room folder): `adaptation_candidate.json`,
`crop_plan.json`, `room.gd`, `room.tscn`, `test_room.gd`, `capture_room.gd`,
`run_capture_guarded.py`, `standalone_test_receipt.json`, `capture_resource_run.json`,
`textures/{stone_figure,branch_canopy}.png`, `textures/crop_manifest.json`,
`captures/{spawn_toward_bench,tree_line,stone_bench,open_winter_sky}.png`,
`captures/capture_manifest.json`.

Followed the proven panorama-to-room pattern without inventing a format:
`video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v1/`,
`video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/` (outdoor courtyard
stand-in), the #171 candidate/report, and
`godot_walk/evidence/2026-11-01-issue-168-room-candidate/COMMANDS.md`.

### Contract freeze and material provenance

Contract freeze: `godot_walk/room_catalog/contract_freeze_v3.json`, sha256
`91c0cb1b47f980193a47d8e221b366f2d452256fa7b383adc818a177c9813ba1` — the newest
freeze the validators accept (`_verify_frozen_contract_reference()` maps a v3
record to `V3_FREEZE`; v4 is for lineage/tool pinning only). Catalog snapshot:
`godot_psx_room_kit-0.2.0.json` (`8feb31a…80d`).

Two surface textures are **direct rectangular crops of the 636×480 seed frame**,
extracted with the existing `video_adaptation_runner.py extract-source-crops`
stage (no resize, no color edit; see `textures/crop_manifest.json`):
`stone_figure` `[190,200,430,480]` and `branch_canopy` `[60,20,380,200]`.
The snow floor, hedge walls and trunks use **local solid-color PSX
`StandardMaterial3D` values authored in `room.gd`** (matching the project palette),
because the seed frame contains no snow or hedge surface. No panorama pixel was
used for any surface, and no shared material file was edited. The project PSX
profile `library-psx-ursc-1.5-native-compositor` and the existing player controller
were reused unchanged.

## 2. Provenance table

| Feature | Observed (source / panorama) | Authored (this candidate) | Unknown / not claimed |
|---|---|---|---|
| Snow-covered open park | Panorama: flat snow field, leafless trees, tree line, low stone bench, blue sky; seed: angel statue + branches only | Bounded 20×16 courtyard stand-in; snow floor at Y=0 | Real dimensions, park extent, camera pose, metric scale; not claimed to be a real room |
| Snow ground | Panorama only (panorama pixels excluded from surfaces) | Flat pale-blue-white solid-color PSX floor crop-free | Snow depth/texture; seed frame shows no snow |
| Leafless trees | Panorama: many bare trees; seed: dense bare branches | Eight static trunk boxes + two thin branch-cross panels each; `branch_canopy` crop on panels, dark solid trunk | Tree count/positions/species/height are authored, not measured |
| Dark tree line | Panorama: dark middle-distance line | Four low closed perimeter wall boxes at Y=2.4, dark green solid material | The panorama shows no wall; this ring is an authored bound, not an observed wall |
| Central stone bench | Panorama: low bench near center | Three static boxes (plinth/seat/back) with direct `stone_figure` crop | Exact size/placement; the crop is the statue, not a faithful bench texture |
| Blue winter sky | Panorama and seed | 512×256 panorama as camera-centered sky, visible above walls | No parallax; not geometry, not collision, not a metric map |
| Static props only | No doors/openings/entities visible | No sockets, all four edges capped, standalone | No connectivity, destinations or hidden rooms inferred |

Provenance flags: `registration_accepted=false`, `scale_calibrated=false`,
`operator_decision.status=pending`, `catalog_admission=candidate_not_admitted`,
`status=candidate_pending_review`.

## 3. Mechanical checks (exact output lines)

`python3 godot_walk/scripts/source_ingestion_runner.py status video-d92fc1fa764aa3a2`
(key lines):
```
"source_decision": "proceed",
"selected_seed": { ... "frame_id": "frame_4347", "timestamp_seconds": 145.01153333333335 },
"attempts_used": 1,
"next_worker_actions": ["run_source_hunyuan.py"]
```
No Hunyuan, feedback, seed change, further panorama attempt, manual fallback or
paid/model call was run despite `can_start_attempt`.

Crop extraction
`python3 godot_walk/scripts/video_adaptation_runner.py extract-source-crops …`:
```
godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v1/textures/crop_manifest.json
```

Bundle validation
`python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle …/adaptation_candidate.json`:
```
  "status": "valid",
  "adaptation_id": "snow-garden-courtyard-v1",
  "candidate_fingerprint": "5f47bc69ab77404d889237e7166084c51ee9e4154a598ef9ab2f014bea72874d",
  "candidate_identity": "5f47bc69ab77404d889237e7166084c51ee9e4154a598ef9ab2f014bea72874d",
  "static_consistency": "passed",
  "runtime_evidence": { "status": "historical fingerprinted records verified; runtime not rerun" },
  "validation_is_read_only": true
```
45 hash-bound dependencies; record sha256 bound through `candidate_identity`.

Godot headless room test
`godot4 --headless --path godot_walk --script res://…/test_room.gd`:
```
Godot Engine v4.6.3.stable.official.7d41c59c4 - https://godotengine.org

Snow garden courtyard candidate reset to safe spawn
SNOW_GARDEN_TESTS_PASSED
```
Checks: snow-floor support, floor ray, closed north boundary, tree-obstacle ray,
walk-and-backtrack, no boundary escape, missing-floor negative control,
open-boundary negative control, and R reset to `[0, 0.6, 6.0]`.

Full script suite `python3 -m pytest -q godot_walk/scripts`:
```
1530 passed, 5 skipped, 67 subtests passed in 269.20s (0:04:29)
```

Source registry `python3 godot_walk/scripts/register_video_sources.py validate`:
```
{
  "valid": true,
  "registered_count": 13
}
```

Ruff on the new guard wrapper
`python3 -m ruff check …/run_capture_guarded.py`:
```
All checks passed!
```

## 4. Captures

Rendered with the guarded script
`python3 …/run_capture_guarded.py --output-dir …/captures --report …/capture_resource_run.json -- godot4 --path godot_walk --script …/capture_room.gd -- --out=res://…/captures`.
Receipt: `return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=9.7`;
preflight and peak-resource samples are in `capture_resource_run.json`. Frame
profile in `captures/capture_manifest.json`: mean 16.67 ms, p95 16.75 ms,
p99 16.88 ms over 300 samples (includes display sync, not a measured gameplay FPS).
All four 1152×648 PNGs were viewed:

- `captures/spawn_toward_bench.png`
- `captures/tree_line.png`
- `captures/stone_bench.png`
- `captures/open_winter_sky.png`

The capture emitted the same non-fatal `ERROR: NO GRAB` from shared `player.gd`
mouse-lock under the offscreen X11 session seen in #171; the harness continued and
wrote all four views.

## 5. Honest comparison with panorama and seed

**Matches.** The panorama sky reads clearly above the low walls and through the
open top: blue winter sky with dense leafless branches, matching the panorama's
dominant blue/bare-tree character. The flat pale snow floor matches the snow field.
The dark perimeter read as a stand-in for the panorama's dark middle-distance tree
line. A low central stone mass echoes the panorama's stone bench. The PSX
nearest-filter treatment gives the same coarse, low-resolution grain.

**Invented / approximated.** The 20×16 rectangle, four low walls, eight-tree grid,
tree heights, bench shape and placement, and the snow/hedge colours are all
authored, not measured. The panorama is an unbounded outdoor park; this candidate
is deliberately a **bounded interior/courtyard stand-in**, not a claim the video
contains a room. The seed frame itself shows only a statue and branches — the
park character comes from the panorama, so the two surface crops are statue and
branches rather than snow or stone-bench pixels.

**Wrong / questionable.** The `branch_canopy` crop on the thin tree panels reads as
floating dark rectangular billboards rather than natural branch canopies (most
obvious in `open_winter_sky.png` and `tree_line.png`) — the largest visual mismatch.
The `stone_figure` crop stretched over the bench boxes reads as a blurry dark-blue
horizontal slab, not a recognisable statue or bench. The low hedge walls have no
counterpart in the panorama; they exist only to bound traversal. The panorama's
actual bench and dense tree line are not reproduced faithfully in position or
shape. The panorama is essentially a background only, so the playable geometry
carries the scene, not the accepted image.

A passing validator and clean captures are **not approval**. This candidate remains
`candidate_pending_review` for operator review; it has not been accepted or
admitted to any catalog.

## 6. Ledger and scope compliance

No existing `source_ingestion_runner.py` stage records room-candidate authoring, so
none was used and no event or receipt was written by hand:
`godot_walk/source_library/sources/video-d92fc1fa764aa3a2/events.jsonl` is unchanged
(14 lines, last event `hunyuan_operator_feedback`). No `select-seed`, winner,
operator decision, catalog admission, `catalog.json` or snapshot edit,
`register_source_room.py`, module metadata or hash-pinned file was touched. Both
calibration flags remain false. Only new files under the source's `rooms/` folder
and this evidence report were created.
