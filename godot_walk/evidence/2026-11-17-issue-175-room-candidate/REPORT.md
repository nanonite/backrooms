# Issue #175 — stage-6 bounded Godot room candidate

Source: `video-102caf53423018b7` ("corridor_straight.mp4", 1920×1080, 24 fps, 96 frames, 4.0 s).
Candidate: `chevron-corridor-v1`.
Built from the accepted Hunyuan panorama **attempt-001-retry-001** (event 11,
`improvement: improved`, "all look good other than the dead end"; no further attempt wanted)
and the operator-selected direct-source seed **frame_0013** (quarter-s-a set, PTS 0.5 s,
sha256 `a836cd3e…38f1`). Both images were viewed before authoring anything.

## 1. What was built

A new, standalone, playable Godot room under
`godot_walk/source_library/sources/video-102caf53423018b7/rooms/chevron-corridor-v1/`:
a finite 12 × 20 design-unit rectangle in XZ, +Y up, uncalibrated. It is a bounded
corridor stand-in with yellow wall-to-wall carpet, green-gold chevron wallpaper walls,
a flat drop ceiling with brown grid ribs and five bright rectangular light panels, three
static square cream pillars with accent bases, white baseboards, and one bright panel on the
capped far wall. All four perimeter edges are closed; `sockets` is `[]`. No doors, entities,
moving or animated props. No hidden rooms or connectivity inferred. The 512×256 panorama is
used only as a camera-centered `PanoramaSkyMaterial` background (fully occluded by the
authored shell in the playable views) and as a design reference; it is not collision geometry
and no surface uses its pixels.

Files created (all new):
`adaptation_candidate.json`, `crop_plan.json`, `room.gd` (+`.uid`), `room.tscn`,
`test_room.gd` (+`.uid`), `capture_room.gd` (+`.uid`), `run_capture_guarded.py`,
`standalone_test_receipt.json`, `capture_resource_run.json`,
`textures/{carpet_floor,chevron_wallpaper,drop_ceiling}.png`,
`textures/crop_manifest.json`, `captures/{spawn_toward_far_wall,wallpaper_wall,pillar_row,ceiling_lights}.png`,
`captures/capture_manifest.json`.

Followed the proven panorama-to-room pattern from
`video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v1/` and the already built #171 candidate
`video-c9115d943f6c3fe4/rooms/wooden-verdure-hall-v1/` (report
`godot_walk/evidence/2026-11-16-issue-171-room-candidate/REPORT.md`). No format was invented.
The source crop team used the existing `video_adaptation_runner.py extract-source-crops` stage
and capture used the existing guarded wrapper.

### Contract freeze used

**`godot_walk/room_catalog/contract_freeze_v3.json`**, the newest freeze the validators accept
(`_verify_frozen_contract_reference()` maps a v3 record to `V3_FREEZE` only). Catalog snapshot:
`godot_psx_room_kit-0.2.0.json`, taken from the freeze, not the live catalog.

### Surface provenance (source crops vs project materials)

All close surfaces are **direct rectangular crops of the 1920×1080 seed frame**, extracted
through the existing `video_adaptation_runner.py extract-source-crops` stage (no resize,
no color edit; see `textures/crop_manifest.json`):

| Crop | Seed-frame pixel bounds | Used for |
|---|---|---|
| `carpet_floor.png` | (1200, 860)–(1700, 1040) | floor |
| `chevron_wallpaper.png` | (40, 340)–(360, 640) | all four walls |
| `drop_ceiling.png` | (760, 10)–(1120, 180) | ceiling plane |

The wallpaper is low resolution **in the panorama**, so the wall surface comes from the
seed-frame crop above, not from the 512×256 panorama pixels. Pillars, accent bases, baseboards,
ceiling ribs, light panels, the far panel and the panorama sky use local solid-color
`StandardMaterial3D` values authored in `room.gd`, matching the existing PSX palette.
No shared material file was edited. The project PSX profile
`library-psx-ursc-1.5-native-compositor` and the existing player controller were reused
unchanged.

## 2. Provenance table

| Feature | Observed (source/panorama) | Authored (this candidate) | Unknown / not claimed |
|---|---|---|---|
| Corridor-like interior | Seed: one carpeted, wallpapered corridor receding with a pillar; panorama: yellow corridor with a bright far dead end | 12×20 rectangle footprint, closed four sides | Real dimensions, full source perimeter; not claimed to be the whole space |
| Yellow wall-to-wall carpet | Both images | Flat floor at Y=0, `carpet_floor` crop tiled 4×8 | Fibre/wear, metric area |
| Green-gold chevron wallpaper | Both images (panorama low-res) | Four solid wall boxes with `chevron_wallpaper` crop | True repeat scale/pattern beyond the visible view |
| Square cream pillar(s) | Seed: one large square pillar the camera passes; panorama: a central pillar | Three static square pillars with accent bases; rhythm authored | Exact count/placement, construction; no metric spacing |
| Drop ceiling + rectangular lights | Both images | Flat ceiling plane, 11 grid ribs, 5 bright light panels; clear height 3.6 | True ceiling construction/height |
| White baseboard line | Seed (clear), panorama (hinted) | Four thin solid baseboard strips | Exact profile |
| Bright far region | Both images (panorama dead end) | One bright panel on the closed north wall, visual only | Not a door, socket, destination or connection |
| Openings / connectivity | None observed; name is not evidence | None authored; all edges capped | No claim of a "straight" 2-opening topology from the clip name |
| Panorama background | Accepted 512×256 panorama | Renderer sky only, no parallax | Not geometry, not collision, not a metric map |

Provenance flags: `registration_accepted=false`, `scale_calibrated=false`,
`operator_decision.status=pending`, `catalog_admission=candidate_not_admitted`.

## 3. Mechanical checks (exact output lines)

Status (`python3 godot_walk/scripts/source_ingestion_runner.py status video-102caf53423018b7`),
key lines:
```
"source_decision": "proceed",
"selected_seed": { ... "frame_id": "frame_0013", ... "timestamp_seconds": 0.5 },
"attempts_used": 1,
"can_start_attempt": true,
"next_worker_actions": ["run_source_hunyuan.py"]
```
No Hunyuan, feedback, seed change, panorama attempt, manual fallback or paid/model call was
run in this stage despite `can_start_attempt`.

Bundle validation
(`python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle …/adaptation_candidate.json`):
```
{
  "status": "valid",
  "adaptation_id": "chevron-corridor-v1",
  "candidate_fingerprint": "444bcbae77518a77f2b4e8e2559c1e9f611520e978c75cfdd7dc91b1597e459e",
  "candidate_identity": "444bcbae77518a77f2b4e8e2559c1e9f611520e978c75cfdd7dc91b1597e459e",
  "static_consistency": "passed",
  "runtime_evidence": { "status": "historical fingerprinted records verified; runtime not rerun" },
  "validation_is_read_only": true
}
```
46 hash-bound dependencies; record sha256 bound through `candidate_identity`.

Godot headless room test
(`godot4 --headless --path godot_walk --script res://…/test_room.gd`):
```
Godot Engine v4.6.3.stable.official.7d41c59c4 - https://godotengine.org

Chevron corridor candidate reset to safe spawn
CHEVRON_CORRIDOR_TESTS_PASSED
```
Checks: spawn floor support, floor ray, closed north boundary, pillar obstacle collision,
walk-and-backtrack, no boundary escape, missing-floor negative control, open-boundary
negative control, R reset to `[0, 0.6, 8.4]`.

Full script suite: `python3 -m pytest -q godot_walk/scripts`
```
1530 passed, 5 skipped, 67 subtests passed in 270.55s (0:04:30)
```
Source registry: `python3 godot_walk/scripts/register_video_sources.py validate`
```
{
  "valid": true,
  "registered_count": 13
}
```
Python lint on the new guard wrapper: `python3 -m ruff check …/run_capture_guarded.py`
-> `All checks passed!` (mirrors the #171 template).

## 4. Captures

Rendered with the guarded script
`python3 …/run_capture_guarded.py --output-dir …/captures --report …/capture_resource_run.json -- godot4 --path godot_walk --script …/capture_room.gd -- --out=res://…/captures`.
Receipt: `return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=9.693`;
preflight (20% VRAM / 25% RAM headroom, no competing compute apps) and peak-resource samples
are in `capture_resource_run.json`; frame profile in `captures/capture_manifest.json`.
All four 1152×648 PNGs were viewed:

- `captures/spawn_toward_far_wall.png`
- `captures/wallpaper_wall.png`
- `captures/pillar_row.png`
- `captures/ceiling_lights.png`

The capture emitted the same non-fatal `ERROR: NO GRAB` from the shared `player.gd`
mouse-lock call under the offscreen X11 session as the #171 capture; the harness continued
and wrote all views.

## 5. Honest comparison with panorama and seed

**Matches.** Yellow wall-to-wall carpet; green-gold chevron wallpaper on both sides; a large
square cream pillar row receding down the corridor; a brown-grid drop ceiling with repeated
bright rectangular light panels; a white baseboard line; a bright patch on the far wall. The
PSX treatment and low-resolution source crops give the same coarse, grainy character as the
source. The spawn view reads as the same kind of corridor the panorama depicts.

**Invented / approximated.** The 12×20 dimensions, the three-pillar count and their exact
spacing, the eleven-rib / five-light rhythm, the accent bases, the baseboards and the far
panel's size are all authored, not measured. The source clip name "straight corridor" was
not treated as evidence of two opposed openings: none are observed in the sampled frames, so
none are authored and all edges are capped. The panorama is essentially invisible in the
playable views because the authored shell occludes the sky, so it functions only as a design
reference. No model-inferred geometry is used as collision or surface data.

**Wrong / questionable.** The wallpaper crop carries a lighter horizontal band near its top;
tiling it produces a visible grey seam across the walls (clear in `wallpaper_wall.png`) that
the panorama does not show. The ceiling crop reads as smeared/streaked from the oblique source
view, and its brown grid lines are authored ribs on top of a texture that already contains
seams, so the ceiling is busier than the seed. The far bright panel is a flat cream rectangle,
not the soft glow seen in the panorama. The pillars are plain boxes rather than the textured
column in the seed. These are faithful-but-coarse stand-ins, not a photometric reconstruction.

A passing validator and clean captures are **not approval**. This candidate remains
`candidate_pending_review` for operator review; it has not been accepted or admitted.

## 6. Ledger and scope compliance

No existing `source_ingestion_runner.py` stage records a room-candidate authoring event, so
none was used and no ledger event was written by hand: `events.jsonl` is unchanged at 11 lines,
last event `hunyuan_operator_feedback` (event 11). The two runner stages that do exist for
this kind of artifact were used: `video_adaptation_runner.py extract-source-crops` wrote
`textures/crop_manifest.json` and the crop PNGs, and the guarded capture wrapper wrote
`capture_resource_run.json` and `captures/capture_manifest.json`. No stage exists for the
standalone Godot test receipt, so `standalone_test_receipt.json` was authored locally exactly
as in the proven #171 candidate. No `select-seed`, `select-winner`, operator decision, catalog
edit, snapshot, `register_source_room.py`, module metadata, or hash-pinned file was touched.
Only new files under the source's `rooms/` folder and this evidence report were created.
