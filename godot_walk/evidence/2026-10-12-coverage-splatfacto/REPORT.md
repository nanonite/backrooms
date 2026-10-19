# #104 Coverage Splatfacto Attempt

Date: 2026-10-12 local (pipeline state timestamps are UTC)

## Pipeline And Inputs

This is an improvement attempt against the #100 Backrooms Gaussian baseline, not a new scene. It reused the accepted #107 source at `data/scenes/backrooms_coverage_v1/video.mp4` and the established `COLMAP/GLOMAP -> Nerfstudio Splatfacto -> Godot` route. The baseline asset was not overwritten.

Source SHA-256: `d50f6770cb5767109202e1bcae41e4e412035ff4852c8a6b86d9e28aeae55f06`

Run directory: `data/scenes/backrooms_coverage_v1_gaussian_splatfacto/` (ignored, isolated from the shared source and tracked #107 evidence).

Stage A returned `ACCEPTED_WITH_WARNINGS`: 111 of 180 eligible frames selected across 7.958 of 8.0 seconds; measured path length was 0.942 frame widths across four distinct travel directions. The warning says median global translation explains 25% of frame change. This is borderline parallax, not evidence that every surface is covered.

The default GLOMAP run aborted during retriangulation with a reconstruction data-ID assertion. Retrying with `GLOMAP_SKIP_RETRIANGULATION=true` produced one selected sparse model with all 111/111 extracted frames registered. `model_coverage.py` reports 100% registration coverage; that metric does not establish that the learned splat contains geometry throughout the camera path.

Stage C completed with Nerfstudio 1.1.5, 30,000 iterations, `eval_mode: all`, and scale regularization enabled. The exported PLY contains 111,812 Gaussians (27 MiB); its SHA-256 is `7e60faaca136efa89bd988643a50fd3af0260ceeea2d355d8b6aad61c84df17c`. No OOM occurred. The staged config records gsplat `1.4.0+pt23cu121` although the script's pinned target is `1.5.1`.

## Alignment Result

Stage D measured a 0.287897-unit floor-to-ceiling span over six stations and applied the chosen synthetic 2.4 m reference (8.3363 m per reconstruction unit). It rejected a strong plane pair on frame axis `x`: the pair at `0.236..0.315` units is only about 0.65 m apart and does not enclose the camera path (`-0.654..1.000`) within the contract's 2 m slack. This pair is consistent with an internal surface such as a column, not the room boundary.

With that pair rejected, the measured opaque-splat bounds still stop short of the registered camera path: approximately 5.00 m on one horizontal axis and 2.27 m on the other. The COLMAP poses mapped through the saved Nerfstudio dataparser transform agree with the installed parser's training camera positions, so this is not a coordinate-conversion discrepancy. It is incomplete geometric coverage in this trained candidate.

The contract correctly failed before writing `alignment_manifest.json`. The pipeline did not run collision generation, traversal, Godot staging, the eight matched production-eye headings, or runtime/fps checks. Those results must not be inferred from the successful training or 100% camera registration.

## Reproduction And Evidence Limits

The resumable command was:

```bash
GLOMAP_SKIP_RETRIANGULATION=true NS_USE_SCALE_REGULARIZATION=true \
  SPLATFACTO_BRUSH_FALLBACK=false TRAIN_BACKEND=splatfacto \
  scripts/splat_pipeline/run_pipeline.sh \
  data/scenes/backrooms_coverage_v1_gaussian_splatfacto
```

The run state, selected sparse-model hashes, checkpoint config, dataparser transform, capture-gate JSON, and exported PLY remain in the ignored run directory. A resume invocation exposed that the runner truncated per-stage logs even when stages were skipped; the runner now appends stage headers so future resumes retain logs. The earlier Stage A-C console logs were already replaced by skip-only entries before that fix.

**Disposition:** keep Chainlink #104 open. The source was reused as directed, but this candidate cannot yet be claimed as a walkable, fully covered improvement. Do not extend collision bounds over unsupported visuals or close the task without operator review and the remaining runtime evidence.
