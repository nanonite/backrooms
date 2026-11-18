# Issue 273 — authored data and collision policy (v1 record)

## Baseline and variant

- Baseline: `slot-canyon-courtyard-v1`, operator-accepted as a bounded standalone
  candidate. Its folder is untouched by this slice.
- Variant: `slot-canyon-courtyard-v2`, a new folder and a new candidate record.
  Same seed (`frame_1363`), same accepted `attempt-001` panorama, same declared
  L-shaped orthogonal XZ footprint, spawn `[0, 0.6, -7]`, floor elevation `0`,
  collidable bodies, camera (`player.tscn`) and PSX profile.

## Retained unchanged (copied, not reinterpreted)

- `WALL_SEGMENTS`: six closed perimeter boxes.
- `FLOOR_SEGMENTS`: two floor boxes.
- `ROCK_OBSTACLES`: three static rock boxes.
- Environment: panorama sky, ambient colour/energy, directional key light.
- Materials: the five direct source crops and the local strata solid colour.
- Player preload, capture/render PSX compositor, R-to-spawn reset.

## Invented visual-only detail (23 nodes, no collider)

- 15 `RELIEF_FINS`: thin boxes flush to the inner wall faces with staggered top
  heights (3.6–6.2 design units) and small Y-axis tilts (±4°). They break the
  flat vertical silhouette in elevation. Positions, counts, heights, tilts and
  material choice (warm/dark crop) are authored, not measured.
- 5 `RELIEF_LEDGES`: thin solid-colour boxes above Y=4.7, i.e. above the
  capsule top, so they cannot obstruct traversal. Authored as high occlusion.
- 3 `RELIEF_ROCK_CAPS`: small chipped boxes on the three existing boulders,
  tilted, using the accepted rock crop. Visual only.

None of these creates a `StaticBody3D`, `CollisionShape3D` or `BoxShape3D`.
The v2 headless test compares the full collider signature of v1 and v2 and
asserts equality, then asserts the visual-node count differs by exactly 23.

## Collision / appearance mismatch (explicit)

The relief is not carved from the wall collider. It can visually overlap the
flat wall and boulder colliders and can read as a flat panel at close range
(the `open_sky_slot` and `west_wall_strata` v2 captures show this). The operator
must decide whether that mismatch is acceptable. No improvement is presumed.

## Negative control

The headless test first confirms the north boundary ray hits, then sets
`NorthWall.collision_layer = 0` and asserts the ray misses (escape detectable),
restores it, then sets all six wall layers to 0 and asserts the ray misses
again (missing boundary detectable), restoring all walls afterwards. A floor
negative control removes `MainFloorCollision` and asserts the floor ray misses.

## Out of scope

No non-orthogonal footprint, no contract version, no metric depth, no model or
download, no catalog admission, no socket choice, no integration, no registration
or calibration change. Both `registration_accepted` and `scale_calibrated` stay
false everywhere.
