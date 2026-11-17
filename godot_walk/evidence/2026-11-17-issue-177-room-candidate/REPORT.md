# Issue #177 — stage-6 bounded Godot room candidate

Source: `video-61b91dbeb9026dc7` (`data/videos/corridor_x.mp4`, 1920×1080, 24 fps, 96 frames, 4.0 s).
Candidate: `chevron-cross-corridor-v1`.
Built from the operator-accepted 512×256 Hunyuan panorama **attempt-001**
(event 9 `hunyuan_operator_feedback`, `improvement: improved`, "all look good other than the
dead end", no further attempt wanted) and the operator-selected direct-source seed
**frame_0085** (extraction run `issue177-quarter-s-a`, decoded index 84, PTS 3.5 s). Both
images were viewed before authoring anything.

## 1. What was built

A new, standalone, playable Godot room under
`godot_walk/source_library/sources/video-61b91dbeb9026dc7/rooms/chevron-cross-corridor-v1/`:
a finite 16 × 20 design-unit rectangle in XZ, +Y up, uncalibrated. It is a bounded interior
corridor stand-in with a tan/yellow swirl-pattern carpet, yellow-green chevron wallpaper on
the closed perimeter and four staggered freestanding wall sections, white baseboards, a cream
drop ceiling with a square grid, ribs and four fluorescent panels, and a small bright panel on
the far wall. All four perimeter edges are closed; `sockets` is `[]`. No doors, entities,
hidden rooms, moving or animated props. The filename's "cross junction" hint is **unverified**
and **no branching topology or connectivity is authored**.

The 512×256 panorama is used only as a camera-centred `PanoramaSkyMaterial` background
(fully occluded by the authored shell in the playable views) and as a design reference; it is
not collision geometry and **no surface uses its pixels**.

Files created (all new):
`adaptation_candidate.json`, `crop_plan.json`, `room.gd` (+`.uid`), `room.tscn`,
`test_room.gd` (+`.uid`), `capture_room.gd` (+`.uid`), `run_capture_guarded.py`,
`standalone_test_receipt.json`, `capture_resource_run.json`,
`textures/{carpet_floor,chevron_wall,ceiling_grid}.png`, `textures/crop_manifest.json`,
`captures/{spawn_toward_partitions,wallpaper_partition,drop_ceiling,far_light_panel}.png`,
`captures/capture_manifest.json`.

Followed the proven pattern from
`video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v1/`,
`video-c9115d943f6c3fe4/rooms/wooden-verdure-hall-v1/`, the near-identical sibling
`video-2671b32f256a4ee7/rooms/chevron-corridor-v1/` and
`godot_walk/evidence/2026-11-01-issue-168-room-candidate/COMMANDS.md`. No format was invented.
Surface crops came from the existing `video_adaptation_runner.py extract-source-crops` stage;
the candidate record's 46 dependency hashes and its identity were recomputed from disk with the
project's own `candidate_identity_v2`.

### Contract freeze used

**`godot_walk/room_catalog/contract_freeze_v3.json`**, sha256
`91c0cb1b47f980193a47d8e221b366f2d452256fa7b383adc818a177c9813ba1`. As in #171/#176, `v3` is
the newest freeze the validators accept for an authorable record
(`_verify_frozen_contract_reference()` maps a `schema_version: 3` record to `V3_FREEZE` only).
Catalog snapshot: `godot_psx_room_kit-0.2.0.json`
(`8feb31a3a8fe82924f4eaf6086e5f6e56c4643b2cffc1239a55a65ff98f3b80d`), taken from the freeze.

### Surface provenance (source crops vs project materials)

All close surfaces are **direct rectangular crops of the 1920×1080 seed frame_0085**, extracted
through the existing `video_adaptation_runner.py extract-source-crops` stage (no resize, no
color edit; see `textures/crop_manifest.json`). No surface was taken from panorama pixels.

| Crop | Seed-frame pixel bounds | SHA-256 | Used for |
|---|---|---|---|
| `carpet_floor` | `[400, 860, 1400, 1060]` | `ed53f52c…111` | walkable floor |
| `chevron_wall` | `[1000, 180, 1500, 760]` | `ea723278…fb6` | perimeter walls + partitions (outlets avoided) |
| `ceiling_grid` | `[120, 0, 820, 210]` | `a03a69cc…5b6` | drop-ceiling plane |

Trim, baseboards, fluorescent panels, grid ribs and the far light panel use local solid-colour
`StandardMaterial3D` values in the existing PSX palette authored in `room.gd`; **no shared
material file was edited**. The project PSX profile
`library-psx-ursc-1.5-native-compositor` and the existing player controller were reused
unchanged.

## 2. Provenance table

| Feature | Observed (source/panorama) | Authored (this candidate) | Unknown / not claimed |
|---|---|---|---|
| Corridor with wall sections | Seed: move past freestanding chevron-wallpapered sections; panorama: patterned partitions both sides | 16×20 rectangle, closed four sides, four staggered thin partitions, clear central lane | Real dimensions, full source perimeter, whether partitions continue |
| "Cross junction" filename hint | Unverified filename only; panorama ends in a dead end | No branching topology authored; `sockets: []` | No connectivity inferred from the video |
| Tan/yellow swirl carpet | Both images, wall-to-wall | Flat floor at Y=0, `carpet_floor` crop tiled 5×6 | Fibre/wear, metric area |
| Yellow-green chevron wallpaper | Both images (panorama low-res) | Four wall boxes + four partition boxes with `chevron_wall` crop | Exact pattern scale, hidden wall faces; source walls look slightly curved, authored ones are flat |
| Cream drop ceiling + grid + bright panels | Seed: grid and fluorescent panels; panorama: gridded ceiling | Flat ceiling plane at clear height 4.2, 10+8 ribs, 4 light panels, `ceiling_grid` crop | True ceiling height, source panel rhythm |
| White baseboards | Seed: white strips under partitions | Thin solid-colour boxes on partitions | Exact profile/height |
| Plain cream pillars / foreground wall | Seed: cream pillar at left, cream wall patches | Not reproduced as separate surfaces; perimeter uses the wallpaper crop everywhere | Which wall they belong to; this is a known mismatch |
| Small bright far rectangle | Both images | Neutral far light panel, 1.6×2.0, visual only | Not a door, socket, destination or connection |
| Panorama background | Accepted 512×256 panorama | Renderer sky only, no parallax | Not geometry, collision or a metric map |

Provenance flags: `registration_accepted=false`, `scale_calibrated=false`,
`operator_decision.status=pending`, `catalog_admission=candidate_not_admitted`.

## 3. Mechanical checks (exact output lines)

Status (`python3 godot_walk/scripts/source_ingestion_runner.py status video-61b91dbeb9026dc7`),
key lines:
```
"source_decision": "proceed",
"selected_seed": { ... "frame_id": "frame_0085", ... "timestamp_seconds": 3.5, ... },
"attempts_used": 1,
"can_start_attempt": true,
"next_worker_actions": ["run_source_hunyuan.py"]
```
No Hunyuan, feedback, seed change, panorama attempt, manual fallback or paid/model call was run
in this stage despite `can_start_attempt`; the operator accepted the existing panorama and
wanted no further attempt.

Bundle validation (`python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle …/adaptation_candidate.json`):
```
{
  "status": "valid",
  "adaptation_id": "chevron-cross-corridor-v1",
  "candidate_fingerprint": "c7bae06b6f7cb3ca19a834aeefb4b427c51adba754943a4e5aa94c25432cba94",
  "candidate_identity": "c7bae06b6f7cb3ca19a834aeefb4b427c51adba754943a4e5aa94c25432cba94",
  "static_consistency": "passed",
  "runtime_evidence": { "status": "historical fingerprinted records verified; runtime not rerun" },
  "validation_is_read_only": true
}
```
46 hash-bound dependencies; record sha256
`89a39bbc771272b6f279b19d38c110b4778ed1536fe525deafff8567dce94ac7` (computed from the final
file after all captures existed).

Godot headless room test (`godot4 --headless --path godot_walk --script res://…/test_room.gd`):
```
Godot Engine v4.6.3.stable.official.7d41c59c4 - https://godotengine.org

Chevron cross corridor candidate reset to safe spawn
CHEVRON_CROSS_CORRIDOR_TESTS_PASSED
```
Checks: spawn floor support, floor ray, closed north boundary, partition obstacle collision,
walk-and-backtrack, no boundary escape, missing-floor negative control, open-boundary negative
control, R reset to `[0, 0.6, 8.4]`. Result recorded in `standalone_test_receipt.json`.

Full script suite: `python3 -m pytest -q godot_walk/scripts`
```
1530 passed, 5 skipped, 67 subtests passed in 277.48s (0:04:37)
```
Source registry: `python3 godot_walk/scripts/register_video_sources.py validate`
```
{
  "valid": true,
  "registered_count": 13
}
```
Python lint on the new guard wrapper:
`python3 -m ruff check …/run_capture_guarded.py` -> `All checks passed!`.

## 4. Captures

Rendered with the guarded script
`python3 …/run_capture_guarded.py --output-dir …/captures --report …/capture_resource_run.json -- godot4 --path godot_walk --script …/capture_room.gd -- --out=res://…/captures`.
Receipt: `"return_code": 0`, `"timed_out": false`, `"error": null`,
`"elapsed_seconds": 10.059`; preflight and peak-resource samples are in
`capture_resource_run.json`; frame profile in `captures/capture_manifest.json`
(mean 16.67 ms, p95 16.754 ms, p99 16.861 ms over 300 samples; includes display sync).
All four 1152×648 PNGs were viewed:

- `captures/spawn_toward_partitions.png`
- `captures/wallpaper_partition.png`
- `captures/drop_ceiling.png`
- `captures/far_light_panel.png`

The capture emitted a non-fatal `ERROR: NO GRAB` from the shared `player.gd` mouse-lock call
under the offscreen X11 session; the capture harness continued and wrote all views.

## 5. Honest comparison with panorama and seed

**Matches.** Yellow-green chevron wallpaper on wall sections; white baseboards; tan/yellow
carpet with the same swirl texture; cream drop ceiling with a grid and bright fluorescent
panels; a long corridor reading with a small bright rectangle at the far end. The staggered
partitions reproduce the "past square wall sections" feel of the selected frame and the
partitions on both sides in the panorama. The PSX treatment and low-resolution source crops
give a coarse, grainy character close to the synthetic source video.

**Invented / approximated.** The 16×20 dimensions, four-partition count and their exact
spacing/length, the 10+8-rib ceiling grid, the four light panels, the baseboard geometry and
the far panel's size are all authored, not measured. The panorama's dead end is honoured only
as a closed far wall, not as a claim about the source's real end condition. The filename's
"cross junction" is not authored: there are no sockets and no branch. The panorama itself is
essentially invisible in the playable views because the authored shell occludes the sky, so it
functions only as a design reference. No model-inferred geometry is used as collision or
surface data.

**Wrong / questionable.** The source's plain cream pillars and cream foreground wall are not
reproduced as separate surfaces — the perimeter uses the chevron wallpaper crop everywhere.
The ceiling crop's perspective grid lines stretch into bright near-radial streaks and the light
panels bloom heavily in `drop_ceiling.png` / `far_light_panel.png`; these are texture/PSX
artefacts, not authored geometry. `wallpaper_partition.png` shows a dark blotch at the top-left
from the ceiling texture. The far panel reads as a flat pale rectangle, not a lit doorway,
which is deliberate. The source's partition walls look slightly curved; the authored ones are
flat orthogonal boxes. The capture frame profile is a display-synced SceneTree measurement,
not a gameplay FPS claim.

A passing validator and clean captures are **not approval**. This candidate remains
`candidate_pending_review` for operator review; it has not been accepted or admitted.

## 6. Ledger and scope compliance

No existing `source_ingestion_runner.py` stage records a room-candidate authoring event, so
none was used and no event was written by hand: `events.jsonl` is unchanged at 9 lines, last
event `hunyuan_operator_feedback`. No `select-seed`, `select-winner`, operator decision,
catalog edit, snapshot, `register_source_room.py`, module metadata, or hash-pinned file was
touched. `registration_accepted=false` and `scale_calibrated=false` unchanged. Only new files
under the source's `rooms/` folder and this evidence report were created.
