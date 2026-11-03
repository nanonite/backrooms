# Issue 186: standard doorway margins, degenerate corner doorways, trim flicker fix

Headless only (no rendering, no captures). Generator `gmap-0.2.0` / `shape-room-0.2.0`; the
`gmap-0.1.0` maps, fills, SVGs and `shape_rooms/gmap-*-gmap-0.1.0/` are byte-identical to before.

## What changed
- Standard cells: every port is >= 1.5 m from both ends of its envelope side, so a 2 m doorway keeps >= 0.5 m of solid wall on each side. Ports sit at the exact centre of the shared edge (half-metre grid; `lattice.port_step_m` = 0.5), shared-edge overlap >= 3 m.
- Degenerate cells (seeded 2d6 >= 11, `--degenerate-max` default 1, never c00 / figure / void): on a 3 m shared edge the port moves to the gmap-0.1.0 position (1 m from the low end) so the doorway touches the cell's envelope corner. Recorded as `mode`, per-port `placement`, `degenerate_budget {max, used}`, and the rules `standard_doorway_margin`, `degenerate_only_in_degenerate_cells`.
- Shape rooms: standard rooms assert the full 0.5 m margin (no corner waiver); degenerate rooms keep the waiver only for their `degenerate_port_ids` (`degenerate_features: ["corner_doorway"]`).
- Trim: jambs and lintel line the doorway reveal (lead's change), and at a corner doorway start at the perpendicular wall's inner face.

## Seed-1 launch command (0.2.0)
```
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/generative_map_walkthrough.tscn -- --map=res://room_catalog/generative_maps/gmap-1-gmap-0.2.0.json --rooms=res://room_catalog/shape_rooms/gmap-1-gmap-0.2.0/index.json
```
(R resets to spawn.) For a walk that contains a degenerate doorway use seed 3 (same command, `3` for `1`).

## Degenerate cells per seed (gmap-0.2.0, budget max 1)
| seed | cells (walkable + void) | degenerate cells | degenerate ports |
|------|-------------------------|------------------|------------------|
| 1 | 14 (12 + 2) | none (used 0) | - |
| 2 | 15 (12 + 3) | none (used 0) | - |
| 3 | 14 (12 + 2) | c03 | c03:p1 at (-11, -11) |

## Headless results
Test: `test_issue183_shape_rooms.gd` (extended with `issue186_trim_checks.gd` and a spec margin check). Seeds 1-3 at 0.1.0 and 0.2.0 all PASS: 22/22 edge traversals both ways, closed doorways blocked, flood fill reaches 12/12 cells and no void cell, both #183 negative controls fail as expected. Trim coplanarity (same-plane, same-facing, positive-area overlap between any trim box and any wall or header box in the assembled map): 0 conflicts in every run; 3 trim boxes belong to the degenerate doorway in seed 3, 0 conflicts there. Negative controls: the pre-fix outside trim and a trim box sharing a wall plane are both detected. Before the corner adjustment the seed-3 degenerate doorway had 5 conflicts (jamb and lintel against the perpendicular wall).

## Requires human visual verification
Flicker gone while walking past doorways; degenerate corner doorway reads as intentional; trim and PSX look unchanged otherwise.
