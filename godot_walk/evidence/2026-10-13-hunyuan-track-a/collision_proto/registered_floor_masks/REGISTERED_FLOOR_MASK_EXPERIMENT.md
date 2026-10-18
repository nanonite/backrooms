# Registered Source-Frame Floor Mask Experiment

## Outcome

This CPU-only experiment makes candidate floor support from the registered
`#100` source frames. It does not establish a walkable route. The 5 cm grid has
one 8-connected component and 25.6575 m2 of occupied cells, but no camera-path
sample or adjacent path-segment midpoint is within the required 0.30 m of a
supported cell. Median camera-to-support distance is 0.885 m; q90 is 2.265 m.
The 90% route gate fails. No Avian/Tnua test or collision asset was produced.

The mask rule selects all image pixels with `v >= 930` in 24 registered views
(frames 9, 17, ... 137, 141, 145, ... 185). The green overlays and contact sheet
are in `overlays/` and [mask_contact_sheet.jpg](mask_contact_sheet.jpg). This is
a reproducible lower-band crop, not semantic segmentation. The overlays have
not been human-reviewed. Foreground surfaces within the crop can create false
plane hits, so its occupancy is only candidate evidence.

Each pixel centre is sampled at 4-pixel stride. The `SIMPLE_RADIAL` distortion
with `f=1230.1892`, `(cx, cy)=(960, 540)`, and `k1=-0.07134034` is inverted by
15 fixed-point iterations. Rays then pass through the registered COLMAP pose,
the recorded Nerfstudio dataparser transform, and the `#100` `ply_to_world`
mapping. Only positive intersections with the declared horizontal plane
`y=-1.27099049 m` enter the grid. Empty cells remain unknown; there is no
interpolation or exterior fill.

## Measurements

| Check | Result |
|---|---:|
| Registered views | 24 / 192 (12.5%) |
| Floor-plane ray hits | 426,240 |
| Grid | 174 x 206 at 0.05 m |
| Occupied / unknown cells | 10,263 / 25,581 |
| Unknown cells filled | 0 |
| 8-connected components | 1 |
| Candidate support area | 25.6575 m2 |
| Camera samples within 0.30 m | 0 / 192 (0.0%) |
| Path-segment midpoints within 0.30 m | 0 / 191 (0.0%) |
| Camera / segment coverage at 1.0 m | 60.9% / 61.8% |
| Camera sample coverage at 1.5 / 2.0 m | 78.6% / 84.4% |
| Max mapped camera-bound residual vs manifest | 2.7e-15 m |
| Sparse COLMAP reprojection observations | 104,051 |
| Reprojection residual mean / median / q90 / q95 / max | 1.072 / 0.872 / 2.218 / 2.693 / 3.993 px |
| Max numerical floor-plane residual | 4.5e-16 m |
| Latest build time / peak RSS | 12.4 s / 930,975,744 bytes |

The `#100` transform scale remains the declared 5.128383849 m per Nerfstudio
unit, a chosen synthetic convention, not surveyed metric scale. The plane
residual is numerical consistency only: the plane was imposed by the
intersection calculation. The COLMAP reprojection residual measures
image-to-sparse-model consistency, not independent metric calibration.

## Negative Controls And Limits

- A doubled `metres_per_unit` value is rejected because it disagrees with the
  declared scale reference.
- An incorrect `up_axis` is rejected because it does not map source up to Godot
  world +Y.
- A 0.30 m-radius inserted hole removes 50 occupied cells; its center remains
  unknown and no cell is filled.
- The shared `read_images` helper currently casts COLMAP point IDs through
  float64. This evidence builder reads `<ddq` observation records directly for
  its reprojection calculation and does not rely on the helper's point IDs.
- The grid's connectivity is not route connectivity: the full observed region
  is one component, but the registered camera path is offset from it. Camera
  sample proximity is not capsule traversal.

Reproduce from the Track A worktree:

```sh
pytest -q godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/test_registered_floor_masks.py
python3 godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/build_registered_floor_masks.py
```

The NPZ, report, overlays, and contact sheet are evidence-only. #135 remains
open. Next useful work is human review and tighter floor-only polygons or
segmentation with occluder handling, followed by a route that reaches at least
90% of the registered path before testing physics. The Hunyuan convention scale
and collision approval remain separate.
