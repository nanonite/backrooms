# Issue 208 — tile, metal and wood floor palettes (gmap-0.12.0)

Status: implementation and automated checks complete. The operator walk and
approval of the look and sound are still pending; a render is not approval.

## What changed

- `room_catalog/material_palettes/palettes-0.3.0.json` (schema
  `material_palette_v3.schema.json`, `schema_version: 3`) keeps the three 0.2.0
  palettes unchanged and adds:
  - `tiled_institutional` — tile floor (`tile`), pale tiled walls, low-key tile ceiling;
  - `metal_service` — metal grating floor (`metal`), concrete walls, metal panel ceiling;
  - `wood_parquet` — wood parquet floor (`wood`), plaster walls, tile ceiling.
  Each carries all four surfaces and the `clean`/`worn`/`damaged` variants.
  `PALETTES_0_3_0.md` records the new values and the regional rule.
- `scripts/generate_palette_0_3_0_textures.py` draws 18 PSX-resolution tile,
  metal and parquet textures on the CPU, reproducibly, with
  `assets/psx_extension/textures/surfaces/palette_0_3_0_textures.json`
  (sha256 per output and for the generating script). Existing concrete,
  plaster and ceiling textures are reused from the 0.2.0 provenance.
- `scripts/gmap_floor_regions.py` adds the `floor_regions:gmap-0.12.0` layer.
  It runs after the library-anchor palette rule:
  - up to 3 non-anchored seed cells, graph distance 1, picked in keyed score
    order;
  - every seed/palette choice is a separate
    `sha256("<seed>:<attempt>:floor_regions:gmap-0.12.0:...")` draw, so one
    room's floor can be re-drawn later without shifting any other cell;
  - library anchors always win; module, void, diagonal-passage, spawn and
    spawn-neighbour cells never become region seeds or members;
  - the layer spends at most 15% of the non-anchored generated envelope area
    and also keeps an envelope safety margin at 60%, so the measured default
    carpet share stays at or above 55% of generated floor area wherever the
    existing anchors already leave room for it.
- `generative_map.py validate` and `generate` now report
  `summary.floor_palettes`: per-map cell counts, envelope area and the default
  carpet share (whole-map and non-anchor), so the measured mix can be read per
  seed without rerunning the sweep.
- gmap-0.12.0 maps reference the canonical 0.3.0 registry path/hash. Older
  maps keep their own 0.1.0/0.2.0 registries and still validate.
- The palette record stays plain map data. A gmap-0.12.0 cell carries
  `registry_version: "0.3.0"`, `region_seed_cell_id` and `region_distance` in
  addition to the old fields; no geometry, light, wear, surface-variant or
  reverb draw changed. The assembly and the shape-room builder already derive
  `surface_acoustic` from the palette floor and the 0.2.0 variants block, so no
  new runtime code was needed. The palette record stays plain in-memory map
  data, so a later runtime can mutate or re-draw one room's floor without
  changing geometry.

## Version and files

- `gmap_build.GENERATOR_VERSION_V12 = "gmap-0.12.0"`, rules include
  `floor_region_layer`.
- Committed gmap-0.12.0 maps, fills and SVGs: seeds 1, 2, 3, 32, 279.
  Shape rooms for the same five maps are committed under
  `room_catalog/shape_rooms/gmap-<seed>-gmap-0.12.0/`.
- `generative_map.schema.json` accepts the new palette-record fields, the
  `floor_regions` record, and the gmap-0.12.0 conditions.
- Version lists in the palette, light, elevation, diagonal, module, assembly
  and headless checks treat gmap-0.12.0 like gmap-0.11.0 where the layer is
  material-only.

## Measured palette mix

Full per-seed data: `palette_mix.json` (seeds 1–60, 768 generated cells).

| Measure | Result |
|---|---|
| Carpet share of non-anchored generated floor area (min per seed) | 78.4% |
| Carpet share of all generated floor area (min per seed) | 55.7% |
| Aggregate carpet share, non-anchored | 87.9% |
| Aggregate carpet share, whole sweep | 80.5% |
| New palette cells (tile / metal / wood) | 40 / 48 / 51 |

New-palette wear coverage across the sweep: tile 21 clean, 17 worn, 2 damaged;
metal 20 clean, 16 worn, 12 damaged; wood 22 clean, 19 worn, 10 damaged.

Seeds 81, 114, 122 and 133 already have more than 45% of their generated floor
area taken by library-anchor palettes before this layer runs. The regional
layer assigns nothing on those maps (the safety budget is zero), so it does not
lower their baseline share; their whole-map carpet share stays what the
existing anchor rule gives.

Committed-map mixes (generated cells only):

| Seed | Region seeds | Yellow | Tile | Metal | Wood | Other anchors |
|---|---|---:|---:|---:|---:|---:|
| 1 | tile c11, wood c09 | 9 | 1 | 0 | 2 | 0 |
| 2 | tile c06, wood c11 | 11 | 1 | 0 | 2 | 0 |
| 3 | tile c09 | 10 | 2 | 0 | 0 | 1 concrete |
| 32 | metal c11, tile c07, wood c02 | 8 | 1 | 2 | 1 | 0 |
| 279 | wood c03 | 10 | 0 | 0 | 2 | 1 concrete |

## Checks run

Python:

- `python3 -m pytest -q godot_walk/scripts` — **681 passed, 5 skipped, 58
  subtests passed** in 6m06s (with the final palette-summary tests included).
- `scripts/test_gmap_floor_regions.py` — **18 passed**: registry validity and
  0.3.0 texture reproducibility, deterministic gmap-0.12.0 maps, canonical
  registry hash rejection, keyed draw behaviour, anchor/spawn exclusion,
  per-seed and aggregate 55% carpet share, strong connectivity, shape-spec v3
  materials, the per-map `floor_palettes` summary and CLI output, old v0.11.0
  maps still valid, and committed map/fill/SVG/shape-room bytes.
- Existing palette, surface, reverb, elevation and module tests still pass.

Godot headless:

```bash
godot4 --headless --path godot_walk --script res://scripts/test_issue208_palettes.gd -- \
  --map=res://room_catalog/generative_maps/gmap-32-gmap-0.12.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-32-gmap-0.12.0/index.json \
  --out=res://evidence/2026-11-09-issue-208/runtime_gmap-32.json
```

Result: `PASS ... rooms={"metal_service":2,"tiled_institutional":1,"wood_parquet":1}
floor_colliders=4 floor_visuals=4 failures=0`. Every checked floor collider
carries `surface_acoustic` = tile/metal/wood, matching the palette, its wear and
variant, and the floor visual uses the palette texture.

The issue199 surface block inside `test_issue183_shape_rooms.gd` also passes on
gmap-32 (`surface_rooms=12 floor_colliders=12 acoustic_resolved=12
surface_tags=48 surface_failures=0`, `palette_mismatch=0`). That script's wider
geometry/flood checks report the same pre-existing failures on the matching
gmap-0.11.0 map, so they are not caused by this palette change; the map graph
itself is strongly connected.

Render captures:

- `captures/contact_sheet_palettes.png` — 3 palettes × clean/worn/damaged.
- Nine individual PNGs in `captures/`.
- Geometry and lights come from the committed gmap-32 map; the capture harness
  forces each palette variant so all nine looks can be judged from one scene
  (the map itself only assigns a subset of variants).

## Operator walk (pending human approval)

Exact command:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-32-gmap-0.12.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-32-gmap-0.12.0/index.json
```

gmap-32 shows carpet plus all three new floors (`wood_parquet` at c02,
`metal_service` at c05/c11, `tiled_institutional` at c07). Listen for the floor
tag changing as you cross those rooms; look for the parquet grain, metal
grating and pale tile grid. The operator must approve the look and sound before
this issue closes. The map is strongly connected and the spawn is on the
default carpet; the agent cannot walk or hear it.
