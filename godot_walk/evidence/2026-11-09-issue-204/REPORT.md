# Issue 204 — per-room reverb flags: wet and dry rooms (gmap-0.11.0)

Status: implementation and automated checks complete. The reverb audio and
ray-cast probing are out of scope (#205/#208); this report prepares a map for
that runtime listen but cannot ask the operator to hear anything yet.

## What changed

- `gmap-0.11.0` adds a deterministic per-room reverb layer
  (`scripts/gmap_reverb.py`) after the gmap-0.10.0 elevation layer.
  Stream: `reverb:gmap-0.11.0`.
  - Every walkable cell carries one boolean `reverb` flag: `true` = wet
    (ringing), `false` = dry (dead carpet pocket). Void cells carry none.
  - The spawn cell is always dry.
  - The draw is **per cell**, not a sequential walk:
    `sha256("<seed>:<attempt>:reverb:gmap-0.11.0:<cell_id>")`. Adding,
    removing or re-drawing one cell does not shift any other cell's flag, so a
    later mutation issue can flip one visited room as a tell.
  - `BASE_PROBABILITY = 0.35`; the probability rises with the nominal room
    volume (`envelope area × authored maximum ceiling`) and gains
    `DOUBLE_HEIGHT_BONUS` when the authored minimum ceiling is at least 3.6 m.
    The wet probability is capped at 0.70; the spawn is 0. The top-level
    `reverb_layer` record stores these constants and the selection rule.
  - One flag is shared by the cell's whole module or shape room.
- `generative_map_assembly.gd` copies the flag to the instanced room as
  `reverb_enabled` metadata and adds a nominal `room_volume_m3` figure. The
  flag is runtime metadata, not geometry: `set_room_reverb(cell_id, enabled)`
  flips it and `room_reverb_enabled(cell_id)` reads it. A missing flag reads as
  dry, so gmap-0.10.0 and older maps load unchanged.
- The validator (`gmap_validate.py`, `gmap_reverb.reverb_errors`) rejects
  non-boolean flags, missing flags on walkable cells, flags on void cells, a
  wet spawn, and any flag or layer metadata that differs from the keyed
  re-derivation. The `generative_map.py validate`/`generate` summary now
  reports wet/dry counts and `wet_ratio`; legacy maps report `layer: absent`
  and every room dry.
- Schema notes: `generative_map.schema.json` describes the cell `reverb` flag
  and the top-level `reverb_layer` record, and the gmap-0.11.0 condition
  requires the flag on every walkable cell.
- `shape_room_rng.version_for_map` maps gmap-0.11.0 to shape-room-0.10.0
  because the reverb layer changes no geometry; old shape-room specs stay
  valid. Version lists in the palette, module, diagonal and runtime checks
  treat gmap-0.11.0 like gmap-0.10.0.
- Regression coverage: 0.1.0–0.10.0 regeneration stays byte-identical, and the
  committed gmap-0.11.0 maps/fills/SVGs and shape rooms are pinned by tests.

## Artifacts

Committed map/fill/SVG and shape-room outputs:

| Seed | Wet | Dry | Notes |
|------|-----|-----|-------|
| 1 | 7 | 7 | two module cells, no diagonal passage |
| 2 | 4 | 11 | module cell, two diagonal passages |
| 3 | 5 | 9 | wet module cell (4.78 m authored ceiling) |
| 279 | 7 | 7 | two drops, three ramps, one module cell; operator-listen candidate |

All four maps validate with `generative_map.py validate` and their generated
shape rooms validate with `shape_room.py validate --mode all_walkable`.

Recommended runtime-listen candidate: `gmap-279-gmap-0.11.0`.

## Checks run

Python (`python3 -m pytest -q godot_walk/scripts`): **663 passed, 5 skipped,
58 subtests passed** (5m26s).

Issue-specific checks (`test_gmap_reverb.py`, 18 passed):

- Same seed gives byte-identical maps and flags; four committed seeds validate.
- gmap-0.11.0 keeps every other layer byte-identical to gmap-0.10.0 for the
  same seed (cells minus `reverb`, edges, light, palettes, wear, surfaces,
  elevation and loop records), and its shape-room geometry is unchanged.
- Removing a cell re-derives the remaining cells' flags unchanged; the draw is
  keyed on seed, attempt, stream and cell id.
- Spawn is dry; both wet and dry rooms occur; module and diagonal-passage cells
  carry the flag; void cells do not.
- The validator rejects a string flag, a missing flag, a wet spawn, a flag on
  a void cell, a flipped flag, and a missing `reverb_layer`.
- Legacy gmap-0.10.0 maps carry no flags, validate, and report every room dry.
- The CLI `validate`/`generate` summary reports wet/dry and `wet_ratio`.
- 0.1.0–0.10.0 committed maps still regenerate byte-identically; the committed
  gmap-0.11.0 map/fill/SVG and shape-room outputs are current and valid.

Seed sweep 1–300 (12 cells, gmap-0.11.0): 0 invalid maps. Wet/dry rooms:
**1682 wet / 2622 dry (wet ratio 0.3908)**. The bias is visible as specified:
nominal volume ≥ 200 m³ is 43.3% wet vs 34.6% below; double-height cells are
45.7% wet vs 37.8% for standard-height cells.

Cross-layer regression: `test_issue201_elevation.gd` passes on the committed
gmap-279-gmap-0.11.0 map (graph 14/14, ramps 3/3, drops 2/2, risers 8/8,
coplanar 0, all negative controls expected).

Godot headless metadata test (`test_issue204_reverb.gd`):

| Seed | Wet | Dry | Rooms | Module rooms | Volumes | Runtime on/off | Legacy 0.10.0 | Controls |
|------|-----|-----|-------|--------------|---------|----------------|---------------|----------|
| 1 | 7 | 7 | 14/14 | 2 | 14/14 | 14/14 | pass (dry) | expected |
| 2 | 4 | 11 | 15/15 | 1 | 15/15 | 15/15 | pass (dry) | expected |
| 3 | 5 | 9 | 14/14 | 1 | 14/14 | 14/14 | pass (dry) | expected |
| 279 | 7 | 7 | 14/14 | 1 | 14/14 | 14/14 | pass (dry) | expected |

The test checks that every instanced shape/module room carries the map flag as
`reverb_enabled` metadata, that `room_volume_m3` matches the nominal map figure,
that the spawn room is dry, and that `set_room_reverb` flips the metadata without
changing the room's children. Negative controls flip a map flag (assembly
follows it) and remove a flag (runtime treats the room as dry). The walkthrough
scene check instantiates `res://scenes/generative_map_walkthrough.tscn` with the
same map and confirms its rooms and spawn metadata.

The older `test_issue183_shape_rooms.gd` stage-1 check is not applicable to
elevation maps; it produces the same failures on gmap-0.10.0 and this layer
does not change them.

Lint: `ruff check` passes on every changed Python file.

## Pending human step

The reverb **audio** and ray-cast probing are the follow-up runtime issue
(#205/#208), so there is nothing to listen to yet and no listen is requested
here. The wet/dry map below is generated and validated, ready for that runtime
issue's operator listen once it implements the audio.

Candidate: `gmap-279-gmap-0.11.0` (7 wet / 7 dry, two drops, three ramps, one
library module). Launch command:

```bash
godot4 --path godot_walk res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-279-gmap-0.11.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-279-gmap-0.11.0/index.json
```

The map summary and the room metadata can be inspected without a human walk.
Operator walk of `gmap-279-gmap-0.11.0` is still pending, as with every map; it
can confirm the map still walks, but it cannot confirm the wet/dry effect until
the runtime audio issue lands. Operator approval of the wet/dry mapping is also
pending.

## Files changed by this issue

- `scripts/gmap_reverb.py` (new), `scripts/gmap_build.py`,
  `scripts/gmap_validate.py`, `scripts/generative_map.py`,
  `scripts/gmap_palette.py`, `scripts/gmap_diagonal_rules.py`,
  `scripts/gmap_module_rules.py`, `scripts/shape_room_rng.py`
- `scripts/generative_map_assembly.gd`, `scripts/issue183_map_checks.gd`,
  `scripts/issue193_diagonal_link_checks.gd`,
  `scripts/test_issue183_shape_rooms.gd`
- `room_catalog/generative_map.schema.json`
- `scripts/test_gmap_reverb.py` (new), `scripts/test_gmap_elevation.py`,
  `scripts/test_issue204_reverb.gd` (new)
- committed `room_catalog/generative_maps/gmap-{1,2,3,279}-gmap-0.11.0.*`
  and `room_catalog/shape_rooms/gmap-{1,2,3,279}-gmap-0.11.0/`
