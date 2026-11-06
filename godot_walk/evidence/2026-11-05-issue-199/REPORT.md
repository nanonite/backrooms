# Chainlink #199 — surface layer, palette variants and acoustic tags

**Status:** implementation committed as `7586380`; #199 closed after operator approval.
`registration_accepted=false` and `scale_calibrated=false` remain unchanged.

## Implementation

- Added `palettes-0.2.0.json` and `material_palette_v2.schema.json`. The frozen
  `palettes-0.1.0.json` and its schema are untouched.
- Each palette now has `wall`, `floor`, `ceiling` and `trim` surfaces with
  `clean`, `worn` and `damaged` variants and one acoustic tag from
  `carpet`, `concrete`, `tile`, `plaster`, `metal`, `wood`, `debris`.
- Added `scripts/generate_surface_variants.py` (CPU-only, deterministic). It
  derives ten worn/damaged textures from five existing repository textures and
  writes `assets/psx_extension/textures/surfaces/surface_variants.json` with the
  source/output hashes. No downloads were used.
- Added `gmap-0.9.0` as a surface post-pass over `gmap-0.8.0` on the independent
  stream `surface:gmap-0.9.0`.
  - Per generated non-module cell: `wear` 0-2 and `surface_variants`.
  - Wear weights follow the light tier: bright 80/18/2, normal 62/30/8, dim
    5/40/55. Landmarks and spawn are clean; dark-wing cells are never clean.
  - Within a cell each surface draws its own variant: wear 0 clean; wear 1
    35/55/10 clean/worn/damaged; wear 2 5/35/60.
  - The gmap-0.5.0 palette assignment, gmap-0.8.0 geometry and light records are
    preserved.
- Runtime uses the selected variant texture/colour and writes
  `surface_acoustic`, `surface_wear` and `surface_variant` on generated floor
  collider bodies. Maps up to and including gmap-0.8.0 render unchanged.
- Added `PALETTES_0_2_0.md`, `issue199_surface_checks.gd` and
  `test_gmap_surface.py`.
- Post-review hardening: gmap-0.9.0 requires the canonical 0.2.0 registry, so
  the map and generated-room material loader cannot disagree. Invalid or
  non-canonical registries skip dependent surface checks, and generated texture
  hashes are verified against `surface_variants.json` during registry
  validation; manifest records are type-checked before their source/hash fields
  are used, missing generated textures return a validation error without
  hashing, and the generator check separately verifies deterministic
  regeneration.

### Scope boundaries

- The optional stain-decal layer was not implemented. Wear is expressed by the
  deterministic worn/damaged texture and colour variants.
- Library-module floor colliders are not tagged yet. Their scenes are
  hash-pinned, and #200 explicitly owns the module-to-acoustic mapping at
  assembly time. The headless check in this issue covers every generated
  shape-room floor collider.
- No normal/roughness maps, new source videos, room production, stitching or
  generation were added.

## Kept maps

The V0.9 maps and shape rooms were generated with the existing deterministic
commands. `gmap-0.9.0` files are new; the V0.8 and older maps are unchanged.

| Seed | Cells incl. void | Palette cells | Wear 0/1/2 | Dark wing |
|---:|---:|---|---|---|
| 1 | 15 | yellow 12 | 7 / 4 / 1 | placed |
| 2 | 18 | yellow 14 | 10 / 3 / 1 | not selected |
| 3 | 15 | yellow 12, industrial 1 | 6 / 4 / 3 | placed |
| 6 | 17 | yellow 10, industrial 1, plaster 1 | 8 / 1 / 3 | placed |
| 11 | 16 | yellow 12, plaster 1 | 5 / 3 / 5 | placed |
| 31 | 17 | yellow 12, plaster 2 | 8 / 5 / 1 | placed |
| 33 | 17 | yellow 10, industrial 2 | 6 / 5 / 1 | not selected |
| 39 | 14 | yellow 10, industrial 2 | 6 / 3 / 3 | not selected |
| 44 | 18 | yellow 12, plaster 2 | 6 / 5 / 3 | not selected |
| 54 | 15 | yellow 10, industrial 2 | 7 / 3 / 2 | not selected |
| 69 | 18 | yellow 12, industrial 1 | 7 / 3 / 3 | not selected |

Seeds 1-3 are the base set. Seeds 33/54/39 supply industrial wear 1/2; seeds
6/44/11 supply plaster wear 0/1/2; seed 11 is the dark-wing wear-2 case.

## Python verification

- `python3 -m pytest -q godot_walk/scripts`: **628 passed, 4 skipped,
  58 subtests passed** in 125.84 s.
- `GMAP_SURFACE_SWEEP=1 python3 -m pytest -q -s
  godot_walk/scripts/test_gmap_surface.py::test_v90_seed_sweep_12_and_20_cells`:
  **1 passed in 310.84 s** (600 maps).
- `ruff check`, `ruff format --check` and `python3 -m py_compile` passed on every
  changed Python file.
- `generative_map.py validate` and `shape_room.py validate --mode all_walkable`
  passed for all 11 kept V0.9 maps.
- V0.9 geometry, light records and palette records equal the corresponding V0.8
  records after removing `wear`, `surface_variants`, `palette_registry` and the
  version/map-id/rules metadata.

## Headless verification

`test_issue183_shape_rooms.gd` passed on every kept map. All rooms report
`palette_mismatch=0`, every generated floor collider resolves to an acoustic
tag, and there were no reported failures.

| Seed | Shape rooms | Lights | Floor colliders | Acoustic resolved | Surface tags | Failures |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 12 | 44 | 12 | 12 | 48 | 0 |
| 2 | 14 | 34 | 14 | 14 | 56 | 0 |
| 3 | 13 | 31 | 13 | 13 | 52 | 0 |
| 6 | 12 | 24 | 12 | 12 | 48 | 0 |
| 11 | 13 | 27 | 13 | 13 | 52 | 0 |
| 31 | 14 | 45 | 14 | 14 | 56 | 0 |
| 33 | 12 | 35 | 12 | 12 | 48 | 0 |
| 39 | 12 | 21 | 12 | 12 | 48 | 0 |
| 44 | 14 | 40 | 14 | 14 | 56 | 0 |
| 54 | 12 | 41 | 12 | 12 | 48 | 0 |
| 69 | 13 | 26 | 13 | 13 | 52 | 0 |

Receipts: `runtime/runtime_gmap-<seed>.json`.

## Visual review

Final canonical captures are under `captures-final2/`; the full palette/wear
grid is `contact_sheet_palette_wear.png`.

| Palette | Wear 0 | Wear 1 | Wear 2 |
|---|---|---|---|
| `backrooms_yellow` | `captures-final2/seed1/surface_backrooms_yellow_wear0_c02.png` | `captures-final2/seed1/surface_backrooms_yellow_wear1_c01.png` | `captures-final2/seed2/surface_backrooms_yellow_wear2_c11.png` |
| `industrial_concrete` | `captures-final2/seed3/surface_industrial_concrete_wear0_c06.png` | `captures-final2/seed33/surface_industrial_concrete_wear1_c10.png` | `captures-final2/seed54/surface_industrial_concrete_wear2_c06.png` |
| `plaster_debris` | `captures-final2/seed6/surface_plaster_debris_wear0_c11.png` | `captures-final2/seed44/surface_plaster_debris_wear1_c02.png` | `captures-final2/seed11/surface_plaster_debris_wear2_c04.png` |

The dark-wing wear-2 capture is
`captures-final2/seed11/dark_wing_wear2_c01.png`. The matched same-room pair is
`captures/matched-wear-v8/matched_gmap-1-gmap-0.8.0_c05.png` against
`captures/matched-wear-v9/matched_gmap-1-gmap-0.9.0_c05.png`, with
`matched_wear_v8_v9.png` as a side-by-side sheet.

I inspected the nine palette/wear captures, the dark-wing capture, the matched
pair and both contact sheets. Clean, worn and damaged variants are visibly
distinct: the yellow wallpaper gains grime/stains and crack lines; the concrete
floor gains oil-like stains and debris; the painted plaster wall gains peeling
patches and damage. The matched seed-1 `c05` pair has mean absolute RGB
difference 9.30, maximum channel difference 56, and 93.8% of pixels changed by
more than 2. The dark-wing wear-2 view is dark but readable, consistent with
the light layer. Some rooms are small or dark, so several captures are
close-up or low-key; that is framing, not a geometry change. The plaster wear-2
view includes a bright module/debris element at its edge. The operator approved
the view on 2026-11-06, noting the added depth.

All captures ran under the guarded Vulkan path. Capture receipts are in
`resource_runs/`.

## Commands

Launch a V0.9 dark-wing example:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-11-gmap-0.9.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-11-gmap-0.9.0/index.json
```

Launch the rotunda:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/generative_map_walkthrough.tscn -- \
  --map=res://room_catalog/generative_maps/gmap-69-gmap-0.9.0.json \
  --rooms=res://room_catalog/shape_rooms/gmap-69-gmap-0.9.0/index.json
```

Regenerate the derived textures and verify them:

```bash
python3 godot_walk/scripts/generate_surface_variants.py generate
python3 godot_walk/scripts/generate_surface_variants.py check
```

## Protected inputs

- `MATERIAL_LANGUAGE.md`, `palettes-0.1.0.json`, the library index/catalog
  snapshots, and the existing source textures were not edited.
- No GPU inference, Hunyuan call, room production, stitching or generation ran.
- Implementation committed as `7586380`; library floor acoustic mapping remains
  part of #200.
