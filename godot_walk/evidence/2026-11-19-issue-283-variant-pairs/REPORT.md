# Issue 283 — variant-to-variant connector-pair evidence (four corridor chains)

Date: 2026-11-19
Issue: #283 (child of #265). Pair evidence only: no map, no catalog edit, no
integration decision and no tested-status decision.

Status: **all four pairs MATE under the stated mechanical assertions; every
socket stays `untested`.** Traversal is not blocked at any doorway. Ceiling and
width mismatches are recorded per pair below. Operator review of the captures
and any tested-status decision is still required.

## Scope and non-changes

- New files only, under
  `godot_walk/evidence/2026-11-19-issue-283-variant-pairs/`.
- Neither room, the catalog, nor any hash-pinned file was edited:
  `scripts/player.gd`, `project.godot`, library room scenes, `catalog.json`,
  `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md` are untouched.
- `tested_connectors`, `test_status` and `layout_eligible` were not changed in
  any catalog or metadata record. `registration_accepted` and `scale_calibrated`
  remain false in the contract, assembly, test report, capture manifest and
  resource receipt.
- No `propose-integrations`, `decide-integration`, map generation or model call
  was made. No module was promoted to layout eligibility.
- Both negative controls run **per pair** through the same
  `_pair_geometry_errors()` gate used by the nominal assertions.

## Reference evidence and method

Method follows #281 (`REPORT.md`, `test_connector_pair.gd`, guarded capture) and
the placement rules in `issue149_layout_core.py::_rotate_xz`. Rooms are instanced
by reference from the four accepted source-library scenes; the assembly is one
parameterized scene, so no room file is modified. The only assembly-only node
is a `ConnectorFloorSeam` static body whose top is at `y = 0.0`, bridging the
abutting floors (the rooms' own floors already meet exactly, so this is a
robustness seam, not a filler for a gap).

Rotation convention (`_rotate_xz`, equivalent to `rotation.y = deg_to_rad(yaw)`):

| yaw | local `(x,z)` → world |
|---|---|
| 0 | `(x, z)` |
| 90 | `(z, -x)` |
| 180 | `(-x, -z)` |
| 270 | `(-z, x)` |

All sockets are at `x = 0`, so a straight chain on the z axis needs only yaw 0
(or its 180 mirror). Every pair below uses yaw 0 for both rooms; the yaw-180
mirror is a valid symmetric alternative that reverses the chain into -z.

### Room facts used (read from the unmodified `room.gd` files)

| Ref | Issue | video | width (x) | depth (z) | height | socket local centers / normals |
|---|---|---|---|---|---|---|
| Cv2-175 | #175 | 102caf53423018b7 | 12.0 | 20.0 | 3.8 | north `(0,0,-10)` `(0,0,-1)`; south `(0,0,+10)` `(0,0,+1)` |
| NL-173 | #173 | d857abe7a94da9d1 | 10.0 | 24.0 | 4.8 | north `(0,0,-12)` `(0,0,-1)`; south `(0,0,+12)` `(0,0,+1)` |
| Cv2-176 | #176 | 2671b32f256a4ee7 | 16.0 | 20.0 | 4.2 | north `(0,0,-10)` `(0,0,-1)`; south `(0,0,+10)` `(0,0,+1)` |
| Cx2-177 | #177 | 61b91dbeb9026dc7 | 16.0 | 20.0 | 4.2 | north `(0,0,-10)` `(0,0,-1)`; south `(0,0,+10)` `(0,0,+1)` |

All four declare `level_doorway_2m_v1`, clear `2.0 x 2.1`, floor `0.0`,
approach `1.2`, and both sockets are `untested`. Base-room interior obstacles
are clear of the `x = 0` lane (pillars at `x = ±3.4`; partitions at `x = ±4.5`;
nested-light plinths/frames at `|x| >= 4.2`), so a straight walk on `x = 0` is
unobstructed.

## Yaw and placement arithmetic per pair

For each pair, from-socket world center `F = from_origin + rotate(from_local, yaw)`,
to-socket world center `T = to_origin + rotate(to_local, yaw)`. Mating requires
`F = T` in XZ, `floor(F) = floor(T)`, opposing normals (`dot = -1`), and equal
clear size. With yaw 0, `to_origin.z = F.z - to_local.z`.

| Pair | Chain | From socket (local → world) | To socket (local → world) | Placement | Seam z |
|---|---|---|---|---|---|
| P1 | Cv2-175 south → Cv2-176 north | `(0,0,+10)` → `(0,0,+10)`, normal `+z` | `(0,0,-10)` → `(0,0,-10)`, normal `-z` | `from_origin (0,0,0)` yaw 0; `to_origin = (0,0,10) - (0,0,-10) = (0,0,20)` yaw 0 | `10` |
| P2 | Cv2-176 south → Cx2-177 north | `(0,0,+10)` → `(0,0,+10)`, normal `+z` | `(0,0,-10)` → `(0,0,-10)`, normal `-z` | `to_origin = (0,0,10) - (0,0,-10) = (0,0,20)` yaw 0 | `10` |
| P3 | Cx2-177 south → NL-173 north | `(0,0,+10)` → `(0,0,+10)`, normal `+z` | `(0,0,-12)` → `(0,0,-12)`, normal `-z` | `to_origin = (0,0,10) - (0,0,-12) = (0,0,22)` yaw 0 | `10` |
| P4 | NL-173 south → Cv2-175 north | `(0,0,+12)` → `(0,0,+12)`, normal `+z` | `(0,0,-10)` → `(0,0,-10)`, normal `-z` | `to_origin = (0,0,12) - (0,0,-10) = (0,0,22)` yaw 0 | `12` |

In every case `x = 0 - 0 = 0` and `y = 0 - 0 = 0` (both sockets declare floor
0.0), and `+z · -z = -1`. The yaw-180 mirror gives the same centers with the
chain reversed (e.g. P1 with both rooms at yaw 180 gives `to_origin.z = -20`).

## Doorway seams — ceiling height, room width, and traversal

The clear aperture is `2.0 x 2.1` in all four rooms, so the `x ∈ [-1,1]`
opening is always common even when the surrounding walls differ in width.

| Pair | Ceiling heights | Ceiling step at seam | Wall widths | Width mismatch at doorway | Walking step | Traversal blocked? |
|---|---|---|---|---|---|---|
| P1 | 3.8 → 4.2 | +0.4 m (visible step in the header/ceiling) | 12.0 → 16.0 | to room 2.0 m wider on each side | 0.0 m | No — walked A→B and back, on floor throughout |
| P2 | 4.2 → 4.2 | 0.0 m (no step) | 16.0 → 16.0 | none (0.0 m each side) | 0.0 m | No |
| P3 | 4.2 → 4.8 | +0.6 m (the 4.2 vs 4.8 case named in the issue) | 16.0 → 10.0 | to room 3.0 m narrower on each side | 0.0 m | No |
| P4 | 4.8 → 3.8 | -1.0 m (visible step; far room lower) | 10.0 → 12.0 | to room 1.0 m wider on each side | 0.0 m | No |

The ceiling step is a visible vertical discontinuity above the 2.1 m clear
header, not a floor step: `*_FLOOR_DELTA 0.000000` and
`*_WALKING_STEP`/`NOMINAL` floor agreement hold for every pair. The wall-width
mismatch leaves a ledge where the narrower room's wall plane stops against the
wider room's wall plane; it does not intrude into the 2.0 m opening. The
`31/31` capsule samples at `x = 0, y = 0.64` across each seam and the real
player walk confirm that neither mismatch blocks traversal.

## Headless test — exact result lines

Command: `godot4 --headless --path godot_walk --script res://evidence/2026-11-19-issue-283-variant-pairs/test_variant_pairs.gd`

```
P1_NOMINAL_CENTER_XZ_ERROR 0.000000
P1_NOMINAL_FLOOR_DELTA 0.000000
P1_NOMINAL_NORMAL_DOT -1.000000
P1_NOMINAL_CLEAR_SIZE [2.0, 2.1] vs [2.0, 2.1]
P1_CEILING_SEAM from_h=3.800000 to_h=4.200000 step=0.400000 walking_step=0.000000
P1_WIDTH_SEAM from_w=12.000000 to_w=16.000000 delta_each_side=2.000000
P1_DOORWAY_CAPSULE_SAMPLES_CLEAR 31/31
P1_FLOOR_CONTINUITY_SUPPORTED true worst_abs_error=0.000000
P1_APERTURE_CENTER_OPEN true NEAR_SIDE_OPEN true JAMB_BLOCKS true HEADER_BLOCKS true
P1_FOOTPRINT_OVERLAP_X 12.000000 OVERLAP_Z 0.000000 NO_OVERLAP true
P1_EXTERIOR_BOUNDARIES_CLOSED 4/4 UNCONNECTED_SOCKETS_OPEN 2/2
P1_TRAVERSAL_A_TO_B x=0.000002 y=0.600000 z=15.999989 on_floor=true
P1_TRAVERSAL_B_TO_A x=-0.000000 y=0.600000 z=4.000000 on_floor=true
P1_TRAVERSAL_RESET x=0.000000 y=0.600000 z=4.000000
P1_NEGATIVE_MISMATCHED_YAW_REJECTED normal_dot=1.000000 errors=["socket normals do not oppose (dot=1.000000)"]
P1_NEGATIVE_FLOOR_OFFSET_REJECTED floor_delta=0.300000 errors=["connector floor elevations differ (delta=0.300000)"]
P2_NOMINAL_CENTER_XZ_ERROR 0.000000
P2_NOMINAL_FLOOR_DELTA 0.000000
P2_NOMINAL_NORMAL_DOT -1.000000
P2_NOMINAL_CLEAR_SIZE [2.0, 2.1] vs [2.0, 2.1]
P2_CEILING_SEAM from_h=4.200000 to_h=4.200000 step=0.000000 walking_step=0.000000
P2_WIDTH_SEAM from_w=16.000000 to_w=16.000000 delta_each_side=0.000000
P2_DOORWAY_CAPSULE_SAMPLES_CLEAR 31/31
P2_FLOOR_CONTINUITY_SUPPORTED true worst_abs_error=0.000000
P2_APERTURE_CENTER_OPEN true NEAR_SIDE_OPEN true JAMB_BLOCKS true HEADER_BLOCKS true
P2_FOOTPRINT_OVERLAP_X 16.000000 OVERLAP_Z 0.000000 NO_OVERLAP true
P2_EXTERIOR_BOUNDARIES_CLOSED 4/4 UNCONNECTED_SOCKETS_OPEN 2/2
P2_TRAVERSAL_A_TO_B x=0.000002 y=0.600000 z=15.999989 on_floor=true
P2_TRAVERSAL_B_TO_A x=-0.000000 y=0.600000 z=4.000000 on_floor=true
P2_TRAVERSAL_RESET x=0.000000 y=0.600000 z=4.000000
P2_NEGATIVE_MISMATCHED_YAW_REJECTED normal_dot=1.000000 errors=["socket normals do not oppose (dot=1.000000)"]
P2_NEGATIVE_FLOOR_OFFSET_REJECTED floor_delta=0.300000 errors=["connector floor elevations differ (delta=0.300000)"]
P3_NOMINAL_CENTER_XZ_ERROR 0.000000
P3_NOMINAL_FLOOR_DELTA 0.000000
P3_NOMINAL_NORMAL_DOT -1.000000
P3_NOMINAL_CLEAR_SIZE [2.0, 2.1] vs [2.0, 2.1]
P3_CEILING_SEAM from_h=4.200000 to_h=4.800000 step=0.600000 walking_step=0.000000
P3_WIDTH_SEAM from_w=16.000000 to_w=10.000000 delta_each_side=-3.000000
P3_DOORWAY_CAPSULE_SAMPLES_CLEAR 31/31
P3_FLOOR_CONTINUITY_SUPPORTED true worst_abs_error=0.000000
P3_APERTURE_CENTER_OPEN true NEAR_SIDE_OPEN true JAMB_BLOCKS true HEADER_BLOCKS true
P3_FOOTPRINT_OVERLAP_X 10.000000 OVERLAP_Z 0.000000 NO_OVERLAP true
P3_EXTERIOR_BOUNDARIES_CLOSED 4/4 UNCONNECTED_SOCKETS_OPEN 2/2
P3_TRAVERSAL_A_TO_B x=0.000002 y=0.600000 z=15.999989 on_floor=true
P3_TRAVERSAL_B_TO_A x=-0.000000 y=0.600000 z=4.000000 on_floor=true
P3_TRAVERSAL_RESET x=0.000000 y=0.600000 z=4.000000
P3_NEGATIVE_MISMATCHED_YAW_REJECTED normal_dot=1.000000 errors=["socket normals do not oppose (dot=1.000000)"]
P3_NEGATIVE_FLOOR_OFFSET_REJECTED floor_delta=0.300000 errors=["connector floor elevations differ (delta=0.300000)"]
P4_NOMINAL_CENTER_XZ_ERROR 0.000000
P4_NOMINAL_FLOOR_DELTA 0.000000
P4_NOMINAL_NORMAL_DOT -1.000000
P4_NOMINAL_CLEAR_SIZE [2.0, 2.1] vs [2.0, 2.1]
P4_CEILING_SEAM from_h=4.800000 to_h=3.800000 step=-1.000000 walking_step=0.000000
P4_WIDTH_SEAM from_w=10.000000 to_w=12.000000 delta_each_side=1.000000
P4_DOORWAY_CAPSULE_SAMPLES_CLEAR 31/31
P4_FLOOR_CONTINUITY_SUPPORTED true worst_abs_error=0.000000
P4_APERTURE_CENTER_OPEN true NEAR_SIDE_OPEN true JAMB_BLOCKS true HEADER_BLOCKS true
P4_FOOTPRINT_OVERLAP_X 10.000000 OVERLAP_Z 0.000000 NO_OVERLAP true
P4_EXTERIOR_BOUNDARIES_CLOSED 4/4 UNCONNECTED_SOCKETS_OPEN 2/2
P4_TRAVERSAL_A_TO_B x=0.000002 y=0.600000 z=18.000017 on_floor=true
P4_TRAVERSAL_B_TO_A x=-0.000000 y=0.600000 z=6.000001 on_floor=true
P4_TRAVERSAL_RESET x=0.000000 y=0.600000 z=6.000000
P4_NEGATIVE_MISMATCHED_YAW_REJECTED normal_dot=1.000000 errors=["socket normals do not oppose (dot=1.000000)"]
P4_NEGATIVE_FLOOR_OFFSET_REJECTED floor_delta=0.300000 errors=["connector floor elevations differ (delta=0.300000)"]
ISSUE283_VARIANT_PAIR_TESTS_PASSED
```

Assertions mapped to the lines above:

1. **Centers / floors / normals / size** — XZ error `0.000000 <= 0.001`, floor
   delta `0.000000`, normal dot `-1.000000 <= -0.999`, both clear sizes
   `[2.0, 2.1]` and both compatibility types `level_doorway_2m_v1` for all four
   pairs.
2. **No collision block at the doorway** — 31 capsule samples (radius 0.3,
   height 1.2) at `y = 0.64` along `x = 0, z = seam ± 1.5` are clear; the real
   player walked A → B and back on every pair while staying on the floor.
3. **Floor continuity** — 25 downward rays across each seam hit at `y = 0.0`
   (worst absolute error `0.000000`); the width/ceiling mismatch does not create
   a walking step.
4. **Matching clear aperture** — center and `x = 0.95` rays open; `x = 1.2`
   jamb and `y = 2.5` header rays blocked; 2.0 m wide, 2.1 m high aperture.
5. **No solid-volume overlap beyond the doorway** — footprint overlap X is
   positive (rooms share the same x band) but overlap Z is `0.000000` for all
   four pairs, so the rooms abut at the doorway rather than interpenetrate.
6. **No leak outside declared openings** — 4/4 exterior side-wall probes closed
   per pair; each room's second socket is a declared opening and is open and
   unconnected (`UNCONNECTED_SOCKETS_OPEN 2/2`), not an undeclared leak.
7. **Negative controls, per pair, same assertions** — mismatched yaw (to-room
   yaw 180 with `to_origin.z = seam - to_depth`, so XZ centers still align)
   is rejected only by `socket normals do not oppose (dot=1.000000)`; a 0.3 m
   floor offset (to-room origin y = 0.3) is rejected only by
   `connector floor elevations differ (delta=0.300000)`.

Machine-readable transforms are in `mechanics/traversal.json`
(`spawn`, `after_a_to_b`, `after_b_to_a`, `after_reset` per pair).

## Captures (guarded, DISPLAY=:1)

Rendered through `run_capture_guarded.py` with `DISPLAY=:1` (Vulkan 1.4.329,
Forward+, RTX 4070 Ti). `--headless` was **not** used for captures. Receipt:
`return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=6.185`.
Twelve 1152x648 PNGs (three views per pair). Frame profile over 300 samples
after 120 warmup frames: mean `4.175247 ms`, p95 `6.076 ms`, p99 `8.698 ms`.
Engine `4.6.3-stable (official)`.

| Pair | File | Camera position → look-at |
|---|---|---|
| P1 | `p1_from_a_to_b.png` | `(0,1.42,6.5)` → `(0,1.3,14.0)` |
| P1 | `p1_from_b_to_a.png` | `(0,1.42,13.5)` → `(0,1.3,6.0)` |
| P1 | `p1_doorway_side.png` | `(2.6,1.42,7.6)` → `(0,1.35,10.4)` |
| P2 | `p2_from_a_to_b.png` | `(0,1.42,6.5)` → `(0,1.3,14.0)` |
| P2 | `p2_from_b_to_a.png` | `(0,1.42,13.5)` → `(0,1.3,6.0)` |
| P2 | `p2_doorway_side.png` | `(2.6,1.42,7.6)` → `(0,1.35,10.4)` |
| P3 | `p3_from_a_to_b.png` | `(0,1.42,6.5)` → `(0,1.3,14.0)` |
| P3 | `p3_from_b_to_a.png` | `(0,1.42,13.5)` → `(0,1.3,6.0)` |
| P3 | `p3_doorway_side.png` | `(2.6,1.42,7.6)` → `(0,1.35,10.4)` |
| P4 | `p4_from_a_to_b.png` | `(0,1.42,8.5)` → `(0,1.3,16.0)` |
| P4 | `p4_from_b_to_a.png` | `(0,1.42,15.5)` → `(0,1.3,8.0)` |
| P4 | `p4_doorway_side.png` | `(2.6,1.42,9.6)` → `(0,1.35,12.4)` |

### What I saw (description only; no appearance judgement)

- `p1_from_a_to_b.png`: a wall of yellow-green chevron wallpaper fills the
  frame; centered in it is a rectangular doorway with a light horizontal band
  near the top. Through the opening is a carpeted room with similar wallpaper.
  The near floor is a linear-patterned carpet.
- `p1_from_b_to_a.png`: facing back through the opening from the wider chevron
  room, which has dark ribs in its ceiling. Inside the far room are two light
  vertical panels flanking the view, a horizontal light strip above, and
  carpet on the floor.
- `p1_doorway_side.png`: an angled view along the wall with the doorway set into
  it, a dark-ribbed ceiling overhead, a baseboard running along the right wall,
  and carpeted floor on both sides; the far room's wallpapered wall shows
  through the opening.
- `p2_from_a_to_b.png`: chevron wallpaper on both sides of a centered rectangular
  doorway with a bright horizontal panel above it; the far room has a matching
  carpeted floor and wallpaper. The ceiling ribs align across the seam.
- `p2_from_b_to_a.png`: viewed from the chevron-cross room back toward the
  chevron room; a rectangular opening with a light strip above, carpet floor,
  and a small lit element in the far room. The two wall planes meet flush at the
  doorway.
- `p2_doorway_side.png`: an angled seam view with a grid ceiling and light
  strips above, carpeted floor on both sides, and continuous wall planes at the
  opening; no ledge is visible where the walls meet.
- `p3_from_a_to_b.png`: the near room has dark walls with vertical light
  columns and a lighter patterned floor; through the bright-trimmed doorway the
  far room shows a darker interior, a yellow-gold rectangular panel, horizontal
  bright rails, and a header band near the top of the opening.
- `p3_from_b_to_a.png`: from the tall nested-light room (dark glossy floor,
  vertical light strips on the walls) looking back through the doorway at the
  shorter room's lighter carpet and chevron wall, with a light horizontal panel
  above the opening. The two floor surfaces differ in texture but meet at the
  same level.
- `p3_doorway_side.png`: an angled seam view where the near room's lighter
  carpet and dark framed wall meet the far room's dark glossy floor and portal
  frames; a ceiling grid with light strips is above. The far wall plane is set
  back from the near one, leaving a visible ledge beside the opening.
- `p4_from_a_to_b.png`: from the tall nested-light room (dark floor, chevron
  walls with vertical strips) through the doorway into the shorter chevron
  room, whose lighter carpet, chevron wall, light horizontal panel, pale
  vertical panel on the right, and ribbed dark ceiling are visible above the
  opening.
- `p4_from_b_to_a.png`: from the shorter chevron room back into the taller
  nested-light room; the near floor is lighter carpet and through the bright
  doorway are a dark glossy floor, dark walls with vertical light strips, and
  white horizontal rails. A dark band with ribs sits above the opening.
- `p4_doorway_side.png`: an angled seam view with the narrower chevron wall
  plane ending against the wider dark wall of the nested-light room; the near
  dark glossy floor and the far lighter carpet meet at one level, and a light
  ribbed ceiling is overhead with a darker ceiling visible through the opening.

The ledges/ceiling discontinuities described are the width and height mismatches
quantified above; traversal was not blocked in any pair. Appearance is not
approved or judged here — the operator must review the PNGs.

## Verification

| Command | Result |
|---|---|
| `godot4 --headless --path godot_walk --script res://evidence/2026-11-19-issue-283-variant-pairs/test_variant_pairs.gd` | exit 0, `ISSUE283_VARIANT_PAIR_TESTS_PASSED` |
| `python3 -m pytest -q godot_walk/scripts` | `1582 passed, 5 skipped, 94 subtests passed in 293.06s (0:04:53)` |
| `python3 godot_walk/scripts/register_video_sources.py validate` | `{"valid": true, "registered_count": 13}` |
| `python3 -m ruff check .../run_capture_guarded.py` | `All checks passed!` |
| Guarded Vulkan capture (`DISPLAY=:1`) | `return_code=0`, twelve 1152x648 PNGs |

## What this test does not show

- **Appearance / feel**: agents cannot judge appearance. Captures are described
  but not approved; the operator must review them.
- **Scale calibration**: `scale_calibrated` stays false. All geometry is in
  declared design units; no measured reconstruction scale is established.
- **Lighting continuity**: four authored environments are combined; no claim is
  made that lighting, shadows or post-processing match across a doorway.
- **Audio**: no audio was rendered, probed or compared.
- **Source-video connectivity**: the connections are authored game connections;
  nothing here establishes that any two source video intervals were adjacent
  in the real location.
- **Registration / integration / tested status**: `registration_accepted` stays
  false, sockets stay `untested`, `layout_eligible` stays false; no integration
  decision or map was produced.
- **Physics beyond the scripted path**: traversal is a single straight line on
  `x = 0`; it does not explore every angle, jump, sprint or long dwell. The
  ceiling/width step is above or beside the 2.0 m clear aperture.

## What a catalog change would be, if the operator decides a pair is tested

Not done here. For each approved pair, a new catalog version (never an edit to
an existing entry) would:

1. append a `tested_connector_pairs` entry with a per-pair `id`,
   `from = {module_id, socket_id: "south"}`,
   `to = {module_id, socket_id: "north"}`,
   `compatibility_type: "level_doorway_2m_v1"`,
   `mechanical_status: "tested_pair"`, `operator_status: "review_pending"`,
   and evidence citing this folder's `traversal.json` and capture manifest:
   - P1: `chevron_v2_175_south__chevron_v2_176_north`
   - P2: `chevron_v2_176_south__chevron_cross_v2_177_north`
   - P3: `chevron_cross_v2_177_south__nested_light_v2_173_north`
   - P4: `nested_light_v2_173_south__chevron_v2_175_north`
2. change `test_status` of the two involved sockets from `untested` to `tested`
   and record the new pair id in the corresponding `tested_connectors` lists;
3. leave `layout_eligible` false until a separate operator integration step,
   and leave `registration_accepted` and `scale_calibrated` false;
4. append an immutable snapshot / library index for the new catalog version and
   register through the existing path.

This report makes none of those changes. P2 is the geometrically cleanest pair
(matching widths 16.0 and matching heights 4.2); P3 carries the 4.2 vs 4.8
ceiling step and a 3.0 m-per-side width mismatch; P4 carries the largest
ceiling step (1.0 m). The operator decides tested status for each.

## Files added

`variant_pairs_contract.json`, `variant_pairs_scene.gd` / `.tscn`,
`test_variant_pairs.gd`, `capture_variant_pairs.gd`, `run_capture_guarded.py`,
`COMMANDS.md`, `mechanics/traversal.json`, `captures/` (twelve PNGs +
`capture_manifest.json`), `capture_resource_run.json`, and this `REPORT.md`.
