# Palettes

Status: gmap-0.5.0 (issue 192). This note extends `../MATERIAL_LANGUAGE.md` without editing it:
that file is hash-pinned by the frozen contract records and the catalog snapshots, so the palette
rules live here instead. Visual results are not verified by agents (no display); they need operator
review.

## Registry

`palettes-0.1.0.json` (schema `material_palette.schema.json`) lists the palettes a generated shape
room can take. Each has a `palette_id`, `match_style_tags`, `source_module_ids` and the fields
`wall`, `floor`, `ceiling` (a texture with `tile_m`, or a solid colour), `trim_color` and
`lamp_color`. Every field carries `provenance: {from: "<res path>::<constant or material name>",
sign: "icon" | "symbol"}`: `icon` values are read from a library room's existing files, `symbol`
values are authored here. The registry never edits library rooms or textures.

| Palette | Source | Look |
| --- | --- | --- |
| `backrooms_yellow` (default) | The kit values generated rooms always used | Yellow wallpaper, kit floor and ceiling textures, olive trim, warm lamps |
| `industrial_concrete` | `industrial-hall-panorama-v3/room.gd` | Grey concrete walls and roof, hall concrete floor texture, dark grey trim, cool lamps |
| `plaster_debris` | `debris-window-rock-room-v1/room.gd` | Painted plaster wall texture, solid grey floor and beige ceiling as the room draws them, cool lamps |

The lamp colour (0.86, 0.88, 0.86) of the two source palettes is authored (`symbol`) as a cool
pale tone chosen in the issue 192 design; it is not read from a library file.

Tile sizes. A wall or floor texture is tiled once per `tile_m` metres (nearest-filtered, unshaded,
as in the kit). `industrial_concrete` floor: the hall floor is 16 m x 13 m at uv scale 4, so one
tile spans about 4 m; `tile_m` 4.0 keeps that (about 80 texels per metre across). `plaster_debris`
wall: `painted_wall.png` (600 x 165) is stretched about 6 m x 4.2 m in the library room; a 4.0 m
square tile gives about the same vertical density (about 40 texels per metre). The `plaster_debris`
floor is the solid colour the library room draws (its `FLOOR_TEXTURE_PATH` constant is defined but not applied there).

## The distance rule

For every walkable cell that holds no library module, take the graph distance d over open (direct)
edges to each placed figure module. The module's palette is the first non-default registry palette
(sorted by `palette_id`) whose `match_style_tags` overlap the module's accepted `style_tags`. Ground
(kit) modules, and figure modules that match no palette, exert no influence.

- d = 1: the module's palette.
- d = 2: that palette with probability 0.5 (one seeded coin per cell, drawn in `cell_id` order for
  every such cell); otherwise the default.
- d >= 3: the default.

Competing anchors: smaller d wins, then the higher module `rarity_tier`, then `module_id`. Each
cell records `palette: {palette_id, anchor_module_id | null, distance | null}`; module and void
cells carry none. There is no blending between palettes.
