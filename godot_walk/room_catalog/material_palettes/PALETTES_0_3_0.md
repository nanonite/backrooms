# Palettes 0.3.0 — tile, metal and wood floors

Status: gmap-0.12.0 (issue 208). This note extends `PALETTES.md`,
`PALETTES_0_2_0.md` and `../MATERIAL_LANGUAGE.md` without editing them. The
0.1.0 and 0.2.0 registries and their textures remain frozen.

## Registry

`palettes-0.3.0.json` (schema `material_palette_v3.schema.json`) keeps the three
0.2.0 palettes unchanged and adds three floor-led regional palettes:

- `tiled_institutional` — tile floor (`tile`), pale tiled walls, low-key tile ceiling;
- `metal_service` — metal grating floor (`metal`), concrete walls, metal panel ceiling;
- `wood_parquet` — wood parquet floor (`wood`), plaster walls, tile ceiling.

Every palette still carries the 0.2.0 `surfaces` block for `wall`, `floor`,
`ceiling` and `trim` and the `clean`/`worn`/`damaged` variants. Acoustic tags
remain within the closed set `carpet`, `concrete`, `tile`, `plaster`, `metal`,
`wood`, `debris`.

The new tile, metal and wood images are generated deterministically on the CPU
by `scripts/generate_palette_0_3_0_textures.py`; the manifest is
`assets/psx_extension/textures/surfaces/palette_0_3_0_textures.json`. Reused
concrete, plaster and ceiling textures point at their existing 0.2.0
provenance. No downloaded art is involved.

gmap-0.12.0 maps must reference this canonical registry path/hash; map
validation rejects any other 0.3.0 registry.

## Generated textures

tiled_institutional.wall.clean: tiled_institutional_wall_clean.png

tiled_institutional.wall.worn: tiled_institutional_wall_worn.png

tiled_institutional.wall.damaged: tiled_institutional_wall_damaged.png

tiled_institutional.floor.clean: tiled_institutional_floor_clean.png

tiled_institutional.floor.worn: tiled_institutional_floor_worn.png

tiled_institutional.floor.damaged: tiled_institutional_floor_damaged.png

tiled_institutional.ceiling.clean: tiled_institutional_ceiling_clean.png

tiled_institutional.ceiling.worn: tiled_institutional_ceiling_worn.png

tiled_institutional.ceiling.damaged: tiled_institutional_ceiling_damaged.png

metal_service.floor.clean: metal_service_floor_clean.png

metal_service.floor.worn: metal_service_floor_worn.png

metal_service.floor.damaged: metal_service_floor_damaged.png

metal_service.ceiling.clean: metal_service_ceiling_clean.png

metal_service.ceiling.worn: metal_service_ceiling_worn.png

metal_service.ceiling.damaged: metal_service_ceiling_damaged.png

wood_parquet.floor.clean: wood_parquet_floor_clean.png

wood_parquet.floor.worn: wood_parquet_floor_worn.png

wood_parquet.floor.damaged: wood_parquet_floor_damaged.png

## Authored colours

tiled_institutional.trim.clean: Color(0.30, 0.32, 0.31)

tiled_institutional.trim.worn: Color(0.26, 0.28, 0.27)

tiled_institutional.trim.damaged: Color(0.21, 0.23, 0.22)

tiled_institutional.lamp: Color(0.92, 0.94, 0.90)

metal_service.trim.clean: Color(0.25, 0.27, 0.28)

metal_service.trim.worn: Color(0.21, 0.23, 0.24)

metal_service.trim.damaged: Color(0.16, 0.18, 0.19)

metal_service.lamp: Color(0.86, 0.89, 0.92)

wood_parquet.trim.clean: Color(0.36, 0.25, 0.15)

wood_parquet.trim.worn: Color(0.31, 0.21, 0.12)

wood_parquet.trim.damaged: Color(0.25, 0.17, 0.10)

wood_parquet.lamp: Color(0.95, 0.92, 0.84)

## Gmap-0.12.0 floor-region rule

The library-anchor palette rule runs first and always wins. A separate
`floor_regions:gmap-0.12.0` stream then draws one to three non-anchored seed
cells and spreads each seed's palette to cells within graph distance 1. The
spawn cell and its direct neighbours are excluded. Every seed and palette
choice is a per-cell sha256 draw, so a single room's floor can be re-drawn
later without shifting another cell's result.

The layer spends at most 15% of the non-anchored generated envelope area and
keeps a 60% envelope safety margin for the default palette, so the measured
carpet share stays at or above 55% of generated floor area wherever the
existing anchors already leave room for it. The default `backrooms_yellow`
palette stays the dominant floor; library anchor palettes can still take their
own cells, as they did before this layer. The palette record stays plain map data
(`palette_id`, `region_seed_cell_id`, `region_distance`) so a later runtime can
mutate or re-draw one room without rebuilding geometry.

## Runtime

Generated rooms with a `surface_variants` record use the selected texture or
colour for the wall, floor, ceiling and trim. Every generated floor collider
carries `surface_acoustic` from the palette floor tag, so tile, metal and wood
footsteps can now play. Older maps keep their own registries and materials.
