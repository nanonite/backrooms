# GDGS splat rendering & calibrated alignment — verification report

**Task:** #74 Verify current GDGS splat rendering and calibrated alignment
**Date:** 2026-10-05
**Worker:** Chainlink agent, workflow chainlink_8v8ci, attempt 1/8
**Verdict:** PASS — real-GPU visual evidence + numerical contract verification, both scenes.

## What was verified

The current Godot/GDGS corridor scenes render the real Splatfacto asset
(`corridor.ply`, 182,569 splats) upright at the calibrated scale, on the real
Vulkan/Forward+ path, and both scenes honour the #83 alignment contract
numerically after runtime initialisation.

## Evidence summary

| Evidence | Location |
|---|---|
| Environment (renderer/GPU/versions) | `ENVIRONMENT.md` |
| Repeatable commands | `COMMANDS.md` |
| Headless contract verification log | `verify_alignment.log` |
| Unit-test log (27 checks) | `test_splat_alignment.log` |
| Collision-body log | `verify_scene.log` |
| Real-GPU log — inspection scene | `corridor-splat-vulkan.log` |
| Real-GPU log — walkable scene | `corridor-walkable-vulkan.log` |
| Screenshots — inspection scene (4) | `screenshots/corridor_splat-*.png` |
| Screenshots — walkable scene (4) | `screenshots/corridor-*.png` |

## Real-GPU capture (the visual proof)

Captured on the desktop session: `DISPLAY=:1`, NVIDIA RTX 4070 Ti, driver
595.91.07, Godot 4.6.3.stable.official.7d41c59c4, **Vulkan 1.4.329, Forward+**,
1280x720. Not headless, not xvfb, not llvmpipe.

Both scenes report the identical rendered splat AABB:

```
SPLAT_AABB: name=CorridorSplatNode pos=(-97.7875, -62.1061, -101.8175) size=(139.4696, 97.0061, 134.5244)
```

All eight screenshots are non-blank (921k–922k changed pixels from background
for the perspective views; 208k for the orthographic top-down). The
`player_pov` frames show the corridor **upright**: floor below, ceiling with
its light band above, walls vertical, a column mid-room. The fringing at the
frame edges is far-field floater, not geometry — the numeric checks below are
the evidence of record for orientation and scale.

The walkable scene's `player_pov` additionally carries the player's live
position label `pos X:-0.65 Y:-0.54 Z:2.89`, matching the contract spawn
(x = −0.6513, z = 2.8875) with the capsule centre 0.5 m above the floor.

## Landmark comparison against #83 numerical evidence

#83 (closed 2026-10-02) established the contract and reported its own
real-GPU run. This run reproduces it:

| Quantity | #83 reported | #74 measured | Match |
|---|---|---|---|
| Rendered splat AABB pos | (−97.7875, −62.1061, −101.8175) | (−97.7875, −62.1061, −101.8175) | exact |
| Rendered splat AABB size | (139.4696, 97.0061, 134.5244) | (139.4696, 97.0061, 134.5244) | exact |
| Reconstruction cameras | 192, inside room | 192, inside room | exact |
| Mean camera eye height | 1.153 m | 1.153 m | exact |
| Floor landmark | (−0.651325, −1.27099, 2.887547) | (−0.651325, −1.27099, 2.887547) | exact |
| Ceiling landmark | (−0.651325, 1.129009, 2.887547) | (−0.651325, 1.129009, 2.887547) | exact |
| Floor→ceiling height | 2.4000 m | 2.4000 m | exact |
| PlayerSpawn | (−0.651325, −0.77099, 2.887547), 0.500 m above floor | same | exact |
| Corridor upright in player_pov | yes | yes | confirmed |

The rendered AABB equals the manifest's predicted `full_min`/`full_max` to four
decimals, so the thing on screen is the thing the contract describes — not a
differently-scaled or differently-oriented asset.

## Headless numerical verification (contract proof)

`verify_alignment.gd` (exit 0) proves, after runtime initialisation:

1. The manifest is self-consistent; its up axis maps to Godot +Y with det = +1.
2. Each scene's **effective** splat mapping equals the contract.
3. GDGS' implicit −180° Z correction fired in **neither** scene (explicit basis
   neutralises it — no double rotation).
4. Both scenes agree on the effective mapping.
5. Landmarks land inside the observed room, floor below ceiling, floor→ceiling
   = 2.40 m within tolerance.
6. The rendered splat AABB matches the contract's predicted value (catches a
   stale `.res` cache or a scene pointing at a different PLY).
7. The floor landmark is the lowest point of the observed room and the ceiling
   the highest — the numeric form of "not on its side".
8. The 192 reconstruction cameras land inside the room at a 1.153 m walking eye
   height.
9. `PlayerSpawn` sits inside the room, 0.5 m above the floor.

`test_splat_alignment.gd` (exit 0, 27/27) unit-tests the manifest reader,
including the positive and negative cases for the GDGS correction predicate.

`verify_scene.gd` (exit 0) confirms the walkable scene's collision:
`GeneratedCollision` built 10,178 triangles (30,534 trimesh face vertices), the
player capsule matches `player.tscn` (r = 0.30 m, h = 1.20 m), and the spawn
capsule bottom (−1.1430 m) clears the generated floor (−1.1430 m).

## Asset provenance

- `corridor.ply` md5 `2f6c2fd5417ffe771ef4147e369d80c5` — matches the manifest's
  `asset.md5`. The scenes load this file, not the retired Brush
  `corridor_straight` asset.
- `corridor_splat.collision.glb` md5 `c8f7a46effade8002a9bc51f74e3b11e` —
  matches TRAVERSAL.md.
- The retired mesh scale 0.800977 is recorded in the manifest's
  `rejected_scales` and was **not** applied. The current scale is the chosen
  5.128384 m/unit (2.40 m declared clear height ÷ 0.46798 ± 0.00937
  reconstruction units, measured over 12 stations).

## Honest limitations

- **Collision overlay is not in this task's scope.** The generated collision is
  physics-only (a `ConcavePolygonShape3D`); Godot does not render collision
  shapes in a normal play/preview capture, so the screenshots show the splat
  and the walkable scene's player but not the collision mesh itself. Collision
  overlay evidence is completed as part of #91 once #84/#85 are ready.
- **This task does not prove walking.** It proves the splat renders upright at
  the calibrated scale and that both scenes honour the contract numerically.
  The walk battery (`verify_traversal.gd`) and the end-to-end gate (#91) are
  separate.
- **Walls are not measured.** `walls_measured: false` — the room's horizontal
  extents are observation bounds from the camera-path window, not measured wall
  planes.
- **The scale is chosen, not measured** (synthetic footage). Re-decide it when
  real footage lands.
- The `overhead_orbit` and `top_down` views are dominated by far-field
  floaters (the splat cloud extends ~140 m from the room). This is expected for
  this asset and is why the numeric checks, not the wide shots, carry the
  orientation/scale evidence.

## Prerequisites retained

- #73 (GDGS renderer de-risked with a known-good demo .ply) — historical
  prerequisite; the GDGS addon and screenshot harness it produced are the ones
  used here.
- #83 (runtime alignment + calibrated scale) — the contract this task verifies
  against.
