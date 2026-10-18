# Camera-Path Visibility Diagnostics

## Finding

The bottom-band result is a capture-coverage limit, not evidence of bad floor
labels or a broken transform. The 24-frame floor-mask contact sheet shows the
selected pixels on carpet, while the registered camera path moves mostly
sideways and looks almost perpendicular to that motion. Bottom-band carpet
projects roughly 3 m ahead of each camera, not onto the camera-path floor
samples.

The existing all-frame candidate footprint remains useful as a **planar design
region**: its 27.855 m2 of occupied XZ cells form one connected component. Its
height is imposed by the #100 floor contract. It is not measured 3D floor and
cannot establish real slope or step limits. A Godot floor fill inside this
region is valid as authored support if it stays separate from the Hunyuan
visual mesh and is labelled as authored.

## Measurements

| Check | Result |
|---|---:|
| Registered source frames | 192 |
| Median absolute frame motion in COLMAP camera axes (x, y, z) | (0.983720, 0.022807, 0.175302) |
| Frames where local `|x| > |z|` motion | 100% |
| Camera pitch, min / median / max | -0.054 / 0.114 / 0.429 deg |
| View heading minus motion, min / median / max | 71.560 / 80.567 / 87.879 deg |
| Camera height above declared plane, min / median / max | 1.091 / 1.157 / 1.186 m |
| Ray-origin vs contract camera-centre residual | 0 m for all frames |
| Bottom-band hit centroid forward distance, min / median / max | 2.828 / 2.940 / 3.007 m |
| Bottom-band hit centroid lateral distance, min / median / max | -0.011 / -0.002 / 0.002 m |

Route-floor visibility is an **in-image upper bound**. The route samples are
the 192 registered camera XZ centres with Y set to the declared #100 floor
height. Projection does not test wall or column occlusion.

| Image region | Pinhole scratch-script reproduction | `SIMPLE_RADIAL` projection | Unseen samples in radial projection |
|---|---:|---:|---|
| Bottom band, `v >= 930` | 0/192 | 0/192 | all frames |
| Lower half, `v >= 540` | 176/192 | 182/192 | 79-88 |
| Full image | 176/192 | 182/192 | 79-88 |

The `176/192` figure reproduces the supplied `obs135.py` pinhole calculation.
The repository diagnostic also applies COLMAP's `SIMPLE_RADIAL` forward model;
that expands the in-frame upper bound to `182/192`. The corrected lower-half
nearest views of those route samples are 5.842-8.427 m away at rows 759.8-841.1.
The pinhole comparison gives 6.036-8.545 m at rows 763.7-841.4. The difference
does not affect the diagnosis: neither model puts any route-floor sample in
the bottom band, and neither accounts for occlusion.

## Interpretation

- The bottom-band selection is visibly carpet in the existing 24-frame contact
  sheet. Reviewing or redrawing those masks will not move floor that was not
  filmed under the route.
- The camera-centre mapping independently agrees with the #100 contract to
  floating-point precision. The ray origins reproduce those centres exactly.
- The camera stays level while moving sideways around the column. A level
  camera about 1.16 m above the declared plane sees the floor only several
  metres forward; the bottom-band plane intersections are about 2.94 m ahead.
- Lower-half image inclusion ignores walls and columns. Treat 176/192 and
  182/192 as upper bounds, not reviewed floor coverage or walkability results.
- The horizontal plane and #100 scale are declared synthetic conventions.
  These checks do not validate metric scale, floor elevation variation, slope,
  or steps. #134 remains `registration_accepted=false`.

## Guidance For #135

The default collision experiment can intentionally select a route inside the
connected candidate XZ footprint, for example around the column, and author a
flat support floor in Godot. Preserve the footprint as source-informed input,
but label the added surface **authored planar support**. Review the column
footprint separately as an obstacle. Export the resulting collision mesh apart
from the Hunyuan visual GLB.

Keep the original #100 camera path as an optional fidelity fork. If it is a
requirement, review floor evidence in the lower half and check occlusion. The
unseen interval remains a gap; do not fill it and call it reconstructed. If
occlusion-aware path-length coverage cannot pass the 90% gate, capture new
footage moving forward with the camera pitched down about 25-30 degrees.

## Reproduction

Run from the Track A worktree:

```sh
python3 godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/camera_path_geometry_diagnostics.py
python3 godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/route_floor_visibility_diagnostics.py
```

Both scripts are read-only with respect to source data. They write their
machine-readable results beside the scripts:
[`camera_path_geometry_diagnostics.json`](camera_path_geometry_diagnostics.json)
and
[`route_floor_visibility_diagnostics.json`](route_floor_visibility_diagnostics.json).
The 24-view carpet sample is
[`mask_contact_sheet.jpg`](registered_floor_masks/mask_contact_sheet.jpg).

Input SHA-256 values recorded by both JSON reports:

| Input | SHA-256 |
|---|---|
| #100 alignment manifest | `85d5b51c8ca9df614b81a6f6dddf8c68015cca14b36e3b007c1a67f50be03598` |
| COLMAP `images.bin` | `86122a114a15e8dd248445eae154996be8a83354fa47328fbb038c56bef68791` |
| COLMAP `cameras.bin` | `722bf3809802099390979b5abf1eaea7fb70c88d955bd68147a08466a48082ae` |
| Nerfstudio `dataparser_transforms.json` | `fdabcd1b1450e65c605f45099a93383aff081fb1009b73f71f3eb854654e8ed4` |

No GPU, inference, rendered scene, physics runtime, or collision asset was used.
