# Issue #235 — M5 door re-roll enumerator evidence

Slice: `rewire-1` passage-graph enumerator, mandatory pins, hard invariants
R0-R11, shape ranking, shortlist, seeded draw and the event payload. M5 is
headless: it creates no runtime geometry and never writes a committed map.
The full-`A` 3-8 rule ships; the deferred Q9 3-8 prefix selector is not used.
The spawn cell is a content-pinned island (Q10) and the exit cell is excluded.

## Files

- `godot_walk/scripts/maze_reroll.py` — Python reference enumerator, event
  payload, replay passage state, fixture builder and `plan`/`fixture` CLI.
- `godot_walk/scripts/maze_reroll.gd` — GDScript runtime twin of the
  enumerator and the cross-language projection.
- `godot_walk/fixtures/maze_reroll_v1.json` — committed five-seed golden
  fixture and six parity cases.
- `godot_walk/scripts/test_maze_reroll.py` — T1-T5, T12-T14 and negative-case
  tests.
- `godot_walk/scripts/test_issue235_reroll.gd` — headless GDScript check that
  reproduces the fixture and parity projections.
- `godot_walk/evidence/2026-11-13-issue-235/parity.json` — the headless
  GDScript report (`failures: []`).

## Golden fixture (§4.5.9)

The fixture reads the five committed `gmap-0.13.0` maps directly. It records
11 bridge directions with a 3-8 cell departed component, the spawn column, and
the decided-Q10 pool split. The counts are the pre-exit structural measurement
from §4.5.9, because the committed maps predate the M3 exit layer; runtime
`plan_reroll` accepts `exit_cell` and rejects an exit inside the target.

| Seed | Directions | Directions with >=2 in-tolerance | Spawn-free (old pin) |
|---:|---:|---:|---:|
| 1 | 1 | 0 | 0 |
| 2 | 1 | 0 | 0 |
| 3 | 0 | 0 | 0 |
| 32 | 5 | 2 | 1 |
| 279 | 4 | 3 | 1 |
| **Total** | **11** | **5** | **2** |

The richest direction is seed 279 `c02 -> c11`: 8 cells, 13 hard-valid
candidates, 3 in tolerance, edit range 1-2. The seed 32 worked example
`c01 -> c00` has hard-valid C1, C2, C3; the shortlist is `[C1, C2]`, C3 is
hard-valid but outside the tier-1 degree tolerance, and event index 1 chooses
C2 (`chosen_rank = 2`).

## Test coverage

- T1 determinism: repeated planning and a sealed event replayed from JSON give
  the same `P`, `state_hash` and `candidate_set_hash`.
- T2 golden fixture: the 11 directions, 5 decided-rule pools and 2 spawn-pinned
  pools above.
- T3 hard invariants: every hard candidate is checked for the same footprint,
  connectivity, strong connectivity, degree <= 4, pinned passages, retained
  fraction, edit bounds and unchanged content.
- T4 shape shortlist: C1/C2/C3 classification plus an explicit relaxed
  shortlist on a synthetic thin pool (`consistency_relaxed = true`).
- T5 seeded draw: stable for the same key, changes with `event_index`, and
  never leaves the shortlist.
- T12 parity: the headless GDScript check recomputes `H_T`, hard counts,
  shortlists and the chosen `P` for the seed 32 and 279 fixtures and compares
  them with the Python-generated fixture.
- T13 negative cases: straight corridor zero candidates, 4-cell tree zero
  candidates, 2-cell target rejected, drop door rejected, visible target
  rejected, module pin removal rejected, spawn island accepted, exit inside
  the target rejected, and a no-candidate door fails closed with a rejected
  event.
- T14 stacked re-rolls: a second target that overlaps an earlier one uses the
  folded current `E_T`; a stale `passages_before` is refused; the two events
  replay to the same state hash and the base map bytes are unchanged.

## Commands run

```bash
python3 -m pytest -q godot_walk/scripts/test_maze_reroll.py
python3 -m pytest -q \
  godot_walk/scripts/test_maze_mutation.py \
  godot_walk/scripts/test_maze_exit.py \
  godot_walk/scripts/test_maze_doors.py \
  godot_walk/scripts/test_maze_follower.py
ruff check godot_walk/scripts/maze_reroll.py godot_walk/scripts/test_maze_reroll.py
ruff format --check godot_walk/scripts/maze_reroll.py godot_walk/scripts/test_maze_reroll.py
cd godot_walk && godot4 --headless --script res://scripts/test_issue235_reroll.gd
```

Observed: 12 M5 tests pass, the four earlier overlay suites pass (63 tests
together with M5), the full `godot_walk/scripts` suite passes (1354 passed,
5 skipped), Ruff is clean, and the GDScript check prints
`ISSUE235_REROLL: PASS directions=11 pool=5 spawn_pinned=2 seed279_hard=13
seed279_shortlist=3 seed32_chosen=C2`.

## Human steps

M5 has no visual or audio acceptance step. The operator walk/listen for the
deferred Q9/Q11/Q12/Q13 tuning defaults remains queued for M14 and is **not**
claimed here.
