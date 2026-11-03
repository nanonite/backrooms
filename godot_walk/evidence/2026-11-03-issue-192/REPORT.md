# Issue #192: neighbour palettes (gmap-0.5.0)

Implemented by a Sonnet 5.5 agent. The lead wrote this report from the agent's hand-back and re-ran pytest and the headless checks on seeds 3 and 129.

## What it does
A palette registry at `room_catalog/material_palettes/palettes-0.1.0.json` holds three palettes: backrooms_yellow (the default), industrial_concrete and plaster_debris. The registry has a schema and a `PALETTES.md`. Every value cites the library room line it was read from, and a validator checks that each citation holds that value. The lamp colours for the two non-default palettes are authored (sign: symbol).

A generated room picks its palette like this:
- At graph distance 1 from a placed figure module, it takes that module's palette.
- At distance 2, it takes it with p = 0.5, using a seeded coin.
- Further away, it keeps the default.

A 0.5.0 map is the 0.4.0 map of the same seed plus palettes, so room geometry is identical.

## Palette rooms per seed (all PASS, palette_mismatch = 0)

| Seed | Default | Industrial | Plaster | Edges both ways | Palette surfaces |
|---|---|---|---|---|---|
| 1 | 12 | 0 | 0 | 26/26 | 257 |
| 2 | 11 | 1 | 0 | 24/24 | 258 |
| 3 | 9 | 1 | 2 | 26/26 | 274 |
| 14 | 9 | 0 | 3 | 24/24 | 252 |
| 30 | 7 | 2 | 3 | 26/26 | 277 |
| 129 | 6 | 3 | 3 | 26/26 | 264 |

- On every seed, trim, wall, reveal and diagonal coplanar counts are 0, and the floor has no gaps.
- New negative control `wrong_palette` is detected on every surface.
- pytest: 567 passed.
- 0.1.0-0.4.0 artifacts regenerate byte-identically and their headless results are unchanged.
- Scratch seeds 4-150 headless: 147/147 PASS, not kept.

## Deviations
1. The Palettes section is in `material_palettes/PALETTES.md`, not MATERIAL_LANGUAGE.md. That file is hash-pinned by the #166 validator.
2. Specs gain a `shape-room-0.5.0` version. Older specs are unchanged.
3. A figure module tagged backrooms_yellow exerts no influence.
4. The d = 2 coin is drawn once per generated walkable cell in cell_id order, whether or not it is used.
5. Design correction by the lead: the plaster_debris floor is the solid colour (0.34, 0.33, 0.31), because that is what the debris room actually draws (`materials["floor"]`). The design had named a texture constant that is defined but unused. An audit confirmed every other field is applied in its library room.
6. The extra headless output and the new control appear only for 0.5.0 specs.
7. For `icon` fields, the registry validator requires the cited line to hold the same texture file or Color.

## Needs human visual verification
- Whether the rooms around the hall and the rocky room read as belonging to them, and how the hard palette boundary looks (there is no blending, by design).
- Texel density of the painted wall and the hall concrete floor under the PSX effect.
- Flat unshaded solid-colour surfaces next to textured ones, including the plaster rooms' flat grey floor.
- The cool pale lamps against grey surfaces.

## Launch
`godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/generative_map_walkthrough.tscn -- --map=res://room_catalog/generative_maps/gmap-N-gmap-0.5.0.json --rooms=res://room_catalog/shape_rooms/gmap-N-gmap-0.5.0/index.json`

Use N = 129 for the biggest mixed rings, or N = 3 for both rings around the original pair.
