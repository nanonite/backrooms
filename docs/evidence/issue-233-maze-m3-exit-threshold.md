# Issue 233 — Maze overlay M3: exit threshold and run end card

Date: 2026-11-13
Parent: #223 (runtime overlay for the #209 design), under #169
Design source: `docs/MAZE_DYNAMICS_PROPOSAL.md`, section 11.1 item 3, with
sections 6.4, 9.1, 9.4, 9.8 and the operator decisions in section 10.
Dependencies: M1 / #231 (`maze_mutation.py`) and M2 / #232 (follower lamp) are
closed and present on `main`.

Status: implementation and automated checks complete. Operator visual review of
the threshold and the end card is pending, and the operator walk is pending. A
render or a headless pass is not approval.

## What changed

- `godot_walk/scripts/maze_exit.py` (new) is the Python reference:
  - `passage_pairs` / `adjacency`: the undirected level/ramp graph over
    non-void cells, excluding one-way drops. This is the graph the §4.5.9
    feasibility measurement used.
  - `reroll_targets`: every 3-8-cell departed component, one record per
    crossing direction. It reproduces the measurement's 11 directions across
    the five committed maps, and seed 3's zero.
  - `select_exit`: the seed-keyed static exit. Placement is, in order: outside
    every target, leaf, smallest total removed target size, generated room,
    then `sha256("<seed>:<attempt>:exit:gmap-0.13.0:<cell_id>")`. A map that
    carries a valid `exit` layer keeps its recorded cell.
  - `reroll_eligibility`: the post-exit map. It marks the exit-containing
    targets `exit_inside` and the threshold passage `exit_threshold_door`.
  - `plan_run`: selects the exit first, then evaluates eligibility. The
    selection function never consumes the post-exit map.
  - `run_end_spec`, `end_card`, `ExitRun`: one `exit_entered` trigger and one
    forced `run_end` mutation per run; the card is derived from the log and has
    `actions: []`.
- `godot_walk/scripts/maze_exit.gd` (new) is the GDScript twin of the selection
  and eligibility logic. It uses the same graph, tiers and keyed rank and reads
  the same recorded-layer field.
- `godot_walk/fixtures/maze_exit_v1.json` (new, text) is the shared fixture for
  the five committed `gmap-0.13.0` maps. Both the Python test and the Godot test
  compare against it, so the two implementations cannot silently diverge.
- `godot_walk/scripts/maze_exit_threshold.gd` (new) builds the original bright
  threshold and clean test-chamber treatment:
  - a bright frame, threshold plate, lit sign and an open leaf at the selected
    doorway;
  - a clean ceiling panel and light bar, a bright floor runner and line;
  - a cool-white threshold light and room fill light;
  - a palette-preserving emission lift on the room's existing wall, floor and
    ceiling materials. The duplicate keeps the base texture path and albedo, so
    the issue-192 palette check still sees the committed palette. No existing
    material, texture or scene file is edited, and every added material is an
    original solid colour.
- `godot_walk/scripts/maze_end_card.gd` (new) is the end card: title, seed,
  rooms visited, edits, re-rolls and a footer. It has no button, link or other
  progression affordance.
- `godot_walk/scripts/maze_exit_runtime.gd` (new) follows the player's cell,
  keeps the in-memory run log, copies the M2 follower edits into it and ends the
  run once when the exit cell is entered. It disables the follower runtime at
  that point and shows the card once.
- `godot_walk/scripts/test_maze_exit.py` (new) covers determinism, the fixture,
  the measured target map, ordering, exit exclusion from follower edits, one
  crossing, one card, counters, no progression, replay, the recorded layer and
  unchanged map bytes.
- `godot_walk/scripts/test_issue233_exit_threshold.gd` (new) is the headless
  runtime check. It compares the live selection to the fixture, checks the
  threshold treatment and its render layer, runs a nine-cell route (the follower
  edits twice and never targets the exit), crosses the exit, and checks one
  `run_end`, one `exit_entered`, one card, the counters and the unchanged map
  hash.
- `godot_walk/scripts/capture_issue233_exit_threshold.gd` (new) renders the
  approach, inside-threshold, room-wide and end-card views.
- `godot_walk/scripts/generative_map_assembly.gd` selects and decorates the
  exit during `assemble`, exposes `exit_cell_id`, `exit_record_data` and
  `exit_threshold_visual`, and starts one `MazeExitRuntime`.
- `godot_walk/scripts/maze_follower_runtime.gd` reads the selected exit cell and
  excludes it from lamp-edit targets. M2's Python controller already accepted an
  `exit_cell`; this wires the live runtime to it. The assembly also refuses
  `set_cell_light` and `apply_cell_light_override` on the exit cell, so the
  exclusion holds at the runtime boundary, not only in the follower selector.

No committed map, fill, SVG, shape-room version, library scene, catalog file,
`project.godot`, `player.gd`, palette or material-language file was edited. No
metadata or layer file was made binary. The map stays UTF-8 JSON text.
`registration_accepted` and `scale_calibrated` remain false.

## Selection

The five committed maps carry no exit layer, so the runtime derives the exit
from the seed. The selection is stable: the same map document always yields the
same cell, port and keyed rank, and the shared fixture asserts it in both
languages.

| Seed | Exit cell | Port | Approach cell | Threshold id | Leaf | Outside all targets | Removed target cells | 3-8 directions | Eligible after exit |
|---:|---|---|---|---|---|---:|---:|---:|---:|
| 1 | `c11` | `c11:p0` | `c03` | `c03|c11` | yes | yes | 0 | 1 | 1 |
| 2 | `c04` | `c04:p0` | `c02` | `c02|c04` | yes | yes | 0 | 1 | 1 |
| 3 | `c03` | `c03:p0` | `c02` | `c02|c03` | yes | yes | 0 | 0 | 0 |
| 32 | `c02` | `c02:p0` | `c01` | `c01|c02` | yes | no (1 target) | 6 | 5 | 4 |
| 279 | `c09` | `c09:p0` | `c07` | `c07|c09` | yes | no (1 target) | 8 | 4 | 3 |

Every chosen exit is a walkable leaf in the level/ramp graph, so the bright
threshold is unambiguous: entering the room crosses the one doorway. Seeds 1-3
keep the exit outside every 3-8 target. Seeds 32 and 279 have every generated
cell inside at least one target; the chosen leaf removes one direction each and
leaves the other pool directions eligible:

- Seed 32 removes the 6-cell direction (`c00` -> `c01`); the 8-cell direction
  (2 in-tolerance candidates in §4.5.9) stays eligible.
- Seed 279 removes the 8-cell direction (`c11` -> `c02`); the 6-cell and 5-cell
  directions (2 in-tolerance candidates each) stay eligible. This is the
  interaction §9.1 warned about, and the post-exit map records it instead of
  hiding it.

The order is enforced by `plan_run`: `select_exit` sees only the pre-exit target
map, and `reroll_eligibility` is called after the cell is fixed. A test asserts
that the chosen exit's `targets_hit` and `removed_cells` match the pre-exit map
and that the post-exit eligible directions never contain the exit.

## Run end

Crossing the exit cell appends one `exit_entered` trigger and one forced
`run_end` mutation. The runtime and the Python driver both stop at that point:
a second entry or a second `force_end` call is inert, and the card is shown once.
The card shows the seed, rooms visited, edits and re-rolls from the log; it has
no next seed, next level, restart or continue action. The `run_end` target is the
static exit cell and the stable threshold id, never a re-roll door.

## Checks run

Python:

```bash
ruff check godot_walk/scripts/maze_exit.py \
  godot_walk/scripts/test_maze_exit.py
python3 -m pytest -q godot_walk/scripts/test_maze_exit.py \
  godot_walk/scripts/test_maze_follower.py \
  godot_walk/scripts/test_maze_mutation.py
python3 -m pytest -q godot_walk/scripts
```

Result: ruff clean; the focused set is 39 passed; the full suite is
1330 passed, 5 skipped, 58 subtests passed in 415.12 seconds (exit 0).

Godot headless (Godot 4.6.3.stable.official.7d41c59c4), all five seeds:

```bash
for seed in 1 2 3 32 279; do
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue233_exit_threshold.gd -- \
    --map=res://room_catalog/generative_maps/gmap-${seed}-gmap-0.13.0.json \
    --rooms=res://room_catalog/shape_rooms/gmap-${seed}-gmap-0.13.0/index.json \
    --out=res://evidence/2026-11-13-issue-233/runtime_gmap-${seed}.json
done
```

Result: `ISSUE233_EXIT_THRESHOLD: PASS` for all five seeds. Each run selected
the fixture's exit, built 13 threshold meshes and 2 lights, played a nine-cell
route with two follower edits (none on the exit), logged one `run_end` and one
`exit_entered`, showed one card with zero actions, and left the map hash
unchanged. The per-seed reports are tracked at
`godot_walk/evidence/2026-11-13-issue-233/runtime_gmap-*.json`.

Regressions:

```bash
for seed in 1 2 3 32 279; do
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue183_shape_rooms.gd -- ...
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue204_reverb.gd -- ...
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue232_follower_edit.gd -- ...
done
```

Result: `ISSUE183_SHAPE_ROOMS: PASS` (including the issue-192 palette check,
257 surfaces and zero mismatches on seed 279), `ISSUE204_REVERB: PASS` and
`ISSUE232_FOLLOWER_EDIT: PASS` for all five seeds. The threshold treatment is
additive, so the base room's palette and light-layer checks stay valid.

`test_issue201_elevation.gd` still reports the pre-existing ramp-step/wall
coplanar failures on seeds 1, 32 and 279. The same failures are present at
`HEAD` before this slice (verified in a throwaway worktree): they name the
generated `RampStep_*` and `Wall_*` nodes, not any M3 node, and the decoration
does not add ramp or wall geometry. It is recorded here as an existing issue, not
a regression from #233.

Map hashes before and after every run:

```text
dacd388ef9780bf1d843f9078b7b8679e476be28df0e0464bb7778218ce2c7f3  gmap-1
07c1cbb219004d1533021ff5d7c5fe18b41d28ed8b01f4ce69535e1c0db8c465  gmap-2
307c8ab769ecf0ed7d13b44176e3607e28816daa2a7489e070b1b0aa4ab70591  gmap-3
087d24978dc4b7e5986dd881d491d43bc2dc4f49652f6e4f25e848e6abbdd7d1  gmap-32
51d296d0113d2c01852845389cbc6d64ac85f232e04d0cf7a8116e9bd05e995c  gmap-279
```

Seed 279's report records the same digest in `map_sha256_before` and
`map_sha256_after`.

## Captures (local, generated; not committed)

Command (repeated per seed, `seed-<n>` output folder):

```bash
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan \
  --resolution 960x540 \
  --script res://scripts/capture_issue233_exit_threshold.gd -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.13.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.13.0/index.json \
  --out=res://evidence/2026-11-13-issue-233/captures/seed-279
```

Output directories are git-ignored by the evidence capture rule:
`godot_walk/evidence/2026-11-13-issue-233/captures/seed-{1,2,3,32,279}/`.

Each folder has `exit_approach.png`, `exit_threshold_inside.png`,
`exit_room_wide.png`, `run_end_card.png` and `manifest.json`.

| Seed | View | SHA-256 | Observation |
|---:|---|---|---|
| 1 | approach | `ef60eefd1f5a7527142757bb4e306127f9f214c100b4cd4de7210fa1e3c523b1` | Green backrooms wall outside; the white/cyan threshold opens into a bright room, with the floor plate and open leaf visible. |
| 1 | inside | `d12dadaa836f875776c491690c12745ebdb9ca5f064aab73a081beb8fbfe4008` | Bright room and ramp, glowing frame, dark maze beyond. |
| 1 | room | `a2b7c908ba292caeea825bbfce7c600f286a181737ce88248c2f3f3eaa344907` | Clean ceiling panel, bright walls, floor runner. |
| 1 | card | `3a3d9046642e4d381fbab376872a843ddd11d7e7a0c3a64b73eafdec5cbd8ef4` | End card layout, no actions. |
| 2 | approach | `da658b3818f7c5eea3c469bf7c037fbc32c8a4048b6e5f91e5937fa6fa8c9f0d` | Same threshold language on a yellow room. |
| 2 | inside | `4144d60705398dc66377e62e11362cb2af06f12a458c6124b0cb69d4ab46b583` | Clean bright room; the ramp and frame read. |
| 2 | room | `d2d43bab5376f3e4c221fdd64355ef49b0c774c8019881cbca973c42826eb6bd` | White ceiling/runner and bright walls. |
| 2 | card | `43cd5c5b0bb485d10f95fc54105ee77e2dcb5fab7ae7f9a86b794b0ae8de9317` | End card layout. |
| 3 | approach | `60d1be5e264ed299d4c4504d80501e777936a17eb7445235275962b8935d6e2a` | Bright door from the corridor. |
| 3 | inside | `1b6ce12a773d23fc6671bdc2593fddd2821451e534ef56b2a03c3d4ebcb93478` | Ramp and open leaf; clear cool-white threshold. |
| 3 | room | `49e5604a09842c16b7264a7fd183ee5ce213a2ea330e85e69fd487b812acaf1a` | Clean bright room with the existing yellow palette lifted, not replaced. |
| 3 | card | `806c52da0221cd012d00c63a2adb245332f0758fcbb057763e8200c154370fa3` | End card layout. |
| 32 | approach | `f84a189a1292e79192cdb6585b3b4ebea664e02e7d714e7432cd9f404a2d1cef` | Bright threshold through the dark wall. |
| 32 | inside | `0ffacb0b73f5b8c1c2679e43e7fe6a7b506f003734c2081ff1ac65e0ea241407` | White ceiling panel, bright floor runner. |
| 32 | room | `169aa3240e67af5cc8e0329089731734d3a9e4a0e540cdb0d08e6697457a73b6` | Clean room treatment. |
| 32 | card | `8a2c0c527c7917795aad42b7c86a1463368749e12a4a599f8ef50c9bfdf8d72b` | End card layout. |
| 279 | approach | `d5dd858d841db824f627f3bb884502ac36ab69b0f5dfaba2441d896617491176` | Cyan/white frame in the dark corridor; the room is unmistakably the bright "out". |
| 279 | inside | `4f717125099854dfdc27c9fe0a0f63cd76ede9650ad134f267659c1c97bb9f58` | Bright walls, ceiling panel, ramp and open leaf; the dark maze is visible beyond. |
| 279 | room | `0e4504f777abea96f4d74d9da25d8381cf72e537a1cb9c65254ceb13287e7bcf` | Clean bright room, consistent with the other four seeds. |
| 279 | card | `559e7e15ca83056c2d73b71bc5367fbe6ccc37a7e7d0891af89e94a659148f11` | End card: seed 279, rooms visited 2, edits 0, re-rolls 0, no actions (capture forced the end before walking). |

These files are local evidence only; this text log is the tracked record. The
threshold reads consistently across the five seeds: the same cyan frame, bright
plate, white open leaf, ceiling panel and cool fill light, with the base room
palette lifted rather than replaced. The capture ran with the player frozen, so
the end-card counters are 2/0/0; the headless runtime check exercises the edit
counters with two follower edits.

## Operator steps pending

1. **PENDING: operator visual review of the threshold and room treatment.**
   Judge the bright-door read, the cyan/white palette, and whether the room is
   clean and bright without looking like a copied third-party asset. This run
   does not claim that review or style acceptance.
2. **PENDING: operator visual review of the end card.** Judge the wording,
   contrast and whether the card reads as the whole escape loop with no expected
   next action.
3. **PENDING: operator walk.** Confirm on foot that the exit is legible from the
   approach side, that entering the bright room reads as crossing the threshold,
   that the run ends once, and that the card appearing with no progression
   action is the intended stop. Agents cannot walk; only the operator can
   confirm this.

No operator approval, registration acceptance or scale calibration is claimed.
`registration_accepted` and `scale_calibrated` remain false.
