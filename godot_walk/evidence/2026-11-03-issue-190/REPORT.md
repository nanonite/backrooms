# Issue #190: shape stage 2a, 45-degree walls in generated rooms (gmap-0.4.0)

Implemented by a Sonnet 5.5 agent against the lead's design in `chainlink show 190`. Headless checks only; nothing was rendered.

Doorways, ports, cells, envelopes and edges stay axis-aligned. Only room outlines gain 45-degree edges. Generator `gmap-0.4.0` / `shape-room-0.4.0`. The CLI default stays `gmap-0.2.0`.

## What a map says
- `shape_stage_max: 2` (default for 0.4.0). A new rule id `shape_stage2_eligibility` is listed.
- A ground or figure cell lists the stage-2 classes it is eligible for in `allowed_primitives`. The validator recomputes the list and requires it to match exactly.
- The seeded draw (own sha256 stream) is recorded as `shape_stage_target` (1 or 2) and, at stage 2, `shape_class_target`. P(stage 2) = 0.4, class weights chamfered_box 3, chamfered_polyomino 3, octagon 2, wedge 1. Threshold cells record 1; module and void cells get no target.
- Module placement rule: a module cell's envelope grown by 0.5 m must share no area with any non-parent room (corner contact included). It extends `module_touches_neighbour`. 0.3.0 keeps the old edge-contact rule.

## Seeds kept
| Seed | Stage-2 rooms realised (class: cell) | Library modules (rotation) | Headless |
|---|---|---|---|
| 1 | chamfered_box x5, chamfered_polyomino x1 (c04) | early_pocket_single_west (180), later_bay_column_bounded (0) | PASS |
| 2 | chamfered_polyomino x2 (c02, c07), wedge x1 (c08, leg 5 m), chamfered_box x2 | gopro_industrial_hall_south_socket (90) | PASS |
| 3 | chamfered_polyomino x1 (c08), chamfered_box x4 (c05 fell back to a box) | debris_window_rock_north_socket (180), gopro_industrial_hall_south_socket (90) | PASS |
| 14 | octagon x1 (c11), chamfered_polyomino x1 (c02), chamfered_box x1 | debris_window_rock_north_socket (180) | PASS |

Seeds 1-3 show chamfered_polyomino, wedge (seed 2) and library modules, but no octagon, so seed 14 was added (first seed with an octagon; seeds 16, 22 and 28 also have one).

Headless results, `test_issue183_shape_rooms.gd`, `all_walkable`:

| Seed | Edges both ways | Closed blocked | Flood cells | Trim pairs | trim_coplanar | wall_coplanar | reveal_faces | Diagonal edges | Capsule stopped | Floor missing | Joint band uncovered | diagonal_coplanar |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 26/26 | 1/1 | 14/14 | 243 | 0 | 0 | 0 | 10 | 30/30 | 0/40874 | 0/2668 | 0 |
| 2 | 24/24 | 3/3 | 13/13 | 245 | 0 | 0 | 0 | 8 | 24/24 | 0/23949 | 0/2132 | 0 |
| 3 | 26/26 | 3/3 | 14/14 | 255 | 0 | 0 | 0 | 12 | 36/36 | 0/44197 | 0/3201 | 0 |
| 14 | 24/24 | 3/3 | 13/13 | 245 | 0 | 0 | 0 | 6 | 18/18 | 0/12717 | 0/1601 | 0 |

All six negative controls fire on every seed: doorway removed, floor rect removed, module socket closed, joint recess removed (#189), diagonal collision removed (capsule stopped 0 of 30 on seed 1, 6 wall-blocked failures), unmitred joint (800 of 2668 band samples uncovered on seed 1). Runtime JSON: `runtime_gmap-{1,2,3,14}-gmap-0.4.0.json` in this folder.

## Other checks
- `python3 -m pytest -q godot_walk/scripts`: 530 passed (488 before, 42 new in `test_gmap_stage2.py`).
- Seeds 1-300: every 0.4.0 map validates and every room builds. Over the 300 maps, 1177 rooms drew stage 2 and 1107 were realised: 827 chamfered_box, 173 chamfered_polyomino, 62 octagon, 45 wedge. The 70 that fell back to stage 1 are all chamfered_polyomino (no valid cut left, or the arms or wide doorways forced a box).
- Headless on 0.4.0 seeds 4-150 (scratch copies, not kept): 147 of 147 PASS, including the 0.3.0 seed 9 gap (reveal and wall coplanar 0).
- 0.1.0, 0.2.0 and 0.3.0 map, fill, svg and shape-room files regenerate byte-identically (existing and new tests). Headless results for those 9 runs are unchanged (22/22, 22/22, 22/22; 22/22, 22/22, 22/22; 26/26, 24/24, 26/26 edges; flood 12, 12, 12; 12, 12, 12; 14, 13, 14; trim pairs 215, 217, 228; 230, 235, 228; 245, 243, 255; all coplanar counts 0).
- Floor-slit experiment: per-triangle floor prisms without the 2 cm overlap leave slits. On scratch seed 15 the dense floor check found 11 of 17391 samples missing and two doorway traversals failed; with the overlap, 0.

## Launch commands
```
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/generative_map_walkthrough.tscn -- --map=res://room_catalog/generative_maps/gmap-N-gmap-0.4.0.json --rooms=res://room_catalog/shape_rooms/gmap-N-gmap-0.4.0/index.json
```
N = 1 (five chamfered boxes), 2 (wedge and two polyomino), 3 (two modules), 14 (octagon). Headless: replace `--path godot_walk res://scenes/...` by `--headless --path godot_walk --script res://scripts/test_issue183_shape_rooms.gd` and keep the two `--map=` / `--rooms=` arguments.

Regenerate:
```
python3 godot_walk/scripts/generative_map.py generate --seed N --index godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json --generator-version gmap-0.4.0 --svg
python3 godot_walk/scripts/shape_room.py generate --map godot_walk/room_catalog/generative_maps/gmap-N-gmap-0.4.0.json --mode all_walkable
```

## Deviations and interpretations
1. `shape_class_target` is recorded next to `shape_stage_target`, so the drawn class is on the cell.
2. **Classes.** The classifier reads a ring by un-cutting its chamfers (`poetics_geometry.chamfer_base`): box base with 4 equal chamfers is `octagon`; one chamfer with a leg over 3 m is `wedge`; other box bases are `chamfered_box`; a base with more than 4 corners is `chamfered_polyomino`. Wedge legs run from max(3.5 m, 60 percent of the short side) up to the whole short side (a whole-side cut gives a right trapezoid, or a right triangle on a square). `classify_primitive(ring, detailed=False)` keeps the old `chamfered_polygon` label, and module poetics uses that, so its output is unchanged.
3. **Construction.** Box-based classes cut the whole envelope (construction box). A chamfered_polyomino needs arms that do not fill a rectangle (the arm width is searched). If no valid chamfer set exists the room stays stage 1; its class is then still in `allowed_primitives`.
4. **Chamfer rules** (`shape_room_chamfer.py`): lattice 1.0-3.0 m in 0.5 m steps; convex corners only; a chamfered edge keeps at least 1.5 m of straight face (a wedge may keep 0); port margin half the doorway width plus 0.5 m to the chamfer start; a degenerate port blocks both ends of its edge; the walkable spine 1 m from every wall stays one connected piece (the "minimum corridor clearance" rule). Added rule not in the design: the line in from every doorway (1.0 and 1.5 m) keeps 0.6 m from every wall, because a doorway opening onto the 45-degree tip of a wedge could not be walked through (found at scratch seeds 73 and 111).
5. **`rects`** for a chamfered room are the 0.5 m raster rectangles wholly inside the cut outline (spawn and the floor-removed control read them). The builder floors and ceilings from `outline_xz`.
6. **Lamps** on a chamfered room use the 4 m grid with a Euclidean 1 m inset from every wall, diagonals included.
7. **Mitre.** Wall boxes keep square ends and stand inside the outline. At a convex joint (135 degrees at a chamfer, 45 degrees at a wedge tip) each end lies inside the neighbouring box, so there is no gap and no visible end face. No reflex diagonal joint exists, since only convex corners are cut. The "unmitred" control pulls diagonal boxes back 0.32 m at both ends. The coverage check samples the wall band around every diagonal joint against the collision boxes.
8. **Floor and ceiling** of a chamfered room: one triangulated mesh each (double-sided material, UV in metres per tile, so texel density matches the boxes). The ceiling is a single plane without the 5 cm slab. Floor collision is one convex prism per triangle, each grown 2 cm in plane; exact-edge prisms and a triangle mesh both leave slits.
9. **Parent rooms of library modules** (needed for "reveal and wall coplanar 0 for all generated seeds", not in the design): in 0.4.0 the parent's arms avoid outline edges that lie on the module's side line with the room beyond it (`shape_room_module_clear.py`, seeds 22 and 28); the parent ceiling avoids the library room's box top planes (table of measured planes for the four usable modules, seed 117). Without these, 0.4.0 maps failed the #189 reveal check.
10. **Check changes.** Raster floor samples within 0.05 m of the outline are skipped (45-degree edges run through sample centres). The wall approach probe is skipped near a second wall (wedge tips) and, in 0.4.0, along any wall on a library joint's line. The dense floor check does not count rays stopped by a library wall that overhangs the room (counted as `module_overhang_samples`). `issue186_trim_checks.gd` enters diagonal boxes by bounding box and compares only their horizontal faces; `issue190_diagonal_checks.gd` compares their vertical faces plane by plane. The shared-plane trim control uses an upright wall. The floor-removed control picks a room without chamfers.
11. `build_map` and the CLI take `--stage-max` default `None` (1 before 0.4.0, 2 for 0.4.0).

## Needs human visual verification
- How the 45-degree walls, the double-sided floor and ceiling planes, and wallpaper texel density look under the PSX effect.
- The sharp 45-degree tip of a wedge, and whether the ceiling without a slab shows anything at a wall top.
- The library wall overhang into the parent room at module joints (up to 0.3 m, known from #188) next to a diagonal wall.
- Whether the octagon, wedge and polyomino rooms read as intended, and whether the operator accepts them.
