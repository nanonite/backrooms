# Issue #171 — stage-6 bounded Godot room candidate

Source: `video-c9115d943f6c3fe4` ("Backrooms - Found Footage #55 (Hills of Synthetic Verdure).mp4").
Candidate: `wooden-verdure-hall-v1`.
Built from the accepted Hunyuan panorama **attempt-002** (event 19, `improvement: improved`,
"lets move on and go with option 1") and the operator-selected direct-source seed
**frame_3357** (16s-a set, PTS 139.973167 s). Both images were viewed before authoring.

## 1. What was built

A new, standalone, playable Godot room under
`godot_walk/source_library/sources/video-c9115d943f6c3fe4/rooms/wooden-verdure-hall-v1/`:
a finite 14 × 18 design-unit rectangle in XZ, +Y up, uncalibrated. It is a long wooden hall
with dark red carpet, horizontal plank walls, six black-framed sash windows (three per long
wall) showing green foliage, a flat slatted ceiling with nine transverse ribs, a bright far
panel, and two static wooden chairs. All four perimeter edges are closed; `sockets` is `[]`.
No doors, entities, moving or animated props. No hidden rooms or connectivity inferred.
The 512×256 panorama is used only as a camera-centered `PanoramaSkyMaterial` background
(fully occluded by the authored shell in the playable views) and as a design reference;
it is not collision geometry and no surface uses its pixels.

Files created (all new):
`adaptation_candidate.json`, `crop_plan.json`, `room.gd` (+`.uid`), `room.tscn`,
`test_room.gd` (+`.uid`), `capture_room.gd` (+`.uid`), `run_capture_guarded.py`,
`standalone_test_receipt.json`, `capture_resource_run.json`,
`textures/{carpet_floor,wood_wall,sash_window,ceiling_slats,chair_reference}.png`,
`textures/crop_manifest.json`, `captures/{spawn_toward_far_wall,window_wall,slat_ceiling,chairs_corner}.png`,
`captures/capture_manifest.json`.

Followed the proven pattern from
`video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v1/` and
`godot_walk/evidence/2026-11-01-issue-168-room-candidate/COMMANDS.md`. No format was invented.

### Contract freeze used

**`godot_walk/room_catalog/contract_freeze_v3.json`**, sha256
`91c0cb1b47f980193a47d8e221b366f2d452256fa7b383adc818a177c9813ba1`.
`contract_freeze_v4.json` exists, but
`video_adaptation_validation._verify_frozen_contract_reference()` maps a v3 record
(`schema_version: 3`) to `V3_FREEZE` only; v4 is used by `verify_versioned_freezes()`
for lineage and tool pinning, not as an authorable record target. v3 is therefore the
newest freeze the validators accept. Catalog snapshot:
`godot_psx_room_kit-0.2.0.json` (`8feb31a…80d`) taken from the freeze, not the live catalog.

### Surface provenance (source crops vs project materials)

All close surfaces are **direct rectangular crops of the 1280×720 seed frame**, extracted
through the existing `video_adaptation_runner.py extract-source-crops` stage (no resize,
no color edit; see `textures/crop_manifest.json`). No surface was taken from panorama pixels.
Frames/mullions, ceiling ribs and the far panel use local solid-color `StandardMaterial3D`
values authored in `room.gd` (matching the existing PSX palette); no shared material file
was edited. The project PSX profile `library-psx-ursc-1.5-native-compositor` and the existing
player controller were reused unchanged.

## 2. Provenance table

| Feature | Observed (source/panorama) | Authored (this candidate) | Unknown / not claimed |
|---|---|---|---|
| Long rectangular hall | Panorama: long axis, windows on both sides; seed: one plank-wall corner | 14×18 rectangle footprint, closed four sides | Real dimensions, full source perimeter; not claimed to be the whole room |
| Wall-to-wall dark red carpet | Both images | Flat floor at Y=0, `carpet_floor` crop tiled 5×6 | Carpile fibre/wear, metric area |
| Horizontal wood plank walls | Seed frame (clear); panorama (vertical-ish slats) | Four solid wall boxes with `wood_wall` crop | Whether source walls are planks or vertical slats; panorama is low-res |
| Sash windows with green outside | Seed: two white sash windows; panorama: black-framed windows both sides | Six window panels (3/side) with frames and mullions, `sash_window` crop | Window count/rhythm beyond the visible views; exterior geometry; no openings in collision |
| Slatted wood ceiling | Panorama: strongly arched radial slats; seed: planks | Flat ceiling + 9 ribs, `ceiling_slats` crop; clear height 4.42 | The source arch is **not reproduced** (see §5); true ceiling height |
| Bright rectangle on far wall | Panorama and seed show a light patch/rectangle | Neutral light panel, 1.4×1.9, visual only | Not a door, socket, destination or connection |
| Two wooden chairs | Seed: two straight-back chairs in the corner | Two static chair props with separate obstacle colliders | Exact placement, construction, function |
| VHS dropout lines / vignetting | Seed frame | Retained in the ceiling crop; not authored as decoration | Not treated as room features |
| Panorama background | Accepted 512×256 panorama | Renderer sky only, no parallax | Not geometry, not collision, not a metric map |

Provenance flags: `registration_accepted=false`, `scale_calibrated=false`,
`operator_decision.status=pending`, `catalog_admission=candidate_not_admitted`.

## 3. Mechanical checks (exact output lines)

Status (`source_ingestion_runner.py status video-c9115d943f6c3fe4`), key lines:
```
"source_decision": "proceed",
"selected_seed": { ... "frame_id": "frame_3357", ... "timestamp_seconds": 139.97316666666666 },
"attempts_used": 2,
"can_start_attempt": true,
"next_worker_actions": ["run_source_hunyuan.py"]
```
No Hunyuan, feedback, seed change, panorama attempt, manual fallback or paid/model call was
run in this stage despite `can_start_attempt`.

Bundle validation (`python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle …/adaptation_candidate.json`):
```
  "status": "valid",
  "adaptation_id": "wooden-verdure-hall-v1",
  "candidate_fingerprint": "3262fc81646c8433f8743fd324dbdc16c3be7db03c136db5d3e52d5c4e794e4a",
  "candidate_identity": "3262fc81646c8433f8743fd324dbdc16c3be7db03c136db5d3e52d5c4e794e4a",
  "static_consistency": "passed",
  "runtime_evidence": { "status": "historical fingerprinted records verified; runtime not rerun" },
  "validation_is_read_only": true
```
48 hash-bound dependencies; record sha256 `abbde98db72397e36585b030592717abb95920a19233ae378384042f43725e63`.

Godot headless room test (`godot4 --headless --path godot_walk --script res://…/test_room.gd`):
```
Godot Engine v4.6.3.stable.official.7d41c59c4 - https://godotengine.org

Wooden verdure hall candidate reset to safe spawn
WOODEN_VERDURE_HALL_TESTS_PASSED
```
Checks: spawn floor support, floor ray, closed north boundary, chair obstacle collision,
walk-and-backtrack, no boundary escape, missing-floor negative control, open-boundary
negative control, R reset to `[0, 0.6, 6.6]`.

Full script suite: `python3 -m pytest -q godot_walk/scripts`
```
1530 passed, 5 skipped, 67 subtests passed in 269.72s (0:04:29)
```
Source registry: `python3 godot_walk/scripts/register_video_sources.py validate`
```
{
  "valid": true,
  "registered_count": 13
}
```
Python lint on the new guard wrapper: `python3 -m ruff check …/run_capture_guarded.py`
-> `All checks passed!`. `black --check` reports it would reformat; the byte-equivalent
template wrapper reports the same, so this matches the proven pattern rather than a new regression.

## 4. Captures

Rendered with the guarded script
`python3 …/run_capture_guarded.py --output-dir …/captures --report …/capture_resource_run.json -- godot4 --path godot_walk --script …/capture_room.gd -- --out=res://…/captures`.
Receipt: `return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=5.207`;
preflight and peak-resource samples are in `capture_resource_run.json`, frame profile in
`captures/capture_manifest.json` (mean 8.68 ms, p95 16.71 ms, p99 83.57 ms over 300 samples;
includes display sync). All four 1152×648 PNGs were viewed:

- `captures/spawn_toward_far_wall.png`
- `captures/window_wall.png`
- `captures/slat_ceiling.png`
- `captures/chairs_corner.png`

The capture emitted a non-fatal `ERROR: NO GRAB` from the shared `player.gd` mouse-lock call
under the offscreen X11 session; the capture harness continued and wrote all views.

## 5. Honest comparison with panorama and seed

**Matches.** Red wall-to-wall carpet; warm wood-plank walls; black-framed sash windows with
bright green exterior in the same palette; two straight-back chairs near a corner; a long
hall with windows on both sides; a small bright patch on the far wall. The PSX treatment and
low-resolution source crops give a similar coarse, grainy character.

**Invented / approximated.** The 14×18 dimensions, the exact three-window-per-side rhythm,
the flat slat ceiling with nine ribs, the chair positions and the far light panel's size are
authored, not measured. The panorama's **strongly arched radial ceiling is not reproduced** —
the candidate uses a flat slatted plane instead; this is the largest visual mismatch. The
panorama itself is essentially invisible in the playable views because the authored shell
occludes the sky, so it functions only as a design reference. No model-inferred geometry is
used as collision or surface data.

**Wrong / questionable.** The ceiling crop retains the source's VHS dropout lines as bright
dashes on the ceiling (visible in `slat_ceiling.png`); they are faithful to the seed but read
as rendering artifacts. The wall crop's dark lower band makes parts of the walls look shadowed
in ways the panorama does not. The green outside each window is a flat crop, not a view of an
exterior; the chairs are simple boxes rather than faithful chair geometry. The capture frame
profile has a high p99 (83.57 ms) from display-sync/outlier frames, not a measured gameplay FPS.

A passing validator and clean captures are **not approval**. This candidate remains
`candidate_pending_review` for operator review; it has not been accepted or admitted.

## 6. Ledger and scope compliance

No existing `source_ingestion_runner.py` stage records a room-candidate authoring event, so
none was used and no event was written by hand: `events.jsonl` is unchanged at 19 lines, last
event `hunyuan_operator_feedback`. No `select-seed`, `select-winner`, operator decision,
catalog edit, snapshot, `register_source_room.py`, module metadata, or hash-pinned file was
touched. Only new files under the source's `rooms/` folder and this evidence report were
created.
