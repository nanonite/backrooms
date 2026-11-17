# Issue #172 — stage-6 bounded Godot room candidate

Source: `video-22909eb734e4d8e2` ("Antelope Canyon in 4K - World's Most Iconic Slot Canyon - UHD 4K.mp4").
Candidate: `slot-canyon-courtyard-v1`.
Built from the accepted Hunyuan panorama **attempt-001** (event 9, `improvement: improved`,
"all look good other than the dead end") and the operator-selected direct-source seed
**frame_1363** (run `issue172-2s-a`, decoded index 1362, PTS 45.4454 s). Both images were
viewed before authoring anything. The seed is a dark, winding slot-canyon interior with
flowing layered sandstone, a bright overhead light and a CENTERSTAR watermark; the
512x256 panorama shows the same warm striated canyon converging on a bright central slot.

## 1. What was built

A new, standalone, playable Godot room under
`godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/`:
an authored **L-shaped orthogonal courtyard** in XZ (+Y up, uncalibrated design units) made
of two legs (8x18 and 7x6 units), bounded by six tall striated sandstone walls (rim Y=7.0),
a two-box sandy floor at Y=0, three static rock obstacles, a thin high light-streak panel,
and an open top showing the panorama as sky. All six perimeter edges are closed;
`sockets` is `[]`. No doors, entities, moving or animated props. No hidden rooms or
connectivity inferred. The source is an outdoor natural slot canyon; this is a bounded
interior/courtyard stand-in whose character follows the picture, not a claim that the
video contains a room.

Files created (all new):
`adaptation_candidate.json`, `crop_plan.json`, `room.gd`, `room.tscn`, `test_room.gd`,
`capture_room.gd`, `run_capture_guarded.py`, `standalone_test_receipt.json`,
`capture_resource_run.json`, `textures/{wall_strata_dark,wall_strata_warm,sandy_floor,slot_glow,rock_rubble}.png`,
`textures/crop_manifest.json`,
`captures/{spawn_up_corridor,bend_turn,west_wall_strata,open_sky_slot}.png`,
`captures/capture_manifest.json`.

Followed the proven pattern from
`video-ccf9722164a0bdc8/rooms/industrial-hall-panorama-v1/` and the newest accepted #171
candidate `video-c9115d943f6c3fe4/rooms/wooden-verdure-hall-v1/`. No format was invented.

### Contract freeze used

**`godot_walk/room_catalog/contract_freeze_v3.json`**, sha256
`91c0cb1b47f980193a47d8e221b366f2d452256fa7b383adc818a177c9813ba1`, the newest freeze the
validators accept for an authorable record (v4 is lineage/tool-pinning only). Catalog
snapshot: `godot_psx_room_kit-0.2.0.json` (`8feb31a…80d`) taken from the freeze, not the
live catalog.

### Surface provenance (source crops vs project materials)

All close surfaces are **direct rectangular crops of the 1280x720 seed frame**, extracted
through the existing `video_adaptation_runner.py extract-source-crops` stage (no resize,
no color edit; see `textures/crop_manifest.json`). No surface was taken from panorama pixels.
The low gravel shelf uses a local solid-color `StandardMaterial3D` authored in `room.gd`.
The project PSX profile `library-psx-ursc-1.5-native-compositor` and the existing player
controller were reused unchanged; no shared material was edited. The panorama is used only
as a camera-centered `PanoramaSkyMaterial` background, visible through the open top.

## 2. Provenance table

| Feature | Observed (source/panorama) | Authored (this candidate) | Unknown / not claimed |
|---|---|---|---|
| Narrow winding slot | Both images: converging layered walls, one bend in seed | L-shaped orthogonal two-leg courtyard; bend at z=2 | Real canyon is curved; full length and shape unknown |
| Layered sandstone walls | Both images: strong flowing/wavy striations | Six tall box walls; `wall_strata_dark` / `wall_strata_warm` crops | Smooth eroded curves; exact striation geometry; wall count |
| Sandy, rock-strewn floor | Seed: light sand patch and scattered rocks | Two-box floor at Y=0 with `sandy_floor` crop | Level/tilt, real grain, metric area |
| Bright overhead slot | Panorama: bright central slot with pale sky; seed: bright upper light | Open top showing panorama sky + high `slot_glow` streak panel | The streak is light only, not a doorway/socket/destination |
| Scattered rocks | Seed: rocks on the sand | Three static boxes with `rock_rubble` crop | Exact count/positions/masses |
| Dark, warm palette | Both images, but seed is much darker | Unshaded crops + warm key light and ambient | Exposure difference from panorama (see §5) |
| Burned-in CENTERSTAR watermark | Seed lower-left, outside crop regions | Not reproduced | Treated as capture artifact, not room feature |
| Panorama background | Accepted 512x256 equirectangular render | Renderer sky only, no parallax, no collision | Not geometry, not a surface or metric map |

Provenance flags: `registration_accepted=false`, `scale_calibrated=false`,
`operator_decision.status=pending`, `catalog_admission=candidate_not_admitted`.

## 3. Mechanical checks (exact output lines)

Status (`source_ingestion_runner.py status video-22909eb734e4d8e2`), key lines:
```
"source_decision": "proceed",
"selected_seed": { ... "frame_id": "frame_1363", "timestamp_seconds": 45.4454 },
"attempts_used": 1,
"can_start_attempt": true,
"next_worker_actions": ["run_source_hunyuan.py"]
```
No Hunyuan, feedback, seed change, panorama attempt, manual fallback or paid/model call was
run in this stage despite `can_start_attempt`.

Bundle validation (`python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle …/adaptation_candidate.json`):
```
  "status": "valid",
  "adaptation_id": "slot-canyon-courtyard-v1",
  "candidate_fingerprint": "80cb05a357dffef917a30c14f65aadd58605890adf48fffa86b8d23bf7e9ff4d",
  "candidate_identity": "80cb05a357dffef917a30c14f65aadd58605890adf48fffa86b8d23bf7e9ff4d",
  "static_consistency": "passed",
  "runtime_evidence": { "status": "historical fingerprinted records verified; runtime not rerun" },
  "validation_is_read_only": true
```
48 hash-bound dependencies; candidate identity was computed with `candidate_identity_v2`.

Godot headless room test (`godot4 --headless --path godot_walk --script res://…/test_room.gd`):
```
Godot Engine v4.6.3.stable.official.7d41c59c4 - https://godotengine.org

Slot canyon courtyard candidate reset to safe spawn
SLOT_CANYON_TESTS_PASSED
```
Checks: spawn floor support, floor ray, closed north boundary, rock obstacle collision,
walk-and-backtrack, no boundary escape, missing-floor negative control, open-boundary
negative control, R reset to `[0, 0.6, -7]`. (An initial run failed the floor negative
control because the probe shared the player's z; the probe was moved to z=-5 and the test
then passed.)

Full script suite: `python3 -m pytest -q godot_walk/scripts`
```
1530 passed, 5 skipped, 67 subtests passed in 326.66s (0:05:26)
```
Source registry: `python3 godot_walk/scripts/register_video_sources.py validate`
```
{
  "valid": true,
  "registered_count": 13
}
```

## 4. Captures

Rendered with the guarded script
`python3 …/run_capture_guarded.py --output-dir …/captures --report …/capture_resource_run.json -- godot4 --path godot_walk --script …/capture_room.gd -- --out=res://…/captures`.
Receipt: `return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=9.497`;
preflight and peak-resource samples are in `capture_resource_run.json`, frame profile in
`captures/capture_manifest.json` (mean 16.67 ms, p95 16.84 ms, p99 16.89 ms over 300
samples; display-sync bound, not measured gameplay FPS). All four 1152x648 PNGs were viewed:

- `captures/spawn_up_corridor.png`
- `captures/bend_turn.png`
- `captures/west_wall_strata.png`
- `captures/open_sky_slot.png`

## 5. Honest comparison with panorama and seed

**Matches.** Warm red-brown-orange palette; flowing horizontal striations on the walls
(clearest in `west_wall_strata.png` and `bend_turn.png`); a light sandy floor with rock
debris; a narrow corridor that bends; bright sky visible above the walls in
`open_sky_slot.png`, echoing the panorama's bright central slot; the coarse PSX treatment
suits the low-resolution source crops.

**Invented / approximated.** The L-shaped footprint, leg widths (8 and 7), wall height 7.0,
six-wall segmentation, three boulder positions and the light-streak size/placement are all
authored, not measured. Walls and rocks are flat boxes, not the smooth sculpted erosion of
the real canyon. The bright streak high on the far wall reads as a small bright rectangle;
it is a light patch, **not** a socket, doorway or connection. The panorama is a static sky
with no parallax and is essentially only a background, not a source of geometry or surfaces.

**Wrong / questionable.** The seed frame is very dark, so the wall captures look much
darker than the brighter, sunlit panorama; `west_wall_strata.png` is especially dim. The
`sandy_floor` crop includes adjacent wall/rock detail, so in `spawn_up_corridor.png` the
floor reads as wavy stripes rather than level sand. BoxMesh UVs produce thin bright seams
at some wall corners, and the open top makes the room read as outdoor sky rather than an
interior — faithful to the slot-canyon source but unusual for Backrooms. No morphing or
animated geometry is used.

A passing validator and clean captures are **not approval**. This candidate remains
`candidate_pending_review` for operator review; it has not been accepted or admitted.

## 6. Ledger and scope compliance

No existing `source_ingestion_runner.py` stage records a room-candidate authoring event, so
none was used and no event was written by hand: `events.jsonl` is unchanged at 9 lines, last
event `hunyuan_operator_feedback`. No `select-seed`, `select-winner`, operator decision,
catalog edit, snapshot, `register_source_room.py`, module metadata, or hash-pinned file was
touched. Only new files under the source's `rooms/` folder and this evidence report were
created.
