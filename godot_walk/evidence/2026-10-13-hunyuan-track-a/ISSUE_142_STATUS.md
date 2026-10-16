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
| Acceptance | **Fail** | **Fail** |

The plane snap covered only 10 of 18 in-sample floor rays and 108 of 162
ceiling rays. The uncaptured points keep the q90 over the 5 cm limit. The
bottom-band holdout fails for both variants. The source mesh has 44,386
degenerate triangles at the ray-fit median scale; the corrected outputs have
2,787,275. The fit was trained in the frame-141 view, but the panorama mesh
spans elevations near +/-90 degrees. Extrapolation outside the observed view
drives the full-mesh scale median to 0.311 and introduces major stretching and
degeneration. This is not a usable global visual correction.

The CPU run took 62.2 seconds and peaked at 1.83 GiB RSS. It used no GPU and
caused no swap. Experimental PLYs are under
`data/track-a/hunyuan/route-a-visual-correction-frame-141/`; they omit vertex
normals and are not suitable for #137. The JSON with fold-level ray residuals,
plane residuals, resource use, and hashes is
`hunyuan_depth_correction_frame_141.json`.

## Current Decision and Blockers

Route A has not passed. Keep `registration_accepted=false` and
`scale_calibrated=false`. Do not use either corrected output in #137. The
second-frame mesh check is still required to decide whether the depth
distortion is specific to frame 141 or whether Route C (panorama evidence
only) is more honest. Frame 152 has no mesh; its SceneGen run requires GPU
capacity approval and has not been started. The CPU cross-frame holdouts do
not replace that check.

The result and failed gates are recorded in `calibration_manifest_frame_141.json`.
