# Issue 201 — elevation: floor levels, ramps and one-way ledge drops (gmap-0.10.0)

Status: implementation and automated checks complete. Operator walk pending; this
report is not an approval.

## What changed

- `gmap-0.10.0` adds a deterministic post-pass (`scripts/gmap_elevation.py`)
  after the gmap-0.9.0 surface layer. Stream: `elevation:gmap-0.10.0`.
  - Per-cell `floor_y` in `{-3.0, -1.5, 0, 1.5, 3.0}`; the spawn cell is 0.
  - Per-edge `vertical`: `level`, `ramp` or `drop`.
  - A climb is one 1.5 m step with probability 0.30; a drop subset is drawn at
    probability 0.20. A ramp is 1.5 m over a 3.25 m run (24.78 degrees), built
    inside the lower cell along the doorway axis and only kept when it fits.
  - Drops are one-way upper to lower, 1.5–4.5 m, and only kept when the lower
    cell can still reach the upper cell. The validator uses the reusable
    `strongly_connected(cell_ids, directed_edges)` function over the map graph.
  - Non-tree `elevation_loop` level/ramp edges provide return routes; loop ramps
    are never placed where another ramp or a drop landing already occupies the
    lower cell.
  - The lower cell of every ramp/drop gets a ceiling of at least the upper floor
    plus 2.6 m. Module cells keep their authored ceilings; drops/ramps into
    modules are not used.
  - Diagonal links and landmarks stay at one level (their tree paths are locked).
- `scripts/shape_room_spec.py` / `shape_room_rng.py` add shape-room-0.10.0:
  `floor_y`, doorway `sill_height_m`/`vertical`, and lower-cell ramp records.
  Shape-room geometry draws stay on the 0.9.0 stream, so old rooms are unchanged.
- `scripts/shape_room_builder.gd`:
  - raised doorway sills (`WallSill_*`) and ledge-lip trim (`TrimLedge_*`);
  - stepped ramp visuals with one sloped convex collider (`Ramp_*`);
  - no change to normal (sill 0) rooms.
- `scripts/generative_map_assembly.gd`:
  - generated rooms are offset by their cell `floor_y`;
  - library modules are placed at their parent cell's `floor_y`;
  - riser walls (`WallRiser_*`) fill every vertical face between different
    levels, on the upper cell side, ending under the upper floor slab;
  - the safety net moves to `min(floor_y) - 4 m`;
  - spawn height follows the origin cell's floor;
  - gmap-0.10.0 is treated as a lit/surface map.
- `generative_map.schema.json`, `shape_room.schema.json` describe the new
  fields. `gmap_rules.check_tree` ignores non-tree elevation loop edges.

## Artifacts

Committed map/fill/SVG and shape-room outputs:

| Seed | Levels | Ramps | Drops | Notes |
|------|--------|-------|-------|-------|
| 1 | 0:12, +1.5:2 | 1 | 0 | baseline |
| 2 | 0:11, +1.5:4 | 1 | 0 | baseline |
| 3 | 0:12, -1.5:2 | 1 | 0 | baseline |
| 279 | 0:7, +1.5:7 | 3 | 2 | operator-walk candidate |

Seed 279 is the first seed in 1–300 with at least two drops and two ramps.

Evidence (intentionally uncommitted; captures/runtime are gitignored):

- `godot_walk/evidence/2026-11-08-issue-201/captures/`
  - `down_from_ledge_c02_c00.png`
  - `up_at_ledge_from_below_c02_c00.png`
  - `along_ramp_c04_c05.png`
  - `double_height_room_c02_c00.png`
- `godot_walk/evidence/2026-11-08-issue-201/runtime/runtime_gmap-{1,2,3,279}.json`

## Checks run

Python:

- `python3 -m pytest -q godot_walk/scripts` → **645 passed, 5 skipped,
  58 subtests passed**.
- `python3 -m pytest -q godot_walk/scripts/test_gmap_elevation.py` → **9 passed**
  (including seeds 1–300 validation).
- Seeds 1–300 all validate for gmap-0.10.0.
- Distribution over seeds 1–300: levels `0:3205, +1.5:510, -1.5:504,
  +3.0:42, -3.0:43`; edges `level:4465, ramp:518, drop:39`.
- Legacy 0.1.0–0.9.0 regeneration is byte-identical to the committed map files
  for seeds 1–3 (test asserts all ten versions).
- Reusable directed strong-connectivity test has a negative case; a valid map
  with a ramp changed to a one-way drop without a return route is rejected with
  `elevation_graph_not_strongly_connected`.
- Ramp run/angle/fit and lower-ceiling clearance are asserted; drops are in
  1.5–4.5 m and keep upper-floor + 2.6 m clearance.
- `generative_map.py validate` and `shape_room.py validate` pass for seeds
  1, 2, 3 and 279.
- `ruff check` passes on all changed Python files.

Godot headless (`test_issue201_elevation.gd`):

| Seed | Graph | Level edges | Ramps | Drops | Landings | Risers | Coplanar | Controls |
|------|-------|-------------|-------|-------|----------|--------|----------|----------|
| 1 | 14/14 | 15/15 | 1/1 | 0/0 | 0 | 1/1 | 0 | all expected |
| 2 | 15/15 | 15/15 | 1/1 | 0/0 | 0 | 1/1 | 0 | all expected |
| 3 | 14/14 | 15/15 | 1/1 | 0/0 | 0 | 2/2 | 0 | all expected |
| 279 | 14/14 | 11/11 | 3/3 | 2/2 | 2 | 8/8 | 0 | all expected |

The seed-279 run traverses level and ramp edges both ways, scripts a walk off
both drop ledges (one landing event each, no reset), checks that the capsule
cannot climb either drop, flood-fills the directed graph from spawn, checks
riser coverage, and checks the new sill/ledge/ramp/riser boxes for same-facing
coplanar faces. Negative controls remove a riser, remove a ramp collider, and
turn a ramp into a drop without a return route; each fails as expected.

Existing gmap-0.9.0 headless checks still pass (`test_issue183_shape_rooms.gd`
on `gmap-3-gmap-0.9.0`: PASS).

## Pending human step

Operator walk of `gmap-279-gmap-0.10.0` (and optionally the seed 1–3 baseline
maps) is still required. The walkthrough can be launched with the existing
`generative_map_walkthrough.tscn` and:

```bash
godot4 --path godot_walk -- --map=res://room_catalog/generative_maps/gmap-279-gmap-0.10.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.10.0/index.json
```

The captures are visual evidence, not operator approval. No audio was changed,
so no listening step is required for this issue.
