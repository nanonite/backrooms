# All-192-Frame Density Check

## Result

The same unreviewed candidate mask rule (`v >= 930`), SIMPLE_RADIAL inverse,
declared #100 floor plane, 5 cm grid, slope/step checks, and no-fill policy were
run over all 192 registered frames. Inputs were streamed one frame at a time:
each frame's sampled rays were immediately binned into integer cell counts and
discarded. The process retained only the small cell accumulator, all camera
pose metadata, and the final grid. No full-resolution mask stack or combined
point cloud was retained.

The density increase does not change the decision. The support is one
8-connected component with 11,142 observed cells (27.855 m2), but remains far
from the registered camera path. At the required 0.30 m radius, coverage is
0/192 camera samples and 0/191 segment midpoints. Even at 1.0 m, coverage is
only 125/192 camera samples (65.1%) and 126/191 segment midpoints (66.0%).
There is no mask bridging, morphology, or extrapolation.

## Measurements

| Measure | 24-frame run | All-192 run |
|---|---:|---:|
| Observed cells | 10,263 | 11,142 |
| Candidate support area | 25.6575 m2 | 27.8550 m2 |
| 8-connected components | 1 | 1 |
| Camera / segment coverage at 0.30 m | 0/192 / 0/191 | 0/192 / 0/191 |
| Camera / segment coverage at 1.0 m | 60.9% / 61.8% | 65.1% / 66.0% |
| Camera nearest support q50 / q90 | 0.885 / 2.265 m | 0.851 / 2.112 m |
| Forward floor-ray hits | 426,240 | 3,409,920 |
| Unknown cells filled | 0 | 0 |
| Runtime / peak RSS | 12.4 s / 931 MB | 2.57 s / 83.3 MB |

The 24-frame end-to-end run also generated 24 full-resolution overlays and a
contact sheet, and computed the COLMAP reprojection residual. The all-frame
timing is the streamed mask-ray projection, cell accumulation, and grid/report
write; it did not regenerate those ancillary artifacts. Thus elapsed time is
not a strict like-for-like benchmark. The 24-vs-192 occupancy and route
coverage comparison does use the same projection rule and 5 cm grid semantics.

At 0.30 m, all 191 consecutive camera-path intervals are unsupported. Their
total path length and longest contiguous gap are both 15.168 m. At 1.0 m, two
unsupported end gaps remain:

| Camera-frame interval | Unsupported segments | Gap length |
|---|---:|---:|
| Frames 1 through 48 | 47 | 2.828 m |
| Frames 174 through 192 | 18 | 1.663 m |

The grid has 180 x 206 cells. All 3,409,920 sampled rays intersect the plane
in front of the camera. The maximum numerical intersection residual is
4.4e-16 m; this only checks arithmetic because the plane is imposed by the
method. The 5.128383849 m/unit scale remains #100's chosen synthetic
convention, not surveyed metric scale. Candidate masks have not been
human-reviewed or validated as semantic floor labels.

## Reproduction And Decision

```sh
python3 godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/build_registered_floor_masks_all_frames.py
```

The independent output files are `registered_floor_mask_support_all_192.npz`
and `registered_floor_mask_support_all_192_report.json`. The illustrative
overlay sheet remains in the earlier [24-frame audit](../registered_floor_masks/REGISTERED_FLOOR_MASK_EXPERIMENT.md).

The coverage threshold remains 0.30 m; this is not a walkability pass. No
Avian/Tnua or GPU test was run. #135 remains open because camera-path coverage,
semantic mask review, accepted metric scale, and controller traversal are
still unproven.
