# Issue #188: operator-accepted library rooms as leaf cells (gmap-0.3.0)

Implemented by a Sonnet 5.5 agent against the lead's design in `chainlink show 188`. The lead wrote this report from the agent's hand-back, because the subagent could not write files under evidence/. The lead also re-ran the seed-2 headless check and the Python suite.

## Placements

Every module joint is `connection_status: proposed_untested`. None of them reuses the #160 or #168 pair approval. No map is marked playable or accepted.

| Seed | Module (rotation) | Role | Parent port | Port xz |
|---|---|---|---|---|
| 1 | godot_early_pocket_single_west_v1 (180) | ground | c10:p1 | (-14, 0) |
| 1 | godot_later_bay_column_bounded_v1 (0) | ground | c07:p2 | (-10, -11.5) |
| 2 | godot_gopro_industrial_hall_south_socket_v1 (90) | figure | c07:p2 | (-1, 26) |
| 3 | video_ccf9722164a0bdc8_debris_window_rock_north_socket_v1 (180) | figure | c08:p1 | (-13, -15) |
| 3 | godot_gopro_industrial_hall_south_socket_v1 (90) | figure | c10:p1 | (15, -6) |

## Results

- **Python tests:** `python3 -m pytest -q godot_walk/scripts` gives 487 passed (426 before, 61 new in `test_gmap_modules.py`). Seeds 1-300 all produce valid 0.3.0 maps and shape rooms.
- **Byte-identical regeneration:** 0.1.0 and 0.2.0 maps, fills, SVGs and shape rooms for seeds 1-3 regenerate unchanged. Their headless checks give the old counts.
- **Headless, 0.3.0** (`runtime_gmap-{1,2,3}-gmap-0.3.0.json`): all PASS.

  | Seed | Edges both ways | Closed doorways blocked | Flood cells | Trim pairs | Trim coplanar | Wall coplanar | Reveal faces |
  |---|---|---|---|---|---|---|---|
  | 1 | 26/26 | 1/1 | 14/14 | 245 | 0 | 0 | 8 |
  | 2 | 24/24 | 3/3 | 13/13 | 243 | 0 | 0 | 5 |
  | 3 | 26/26 | 3/3 | 14/14 | 255 | 0 | 0 | 10 |

  - Sockets land 0.02 m from their port, with the socket opened.
  - Doorway apertures hold no collider.
  - The floor is supported across each joint.
  - Negative controls fail as expected: doorway removed, floor rect removed, module socket left closed.
- **Lead re-run of seed 2:** `ISSUE183_SHAPE_ROOMS: PASS ... edges_both_ways=24/24 ... trim_coplanar=0 modules=1 landed=1 open=1 aperture_clear=1 wall_coplanar=0 reveal_faces=5`.
- **Further seeds:** seeds 4-40 also PASS. They were run in a temporary folder and not kept.

## Deviations from the design

1. **0.02 m landing clearance.** The module sits 0.02 m off its parent. Library walls stand just outside their footprint, so an exact landing makes the library wall face coplanar with the parent's outer wall face. The validator allows the 0.02 m overhang.
2. **Isolation rule (`module_touches_neighbour`).** A module cell may touch no walkable cell except its parent, because library walls overhang. Threshold cells cannot be parents, and voids never attach to module cells.
3. **Port margin by doorway width.** The margin is half the door width plus 0.5 m of wall: 1.5 m for 2.0 m doors, 1.7 m for 2.4 m doors. Ports of a 2.4 m door keep 3 m from other ports. Shape rooms with a 2.4 m door use arms at least 4 m wide, or a box when the envelope is narrower.
4. **Extras.**
   - New rule ids: `module_budget`, `module_leaf_proposed_untested`, `module_socket_landing`, `module_usable_once`.
   - New `module_budget {min, max, used}` field.
   - Module cells use `ceiling_range_m` = [h, h].
   - 0.3.0 shape-room doorways carry `compatibility_type`.
   - Module cells get no shape room.
5. **Check adjustments.**
   - Kit floor colliders (`AuthoredFloor`, `AuthoredPlanarRouteFloor`, `ConnectorThreshold`) count as floor.
   - The 0.5 m wall-approach probe is skipped on a parent edge that carries a module joint.
   - Unreached flood samples inside a module cell are reported, not failed: 8 in the debris room, seed 3.
   - Floor-level underside faces are not trim conflicts.
   - The undo-clearance control is informational. It cannot fire for the column, whose wall straddles its footprint edge.
6. **CLI default.** The CLI default stays `gmap-0.2.0`. Generate 0.3.0 with `generative_map.py generate --generator-version gmap-0.3.0`, then `shape_room.py generate --mode all_walkable`.

**How sockets are opened:** the #160/#168 mechanism, with the exported `connector_open` set before `add_child`.
- The standalone player, environment and PSX-preset switches are turned off.
- A duplicate `WorldEnvironment` that the hall brings is freed after instancing.
- No library scene or catalog file was edited.

## Needs human visual verification

- **Thicker wall at the joint:** the library wall overhangs the parent wall by about 0.12-0.3 m, so it reads as a thicker wall segment.
- **Floor slit:** a 2 cm floor slit at each joint doorway. Collision is bridged.
- **Reveal z-fight:** 5-10 small coplanar reveal and lintel faces per map where the two openings meet. They are counted, not failed, so some flicker there is possible.
- **Look and acceptance:** how the rooms look under the PSX effect, and whether each `proposed_untested` connection is acceptable.

## Launch

```
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/generative_map_walkthrough.tscn -- --map=res://room_catalog/generative_maps/gmap-N-gmap-0.3.0.json --rooms=res://room_catalog/shape_rooms/gmap-N-gmap-0.3.0/index.json
```

N=1 shows the kit rooms, N=2 the hall, and N=3 the debris room plus the hall.
