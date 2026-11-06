# Palettes 0.2.0 — surface variants and acoustic tags

Status: gmap-0.9.0 (issue 199). This note extends `PALETTES.md` and
`../MATERIAL_LANGUAGE.md` without editing either. The 0.1.0 registry remains frozen.

## Registry

`palettes-0.2.0.json` (schema `material_palette_v2.schema.json`) keeps the three
palettes and their style tags from 0.1.0. Each palette now has a `surfaces` block
for `wall`, `floor`, `ceiling` and `trim`. Each surface carries:

- an `acoustic` tag from the closed set `carpet`, `concrete`, `tile`, `plaster`,
  `metal`, `wood`, `debris`; footsteps in #200 will read the floor tag;
- `clean`, `worn` and `damaged` variants. Textured variants use repository
  textures, with worn/damaged textures generated deterministically by
  `scripts/generate_surface_variants.py`; colour variants are authored below.

The generator is CPU-only and reproduces every output byte-for-byte. Its
manifest is `assets/psx_extension/textures/surfaces/surface_variants.json`.
gmap-0.9.0 maps must reference this canonical registry path/hash; map
validation rejects any other 0.2.0 registry.

## Authored variant colours

backrooms_yellow.trim.clean: Color(0.37, 0.34, 0.23)

backrooms_yellow.trim.worn: Color(0.32, 0.29, 0.19)

backrooms_yellow.trim.damaged: Color(0.26, 0.23, 0.15)

industrial_concrete.wall.clean: Color(0.43, 0.43, 0.40)

industrial_concrete.wall.worn: Color(0.37, 0.37, 0.34)

industrial_concrete.wall.damaged: Color(0.30, 0.30, 0.28)

industrial_concrete.ceiling.clean: Color(0.34, 0.35, 0.33)

industrial_concrete.ceiling.worn: Color(0.29, 0.30, 0.28)

industrial_concrete.ceiling.damaged: Color(0.23, 0.24, 0.22)

industrial_concrete.trim.clean: Color(0.28, 0.29, 0.28)

industrial_concrete.trim.worn: Color(0.24, 0.25, 0.24)

industrial_concrete.trim.damaged: Color(0.19, 0.20, 0.19)

plaster_debris.floor.clean: Color(0.34, 0.33, 0.31)

plaster_debris.floor.worn: Color(0.30, 0.28, 0.26)

plaster_debris.floor.damaged: Color(0.24, 0.22, 0.20)

plaster_debris.ceiling.clean: Color(0.43, 0.42, 0.38)

plaster_debris.ceiling.worn: Color(0.37, 0.36, 0.32)

plaster_debris.ceiling.damaged: Color(0.30, 0.29, 0.26)

plaster_debris.trim.clean: Color(0.24, 0.25, 0.23)

plaster_debris.trim.worn: Color(0.20, 0.21, 0.19)

plaster_debris.trim.damaged: Color(0.16, 0.17, 0.15)

## Gmap-0.9.0 wear rule

`surface:gmap-0.9.0` draws one wear level per generated non-module cell:
`0` clean, `1` worn, `2` damaged. The weights follow the cell's light tier:

| Light tier | wear 0 | wear 1 | wear 2 |
|---|---:|---:|---:|
| bright | 80% | 18% | 2% |
| normal | 62% | 30% | 8% |
| dim (dark wing) | 5% | 40% | 55% |

Landmarks and the spawn cell are always `0`. A dark-wing cell is never `0`.
Within a cell each surface draws its own variant: at wear 0 it is `clean`; at
wear 1 the weights are 35% clean / 55% worn / 10% damaged; at wear 2 they are
5% clean / 35% worn / 60% damaged. The palette assignment from gmap-0.5.0 is
unchanged and is checked separately.

## Runtime

Generated rooms with a `surface_variants` record use the selected texture or
colour for the wall, floor, ceiling and trim. Every generated floor collider
carries `surface_acoustic` from the palette floor tag. Maps up to and including
gmap-0.8.0 keep their original materials and have no acoustic metadata.
