# Issue 183: shape stage 1 rooms and walkable assembly

Generated rooms are the stereotyped ground: every feature is a symbol, each room is bounded by its map
cell, and rooms never change the map. `registration_accepted=false`, `scale_calibrated=false`.

## What was checked (headless, physics only, no rendering)

- Python: primitive per port pattern, doorway wall margins, polygon inside envelope, connectivity,
  determinism (byte-identical), schema, stage_max 0 gives boxes, all features symbols, negative controls.
- Godot per room: floor ray support at 0.5 m samples inside the polygon and none outside; the player
  capsule (r 0.3, h 1.2) blocked at wall samples away from doorways; clear through open doorways;
  closed_visible doorways blocked.
- Godot assembled map: every direct edge passable in both directions (capsule sweep from 1 m inside one
  cell to 1 m inside the other with floor support throughout); every closed edge blocked; flood fill from
  the spawn reaches every walkable cell and no void cell.
- Negative controls: one doorway removed fails traversal; one floor rectangle removed fails support.

## Results

| map | mode | rooms | edges both ways | closed blocked | flood cells | void reached | controls failed as expected |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gmap-1-gmap-0.1.0 | all_walkable | 12 | 22/22 | 1/1 | 12/12 | 0 | doorway_removed, floor_rect_removed |
| gmap-1-gmap-0.1.0 | pending | 5 | 0/0 | 7/7 | 1/1 | 0 | floor_rect_removed |
| gmap-2-gmap-0.1.0 | all_walkable | 12 | 22/22 | 1/1 | 12/12 | 0 | doorway_removed, floor_rect_removed |
| gmap-3-gmap-0.1.0 | all_walkable | 12 | 22/22 | 2/2 | 12/12 | 0 | doorway_removed, floor_rect_removed |

## Shapes (all_walkable)

- gmap-1-gmap-0.1.0: primitives {'dead_end': 4, 'l_shape': 4, 't_shape': 1, 'u_shape': 3}; classes {'box': 11, 'l_shape': 1}; construction {'arms': 5, 'box': 7}
- gmap-2-gmap-0.1.0: primitives {'dead_end': 3, 'l_shape': 4, 'straight': 3, 't_shape': 1, 'u_shape': 1}; classes {'box': 12}; construction {'arms': 4, 'box': 8}
- gmap-3-gmap-0.1.0: primitives {'dead_end': 4, 'l_shape': 3, 'straight': 1, 't_shape': 2, 'u_shape': 2}; classes {'box': 10, 'l_shape': 1, 'rectilinear_polygon': 1}; construction {'arms': 8, 'box': 4}

## Operator walkthrough (seed 1)

```
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/generative_map_walkthrough.tscn -- --map=res://room_catalog/generative_maps/gmap-1-gmap-0.1.0.json --rooms=res://room_catalog/shape_rooms/gmap-1-gmap-0.1.0/index.json
```

Press R to reset to the spawn in cell c00.

## Headless test

```
godot4 --headless --path godot_walk --script res://scripts/test_issue183_shape_rooms.gd -- --map=res://room_catalog/generative_maps/<map_id>.json --rooms=res://room_catalog/shape_rooms/<map_id>/index.json
```

## Requires human visual verification

Texture density and UV scale, olive trim, the recessed dark panel at closed doorways, lamp placement,
the PSX look and overall room feel cannot be judged without rendering. No captures were taken.
