# Issue 142 Calibration Status

Date: 2026-10-15

> The feature-matching screens below are historical only. They are superseded
> by the ray-depth method and must not be used or rerun for this decision.

## Decision

Calibration remains **unaccepted**. Do not change the candidate transform or
set `scale_calibrated` / `registration_accepted` to true. The existing
`1.5582858479 m/Hunyuan-unit` value is still derived from the chosen 2.4 m
clear-height convention. It is not independent metric evidence.

## Frame 141 Correspondence Screen

Run the CPU-only screen from the repository root with the `nerfstudio` Python
environment:

```sh
/home/goya/anaconda3/envs/nerfstudio/bin/python \
  godot_walk/evidence/2026-10-13-hunyuan-track-a/hunyuan_calibration_screen.py \
  --output godot_walk/evidence/2026-10-13-hunyuan-track-a/hunyuan_calibration_screen.json
```

The script reprojects `remove_fg1_image_sr.png` into the registered frame-141
camera. It uses the COLMAP `SIMPLE_RADIAL` intrinsics and lens distortion. It
then matches SIFT features, applies a 3 px homography RANSAC screen, and checks
the inlier locations against registered COLMAP 3D observations within 10 px.
The JSON records input hashes and the measured counts.

| Check | Result |
|---|---:|
| Source / Hunyuan-view SIFT features | 207 / 57 |
| Lowe-ratio matches (`0.75`) | 15 |
| Homography inliers (`3 px`) | 7 |
| Occupied source image cells (`4 x 4`) | 1 |
| Unique registered COLMAP points near inliers (`10 px`) | 4 |

The seven inliers map to a tight patch of the panorama, about x=1055-1077 and
y=601-629 pixels. This is not a spatially distributed landmark set. No
Hunyuan-to-COLMAP similarity fit or residual is justified. Feature agreement
does not establish that two generated image details are the same physical
landmark. The automated screen is a rejection aid, not a registration gate.
Its manual-review prefilter requires at least 20 inliers, 12 unique registered
points, and 6 occupied cells; passing those heuristic counts would still not
accept calibration.

The comparison uses Hunyuan's inpainted background image because its pixel grid
corresponds to the exported background mesh. It does not claim that the
inpainted pixels or their generated depth are ground truth.

## Independent Scale Availability

The #100 package has the generated `corridor_travel` video, registered images,
and COLMAP sparse reconstruction. The alignment manifest explicitly labels its
2.4 m corridor height and 5.128383849 m-per-Nerfstudio-unit mapping as chosen
conventions. The video generator is prompt-based and supplies no surveyed
dimension or source CAD. Monocular COLMAP scale is therefore not physical by
itself. No independent measured dimension was found in the available #100
inputs.

Frame 152 is a useful additional source view for a future attempt: its camera
baseline from frame 141 is 0.9662 declared metres, its orientation differs by
11.79 degrees, and the two COLMAP frames share 84 triangulated points. These
values use #100's declared scale; they are not survey measurements and do not
provide Hunyuan correspondences.

## Frame-152 Correspondence Screen

The CPU screen was also run against the measured-FOV Panogen output:

| Check | Result |
|---|---:|
| Source / Hunyuan-view SIFT features | 189 / 37 |
| Lowe-ratio matches (`0.75`) | 29 |
| Homography inliers (`3 px`) | 7 |
| Occupied source image cells (`4 x 4`) | 3 |
| Unique registered COLMAP points near inliers (`10 px`) | 3 |

The 7 inliers do not meet the manual-review prefilter. A second screen used the
partial SceneGen `remove_fg1_image_sr.png` output (2560x1280): 9 ratio matches,
6 inliers, 4 occupied cells, and 1 nearby registered point. Neither result
supports a Hunyuan-to-COLMAP similarity fit. The generated imagery is not
evidence that its visual details correspond to the same physical scene points.

Re-run the SceneGen-output screen from the repository root with the
`nerfstudio` Python environment:

```sh
/home/goya/anaconda3/envs/nerfstudio/bin/python \
  godot_walk/evidence/2026-10-13-hunyuan-track-a/hunyuan_calibration_screen.py \
  --source data/scenes/corridor_travel/images/frame_0152.jpg \
  --panorama data/track-a/hunyuan/scene-frame-0152-attempt-01/remove_fg1_image_sr.png \
  --colmap data/scenes/corridor_travel/sparse/0 \
  --output godot_walk/evidence/2026-10-13-hunyuan-track-a/hunyuan_calibration_screen_frame_152_scene_attempt_01.json
```

## Resource-Gated Inference

The first frame-152 Panogen attempt used the default candidate set and stopped
during CPU-side FP8 GeMM conversion, before CUDA allocation or image inference.
This was a resource stop, not an inference failure.

A second attempt added `--measured-fov-only` to avoid the unneeded default FOV
candidate. It completed one 1280x640, seed-42 panorama with measured FOV
75.934660 degrees, FP8, and sequential CPU offload. Its SHA-256 is
`135dd2a83e4865c2516d8d66a2b1670ba6dd65fbef9c7204438cc62e45f3d3d5`; peak CUDA
allocation was 3,391,193,088 bytes. Host RSS peaked near 25.5 GiB and global
swap use near 19.5 GiB. The result is stored at
`data/track-a/hunyuan/panorama-frame-0152-attempt-02/measured_fov_75.93_seed_42/panorama.png`.

SceneGen then ran on that panorama under a CPU, memory, swap, and GPU guard.
It completed FP8 conversion, foreground-1 inference, and the 50-step scene
generation, and wrote its foreground mask and inpainted image files. It was
stopped during foreground-2 processing when host available memory reached
4.0 GiB and GPU free memory reached 1,364 MiB. SIGINT did not unwind the Python
process; it was terminated with SIGTERM after the resource stop, exit code
143. The run wrote no `mesh_layer*.ply`; its manifest remains `running` because
the process could not record an exception. Partial files are under
`data/track-a/hunyuan/scene-frame-0152-attempt-01/` and must not be treated as
a completed SceneGen result. The host recovered after termination.

A separate mesh-only resume used those saved decomposition files, so it did not
reload the diffusion models. It started with 10,381 MiB free VRAM and 33.1 GiB
host memory available. At 3:25 elapsed, free VRAM fell below the 2,048 MiB
guard (observed 1,943 MiB); host memory was still 18.2 GiB available and swap
use was 10.3 GiB. The watchdog sent SIGINT, then escalated to SIGTERM; exit
code was 143. No mesh layer was written, and the separate output manifest at
`data/track-a/hunyuan/scene-frame-0152-mesh-resume-01/scene_manifest.json`
remains `running`. The source of the changing GPU allocation was not
established. This was a GPU-headroom stop, not a measured geometry failure.
Do not retry either local SceneGen path while GPU availability is unstable.

## Ray-Depth Fit and Route A Results

No feature matching is used. Each COLMAP observation maps to a panorama ray
through the camera model, and the run-05 mesh grid matches that convention
within 1.7e-5 degrees. The baseline compares COLMAP range with Hunyuan mesh
range along each same ray. It found 358 usable observations of 392, across 15
of 16 source-image cells. Their scale ratio varies by panorama band and depth,
so no single similarity transform is supported.

The locked Route A test used the six-term quadratic in standardized elevation
and log-depth. It fits `log(scale)` and exponentiates the prediction so the
radial scale stays positive. It used no feature matching, per-band free scales,
or per-vertex warp. Five spatial-cell folds and leave-one-panorama-band-out
validation were run. 217 additional floor points from other registered frames
passed a sparse COLMAP z-buffer visibility check; they were validation-only.

### Oracle Check and Re-Locked Gates

The original 5 cm plane-residual gate was **invalid: below the oracle noise
floor**. Plane members were COLMAP points within +/-10 cm of a #100 plane and
were then scored against that same plane. Replaying their exact COLMAP depths
gives these legacy plane q90 values:

| Exact COLMAP-depth oracle | Count | Legacy plane absolute q90 |
|---|---:|---:|
| Frame-141 floor members | 18 | 7.70 cm |
| Frame-141 ceiling members | 162 | 7.06 cm |
| Other-frame floor holdout | 217 | 8.34 cm |
| Primary point-depth vertical error | 397 total | 0.00 cm |

Thus even exact point recovery cannot satisfy the old 5 cm plane gate. The
manifest now locks the replacement primary metric before any refit:
`abs((corrected_depth - target_depth) * direction_world_y)`, against each
sample's own COLMAP 3D point. Floor-member q90 must be at most 5 cm (3 cm goal),
ceiling-member q90 at most 5 cm, camera-anchor residual 0, on every spatial
fold, every leave-one-band-out fold (including the floor band), and the
other-frame floor holdout. Keep the old plane metric beside its oracle for
context only.

The re-locked mesh gate is at most 44,829 degenerate triangles (44,386 source
baseline plus 1%), at least 99% of triangle-edge lengths in [0.5x, 2x] of the
source lengths after one global median scale, and zero flipped faces. The six
model terms are unchanged. The field clamps each standardized input to that
training fit's observed range. Plane snapping now feathers to wall-field depth
over a fixed 2 degrees of panorama elevation. These requirements and the
two-frame decision rule are in `calibration_manifest_frame_141.json`.

| Metric | Smooth field | Plane snapping + same wall field |
|---|---:|---:|
| In-sample floor / ceiling absolute q90 | 10.8 / 10.7 cm | 10.8 / 10.7 cm |
| Pooled 5-fold floor / ceiling absolute q90 | 51.0 / 15.2 cm | 12.1 / 15.2 cm |
| Leave-bottom-band-out floor q90 | 59.6 cm (12 points) | 17.8 cm (12 points) |
| Other-frame floor holdout q90 | 10.0 cm (217 points) | 10.0 cm (217 points) |
| Camera-anchor residual | 0 m | 0 m |
| Max reported seam-edge stretch | 88.7x across grid | 414.7x across snap boundary |
| Edges outside 0.5x-2x | 12,706,998 | 14,602 / 15,263 boundary edges |
| Degenerate triangles | 2,787,275 | 2,787,275 |
| Legacy plane gate | **Invalid** | **Invalid** |

The old plane scores are not pass/fail evidence because the oracle itself is
above 5 cm. The previous mesh outputs independently exceeded the currently
locked quality limits: each had 2,787,275 degenerate triangles versus the
44,829 maximum, and the prior edge analysis also showed extensive distortion.
The earlier run extrapolated the polynomial outside the observed frame-141
training domain, driving its full-mesh median scale to 0.311. The bounded,
feathered rerun below supersedes those mesh-quality results.

The CPU run took 62.2 seconds and peaked at 1.83 GiB RSS. It used no GPU and
caused no swap. Experimental PLYs are under
`data/track-a/hunyuan/route-a-visual-correction-frame-141/`; they omit vertex
normals and are not suitable for #137. The JSON with fold-level ray residuals,
plane residuals, resource use, and hashes is
`hunyuan_depth_correction_frame_141.json`.

## Final CPU Iteration (2026-10-16)

This section supersedes the earlier bounded/feathered result table above. The
locked six-term model was rerun on both registered frames. Frame 141 used the
run-05 mesh. Frame 152 used its own SceneGen mesh and camera metadata. The
frame-152 ray-fit plane check was explicitly skipped; no frame-141 camera or
plane block was reused. Plane snapping itself was evaluated on both frames.

Scale profiles below show each slice's median divided by that frame's all-ray
median. Both frames show a lower relative scale beyond 10 m. The absolute
medians differ, and the frame-152 bottom band has only 14 observations.

| Slice | Frame 141 n | Frame 141 normalized | Frame 152 n | Frame 152 normalized |
|---|---:|---:|---:|---:|
| Top band | 167 | 1.020 | 184 | 1.023 |
| Middle band | 171 | 0.914 | 191 | 0.963 |
| Bottom band | 20 | 1.148 | 14 | 1.056 |
| 0-4 m | 74 | 1.015 | 55 | 1.035 |
| 4-6 m | 109 | 1.001 | 147 | 1.009 |
| 6-10 m | 108 | 1.037 | 111 | 0.998 |
| >10 m | 67 | 0.814 | 76 | 0.835 |

All primary q90 values below are vertical errors to each observation's own
COLMAP point. Distances are centimetres. Every method keeps the camera anchor
fixed (0 m residual).

| Frame / method | In-sample floor / ceiling | 5-fold floor / ceiling | Floor-band leave-out | Worst ceiling-band leave-out | Other-frame floor | Edges in range | Degenerate triangles | Flipped faces |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 141 smooth field | 7.6 / 11.7 | 42.3 / 14.9 | 15.6 | 86.6 | 9.9 | 94.05% | 44,079 | 53,022 |
| 141 plane snap | 8.0 / 11.1 | 9.0 / 14.6 | 15.2 | 38.1 | 9.8 | 93.47% | 44,079 | 73,535 |
| 152 smooth refit | 13.3 / 7.9 | 16.1 / 13.1 | 26.9 | 146.9 | 12.3 | 100.00% | 45,536 | 0 |
| 152 plane-snap refit | 13.3 / 8.0 | 16.1 / 13.1 | 5.5 | 71.2 | 11.8 | 99.48% | 45,536 | 50,057 |

The locked limits are 5 cm for every held-out floor/ceiling q90, at most 44,829
degenerate triangles, at least 99% of edges within 0.5x-2x of source, and zero
flipped faces. No frame-specific refit passes. The 152 plane-snap floor-band
leave-out q90 is 5.5 cm, still over the limit; its other held-out gates and
mesh checks also fail. Frame-152 smooth and snapped outputs each have 45,536
degenerates, above the locked 44,829 limit. The frame-152 source baseline
already contains 45,389 degenerate triangles; the fixed gate remains the
predeclared frame-141 limit.

Plane snapping used the locked 2-degree feather. Boundary-edge stretch q90 / q99
/ max was 3.13 / 56.38 / 201.48 on frame 141, and 1.37 / 2.58 / 3.36 on frame
152. The smoother frame-152 mesh still fails its floor/ceiling holdouts and
degenerate-triangle limit. Frame-141 smooth-field edges are only 94.05% within
range and 53,022 faces are flipped. Frame-152 plane snap has 50,057 flipped
faces.

Applying frame-141 coefficients unchanged to frame 152 was informational only
and did not qualify for Route A. Smooth transfer produced 19.0 / 15.0 cm
five-fold floor/ceiling q90, 12.0 cm floor-band leave-out, and 18.1 cm external
floor q90; its mesh had 96.05% in-range edges, 45,679 degenerates, and 572
flipped faces. Plane-snap transfer had 19.0 / 14.1 cm five-fold q90, 5.5 cm
floor-band leave-out, and 18.1 cm external floor q90; its mesh had 95.24%
in-range edges, 45,679 degenerates, and 14,309 flipped faces.

The frame-141 and frame-152 ray-fit all-ray medians were 1.4315 and 1.7001
declared m/Hunyuan-unit. Frame 141 used 358/392 registered observations; frame
152 used 389/412 after masking 23 foreground observations. The frame-152 mask
labels were `{0, 1, 2, 3}`, so `>0` was used as foreground. The exact COLMAP
point-depth oracle still makes the old 5 cm plane gate invalid; that gate is
context only, not a failed fit criterion. Both JSON evaluations report runtime,
peak RSS, folds, ray residuals, mesh quality, and experimental output paths.
Runtime / peak RSS: frame 141 33.8 s / 2.40 GiB; frame 152 70.9 s / 2.41 GiB.
Both were CPU-only; no GPU was used.

**Decision: Route C.** The locked rule requires at least one frame-specific
refit to pass every primary held-out and mesh-quality gate on both frames. None
does. Keep the panorama evidence and documented ray-depth distortion profile;
do not continue Route A fitting. Close #142 as Route C. Keep
`registration_accepted=false` and `scale_calibrated=false`. No corrected mesh
may be used by #137.

Reports: `hunyuan_ray_depth_fit_frame_141.json`,
`hunyuan_ray_depth_fit_frame_152.json`,
`hunyuan_depth_correction_frame_141.json`, and
`hunyuan_depth_correction_frame_152.json`. Final corrected meshes are in
`data/track-a/hunyuan/route-a-visual-correction-v3-frame-141/` and
`data/track-a/hunyuan/route-a-visual-correction-v4-frame-152/`; all are
experimental only. The manifest and assessment history are in
`calibration_manifest_frame_141.json`.
The earlier evaluator retries left partial PLYs under
`route-a-visual-correction-v2-frame-141/` and
`route-a-visual-correction-v3-frame-152/`. Those directories are superseded
artifacts from report/export errors, not accepted results; do not use them.

The frame-152 SceneGen run was the previously approved generation run, not part
of this CPU-only iteration. It completed with peak CUDA allocation
6,431,235,536 bytes, runtime 742 s, minimum host-available RAM 10,259 MiB,
minimum free VRAM 3,986 MiB, and peak system swap use 42,265 MiB. No new
SceneGen, Panogen, or GPU work was performed here.
