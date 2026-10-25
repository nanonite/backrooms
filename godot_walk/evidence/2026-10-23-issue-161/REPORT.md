# Issue 161 — PSX affine texture comparison

## Review status

The operator reviewed the live walkthrough and selected profile B (affine mapping off) as the project default. The project now defaults to affine mapping off while keeping nearest filtering and vertex snap intensity 1. `registration_accepted` and `scale_calibrated` remain false. The captures and metrics below are the original A/B evidence; they are retained unchanged as the basis for that decision.

## Comparison

Profile A preserves the pinned URSC settings: affine mapping on, nearest filtering, vertex snap intensity 1. Profile B disables only affine mapping. Both were captured from the same #156 seed-149 walkthrough, using the same geometry, textures, layout, and camera poses at 1280×720. The capture harness settled 18 frames per view. The nine views cover the column room, branch room, floor, ceiling, and left/right pans. The exact poses and profile settings are in `capture_manifest.json`.

ODiff 4.5.0 used a 0.1 threshold. Three repeat captures at one anchor per profile produced 0.0000% changed pixels, so the measured repeat-noise ceiling is 0.0000%. All nine A/B views differ above that ceiling:

| View | Surfaces | Changed pixels |
| --- | --- | ---: |
| `branch_center` | wall, floor, ceiling | 7.76% |
| `ceiling_walk_line` | ceiling, wall | 8.79% |
| `column_east_wall` | wall, floor, ceiling | 25.84% |
| `column_patch_anchor` | column, wall, floor, ceiling | 4.00% |
| `floor_walk_line` | floor, wall | 6.67% |
| `hall_step_left` | wall, floor, ceiling | 7.59% |
| `hall_step_right` | wall, floor, ceiling | 7.90% |
| `wall_pan_left` | wall, floor, ceiling | 6.70% |
| `wall_pan_right` | wall, floor, ceiling | 5.84% |

The contact sheet (`comparison.jpg`) shows a visible tradeoff. In the broad pocket-room views, profile B makes the floor's square tiling much more pronounced and gives the wall and ceiling pattern a more regular appearance. Profile A has a softer floor pattern and more visible texture distortion. The close `column_east_wall` capture also changes substantially and looks blurred in B; that camera pose includes a large black area, so it is weak evidence for judging that surface. The `column_patch_anchor` changes less (4.00%) and shows no clear overall winner.

These are matched stills and two fixed pan angles, not a temporal motion analysis. ODiff establishes that the output changes above repeat noise; it does not establish that either profile is more attractive or that it fixes texture swim. The operator's live walkthrough review selected B; the F7 toggle remains available to compare it with A.

## Runtime and resources

The guarded Vulkan run loaded the #156 walkthrough to ready in 2,060 ms. At one fixed branch-room pose, it measured 300 unthrottled rendered-frame intervals per profile after 30 warmup frames:

| Profile | p50 | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| A — affine on | 0.265 ms | 0.375 ms | 0.409 ms | 0.905 ms |
| B — affine off | 0.243 ms | 0.322 ms | 0.382 ms | 0.431 ms |

These single-run timings are a machine-specific comparison, not a sustained-FPS guarantee. The profile measurement JSON records the sample method. The GPU/RAM guard found no competing compute jobs; peak process RSS was 2.43 GB and GPU memory rose by 557 MB (sampled peak delta). The full preflight and run record is `resource_runs/issue161-profile-performance-final.json`.

After the operator chose B, a guarded capture using the project default and no runtime profile override was compared with the original affine-off `branch_center` reference. ODiff reported 0.0000% changed pixels, matching within the 0.0000% repeat-noise ceiling. The capture manifest and comparison are `captures/project_default/project_default.json` and `project_default_comparison.json`. An earlier smoke check attempted Godot's editor-only global-uniform getter at runtime and failed; its run record is preserved as `resource_runs/issue161-default-smoke.json`. The rendered comparison is the valid runtime verification.

The walkthrough emits the existing `ERROR: NO GRAB` warning when launched by the automated capture process without an interactive display. The captures and performance process exited successfully. This warning concerns mouse capture in automation and is not evidence of a scene-load failure.

## Evidence files

- `index.html` — comparison, metrics, and operator prompt.
- `comparison.jpg` — matched A/B contact sheet.
- `review_metrics.json` — ODiff view and repeat-noise results.
- `project_default_comparison.json` — confirms the project-default render matches the accepted affine-off capture.
- `capture_manifest.json` — capture poses, settings, and paths.
- `source_hashes.json` — hashes of renderer, shader, room, layout, and texture inputs.
- `profile_performance.json` and `resource_runs/issue161-profile-performance-final.json` — frame timing and guarded resource data.

