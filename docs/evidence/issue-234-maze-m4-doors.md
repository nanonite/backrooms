# Issue 234 — Maze overlay M4: door state and lock-behind

Date: 2026-11-13
Parent: #223 (runtime overlay for the #209 design), under #169
Design source: `docs/MAZE_DYNAMICS_PROPOSAL.md`, section 11.1 item 4, with
sections 4.4, 4.6, 6.4, 6.5, 9.5 and the operator decisions in section 10.
Dependencies: M1 / #231 (`maze_mutation.py`) and M3 / #233 (static exit) are
closed and present on `main`.

Status: implementation and automated checks complete. Operator visual review of
the closed and open leaf, and the operator walk, are pending. A capture or a
headless pass is not approval.

## What changed

- `godot_walk/scripts/maze_doors.py` (new) is the Python reference:
  - `plan` derives one record per traversable doorway from the committed map's
    `edges` and the generated shape-room specs. The map's own `doors[]`
    placeholders and bytes are never edited.
  - Each crossing records the **departed** component (the side the player
    leaves) and its 3-8 cell size, matching §4.6. The target is a bridge only
    when removing the doorway disconnects that side.
  - `leaf_fit` decides whether one vertical leaf can fill the port. A level port
    fits when both sills are zero. A ramp port fits only when the lower side
    records a sill and a ramp whose rise lands exactly at that sill, so the leaf
    sits on the top landing without rebuilding the ramp. A drop port never
    fits. A library doorway has no leaf and is skipped.
  - `lock_spec` / `open_spec` build the `door_lock` / `door_unlock` mutations;
    both use change class `state` with `open` / `latched`. `DoorRun` records the
    room entry, latches an eligible crossing, opens from either side, and
    replays a saved log. `fold_states`, `state_hash`, `port_states`,
    `exit_reachable` and `door_counters` complete the headless contract.
- `godot_walk/scripts/maze_doors.gd` (new) is the GDScript twin of the registry,
  leaf fit, crossing eligibility, state fold and canonical state hash. The
  Python and Godot tests read the same fixture, so the two cannot silently
  diverge.
- `godot_walk/fixtures/maze_doors_v1.json` (new, text) is the shared fixture for
  the five committed `gmap-0.13.0` maps: the compact plan projection and a
  lock/unlock/lock replay per seed.
- `godot_walk/scripts/maze_door_leaf.gd` (new) builds the procedural leaf:
  a header-hung panel with a real `StaticBody3D` collider at the doorway plane,
  a palette-material inset panel, handle and latch bolt. It is built only when
  a door first latches, so a walkthrough without a crossing looks exactly like
  the committed opening. The leaf reuses the room's own `trim` and `dark`
  palette materials; no texture, mesh, scene or third-party asset is added.
  Manual open swings the leaf into the departed side, away from the player.
- `godot_walk/scripts/maze_door_runtime.gd` (new) follows the player's cell
  transitions, latches an eligible crossing behind the player, records one
  `door_lock`, and opens the nearest latched door from the player's side with
  `E` or the `open_door` API. It refuses a latch that would remove the exit
  route or expose the departed side, and it does nothing after the run ends.
  `restore_log` replays the door subset of a saved log.
- `godot_walk/scripts/generative_map_assembly.gd` builds the door registry
  after the static exit and starts one `MazeDoorRuntime`; it exposes
  `door_plan_data`, `door_state`, `door_state_snapshot` and `open_door`.
- `godot_walk/scripts/maze_exit_runtime.gd` copies the door events into the run
  log at run end and disables the door runtime. The end card's counters and
  actions are unchanged.
- `godot_walk/scripts/test_maze_doors.py` (new) covers the fixture, departed-side
  semantics, library/drop skipping, ramp fit and its missing-landing negative,
  one latch per crossing, overlay folding, occlusion, exit reachability, manual
  open from the current side, save/restore and unchanged map bytes.
- `godot_walk/scripts/test_issue234_doors.gd` (new) is the headless runtime
  check: it compares the live plan to the fixture, crosses a library doorway and
  an ineligible generated doorway without locking, crosses an eligible door,
  checks the closed leaf's visibility and ray occlusion, opens it from the
  current side, restores the saved log, verifies the exit threshold never
  latches, ends the run at the exit and checks the unchanged map hash.
- `godot_walk/scripts/capture_issue234_doors.gd` (new) renders the closed,
  latched-detail and open states.

No committed map, fill, SVG, shape-room version, library scene, catalog file,
`project.godot`, `player.gd`, palette or material-language file was edited. No
metadata or layer file was made binary. The map stays UTF-8 JSON text.
`registration_accepted` and `scale_calibrated` remain false.

### Leaf geometry choice

The leaf is additive runtime geometry in the M3 pattern rather than a new
committed shape-room version. That choice keeps every committed shape-room
record, room hash, map hash and library scene valid; a new shape-room version
would require regenerating and recommitting the five seeds' records for no
runtime benefit. The proposal's §9.5 "new shape-room version" and this runtime
leaf implement the same mesh and collider contract; a later offline shape-room
version can bake the same leaf without changing the overlay state.

### Interaction with the M3 target labels

M3's `maze_exit.reroll_targets` stores the component on the **arrival** side
under the `from_cell -> to_cell` label. §4.6 defines the re-roll target as the
**departed** side. M4 computes its own departed component for every crossing so
a latch behind the player is the side the player actually left. The M3 exit
record (`cell_id`, `threshold_id`, `port_id`) is consumed unchanged; no M3 file
or fixture is edited. This is a note for M5, which will need the same
departed-side reading when it consumes the re-roll eligibility map.

## Door registry per seed

`|doors|` counts every traversable `direct` doorway between walkable cells.
`leaf` counts the generated doorways whose port can carry the procedural leaf.
`eligible` counts crossing directions that pass the M4 structural contract:
leaf, bridge, 3-8 departed cells, no exit on the departed side, and not the
exit threshold or an exit-cell doorway.

| Seed | Doors | Leaf-capable | Library | Drops | Eligible crossings |
|---:|---:|---:|---:|---:|---|
| 1 | 16 | 12 | 2 | 2 | 1: `c03`-`c05`, `c05` -> `c03`, 5 cells |
| 2 | 16 | 15 | 1 | 0 | 1: `c03`-`c07`, `c07` -> `c03`, 4 cells (ramp) |
| 3 | 16 | 15 | 1 | 0 | 0 |
| 32 | 13 | 11 | 2 | 0 | 4: `c00`-`c01` (8), `c00`-`c03` (5), `c01`-`c05` (4), `c03`-`c08` (3, ramp) |
| 279 | 16 | 14 | 1 | 1 | 3: `c02`-`c11` (6), `c04`-`c06` (4), `c06`-`c11` (5, ramp) |

Seed 3 has no 3-8-cell bridge in either direction, so its runtime correctly
builds no leaf and latches nothing. The committed library doorways
(`c07|c13`, `c10|c12`, `c09|c13`, `c06|c12`, `c07|c12`) are reported in
`skipped_doors` with `library_doorway` and are never locked. The drop doorways
(`c01|c02`, `c02|c04`, `c00|c02`) are reported with `drop_door` and never get a
leaf. The exit threshold (`c03|c11`, `c02|c04`, `c02|c03`, `c01|c02`, `c07|c09`)
and every doorway incident to the exit cell are excluded.

## Latch, occlusion and open

Crossing an eligible door appends one `room_entered` trigger and one
`door_lock` mutation with `change: state open -> latched`. The live `doors[]`
view is `MazeDoorRuntime.snapshot()["doors"]`, which merges the derived registry
with the overlay's `door_overrides`; the committed map's own `doors[]` array is
never edited. The leaf is built in the `cell_a` room at the recorded doorway,
fills the opening with an opaque panel and a `StaticBody3D` collider, and the
departed side becomes invisible to the §9.6 visibility proxy through both
ports. A ray across the doorway hits the leaf body while it is latched and
misses it after the open.

Manual open is refused unless the player is in one of the door's two cells. It
appends one `door_unlock` with `state latched -> open`, disables the leaf
collider and swings the leaf into the departed side, never toward the player.
`restore_log` rebuilds the same states and leaf poses from the log; the state
hash is the canonical `"maze-door-state-0.1.0"` digest of the sorted threshold
states, computed identically in Python and GDScript.

The exit is checked on every latch with the closed door removed from the
level/ramp graph. Because an eligible crossing is a bridge and the exit is not
in the departed component, the exit stays reachable on the player's side. A
latch that would fail the check is logged as a rejected `door_lock` with
`exit_route_removed` and applied to no leaf; a visibility failure is logged as
`visible_target`. Neither case occurs on the five committed seeds.

## Checks run

Python:

```bash
ruff check godot_walk/scripts/maze_doors.py \
  godot_walk/scripts/test_maze_doors.py
python3 -m pytest -q godot_walk/scripts/test_maze_doors.py \
  godot_walk/scripts/test_maze_mutation.py \
  godot_walk/scripts/test_maze_follower.py \
  godot_walk/scripts/test_maze_exit.py
python3 -m pytest -q godot_walk/scripts
```

Result: ruff clean; the focused set is 51 passed; the full suite is
1342 passed, 5 skipped, 58 subtests passed in 409.39 seconds (exit 0). The
twelve new tests cover the plan fixture, departed-side targets, library/drop
skipping, the ramp missing-landing negative, one latch per crossing, overlay
folding, occlusion, exit reachability, manual open, save/restore and unchanged
map bytes.

Godot headless (Godot 4.6.3.stable.official.7d41c59c4), all five seeds:

```bash
for seed in 1 2 3 32 279; do
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue234_doors.gd -- \
    --map=res://room_catalog/generative_maps/gmap-${seed}-gmap-0.13.0.json \
    --rooms=res://room_catalog/shape_rooms/gmap-${seed}-gmap-0.13.0/index.json \
    --out=res://evidence/2026-11-13-issue-234/runtime_gmap-${seed}.json
done
```

Result: `ISSUE234_DOORS: PASS` for all five seeds. Seed 279 latched
`c02|c11`, hit the leaf with a ray while closed, missed it after open, kept the
exit reachable with the leaf closed, restored the saved log to the same
`053aecd384213b10196f52353c63376587eb2fdd684afd21a8d885e8fab8c5ca` hash, and
left the map hash unchanged. Seeds 1, 2 and 32 pass the same checks; seed 3
correctly reports zero eligible crossings, no leaf and an open exit.

Regressions on all five seeds:

```bash
godot4 --headless --path godot_walk --script res://scripts/test_issue232_follower_edit.gd -- ...
godot4 --headless --path godot_walk --script res://scripts/test_issue233_exit_threshold.gd -- ...
godot4 --headless --path godot_walk --script res://scripts/test_issue183_shape_rooms.gd -- ...
godot4 --headless --path godot_walk --script res://scripts/test_issue204_reverb.gd -- ...
```

Result: `ISSUE232_FOLLOWER_EDIT: PASS`, `ISSUE233_EXIT_THRESHOLD: PASS`,
`ISSUE183_SHAPE_ROOMS: PASS` (including the issue-192 palette check) and
`ISSUE204_REVERB: PASS` for all five seeds. The leaf is built only after a
crossing, so the load-time shape-room and palette checks see the unchanged
rooms.

Map hashes before and after every run:

```text
dacd388ef9780bf1d843f9078b7b8679e476be28df0e0464bb7778218ce2c7f3  gmap-1
07c1cbb219004d1533021ff5d7c5fe18b41d28ed8b01f4ce69535e1c0db8c465  gmap-2
307c8ab769ecf0ed7d13b44176e3607e28816daa2a7489e070b1b0aa4ab70591  gmap-3
087d24978dc4b7e5986dd881d491d43bc2dc4f49652f6e4f25e848e6abbdd7d1  gmap-32
51d296d0113d2c01852845389cbc6d64ac85f232e04d0cf7a8116e9bd05e995c  gmap-279
```

## Captures (local, generated; not committed)

Command (repeated per seed, `seed-<n>` output folder):

```bash
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan \
  --resolution 960x540 \
  --script res://scripts/capture_issue234_doors.gd -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.13.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.13.0/index.json \
  --out=res://evidence/2026-11-13-issue-234/captures/seed-279
```

Output directories are git-ignored:
`godot_walk/evidence/2026-11-13-issue-234/captures/seed-{1,2,3,32,279}/`.

| Seed | View | SHA-256 | Observation |
|---:|---|---|---|
| 1 | closed | `c2f110e5488d3b7ff2c89dcbff25856eff8775263b26ecd6940085cdf83a56da` | The leaf fills the level doorway from the player's side; the dark inset, handle and latch read as a sealed door. |
| 1 | latched detail | `ca31fcdbea8c9b36e0d192722472f103cd93862f45b252f4ca2f374e447029b7` | Close view of the closed panel and left-hand latch bolt. |
| 1 | open | `9dc06c3c7148c86f75821e556c4e1c33ebff421451cc77e54cca5be2a183a4db` | The doorway is clear; the leaf is parked on the departed-side wall. |
| 2 | closed | `121f949ace18f115435830a717d5f638634d558a3e16f89e440bc98f09d4e20a` | The ramp door leaf fits the port above the sill; the ramp is unchanged. |
| 2 | latched detail | `44b4f58036f8559054b557896fc0d21d52dccca62e5214266205f82d9bc3c52c` | The latch and panel at the top landing. |
| 2 | open | `a2c04485139664b67f8a5c273724c930af1b503e8403c30e54c568efda31e9f3` | The ramp and the clear opening survive the open. |
| 32 | closed | `332d61d1aa5bae7b36521ebb47808f868b375e0392de1137ee5fcfc98b069efd` | The 8-cell departed-side door closes; no pop is visible from the target. |
| 32 | latched detail | `b94105b8de3a4e70246db33aa5f96affcba1102aca8e4f5964ce74dbd1f67367` | The latch bolt and dark panel. |
| 32 | open | `cf7bafb44cda3d5e2908b921a2223d37afe1800491e78202d8ba940da2f4bad1` | The opening is clear and the leaf is parked on the departed side. |
| 279 | closed | `46c1daf3646843aa4a1be7c781fae15e430ee44e867b65977e0f2944255ceb2b` | The level door is sealed in the yellow room; the room beyond is fully occluded. |
| 279 | latched detail | `155acc53e3c5b0f5a72157616a22f64e993b0fd998e360f32a7323d5f8f00f50` | Close view of the closed panel and latch. |
| 279 | open | `fe0f98089a74735c9bf7f28e3a1fef8ae599c9e68df6feee4c4e03416bae80fa` | The doorway is clear; the leaf is parked on the departed-side wall and the room beyond is visible. |
| 3 | none | — | No eligible crossing; the capture writes a manifest with `eligible: 0` and no views. |

The manifests record `ray_closed: true` and `ray_open: false` for seeds 1, 2,
32 and 279. These files are local evidence only; this text log is the tracked
record. The closed leaf is dark against the palette wall and reads as a sealed
door; the open leaf is visible as the parked panel at the side of the opening.
The operator's style judgement is pending.

## Operator steps pending

1. **PENDING: operator visual review of the closed and open leaf.** Judge the
   dark inset panel, the handle and latch bolt, and whether the open leaf reads
   as the same door parked against the departed-side wall. This run does not
   claim that review or style acceptance.
2. **PENDING: operator walk.** Confirm on foot that an eligible door closes and
   latches behind the player, that the departed room is occluded, that `E` opens
   it from the current side, that the exit remains reachable with the door
   closed, and that a library doorway is never silently locked. Agents cannot
   walk; only the operator can confirm this.

No operator approval, registration acceptance or scale calibration is claimed.
`registration_accepted` and `scale_calibrated` remain false.
