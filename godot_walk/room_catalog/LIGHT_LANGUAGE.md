# Generated room light language

Version: `light-language-0.1.0` (Chainlink #198, gmap-0.8.0).

This is a map-driven presentation layer for generated rooms. It does not alter
room geometry, source textures, library-room materials, registration, or scale.

## Scope and versioning

- Maps `gmap-0.1.0` through `gmap-0.7.0` keep their original unshaded materials,
  emissive lamp boxes, and 0.8 ambient energy.
- Maps `gmap-0.8.0` carry a `light` record for each non-void cell. Their generated
  rooms use per-vertex lit PSX materials, nearest texture filtering, and the
  existing PSX compositor.
- Library rooms retain the unshaded material language from
  `MATERIAL_LANGUAGE.md`; this document does not change or replace that contract.
- `registration_accepted` and `scale_calibrated` remain false.

## Map decisions

The post-pass uses an independent named stream, `light:gmap-0.8.0`, derived from
the map seed and successful layout attempt. It never changes cell geometry,
ports, edges, palettes, landmark choice, or layout search.

Each non-void cell records a tier (`dim`, `normal`, or `bright`), a color
temperature from 3800 K to 5200 K, and one indexed state for every generated
lamp position in its shape-room spec. Lamp states are drawn as 80% on, 12%
flicker, and 8% dead before the dark-wing adjustment. The general tier draw uses
15% dim, 70% normal, and 15% bright. Spawn is raised to at least normal.

At most one dark wing is selected per map, with probability 0.35. It is a
directly connected group of two or three generated non-spawn, non-landmark
cells. Every cell in that group is dim; more than half of its lamps are dead.
If the draw succeeds but no eligible adjacent pair exists, the map records an
unavailable wing and why. A landmark is bright and its lamp ring stays on.
Generated cells directly adjacent to a placed library figure module are bright
to ease the visual transition to that module's baked appearance.

## Runtime rendering

- Generated wall, floor, ceiling, trim, and lamp materials use Godot
  `SHADING_MODE_PER_VERTEX` (Gouraud), with no more than 1 m between mesh
  vertices. Texture sampling stays nearest-filtered.
- Each map lamp gets one `OmniLight3D` with a 6 m range and shadows disabled.
  Generated cells within 6.2 m use different visual/light cull layers, so a
  shadowless light cannot illuminate a nearby room through a thin wall. The
  deterministic spatial coloring can reuse a layer for farther cells; layer 20
  is reserved for library-module visuals.
- Tier energies are 0.45, 0.9, and 1.35 for dim, normal, and bright. Color comes
  from the recorded temperature. Dead lamps have a dark box and zero light
  energy. Flickering lamps use a seeded 8 Hz pattern selected by elapsed time,
  so the pattern does not depend on frame count.
- Ambient energy is 0.2 for the light-layer map; the background remains visible
  and dark areas are not intended to render pitch black.
- The existing PSX compositor runs after the lit scene. The URSC material preset
  continues to process library and unshaded meshes; it leaves per-vertex
  generated materials intact so real lights can shade them.

## Limits

The 6 m lights do not cast shadows. Cell-specific light masks prevent direct
light from bleeding through room walls, but openings still show normal light
falloff across the doorway. This is a presentation control, not baked lighting
or global illumination. Vertex lighting can still look blotchy on a surface
with sparse geometry; the runtime check records actual vertex spacing, and the
review captures must be inspected for visible facets, black patches, or seams.
