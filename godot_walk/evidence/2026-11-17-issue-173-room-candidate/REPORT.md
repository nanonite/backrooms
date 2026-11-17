# Issue #173 — stage-6 bounded Godot room candidate

Source: `video-d857abe7a94da9d1` ("Max Cooper - Repetition (Official Video By Kevin McGloughlin).mp4", 1280×720, 24 fps, 8,556 frames, 356.566 s).
Candidate: `nested-light-corridor-v1`.
Built from the accepted Hunyuan panorama **attempt-001** (event 11, `hunyuan_operator_feedback`,
`improvement: improved`, "all look good other than the dead end"; no further attempt wanted) and the
operator-selected direct-source seed **frame_6721** (issue173-10s-c set, 280.0 s). Both images were
viewed before authoring anything. The panorama shows nested glowing white rectangular frames
receding toward a small overexposed white square in darkness; the seed shows a glossy black corridor
with tall vertical white panels, a mirror-black floor with white transverse strips and an
overexposed far wall.

## 1. What was built

A new, standalone, playable Godot room under
`godot_walk/source_library/sources/video-d857abe7a94da9d1/rooms/nested-light-corridor-v1/`:
a finite 10 × 24 design-unit rectangle in XZ, +Y up, uncalibrated. It is a bounded interior
corridor stand-in: dark glossy walls with ten repeated vertical white light panels, a reflective
dark floor with white transverse strips, a dark strip ceiling, five repeated bright portal outlines
that echo the panorama's nested rings, and a bright overexposed far wall. All four perimeter edges
are closed and collidable; `sockets` is `[]`. Two static panel-plinth props have separate obstacle
colliders. No doors, entities, moving or animated props. No hidden rooms or connectivity inferred.

The 512×256 panorama is used only as a camera-centered `PanoramaSkyMaterial` background (fully
occluded by the authored shell in playable views) and as a design reference; it is not collision
geometry and no surface uses its pixels.

Files created (all new): `adaptation_candidate.json`, `crop_plan.json`, `room.gd` (+`.uid`),
`room.tscn`, `test_room.gd` (+`.uid`), `capture_room.gd` (+`.uid`), `run_capture_guarded.py`,
`standalone_test_receipt.json`, `capture_resource_run.json`,
`textures/{reflective_floor,gloss_wall,light_panel,ceiling_strips,far_light}.png`,
`textures/crop_manifest.json`,
`captures/{spawn_toward_far_light,nested_portal_frames,lit_wall_panels,far_light_wall}.png`,
`captures/capture_manifest.json`.

Followed the proven pattern from
`video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v1/` and the built #171 candidate
`video-c9115d943f6c3fe4/rooms/wooden-verdure-hall-v1/`. No format was invented.

### Contract freeze used

**`godot_walk/room_catalog/contract_freeze_v3.json`**, sha256
`91c0cb1b47f980193a47d8e221b366f2d452256fa7b383adc818a177c9813ba1` — the newest freeze the
validators accept for an authorable v3 record (v4 is used by `verify_versioned_freezes()` for
lineage/tool pinning, not as a record target). Catalog snapshot
`godot_psx_room_kit-0.2.0.json` (`8feb31a3…80d`) was taken from the freeze, not the live catalog.

### Surface provenance (source crops vs project materials)

All close surfaces are **direct rectangular crops of the 1280×720 seed frame**, extracted through
the existing `video_adaptation_runner.py extract-source-crops` stage (no resize, no color edit; see
`textures/crop_manifest.json`): `reflective_floor`, `gloss_wall`, `light_panel`, `ceiling_strips`,
`far_light`. No surface was taken from panorama pixels. The bright portal trim, dark frame and far
wall border use local solid-colour `StandardMaterial3D` values authored in `room.gd` (PSX palette);
no shared material file was edited. The project PSX profile
`library-psx-ursc-1.5-native-compositor` and the existing player controller were reused unchanged.

## 2. Provenance table

| Feature | Observed (source/panorama) | Authored (this candidate) | Unknown / not claimed |
|---|---|---|---|
| Long dark corridor | Panorama: nested rings along a central axis; seed: one symmetrical interior | 10 × 24 rectangle footprint, closed four sides | Real dimensions, full source perimeter; not claimed to be the whole space |
| Reflective floor with bright transverse strips | Seed: clear; panorama: dark base | Flat floor at Y=0, `reflective_floor` crop tiled 2×6 plus five solid bright strip boxes | Strip rhythm/spacing; metric area |
| Glossy dark walls with tall white panels | Seed: clear on both sides; panorama: dark walls | Four solid wall boxes with `gloss_wall` crop and ten `light_panel` boxes (5/side) | Panel count, height and spacing beyond the visible view |
| Nested glowing rectangular frames | Panorama: many thin irregular white rectangles receding inward | Five thick bright portal outlines (two jambs + header each), solid PSX colour, visual only | Exact frame count/geometry; no claim that the source has constructed frames |
| Dark ceiling with strip lights | Seed: dark with strips; panorama: dark | Flat ceiling with `ceiling_strips` crop plus five solid bright strips; clear height 4.56 | True ceiling height/shape; the source may not be flat-ceilinged |
| Overexposed bright far wall | Both images; operator flagged it as "the dead end" | Bright panel with dark border on the closed north boundary, `far_light` crop | Not a door, socket, destination or connection; no hidden room inferred |
| Two low panel plinths | Not clearly resolved in either image | Two static low boxes with obstacle colliders | Their source existence/function is unknown; authored for traversal coverage |
| Panorama background | Accepted 512×256 panorama | Renderer sky only, no parallax | Not geometry, not collision, not a metric map |
| Repetition/rhythm value for the generative map | Source is repetition-driven (issue text) | Not modelled here | Left to a separate operator decision; no rule is derived or claimed |

Provenance flags: `registration_accepted=false`, `scale_calibrated=false`,
`operator_decision.status=pending`, `catalog_admission=candidate_not_admitted`.

## 3. Mechanical checks (exact output lines)

Status (`python3 godot_walk/scripts/source_ingestion_runner.py status video-d857abe7a94da9d1`):
```
"source_decision": "proceed",
"selected_seed": { ... "frame_id": "frame_6721", ... "timestamp_seconds": 280.0, ... },
"attempts_used": 1,
"attempt_limit": 3,
"can_start_attempt": true,
"next_worker_actions": ["run_source_hunyuan.py"]
```
`can_start_attempt` was deliberately **not** used: no Hunyuan, feedback, seed change, panorama
attempt, manual fallback or paid/model call was run in this stage.

Bundle validation (`python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle …/adaptation_candidate.json`):
```
  "status": "valid",
  "adaptation_id": "nested-light-corridor-v1",
  "candidate_fingerprint": "968536959a6bf9247c82e618e251c66102853a707fc92d9ef4d5ca5f992fa5e7",
  "candidate_identity": "968536959a6bf9247c82e618e251c66102853a707fc92d9ef4d5ca5f992fa5e7",
  "static_consistency": "passed",
  "runtime_evidence": { "status": "historical fingerprinted records verified; runtime not rerun" },
  "validation_is_read_only": true
```
48 hash-bound dependencies; record sha256
`380fc7fcf7fb6f8bf869fb2726161043937a5359c4b90b0f78cfb4dbd466eeea`.

Godot headless room test (`godot4 --headless --path godot_walk --script res://…/test_room.gd`):
```
Godot Engine v4.6.3.stable.official.7d41c59c4 - https://godotengine.org

Nested light corridor candidate reset to safe spawn
NESTED_LIGHT_CORRIDOR_TESTS_PASSED
```
Checks: spawn floor support, floor ray, closed north boundary ray, plinth obstacle ray,
walk-and-backtrack, no boundary escape, missing-floor negative control, open-boundary negative
control, R reset to `[0, 0.6, 10.0]`.

Full script suite (`python3 -m pytest -q godot_walk/scripts`):
```
1530 passed, 5 skipped, 67 subtests passed in 268.01s (0:04:28)
```
Source registry (`python3 godot_walk/scripts/register_video_sources.py validate`):
```
{
  "valid": true,
  "registered_count": 13
}
```
Python lint (`python3 -m ruff check …/run_capture_guarded.py`): `All checks passed!`.

## 4. Captures

Rendered with the guarded script
`python3 …/run_capture_guarded.py --output-dir …/captures --report …/capture_resource_run.json -- godot4 --path godot_walk --script …/capture_room.gd -- --out=res://…/captures`.
Receipt: `return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=9.545`;
preflight and peak-resource samples are in `capture_resource_run.json`; frame profile in
`captures/capture_manifest.json` (mean 16.67 ms, p95 16.77 ms, p99 16.88 ms over 300 samples;
includes display sync). All four 1152×648 PNGs were viewed:

- `captures/spawn_toward_far_light.png` — spawn view with nested bright portals receding to the far panel
- `captures/nested_portal_frames.png` — the repeated portal outlines down the corridor
- `captures/lit_wall_panels.png` — vertical white panels on the glossy west wall and ceiling strips
- `captures/far_light_wall.png` — the closed overexposed far wall up close

The capture emitted the same non-fatal `ERROR: NO GRAB` from the shared `player.gd` mouse-lock call
under the offscreen X11 session seen in the #171 capture; the harness continued and wrote all views.

## 5. Honest comparison with panorama and seed

**Matches.** The spawn view reproduces the panorama's strongest reading: a sequence of bright
rectangular outlines nested down a dark axis, converging on a bright square. The seed's glossy
black wall sections with tall vertical white panels, the dark reflective floor cut by white
transverse strips, the ceiling strip lights and the overexposed far wall are all present and in the
same coarse palette. The PSX treatment and low-resolution source crops give a similar grainy,
low-detail character.

**Invented / approximated.** The 10×24 dimensions, five portal frames, ten wall panels, five
floor strips, two plinths, the dark border around the far panel and the flat rectangular shell are
authored, not measured. Portal outlines are built as thick bright bars rather than the panorama's
thin irregular glowing lines. The far bright wall is deliberately kept closed because both images
show a terminus and the operator called out "the dead end"; no continuation, doorway, socket or
hidden room is claimed.

**Wrong / questionable.** The ceiling in the captures reads much brighter and creamier than the
seed's dark ceiling: the `ceiling_strips` crop contains an overexposed region near the far end and
its tiling spreads that brightness down the corridor. The portal bars are more regular and heavier
than the panorama's uneven rings. The far panel is a flat uniform rectangle, not a photographic
bloom. The panorama itself is effectively invisible in playable views because the authored shell
occludes the sky, so it functions only as a design reference. The `NO GRAB` console error is a
capture-environment artefact, not a room feature. The frame profile is display-sync-bound, not a
measured gameplay FPS.

A passing validator and clean captures are **not approval**. This candidate remains
`candidate_pending_review` for operator review; it has not been accepted or admitted.

## 6. Ledger and scope compliance

No existing `source_ingestion_runner.py` stage records a room-candidate authoring event, so none was
used and no event or source-ledger receipt was written by hand: `events.jsonl` is unchanged at 11
lines, last event `hunyuan_operator_feedback`. No `select-seed`, Hunyuan, feedback, paid/model call,
operator decision, `register_source_room.py`, catalog edit, catalog snapshot, module metadata or
hash-pinned file (`scripts/player.gd`, `project.godot`, library room scenes, `catalog.json`,
`MATERIAL_LANGUAGE.md`, `PALETTES.md`) was touched. `registration_accepted=false` and
`scale_calibrated=false` are unchanged. Two unrelated pre-existing untracked evidence paths were
left untouched.
