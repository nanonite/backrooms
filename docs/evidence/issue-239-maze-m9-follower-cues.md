# Issue 239 — Maze overlay M9: follower presence cues

Date: 2026-11-13
Parent: #223 (runtime overlay for the #209 design), under #169
Design source: `docs/MAZE_DYNAMICS_PROPOSAL.md`, section 11 (M9 row), with
sections 5.6, 8.1-8.5 and the operator decisions in section 10 (Q4 and Q8).
Dependencies: M1 / #231 (`maze_mutation.py`) and M2 / #232
(`maze_follower.py`) are closed and present on `main`; M8 / #238 is closed and
provided the follower runtime that this slice extends.

Status: implementation and automated checks complete. The operator listen and
the operator walk are pending. A headless pass or a rendered capture is not a
listen check. No operator approval is claimed.

## What changed

- `godot_walk/scripts/maze_cues.py` (new) is the headless cue reference:
  - The four cue kinds from §8.2 are `follower_step`, `door_close`,
    `lock_click` and `door_reopen`. The three door cues bypass the optional
    cadence because §8.4 makes `door_close` and `lock_click` mandatory on an
    eligible door.
  - `follower_step` sources a cell one or two direct-passage hops from the
    player and prefers the two-hop ring. The source position is the envelope
    centre just above the cell floor. Step count is a keyed draw in 1-3.
  - Volume is a fixed distance rule, not a random mix guess:
    `volume_db = base - 6 * log2(max(distance, 1 m))`, clamped per cue kind.
    `follower_step` uses a -12 dB base and a -45 dB floor; door cues use -8 dB
    and -35 dB. The lowpass is fixed on the bus, so the cue never probes the
    source room's reverb.
  - `cue_cooldown_seconds` is a keyed draw in 8-15 seconds. `CueTrack` applies
    the first-four-rooms gate, the one-cue-per-edit rule, the quiet-player
    preference and the cooldown in the same order as the GDScript runtime.
  - `cue_event_spec` builds a `follower_cue` mutation with the auditable `cue`
    block (kind, target, position, graph distance, metre distance, volume,
    step count, delays, latch/tail samples, cooldown, visible-node count,
    player cell). The event has no `change` and no `rewire`, so the M1 fold
    treats it as inert.
- `godot_walk/scripts/maze_follower_audio.gd` (new) is the output layer:
  - Creates a dedicated `Follower` bus in code, with one
    `AudioEffectLowPassFilter` at 1600 Hz. `project.godot` is untouched.
  - Owns a pool of eight `AudioStreamPlayer3D` nodes. Every node under the
    driver is a `Node3D` group or an audio player; there is no
    `VisualInstance3D` and therefore no visible follower.
  - Reuses committed footstep stems only: the default body and soft transient
    for distant steps, the land hard transient pitched down for `door_close`,
    the metal hard transient for the latch, and the land body pitched down as
    the room-tone tail. No new audio asset, scene, mesh or texture is added.
  - Applies the distance volume itself (`ATTENUATION_DISABLED`) so the cue
    rule has one owner and can be checked headlessly. 3D position still drives
    panning. Delayed layers (latch, tail, later steps) are played from a small
    queue on the same clock as the cue driver.
- `godot_walk/scripts/maze_follower_cues.gd` (new) is the runtime cue driver:
  - Listens to the follower's new `cell_entered` and `edit_applied` signals
    and the door runtime's `door_latched` and new `door_rerolled` signals.
  - A `follower_step` needs five distinct rooms, no cue inside the current
    8-15 second gap, and a quiet player (`|v_xz| <= 0.25 m/s`). A moving
    player's cue is deferred for up to four seconds and dropped if the player
    never stops. One edit produces at most one optional cue.
  - `door_latched` records `door_close` then a delayed `lock_click` (0.12 s).
    `door_rerolled` records `door_reopen` with the same
    `lock_click` sample path plus one room-tone tail at 0.28 s. The latch is
    never a different door sound.
  - Every played cue is an in-memory `follower_cue` event. The driver reports
    its own clock, next allowed time, kind counts, pool size, bus lowpass and
    visible-node count for the headless check.
- `godot_walk/scripts/maze_follower_runtime.gd` emits
  `cell_entered(cell_id, visit_count, is_new)` and `edit_applied(event)`. Its
  cadence, target ranking and edit arithmetic are unchanged.
- `godot_walk/scripts/maze_door_runtime.gd` emits `door_rerolled(threshold)`
  when `open_door` commits a pending re-roll and the leaf opens. It is emitted
  only after a successful commit; a rejected or absent pending re-roll does
  not claim a reveal.
- `godot_walk/scripts/generative_map_assembly.gd` starts one
  `MazeFollowerCues` after the door and re-roll runtimes and publishes it as
  `maze_follower_cues`.
- `godot_walk/scripts/maze_exit_runtime.gd` copies the cue events into the run
  log before `run_end`, disables the cue driver with the follower and door
  runtimes, and leaves the end-card counters and actions unchanged. Cue events
  do not count as edits or re-rolls.
- `godot_walk/scripts/test_maze_cues.py` and
  `godot_walk/scripts/test_issue239_follower_cues.gd` cover the M9 contract.

No committed map, fill, SVG, shape-room version, library scene, catalog file,
`project.godot`, `player.gd`, palette, material-language file or frozen audio
stem was edited. No metadata or layer file was made binary. `registration_accepted`
and `scale_calibrated` remain false.

## Cue rules as implemented

| Cue | Gate | Position | Sound reuse | Recorded checks |
|---|---|---|---|---|
| `follower_step` | 5th room onward; quiet player; one per edit; 8-15 s gap | cell 1-2 direct hops away, envelope centre, floor + 1 m | default soft transient + default body | `after_four_rooms`, `graph_distance_one_to_two`, `one_cue_per_edit`, `volume_by_distance`, `audio_only`, `inert_cue` |
| `door_close` | mandatory eligible latch | door leaf or port midpoint | land hard transient, pitch 0.72 | `mandatory_door_contract`, `door_close_before_latch`, `volume_by_distance`, `audio_only`, `inert_cue` |
| `lock_click` | mandatory, 0.12 s after `door_close` | same door | metal hard transient, dry | `mandatory_door_contract`, `lock_click_after_close`, `volume_by_distance`, `audio_only`, `inert_cue` |
| `door_reopen` | mandatory once per successful re-roll reveal | same door | same metal latch as `lock_click`, plus land body tail at 0.28 s | `mandatory_door_contract`, `same_latch_as_lock_click`, `room_tone_tail`, `volume_by_distance`, `audio_only`, `inert_cue` |

`door_reopen` is deliberately not a new sample, a new door sound or a second
latched source. The event carries both sample paths so the operator can confirm
the same latch before the tail.

## Reference results

The five-seed route reaches the first edit and the first eligible door in this
order. Distances are measured from the player position captured at cue time;
volumes are the authored rule, not a measured mix.

| Seed | Cues | Kinds | Step hops / m / dB / count | Re-open path |
|---:|---:|---|---|---|
| 1 | 6 | step 3, close 1, latch 1, reopen 1 | 2 / 11.41 / -33.07 / 2; 2 / 13.84 / -34.74 / 3; 2 / 9.53 / -31.52 / 1 | direct cue wiring; seed has no latchable eligible door |
| 2 | 6 | step 3, close 1, latch 1, reopen 1 | 2 / 14.03 / -34.86 / 2; 2 / 13.81 / -34.73 / 2; 2 / 15.14 / -35.52 / 1 | direct cue wiring; no latchable eligible door |
| 3 | 6 | step 3, close 1, latch 1, reopen 1 | 2 / 17.50 / -36.78 / 3; 2 / 17.50 / -36.78 / 3; 2 / 17.81 / -36.93 / 2 | direct cue wiring; seed 3 has no eligible bridge |
| 32 | 8 | step 3, close 2, latch 2, reopen 1 | 2 / 8.64 / -30.67 / 1; 2 / 16.78 / -36.41 / 3; 2 / 8.64 / -30.67 / 2 | real `door_rerolled` path after the pending `c00|c01` re-roll |
| 279 | 6 | step 3, close 1, latch 1, reopen 1 | 2 / 17.89 / -36.97 / 3; 2 / 13.02 / -34.21 / 2; 2 / 13.02 / -34.21 / 2 | direct cue wiring; the first eligible crossing is visible-target rejected by M4 |

On seed 32 the first movement crosses the eligible `c00|c01` door and produces
the mandatory close/latch pair before the fifth room. That is intentional: the
door contract is not an optional follower cue. The test therefore counts only
`follower_step` for the four-room gate and allows mandatory door cues earlier.

## Checks run

Python:

```bash
python3 -m pytest -q godot_walk/scripts/test_maze_cues.py \
  godot_walk/scripts/test_maze_follower.py \
  godot_walk/scripts/test_maze_follower_edits.py \
  godot_walk/scripts/test_maze_mutation.py
```

Result: 57 passed. The wider overlay set also passed: `test_maze_doors.py`,
`test_maze_rewire.py`, `test_maze_reroll.py`, `test_maze_exit.py`,
`test_maze_run_save.py` (114 passed together with the focused files).

Full suite:

```bash
python3 -m pytest -q godot_walk/scripts
```

Result: 1414 passed, 5 skipped, 58 subtests passed in 419.22 seconds.

Lint:

```bash
python3 -m ruff check godot_walk/scripts/maze_cues.py \
  godot_walk/scripts/test_maze_cues.py
python3 -m ruff format --check godot_walk/scripts/maze_cues.py \
  godot_walk/scripts/test_maze_cues.py
```

Result: `ruff check` clean; `ruff format --check` reports both files already formatted.

Godot headless (Godot 4.6.3.stable.official.7d41c59c4):

```bash
for seed in 1 2 3 32 279; do
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue239_follower_cues.gd -- \
    --map=res://room_catalog/generative_maps/gmap-${seed}-gmap-0.13.0.json \
    --rooms=res://room_catalog/shape_rooms/gmap-${seed}-gmap-0.13.0/index.json \
    --out=res://evidence/2026-11-13-issue-239/runtime_gmap-${seed}.json
done
```

Result: `ISSUE239_FOLLOWER_CUES: PASS` for all five seeds. Each report records
`visible_nodes: 0`, `pool_size: 8`, `bus_ready: true`, `lowpass_hz: 1600`,
the cue events and the unchanged map hash. Seed 32 records
`reopen_mode: "rewire"`; the other seeds record the direct cue wiring because
their eligible-door or re-roll path is unavailable or rejected by the M4
contract.

Regression checks on the changed runtimes:

```bash
for seed in 1 2 3 32 279; do
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue232_follower_edit.gd -- --map=... --rooms=...
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue238_follower_surfaces.gd -- --map=... --rooms=...
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue233_exit_threshold.gd -- --map=... --rooms=...
done
```

Result: `ISSUE232_FOLLOWER_EDIT: PASS`, `ISSUE238_FOLLOWER_SURFACES: PASS` and
`ISSUE233_EXIT_THRESHOLD: PASS` for all five seeds. The M4/M6/M7 checks were
rerun on seed 32 (`ISSUE234_DOORS: PASS`, `ISSUE236_REWIRE: PASS`,
`ISSUE237_SAVE_RESTORE: PASS`) and on seed 279 for the visible-target and
restore paths.

## No visible follower

The cue driver has a `Node3D` `CuePool` and eight `AudioStreamPlayer3D`
children. It contains no `VisualInstance3D`, `MeshInstance3D`, light, collider
or sprite. The headless test traverses the driver and reports
`visible_nodes: 0`; the same value is stored in every cue event. The follower
is not a body, a pathfinding agent or a chase behaviour.

No capture is produced for this slice: the change is audio-only and the
follower is deliberately never rendered. The headless runtime reports in
`godot_walk/evidence/2026-11-13-issue-239/` are the tracked evidence.

## Audio is not asserted

The dummy audio driver produces no sound, and `.wav` import companions are
per-machine (`godot_walk/.gitignore` ignores `*.import`), so a fresh headless
run intentionally does not claim decoded playback. The test checks that the
five committed sample files exist, that every player routes to the `Follower`
bus and that the cue events carry the authored sample paths, timing, distance
and volume. Audible playback and the mix are the operator listen step.

## Map hashes

The committed maps are never written. Each Godot report has
`map_sha256_before == map_sha256_after`:

```text
seed 1   dacd388ef9780bf1d843f9078b7b8679e476be28df0e0464bb7778218ce2c7f3
seed 2   07c1cbb219004d1533021ff5d7c5fe18b41d28ed8b01f4ce69535e1c0db8c465
seed 3   307c8ab769ecf0ed7d13b44176e3607e28816daa2a7489e070b1b0aa4ab70591
seed 32  087d24978dc4b7e5986dd881d491d43bc2dc4f49652f6e4f25e848e6abbdd7d1
seed 279 51d296d0113d2c01852845389cbc6d64ac85f232e04d0cf7a8116e9bd05e995c
```

## Operator steps pending

1. **PENDING: operator listen on a real walk.** Confirm that the distant step
   is identifiable as a step without sounding like the player's own footsteps,
   that the 8-15 second silence reads as occasional rather than random, and
   that the fixed 1600 Hz lowpass is not too dull or too bright. No audio
   assertion was made.
2. **PENDING: operator listen to the door contract.** Confirm `door_close`
   followed by `lock_click` is legible on an eligible door, and that
   `door_reopen` sounds like the same latch plus a room-tone tail rather than a
   second door. Seed 32 is the reference for the real re-roll reveal.
3. **PENDING: operator walk.** Confirm the follower stays unheard in the first
   four rooms, that the cue does not fire while the player is moving, and that
   a cue after an edit helps the "something changed" beat without becoming a
   metronome.
4. **PENDING: mix tuning.** The bus volume, the lowpass cutoff, the step
   sample layers and the 1-3 step spacing are provisional values for M14; this
   slice only wires them and records the authored numbers.

No operator approval, registration acceptance or scale calibration is claimed.
`registration_accepted` and `scale_calibrated` remain false.
