# Issue 232 — Maze overlay M2: follower lamp state and flicker

Date: 2026-11-13
Parent: #223 (runtime overlay for the #209 design), under #169
Design source: `docs/MAZE_DYNAMICS_PROPOSAL.md`, section 11.1 item 2, with
sections 5.2-5.5, 9.1-9.6 and the operator decisions in section 10.
Dependency: M1 / #231 (`maze_mutation.py`) is closed and present on `main`.

Status: implementation and automated checks complete. Operator visual review of
the captures, the operator walk and the listen check are pending. A render or a
headless pass is not approval.

## What changed

- `godot_walk/scripts/maze_follower.py` (new) is the M2 headless reference:
  - `visible_cells` / `cell_is_hidden`: a bounded graph walk through open and
    `closed_visible` openings. The provisional depth is two doorway hops; void
    cells are never entered. This is the cheap proxy from §5.3/§9.6, not a
    camera test.
  - `lamp_state_record` and `lamp_flicker_record`: the per-cell override
    records. An edit stores the whole cell lamp list under
    `cell_overrides[cell_id]["lamp_state"]` or `["lamp_flicker"]`, so a later
    edit in the same cell continues the previous record instead of losing
    earlier lamps.
  - `select_lamp_target`: prefers cells passed 1-3 rooms ago, then degree 2 or
    more, then a stable keyed rank; excludes the current cell, spawn, exit,
    module, landmark, last-edited cell and every visible cell.
  - `plan_lamp_edit`: fires only on a cadence beat (5, 9, 13, ... from M1),
    drops the beat without an event when no hidden target exists, and derives
    the edit from the keyed event draw
    `sha256("<seed>:<attempt>:<event_index>:follower:gmap-0.13.0:<cell>:lamp-edit")`.
  - `FollowerController`: appends `room_entered` triggers, folds the accepted
    `follower_edit` into the M1 overlay and exposes the effective lamp state.
- `godot_walk/scripts/maze_visibility.gd` (new) is the runtime visibility proxy
  with the same graph rule.
- `godot_walk/scripts/maze_follower_runtime.gd` (new) is the live driver. It
  follows the player's cell, counts distinct entries, selects a hidden target on
  the same beats and applies the same keyed choice as the Python reference. Its
  in-memory `cell_overrides` and `edit_events` are the M2 override records. It
  does nothing while the player's physics processing is off, so the existing
  capture harnesses that freeze the player stay deterministic.
- `godot_walk/scripts/maze_light_controller.gd` (new) is the runtime light
  controller. It records the pristine lamp material, tier, colour temperature
  and node paths at assembly time, then replaces only one lamp's material and
  OmniLight. `on`, `flicker` and `dead` are supported, as is a folded override
  record (`lamp_state` + `lamp_flicker`).
- `godot_walk/scripts/generative_map_assembly.gd` adds the narrow runtime
  points promised in §9.4: `set_cell_light`, `apply_cell_light_override`,
  `cell_light_state`, `cell_light_states` and `cell_lamp_flicker_seeds`, and
  starts one `MazeFollowerRuntime` after the player in the walkthrough. Library
  module and landmark rooms refuse the edit; their light is baked or frozen.
- `godot_walk/scripts/test_maze_follower.py` (new) covers the visibility gate,
  both lamp classes, cadence, re-entry, target exclusions, replay determinism
  and the unchanged map file.
- `godot_walk/scripts/test_issue232_follower_edit.gd` (new) is the headless
  runtime check: five distinct rooms, a lamp edit applied while the target is
  hidden, re-entry twice, flicker/on/dead, override replay, one changed cell,
  unchanged geometry and an unchanged map hash.
- `godot_walk/scripts/capture_issue232_follower_edit.gd` (new) renders the
  before/after lamp captures.

No committed map, fill, SVG, shape-room version, library scene, catalog file,
`project.godot`, `player.gd`, palette or material-language file was edited.
No metadata or layer file was made binary. The map stays UTF-8 JSON text.

## Behaviour

The first visible edit is a lamp flip in a room the player has already left.
On seed 279 the walk enters `c00, c01, c02, c04, c03`; at the fifth distinct
visit `c03`, `c04` is outside the two-hop proxy view, so the live driver edits
one of its lamps (`c04[2]`, on -> flicker). Re-entering `c04` shows the new state
and does not re-fire the beat. A later trigger without a new distinct cell never
consumes a beat. If no hidden eligible target exists, the beat is dropped and no
mutation record is written, per §5.3.

The generated-room runtime applies the state in place. Geometry, collision,
room transforms and every other cell are untouched. The committed map file hash
is unchanged.

## Checks run

Python:

```bash
python3 -m pytest -q godot_walk/scripts/test_maze_follower.py \
  godot_walk/scripts/test_maze_mutation.py
ruff check godot_walk/scripts/maze_follower.py \
  godot_walk/scripts/test_maze_follower.py
```

Result: 27 passed; ruff clean. The full suite also passed:
`python3 -m pytest -q godot_walk/scripts` — 1318 passed, 5 skipped,
58 subtests passed in 418.85 seconds.

Godot headless (Godot 4.6.3.stable.official.7d41c59c4):

```bash
for seed in 1 2 3 32 279; do
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue232_follower_edit.gd -- \
    --map=res://room_catalog/generative_maps/gmap-${seed}-gmap-0.13.0.json \
    --rooms=res://room_catalog/shape_rooms/gmap-${seed}-gmap-0.13.0/index.json
done
```

Result: `ISSUE232_FOLLOWER_EDIT: PASS` for all five seeds. Seed 279 recorded
`route=5 target=c04 lamp=2 before=on after=dead changed_cells=1/14
live_edit=lamp_state@c04 map_sha256=unchanged`. The live driver's first edit
reproduces the Python reference target and state, and two re-entries leave the
edit in place without a second event. Its full report is tracked at
`godot_walk/evidence/2026-11-13-issue-232/runtime_gmap-279.json`.

Regression checks on the changed assembly:

```bash
godot4 --headless --path godot_walk \
  --script res://scripts/test_issue183_shape_rooms.gd -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.13.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.13.0/index.json
godot4 --headless --path godot_walk \
  --script res://scripts/test_issue204_reverb.gd -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.13.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.13.0/index.json
```

Both pass (`ISSUE183_SHAPE_ROOMS: PASS`, `ISSUE204_REVERB: PASS`).

Map hash:

```text
sha256 godot_walk/room_catalog/generative_maps/gmap-279-gmap-0.13.0.json
= 51d296d0113d2c01852845389cbc6d64ac85f232e04d0cf7a8116e9bd05e995c
```

The Python and Godot checks read the same digest before and after the edits.

## Captures (local, generated; not committed)

Command:

```bash
godot4 --path godot_walk \
  --script res://scripts/capture_issue232_follower_edit.gd -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.13.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.13.0/index.json \
  --out=res://evidence/2026-11-13-issue-232/captures \
  --cell=c04 --lamp=2 --distance=3.5 --pitch=0.70
```

Output directory (git-ignored by the evidence capture rule):
`godot_walk/evidence/2026-11-13-issue-232/captures/`

| File | State |
|---|---|
| `before_c04_02_on.png` | target lamp `c04[2]` on, before the edit |
| `after_c04_02_dead.png` | the same lamp dead |
| `after_c04_02_on.png` | the lamp restored on |
| `after_c04_02_flicker.png` | the same lamp flickering with seed 424242 |
| `manifest.json` | capture metadata |

The before/dead pair has the same camera, room and neighbouring lamps; only the
target lamp changes. The image difference is measurable (mean RGB difference
2.74/1.88/0.94; max 255/211/133), and the dead frame is visibly dimmer. These
files are local evidence only; this text log is the tracked record.

## Operator steps pending

1. **PENDING: operator visual review of the captures.** Judge the dead/on/
   flicker tells and whether the change reads as an out-of-sight edit rather
   than a glitch. This run does not claim that review.
2. **PENDING: operator walk and listen.** The cadence constants, the two-hop
   visibility proxy and the flicker readability need the M14 tuning walk; none
   of Q9/Q11/Q12/Q13 is changed here.
3. **PENDING: live walk confirmation.** The driver is attached to the
   walkthrough, but only the operator can confirm on foot that the first edit
   reads as out-of-sight and that the two-hop proxy is not too generous. This
   run does not claim that walk.

No operator approval, registration acceptance or scale calibration is claimed.
`registration_accepted` and `scale_calibrated` remain false.
