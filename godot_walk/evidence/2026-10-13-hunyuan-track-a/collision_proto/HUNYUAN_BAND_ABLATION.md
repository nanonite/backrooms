# Hunyuan Floor-Band Ablation

## Result

This CPU-only ablation makes a local support patch from the run-05 layer-1
panorama sheet. The geometry is smooth under the prototype slope and step
limits. It does not reach the registered camera path. It cannot support a
capsule at frame 141 or a route from that camera. #134 remains
`registration_accepted=false`; the patch uses its `1.558285848`
convention-derived scale only as an experiment. This is not surveyed metric
scale and is not collision approval.

The previous #100 source-grid report and its outputs are unchanged. New files
are separate: `hunyuan_band.py`, `build_hunyuan_band.py`,
`test_hunyuan_band.py`, `hunyuan_band_ablation_report.json`,
`hunyuan_band_patch_experimental_not_collision.obj`, and
`hunyuan_band_patch_experimental_not_collision.npz`.

## Inputs And Topology

The input is `data/track-a/hunyuan/scene-run-05/mesh_layer1.ply`: 7,372,800
vertices and 14,783,952 triangles. Its first 14,737,920 faces are the original
3840 x 1920 grid triangles, including 3,838 panorama-seam faces. The remaining
46,032 are upstream boundary-fill triangles. This ablation excludes all
boundary-fill faces and the seam. It retains only original non-seam triangles
whose three vertices satisfy the crop.

The upstream WorldComposer background mesh excludes the sky mask, not the
foreground-object mask. It can therefore retain sheet faces under the two
`columns` detections. This ablation applies `fg1_mask.png` explicitly. It uses
the upstream mask resize: PIL nearest from 2560 x 1280 to 3840 x 1920. The
resized mask overlaps 9,674 of the 85,790 selected vertices (11.28%). This is
slightly above the earlier 9,471 / 11.04% estimate in `COLLISION_DESIGN.md`;
that earlier estimate is preserved there. The reproducible run here follows
the repository's PIL resize path.

Selection is `v=[0.56,0.62]` from the panorama top and absolute yaw <=35 degrees
from local `-X`. The crop has 84,930 eligible quads. The foreground mask cuts
9,733 quads and 19,447 triangles. These quads form one 8-connected open
cutout, at grid rows 1075-1129 and columns 1799-2006. It reaches the crop
boundary; it is a notch, not an enclosed hole. No masked or unknown face is
filled or bridged. There are 150,413 triangles after crop and mask filtering.

## Geometry And Camera Coverage

| Measure | Result |
|---|---:|
| Triangles before slope/step gate | 150,413 |
| Triangles rejected by slope or step | 0 |
| Connected components (shared-edge) | 1 |
| Surface area | 13.0863 m2 |
| Accepted patch vertices / triangles | 76,116 / 150,413 |
| Slope q50 / q90 / q95 / q99 / max | 1.262 / 2.127 / 2.462 / 3.202 / 5.323 deg |
| Maximum vertical edge step q50 / q90 / q95 / q99 / max | 0.287 / 0.923 / 1.204 / 1.537 / 2.328 mm |
| Candidate floor height relative to #100 declared floor, q05 / median / q95 | 5.19 / 9.12 / 12.30 cm |
| Frame-141 camera anchor to nearest support, horizontal XZ | 2.666 m |
| Registered camera samples within 0.30 m of support | 0 / 192 |
| Path distance q50 / q90 / q95 / max | 2.231 / 2.564 / 2.663 / 2.815 m |

The 64-centroid nearest-triangle search was compared with 256 candidates; the
maximum distance difference was 0.0 m. A separate 1024-candidate check also
returned identical values. The registered frame-141 center matches the
provisional transform translation. The patch's nearest point is still 2.666 m
away in XZ, far outside the 0.30 m capsule radius. A local capsule support route
cannot start at that camera. Camera-sample distance is a proximity measure, not
a traversal test.

All accepted triangles retain downward-facing world normals (150,413 of
150,413). The mesh also remains an open sheet. These facts are additional
reasons not to pass the OBJ directly to physics. No winding repair was applied.

## Verification And Limits

Run from the Track A worktree:

```sh
pytest -q godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/test_hunyuan_band.py
python3 godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/build_hunyuan_band.py
ruff check godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/hunyuan_band.py godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/build_hunyuan_band.py godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/test_hunyuan_band.py
```

Nine focused CPU tests pass. The PLY was read with a memory map. The build
took about 2.04 seconds and reported 931 MB peak process RSS; the OBJ is 5.95
MB and compressed NPZ is 2.36 MB. No GPU, Hunyuan inference, render, collision
GLB, runtime contract, or production asset was used or changed.

No Avian test was added. The patch does not meet the registered camera, so a
physics test would not validate a route from the required start. The transform
also remains unaccepted, and the patch's triangle winding is downward. The
source-grid prototype remains the separate #100-only result; it is not
overwritten or merged with this Hunyuan candidate. #135 remains open because
metric registration and the controller positive/negative traversal gates are
not met.
