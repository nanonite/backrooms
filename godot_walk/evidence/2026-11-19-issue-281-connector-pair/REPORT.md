# Issue 281 — connector-pair test: chevron-corridor-v2 north vs textured-large-room hall_end

Date: 2026-11-19
Issue: #281 (child of #265). Pair test only: no map, no catalog edit, no integration decision.
Status: **PAIR MATES under the stated mechanical assertions; sockets remain `untested`.**
Operator review of the captures and any tested-status decision is still required.

## Scope and non-changes

- New files only, under `godot_walk/evidence/2026-11-19-issue-281-connector-pair/`.
- Neither room scene, the catalog, nor any hash-pinned file was edited:
  `scripts/player.gd`, `project.godot`, library room scenes, `catalog.json`,
  `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md` are untouched.
- `tested_connectors`, `test_status` and `layout_eligible` were not changed in
  any catalog or metadata record. `registration_accepted` and `scale_calibrated`
  remain false in the assembly, contract, test report and capture manifest.
- No `propose-integrations`, `decide-integration`, map generation or model call
  was made. No module was promoted to layout eligibility.

## Pair and reference evidence

- **A** = `video_102caf53423018b7_chevron_corridor_v2_north_south_socket_v1`
  (`chevron-corridor-v2-north-south-socket/room.tscn`, #275). Sockets: north
  `(0,0,-10)` normal `(0,0,-1)`; south `(0,0,+10)` normal `(0,0,+1)`; both
  `level_doorway_2m_v1`, clear `2.0 x 2.1`, floor `0.0`, approach `1.2`.
- **B** = `godot_source_textured_large_room_v1` socket `hall_end`,
  local floor center `(13.06,0,0)`, outward normal `(1,0,0)`, floor `0.0`,
  clear `2.0 x 2.1`, compatibility `level_doorway_2m_v1`. Its
  `closure_behavior` states the accepted baseline wall and collider stay closed,
  so B was not edited. A new **test-only adapter scene** extends the accepted
  baseline script by reference, frees `HallEndBoundaryVisual` and
  `HallEndBoundary`, and rebuilds two returns plus a header at floor 0.0. It
  deliberately does **not** apply the issue #164 `-1.27099049` library-floor
  shift, so B's floor stays at 0.0 as declared in the catalog entry.
- Pattern followed: #275 `REPORT.md`; #168 `connector_contract.json` and
  `COMMANDS.md`; #168 two-room assembly, headless test and guarded capture
  scripts; `issue149_layout_core.py` rotation and socket placement rules.

## Yaw and placement arithmetic

Rotation convention from `issue149_layout_core.py::_rotate_xz`, equivalent to
Godot `rotation.y = deg_to_rad(yaw)`:

| yaw | local `(x,z)` → world |
|---|---|
| 0 | `(x, z)` |
| 90 | `(z, -x)` |
| 180 | `(-x, -z)` |
| 270 | `(-z, x)` |

B's `hall_end` world center is `(13.06, 0, 0)` with world normal `(+1,0,0)`.
Mating requires A's chosen socket normal to be `(-1,0,0)` and its world floor
center to be `(13.06, 0, 0)`.

- A north local center `(0,-10)` rotated by yaw 90 → `(-10, 0)`; local normal
  `(0,-1)` rotated by yaw 90 → `(-1, 0)` = `-x`. **Usable.**
- A origin: `x = 13.06 - (-10.0) = 23.06`, `z = 0 - 0 = 0`,
  `y = 0 - 0 = 0` (both sockets declare floor 0.0). Result:
  **`a_origin = (23.06, 0, 0)`, `a_yaw_degrees = 90`, socket `north`.**
- Why the other socket / yaw are or are not usable:
  - yaw 0: north `(0,0,-1)` and south `(0,0,+1)` keep z normals; dot with B
    `(+1,0,0)` is 0 for both. Not usable.
  - yaw 90: north → `(-1,0,0)` usable (chosen); south → `(+1,0,0)`, parallel
    to B, not usable.
  - yaw 180: north → `(0,0,+1)`, south → `(0,0,-1)`; dot 0 for both. Not usable.
  - yaw 270: north → `(+1,0,0)` not usable; south → `(-1,0,0)` usable as the
    symmetric alternative. It yields the same A origin `(23.06,0,0)` because
    the two sockets are symmetric about A's center.

The assembly adds a test-only threshold plate / `DoorwayFloorSeam` at
`x = 13.02`, spanning `x ∈ [12.90, 13.14]`, `z ∈ [-1.0, 1.0]`, top `y = 0.0`,
bridging B's hall floor (ends `x = 13.0`) and A's floor (starts `x = 13.06`).

## Headless walk test — exact result lines

Command: `godot4 --headless --path godot_walk --script res://evidence/2026-11-19-issue-281-connector-pair/test_connector_pair.gd`

```
NOMINAL_PAIR_CENTER_XZ_ERROR 0.000001
NOMINAL_PAIR_FLOOR_DELTA 0.000000
NOMINAL_PAIR_NORMAL_DOT -1.000000
NOMINAL_PAIR_CLEAR_SIZE [2.0, 2.1] vs [2.0, 2.1]
DOORWAY_CAPSULE_SAMPLES_CLEAR 31/31
FLOOR_CONTINUITY_SUPPORTED true worst_abs_error=0.000000
APERTURE_CENTER_OPEN true NEAR_SIDE_OPEN true JAMB_BLOCKS true HEADER_BLOCKS true
FOOTPRINT_OVERLAP_X -0.060000 OVERLAP_Z 10.000000 NO_OVERLAP true
EXTERIOR_BOUNDARIES_CLOSED 6/6 DECLARED_SOUTH_OPEN true
TRAVERSAL_A_TO_B x=4.000011 y=0.600000 z=0.000001 on_floor=true
TRAVERSAL_B_TO_A x=16.000000 y=0.600000 z=0.000000 on_floor=true
TRAVERSAL_RESET x=16.000000 y=0.600000 z=0.000000
NEGATIVE_MISMATCHED_YAW_REJECTED normal_dot=0.000000 errors=["socket normals do not oppose (dot=0.000000)"]
NEGATIVE_FLOOR_OFFSET_REJECTED floor_delta=0.300000 errors=["connector floor elevations differ (delta=0.300000)"]
ISSUE281_CONNECTOR_PAIR_TESTS_PASSED
```

Assertions, mapped to the lines above:

1. **Centers / floors / normals / size** — XZ center error `0.000001 <= 0.001`,
   floor delta `0.000000`, normal dot `-1.000000 <= -0.999`, clear sizes both
   `[2.0, 2.1]`, compatibility types equal.
2. **No collision block at the doorway** — 31 capsule samples of radius 0.3,
   height 1.2 at `y = 0.64`, `x = 13.06 ± 1.5`, all clear; center ray at
   `y = 1.1` open; real player walked A → B and back while staying on the floor.
3. **Floor elevation continuity** — 25 downward rays across the seam all hit
   at `y = 0.0` (worst absolute error `0.000000`).
4. **Matching clear size** — center and `z = 0.95` rays open, `z = 1.2` jamb
   and `y = 2.5` header rays blocked; 2.0 m wide, 2.1 m high aperture.
5. **No solid-volume overlap beyond the doorway** — catalog footprint overlap
   in X is `-0.060000` (a 0.06 m separation at the abutment), so the rooms
   abut rather than interpenetrate in footprint. The independently authored
   jamb thicknesses do overlap by ~0.06 m *inside the doorway frame*; this is
   recorded below as a limitation, not treated as a fit failure.
6. **No leak outside declared openings** — 6/6 exterior wall probes closed
   (B west/north/south/hall-side, A west/east mapped into world axes). A's
   south socket is a declared opening and is open/unconnected; it is not a leak
   outside the declared openings, but it remains untested.
7. **Negative controls, same assertions as the nominal pair** — mismatched yaw
   (yaw 0, A origin `(13.06,0,10)`, XZ centers aligned) is rejected only by
   `socket normals do not oppose (dot=0.000000)`; a 0.3 m floor offset (yaw 90,
   A origin `(23.06,0.3,0)`) is rejected only by
   `connector floor elevations differ (delta=0.300000)`.

Player transforms are recorded in `mechanics/traversal.json`
(`spawn`, `after_a_to_b`, `after_b_to_a`, `after_reset`); camera transforms are
recorded in `captures/capture_manifest.json`.

## Captures (guarded, DISPLAY=:1)

Rendered through `run_capture_guarded.py` with `DISPLAY=:1` (Vulkan 1.4.329,
Forward+, RTX 4070 Ti). `--headless` was not used for captures. Receipt:
`return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=3.303`.
Four 1152x648 PNGs; frame profile over 300 samples after 120 warmup frames:
mean `4.16572 ms`, p95 `4.335 ms`, p99 `4.386 ms`.

| File | Camera position → look-at |
|---|---|
| `from_chevron_to_large_room.png` | `(16.5, 1.42, 0.0)` → `(10.0, 1.3, 0.0)` |
| `from_large_room_to_chevron.png` | `(9.0, 1.42, 0.0)` → `(16.5, 1.3, 0.0)` |
| `chevron_side_doorway.png` | `(15.2, 1.42, 2.2)` → `(13.06, 1.3, 0.0)` |
| `large_room_hall_end.png` | `(10.5, 1.42, 1.2)` → `(13.3, 1.3, 0.0)` |

### What I saw (description only; no appearance judgement)

- `from_chevron_to_large_room.png`: standing in the chevron room facing a
  rectangular opening. Chevron-patterned wallpaper with a light baseboard on
  both sides, a linear-patterned carpet floor, and a dark strip at the
  threshold. Through the opening is a narrower carpeted passage with the same
  wallpaper and a horizontal light panel near the top of the opening.
- `from_large_room_to_chevron.png`: standing in the large-room hallway facing
  the doorway at the end of a carpeted passage with chevron wallpaper on both
  side walls. Beyond the opening is a room with a ribbed ceiling grid, a
  light-colored vertical panel on the right, a white horizontal ledge, and a
  small dark rectangular opening farther back.
- `chevron_side_doorway.png`: an angled view of the doorway from the chevron
  side. The chevron-wallpapered wall plane, its rectangular opening, the dark
  threshold strip, carpet on both sides, and a ribbed ceiling above are all
  visible; part of the far room's wallpapered wall appears through the opening.
- `large_room_hall_end.png`: an angled view from the large-room hallway toward
  the opening. A light-colored vertical panel just inside the far room, the
  carpeted floor with a dark threshold strip, a ribbed ceiling with dark ribs,
  and a small dark rectangular shape on the far side are visible.

The small dark rectangular opening seen from the large-room side is consistent
with A's south socket, which stays open and unconnected in this pair (reported
by `DECLARED_SOUTH_OPEN true`).

## Verification

| Command | Result |
|---|---|
| `godot4 --headless --path godot_walk --script res://evidence/2026-11-19-issue-281-connector-pair/test_connector_pair.gd` | exit 0, `ISSUE281_CONNECTOR_PAIR_TESTS_PASSED` |
| `python3 -m pytest -q godot_walk/scripts` | `1582 passed, 5 skipped, 94 subtests passed in 279.96s (0:04:39)` |
| `python3 godot_walk/scripts/register_video_sources.py validate` | `{"valid": true, "registered_count": 13}` |
| `python3 -m ruff check .../run_capture_guarded.py` | `All checks passed!` |
| Guarded Vulkan capture (`DISPLAY=:1`) | `return_code=0`, four 1152x648 PNGs |

## What this test does not show

- **Appearance / feel**: agents cannot judge appearance. The captures are
  described above but not approved; the operator must review them.
- **Scale calibration**: `scale_calibrated` stays false. The pair uses declared
  design-unit geometry; no measured reconstruction scale is established.
- **Lighting continuity**: two authored environments are combined; no claim is
  made that lighting, shadows or post-processing match across the doorway.
- **Audio**: no audio was rendered, probed or compared.
- **Source-video connectivity**: like the #168 evidence, the connection is an
  authored game connection. Nothing here establishes that the two source video
  intervals were adjacent in the real location.
- **Registration / integration**: `registration_accepted` stays false. The
  sockets remain `test_status: untested` and A stays layout-ineligible.
- **Physics beyond the scripted path**: traversal is a single straight line
  along `z = 0`; it does not explore every angle, jump, sprint or long dwell.
- **Jamb seam**: the two independently authored wall planes sit about 0.15 m
  apart with ~0.06 m of jamb-thickness overlap inside the doorway frame. The
  threshold plate bridges the floor gap; no shared jamb geometry was authored
  for this pair. Whether to author a shared frame is an operator decision.

## What a catalog change would be, if the operator decides the pair is tested

Not done here. If the operator approves the pair, a new catalog version would:

1. append a `tested_connector_pairs` entry (new version only) with
   `id` like `chevron_v2_north__large_room_hall_end_v1`,
   `from = {module_id: <chevron v2 id>, socket_id: "north"}`,
   `to = {module_id: "godot_source_textured_large_room_v1", socket_id: "hall_end"}`,
   `compatibility_type: "level_doorway_2m_v1"`,
   `mechanical_status: "tested_pair"`, `operator_status: "review_pending"`,
   and `evidence` citing this folder's `traversal.json` and capture manifest;
2. change `test_status` of A's `north` socket (and B's `hall_end` socket in the
   module that declares it) from `untested` to `tested`, and record the new
   pair id in the corresponding `tested_connectors` lists;
3. leave `layout_eligible` false until a separate operator step approves
   integration, and leave `registration_accepted` and `scale_calibrated` false;
4. append an immutable snapshot / library index for the new catalog version
   and register through the existing path, without editing any existing entry.

This report does not make that change.

## Files added

`connector_pair_contract.json`, `connector_pair_scene.gd` / `.tscn`,
`test_only_hall_end_adapter.gd` / `.tscn`, `test_connector_pair.gd`,
`capture_connector_pair.gd`, `run_capture_guarded.py`, `COMMANDS.md`,
`mechanics/traversal.json`, `captures/` (four PNGs + `capture_manifest.json`),
`capture_resource_run.json`, and this `REPORT.md`.
