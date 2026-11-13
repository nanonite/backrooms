# Issue #237 — M7 door re-roll: save, restore and cache

Date: 2026-11-13
Parent: #223 (runtime overlay for the #209 design), under #169
Design source: `docs/MAZE_DYNAMICS_PROPOSAL.md`, section 11 (M7), with
sections 3.1, 3.2, 3.5, 4.6, 4.7, 9.3, 9.7, 9.8 and the operator decisions in
section 10. Dependencies: M6 / #236 is closed and present on `main`.

Status: implementation and automated checks complete. There is no visual or
audio acceptance step in this slice; the operator walk and reveal review from
M6 remain pending and are not claimed here.

## What changed

- `godot_walk/scripts/maze_run_save.py` (new) is the headless save contract:
  - a save is `{schema_version, save_kind, save_version, base, event_log}`;
  - `base` is the map identity, including the raw `base_map_sha256` and the
    optional catalog snapshot hash;
  - `event_log` is the ordered trigger/mutation log; no overlay snapshot, no
    shortlist and no candidate pool are stored;
  - `build_save` folds the log before writing, so a bad hash chain, wrong base,
    reordered event or stale draw is refused;
  - `write_save` validates first, writes UTF-8 JSON through a temporary file and
    atomically replaces the destination; `read_save` validates against the
    current map;
  - `restore_rewire_state` replays accepted `door_reroll` records from the base,
    bumps `passage_revision` from the current spec for stacked re-rolls, and
    returns the passage state, revision map, `branch_epoch`, `reroll_serial`
    and the rewire state hash;
  - `pending_rerolls` re-enumerates a latched door from its accepted
    `door_lock` record at `len(event_log) + 1`; the save never revives a stale
    pending list;
  - `room_cache_key`/`RoomCache` carry the M7 cache contract.
- `godot_walk/scripts/maze_run_save.gd` (new) is the runtime twin. It builds a
  save from the base identity plus the door/re-roll log, validates the base and
  event order, reads/writes UTF-8 JSON atomically, and exposes the same cache
  key layout. Runtime events that predate the save have the base block attached
  without editing the live log.
- `godot_walk/scripts/maze_room_cache.gd` (new) is the revision-aware room
  cache. Its key includes the base map ID/hash, `branch_epoch`,
  `passage_revision`, `content_revision` and the stable cell ID.
- `godot_walk/scripts/maze_rewire_runtime.gd` gains:
  - `restore_events`, which resets to the base, replays accepted re-rolls with
    their stored `P` and no re-enumeration, and then re-enumerates every
    latched door that has only a `door_lock` record;
  - reset support that rebuilds any mutated rooms back to their base specs
    before a replay in the same scene;
  - the revision cache filled from the derived specs and exposed in
    `snapshot().cache`.
- `godot_walk/scripts/generative_map_assembly.gd` records the committed map path
  and exposes `run_base_identity`, `run_save`, `restore_run`,
  `write_run_save` and `load_run_save`.
- `godot_walk/scripts/maze_rewire.py` / `.gd` separate the replay-supported
  algorithm versions from the current enumerator. A stored `rewire-1` event
  still applies its `P` when the enumerator advances; an unknown future version
  is refused.
- `godot_walk/scripts/test_maze_run_save.py` and
  `godot_walk/scripts/test_issue237_save_restore.gd` are the new tests.

No committed map, shape-room file, library scene, catalog file, `project.godot`,
`player.gd`, palette or material-language file was edited. No metadata or layer
file was made binary. `registration_accepted` and `scale_calibrated` remain
false.

## Save format

```json
{
  "schema_version": 1,
  "save_kind": "maze-run-save",
  "save_version": "maze-run-save-0.1.0",
  "base": {
    "map_id": "gmap-32-gmap-0.13.0",
    "base_map_sha256": "<raw committed map hash>",
    "generator_version": "gmap-0.13.0",
    "seed": 32,
    "attempt": 0,
    "catalog_snapshot_sha256": "<optional>"
  },
  "event_log": ["<ordered trigger and mutation records>"]
}
```

The M6 runtime log is the door/re-roll subset (`door_lock`, `door_unlock`,
`door_reroll`). The M1 Python format remains the sealed headless log; the M7
save builder validates that form when present and refuses a base mismatch or a
broken hash chain.

## Restore and pending re-rolls

- Committed `door_reroll` events replay their stored `passages_after` and
  doorway records. They do not call the enumerator, so a later algorithm
  version cannot reinterpret an old event.
- A save made while the leaf is latched but before the `door_reroll` record has
  no pending shortlist in the file. On restore, `door_lock` is read from the
  log, the current passage state is folded, and `prepare` re-enumerates at the
  next event index. Losing the old in-memory shortlist is safe because no
  mutation had happened.
- A rejected `door_reroll` marks the threshold blocked and is not retried.
- A `door_unlock` after the lock clears any pending entry.
- Reload at the door produces the same `P`, the same event index and the same
  `state_hash`; the second save then reloads the committed `P` from the log.

## Cache contract

`maze-room-cache-0.1.0` keys are:

```text
version|map_id|base_map_sha256|branch_epoch|passage_revision|content_revision|cell_id
```

A cell whose `passage_revision` changed is a miss even when its ID and every
non-doorway field are identical. Changing `branch_epoch` or
`content_revision` is also a miss. The current runtime fills the cache while
replaying a re-roll; #162's streamer can become the first consumer without
re-keying rooms by `cell_id` alone.

## T6, T11 and T14

- **T6 replay from stored `P`:** an accepted M6 event replays its
  `passages_after` and doorway records without re-enumeration. The state hash
  matches the M6 fixture hash
  `ccd2de1afc771b346d5e853e04ea1b5858573caefa268649ce79b62eef2e8f51` for the
  seed 32 `c00 -> c01` case. A stored `rewire-1` event still applies after the
  enumerator version advances; `rewire-9` is refused.
- **T11 save/restore and cache:** base hash plus the log restores the same `P`
  and state hash, including a save/reload with only a `door_lock` record. A
  changed `passage_revision` is a cache miss, and the #156 finite streamer
  fixture is unchanged.
- **T14 stacked re-rolls:** the seed 279 `c06 -> c11` then `c11 -> c02` pair
  folds the second `passages_before` from the current state, survives an
  intermediate save/restore, and ends at the same revision map and state hash.

## Commands run

Python:

```bash
ruff check godot_walk/scripts/maze_run_save.py \
  godot_walk/scripts/test_maze_run_save.py godot_walk/scripts/maze_rewire.py
ruff format --check godot_walk/scripts/maze_run_save.py \
  godot_walk/scripts/test_maze_run_save.py
python3 -m pytest -q godot_walk/scripts/test_maze_run_save.py
python3 -m pytest -q godot_walk/scripts
```

Observed: Ruff clean; the M7 suite is 9 passed; the full `godot_walk/scripts`
suite is **1375 passed, 5 skipped, 58 subtests passed** in 418.27 seconds
(exit 0).

Godot headless (Godot 4.6.3.stable.official.7d41c59c4), all five seeds:

```bash
for seed in 1 2 3 32 279; do
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue237_save_restore.gd -- \
    --map=res://room_catalog/generative_maps/gmap-${seed}-gmap-0.13.0.json \
    --rooms=res://room_catalog/shape_rooms/gmap-${seed}-gmap-0.13.0/index.json \
    --out=res://evidence/2026-11-13-issue-237/save_restore_gmap-${seed}.json
done
```

Seed 32 reports `pending=true restored=true same_p=true same_hash=true
cache_miss=true map_sha256=unchanged`. Seeds 1, 2, 3 and 279 have no
runtime-eligible re-roll and report an empty run that saves and restores
unchanged. The five text reports are committed under
`godot_walk/evidence/2026-11-13-issue-237/`.

Regressions:

- M6 re-roll on all five seeds: `ISSUE236_REWIRE: PASS`.
- M1-M5 Python overlay suites: 75 passed.
- #156 finite streamer: `ISSUE156_STREAMING_CONTRACT: PASS` and
  `ISSUE156_NEGATIVE_CONTROLS: PASS`.

Map hashes before and after every run:

```text
dacd388ef9780bf1d843f9078b7b8679e476be28df0e0464bb7778218ce2c7f3  gmap-1
07c1cbb219004d1533021ff5d7c5fe18b41d28ed8b01f4ce69535e1c0db8c465  gmap-2
307c8ab769ecf0ed7d13b44176e3607e28816daa2a7489e070b1b0aa4ab70591  gmap-3
087d24978dc4b7e5986dd881d491d43bc2dc4f49652f6e4f25e848e6abbdd7d1  gmap-32
51d296d0113d2c01852845389cbc6d64ac85f232e04d0cf7a8116e9bd05e995c  gmap-279
```

## Human steps pending

1. **PENDING: operator walk.** Walk a door re-roll run, save while the door is
   latched, reload, and confirm that opening the door reveals the same
   rearranged branch and that the committed re-roll survives a second reload.
   Agents cannot walk.
2. **PENDING: M6 operator visual review.** The reveal style/no-pop review from
   #236 is still open; this slice does not re-claim it.

No operator approval, registration acceptance or scale calibration is claimed.
`registration_accepted` and `scale_calibrated` remain false.
