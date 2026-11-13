# Issue #236 — M6 door re-roll: runtime rebuild and reveal

Date: 2026-11-13
Parent: #223 (runtime overlay for the #209 design), under #169
Design source: `docs/MAZE_DYNAMICS_PROPOSAL.md`, section 11 (M6), with sections
4.5.7, 4.5.8, 4.5.11, 4.6, 6.2, 6.3, 6.5, 9.2, 9.5 and the operator decisions
in section 10. Dependencies: M5 / #235, M4 / #234, M3 / #233 and M1 / #231 are
closed and present on `main`.

Status: implementation and automated checks complete. Operator visual review of
the reveal and the operator walk are pending. A capture or a headless pass is
not approval.

## What changed

- `godot_walk/scripts/maze_rewire.gd` (new) is the derived-spec contract:
  - `derive_specs` copies only the cells whose incident doorway set changed and
    removes the doorway records for `E_T \ P`, adds one 1.4 m × 2.2 m open
    doorway for each `P \ E_T` at the stored center, updates the doorway
    features, and bumps `passage_revision`. Every other field is a deep copy.
  - `geometry_issues` checks the wall span, the 0.2 m corner margin, the ceiling
    clearance, kept-opening spacing, content-pinned cells and every non-doorway
    field (`cell_id`, envelope, floor, light, wear, surface variants, palette,
    reverb, materials, props, module scenes). A module, landmark or diagonal cell
    is never re-doored.
  - `apply_event_to_state` refuses a stale `passages_before` and applies the
    stored `P` without re-enumerating.
  - `state_hash` is the canonical `maze-rewire-state-0.1.0` digest over the
    current passages, `passage_revision` map, `branch_epoch` and
    `reroll_serial`.
- `godot_walk/scripts/maze_graph.gd` (new) is the GDScript F0-F2 runtime check:
  F0 strongly connected over every walkable cell, F1 exit reachable from the
  player, F2 every cell reachable from the player can reach the exit. Drops are
  upper-to-lower only; level and ramp passages are bidirectional.
- `godot_walk/scripts/maze_rewire_runtime.gd` (new) owns the runtime state:
  - `prepare` caches the M5 ranked list when an eligible leaf latches;
  - `commit` draws from the cached shortlist with the commit `event_index`,
    validates geometry and F0-F2 with the real specs, rebuilds only the changed
    room nodes, and swaps them while the leaf is still closed;
  - the old room nodes stay until every check passes; a failure opens the old
    branch and marks the door blocked for the run;
  - `apply_stored_event` is the replay path: it reads the stored `P` and
    doorway records and never re-enumerates;
  - the leaf is reparented to the rebuilt host room, so the door that hid the
    swap is not lost.
- `godot_walk/scripts/maze_reroll.gd` gains the GDScript `doorway_records` and
  `rewire_block` twins of the M5 Python payload. The keyed doorway draw, width,
  height and margin match the Python reference.
- `godot_walk/scripts/maze_door_runtime.gd` now gates the latch on a cached
  re-roll candidate (the provisional Q13 eligible-only rule) and commits the
  re-roll before the leaf opens. A door with no candidate logs a rejected
  `door_reroll` event and does not latch. `apply_rewire_plan` merges the live
  door states by threshold and drops the leaf of a removed threshold.
- `godot_walk/scripts/maze_doors.gd` / `.py` mark a re-roll internal doorway
  `rewire_internal`: it is an open cut, never a leaf and never lock-behind
  eligible.
- `godot_walk/scripts/doorway_sizes.gd` / `.py` add the original
  `maze_rewire_1_4m_v1` doorway size so the unchanged shape-room builder can
  cut the new opening. No committed shape-room, map, library scene or palette
  file is edited. The table remains text-only and the Python/GDScript parity
  test still passes.
- `godot_walk/scripts/generative_map_assembly.gd` builds derived rooms, refreshes
  the door registry from the in-memory current passage graph, exposes
  `apply_stored_rewire`, `rewire_snapshot` and `passage_revision`, and starts one
  `MazeRewireRuntime` per walkthrough.
- `godot_walk/scripts/maze_follower_runtime.gd` accepts the current passage map
  so the visibility gate reads the post-re-roll graph. The committed map is
  still the base; no follower mechanic is added.
- `godot_walk/scripts/test_issue234_doors.gd` is updated to the M6 gate: a
  structurally eligible door without a re-roll candidate does not latch, and the
  door restore check now runs before the reveal (a committed re-roll legitimately
  changes the door registry, so the old plan hash is no longer the right
  comparison).
- `godot_walk/scripts/test_issue236_rewire.gd` (new) is the headless M6 test.
- `godot_walk/scripts/maze_rewire.py` (new) is the Python reference for the
  derived specs, doorway geometry, F0-F2 and the fixture builder.
- `godot_walk/scripts/test_maze_rewire.py` (new) covers T6-T10 and T13 at the
  spec/graph level and runs the GDScript headless check for the seed 32 case.
- `godot_walk/fixtures/maze_rewire_v1.json` (new, text) is the shared fixture:
  the seed 32 runtime case, the two seed 279 structural cases, and the seed 1/2
  no-candidate cases.
- `godot_walk/scripts/capture_issue236_rewire.gd` (new) renders the closed,
  closed-after-swap and open views. Captures are local and git-ignored.

No committed map, fill, SVG, shape-room version, library scene, catalog file,
`godot_walk/project.godot`, `player.gd`, palette or material-language file was
edited. No metadata or layer file was made binary; the map stays UTF-8 JSON
text. `registration_accepted` and `scale_calibrated` remain false.

## Runtime coverage on the committed seeds

The M5 structural pools are not all reachable at runtime. The M6 gate adds the
closed-leaf visibility rule from §4.6: a target cell that is still visible from
the B side rejects the crossing with `visible_target`.

| Seed | Runtime-eligible re-roll | Result |
|---:|---|---|
| 1 | none | eligible crossing `c05 -> c03`, no candidate; latch rejected |
| 2 | none | eligible crossing `c07 -> c03`, no candidate; latch rejected |
| 3 | none | no 3-8-cell bridge |
| 32 | `c00 -> c01` | committed; `c03|c04` closed, `c04|c06` opened; 3 rooms rebuilt |
| 279 | none | the structural pools are visible through the `c00`-`c02` drop; `c11 -> c02` and `c06 -> c11` reject with `visible_target` |

This is a coverage observation for the deferred Q9 tuning walk, not a design
change. Seed 279's stored event still rebuilds c04, c05 and c06 in the replay
check, and its `state_hash` matches the fixture; the slice does not bypass the
visibility rule to make that door eligible. The M4 test now records the
provisional Q13 consequence: a door with no re-roll ready does not latch.

## Seed 32 runtime case

Crossing `c00 -> c01` latches `c00|c01` and caches the M5 list. The accepted
event is index 2 (the lock is index 1) and chooses rank 2:

- `passages_before`: `c00|c03`, `c00|c06`, `c03|c04`, `c03|c08`, `c06|c07`,
  `c08|c09`, `c09|c13`
- `passages_after`: `c00|c03`, `c00|c06`, `c03|c08`, `c04|c06`, `c06|c07`,
  `c08|c09`, `c09|c13`
- changed cells: `c03`, `c04`, `c06`; `passage_revision` 1 for each
- doorway: closed `c03|c04`, opened `c04|c06` at `[6.342763, 1.0]`, 1.4 m wide,
  2.2 m high
- F0/F1/F2 true; exit `c02` reachable; `state_hash`
  `ccd2de1afc771b346d5e853e04ea1b5858573caefa268649ce79b62eef2e8f51`

The unchanged target cells (`c00`, `c07`, `c08`, `c09`, `c13`) keep their exact
node instances. `c00` is the spawn cell and is content-pinned: its room and
marker are not rebuilt and only its incident passages could change. No cell is
retired. The internal `c04|c06` doorway is open and has no leaf; the threshold
`c00|c01` keeps its leaf and is the only lockable door.

## Checks run

Python:

```bash
ruff check godot_walk/scripts/maze_rewire.py \
  godot_walk/scripts/test_maze_rewire.py \
  godot_walk/scripts/maze_doors.py godot_walk/scripts/doorway_sizes.py
python3 -m pytest -q godot_walk/scripts/test_maze_rewire.py
python3 -m pytest -q godot_walk/scripts
```

Observed: Ruff clean on the new files; the M6 suite is 12 passed; the full
`godot_walk/scripts` suite is **1366 passed, 5 skipped, 58 subtests passed** in
411.81 seconds (exit 0).

Godot headless (Godot 4.6.3.stable.official.7d41c59c4), all five seeds:

```bash
for seed in 1 2 3 32 279; do
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue236_rewire.gd -- \
    --map=res://room_catalog/generative_maps/gmap-${seed}-gmap-0.13.0.json \
    --rooms=res://room_catalog/shape_rooms/gmap-${seed}-gmap-0.13.0/index.json \
    --out=res://evidence/2026-11-13-issue-236/runtime_gmap-${seed}.json
done
```

Result: `ISSUE236_REWIRE: PASS` on all five seeds. Seed 32 reports
`changed=3 rebuilt=3 rerolled=true hidden=true` and end-card `rerolls=1`; seed
279 reports `changed=3 rebuilt=3 replay=true`; seeds 1 and 2 report
`no_candidate=true` and end-card `rerolls=0`; seed 3 has no eligible crossing. The reports are committed as text under
`godot_walk/evidence/2026-11-13-issue-236/`.

Regressions:

- M4 door leaves on all five seeds:
  `ISSUE234_DOORS: PASS` for seeds 1, 2, 3, 32 and 279. Seed 32 latches, commits
  the re-roll and opens; seeds 1, 2 and 279 correctly report no latch for their
  structurally eligible crossings.
- M5 enumerator: `ISSUE235_REROLL: PASS directions=11 pool=5 spawn_pinned=2
  seed279_hard=13 seed279_shortlist=3 seed32_chosen=C2`.
- M2 follower edit and M3 exit threshold: `ISSUE232_FOLLOWER_EDIT: PASS` and
  `ISSUE233_EXIT_THRESHOLD: PASS` on all five seeds.
- Shape rooms and reverb: `ISSUE183_SHAPE_ROOMS: PASS` and
  `ISSUE204_REVERB: PASS` on all five seeds, including the palette and module
  checks.
- The M5 fixture and the five-seed golden counts are unchanged.
- The M4 fixture and door plan projection are unchanged; only the runtime latch
  gate is stricter.

Map hashes before and after every run:

```text
dacd388ef9780bf1d843f9078b7b8679e476be28df0e0464bb7778218ce2c7f3  gmap-1
07c1cbb219004d1533021ff5d7c5fe18b41d28ed8b01f4ce69535e1c0db8c465  gmap-2
307c8ab769ecf0ed7d13b44176e3607e28816daa2a7489e070b1b0aa4ab70591  gmap-3
087d24978dc4b7e5986dd881d491d43bc2dc4f49652f6e4f25e848e6abbdd7d1  gmap-32
51d296d0113d2c01852845389cbc6d64ac85f232e04d0cf7a8116e9bd05e995c  gmap-279
```

## Captures (local, generated; not committed)

Command for the seed 32 reveal:

```bash
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan \
  --resolution 960x540 \
  --script res://scripts/capture_issue236_rewire.gd -- \
  --map=res://room_catalog/generative_maps/gmap-32-gmap-0.13.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-32-gmap-0.13.0/index.json \
  --out=res://evidence/2026-11-13-issue-236/captures/seed-32-nopsx \
  --no-psx
```

The PSX presentation pass is disabled for the pop comparison: its ordered
dither quantizes tiny lighting changes into visible banding even when no
geometry moved. Without the pass, the camera on the B side sees the identical
pixels before and after the swap:

| View | SHA-256 | Observation |
|---|---|---|
| closed before | `dea5d3ac36639137a6e864dc0393a85128eaba020023ad4a1ce52c6952c21498` | Leaf sealed; target fully hidden |
| closed after swap | `dea5d3ac36639137a6e864dc0393a85128eaba020023ad4a1ce52c6952c21498` | Byte-identical to the closed-before view; no pop |
| open after | `e585be8b83c1d497cad05450ddf4f2360fe1f66735463695fb6d4d1cf4d6a762` | The door opens to the rebuilt branch |

The manifest records `no_pop: true`, `ray_closed: true`, `ray_open: false`.
Seed 279 and seed 1 captures write an empty-reroll manifest with no views; they
have no runtime-eligible door.

## Operator steps pending

1. **PENDING: operator visual review of the reveal.** Walk through `c00 -> c01`
   on seed 32, turn around, open the door, and judge that the same rooms read as
   rearranged rather than replaced. The automated check proves the closed leaf
   hides the swap; it does not judge the feel or the style. This run does not
   claim that review.
2. **PENDING: operator walk.** Confirm on foot that the door latches, that the
   leaf hides the branch during the rebuild, that opening it shows the new
   passage layout, that the spawn room and marker are unchanged, and that the
   exit is still reachable. Agents cannot walk.

No operator approval, registration acceptance or scale calibration is claimed.
`registration_accepted` and `scale_calibrated` remain false.
