# Video -> Walkable Gaussian Splat

**Long-term target:** Milestone #10, a first-person Bevy 0.18 experience with Gaussian-splat visuals and co-registered collision.

## Current Execution Context

The active Chainlink work is the synthetic Backrooms proof of concept under #78 and #101. Its current runtime and pipeline are in `godot_walk/` and `scripts/splat_pipeline/`; this validates the video-to-walkable-scene workflow before the Bevy integration. The Bevy issue table that previously assigned #101-#110 to controller, renderer, and alignment work is stale: those IDs now refer to different live Chainlink issues. In particular, current Chainlink #104 is **Capture and reconstruct a fully covered synthetic Backrooms walkthrough**, not the former BE-4 alignment task. Do not reuse the old issue-number mapping.

The checked-in workspace currently contains the Godot prototype, not the `splat_walk/` Bevy crate described by the long-term target. Keep the Godot proof-of-concept and the future Bevy integration distinct; new Bevy work needs current issue IDs rather than the stale table.

## Current Chainlink Build Order

| Issue | Current goal | State / dependency |
|-------|--------------|-------------------|
| #78 | Deliver a reproducible video-to-walkable-scene pipeline | Parent epic |
| #101 | Verify the synthetic Backrooms PoC as a PSX-scale walking simulator | Open; bounded Gaussian patch found; hybrid PSX extension is next |
| #103 | Measure standard cleanup of the existing splat | Open for operator review; candidate report recommends new coverage |
| #104 | Capture and reconstruct a fully covered synthetic Backrooms walkthrough | Candidate trained; alignment found incomplete geometry coverage; keep open |
| #113 | Build a PSX room extension around a reliable Gaussian patch | In progress; manual room-v2 implementation is tracked by child #115 |
| #115 | Build and verify a manually authored PSX room extension v2 | Active child of #113; preserve and improve on the isolated control |
| #114 | Characterize minimum-good-splat capture patterns across synthetic videos | Planned after #113; blocked until the extension workflow is reproducible |
| #106 | Evaluate a textured-mesh route alongside Gaussian splats | Open parallel track |
| #107 | Produce one shared source clip for Gaussian and mesh routes | Closed; source and evidence are available |
| #108 | Build the textured mesh from the shared clip | Closed; negative result is valid and documented |
| #109 | Compare mesh and Gaussian routes at matched views | Open; requires #104's Gaussian output and walkable route |
| #102 | Add real-world fixture tiers after the synthetic PoC | Later |

Other open work under #78 includes #105 (cleanup techniques and limits), #93 (guidance consolidation), and #92 (DA3-Streaming evaluation). These are not prerequisites for running #104 with the already accepted source.

## #101 Hybrid PSX Completion Workflow

Operator direction on 2026-10-13 explicitly adds a product-art path alongside source reconstruction: use a reliable Gaussian patch as the visual anchor, then manually create a plausible PSX-style walkable room around it with authored 3D geometry. This is intentional game-world completion, not recovery of unseen geometry from the video. Keep surface provenance clear in assets and reports. The PoC is about a practical, repeatable art workflow, not photorealistic reconstruction or access to a world model's latent embeddings. Do not depend on paid services or model-specific interfaces.

The first bounded-region study is `godot_walk/evidence/2026-10-13-bounded-psx/`. It found the strongest native patch near world x=+0.50, z=1.70 m, but no sampled position had clean native 360-degree views. Its separate candidate encloses about 2 m2 and supports a 4.308 m out-and-back route; authored geometry rejects at least 54.9% of route pixels. This proves a small patch can anchor a hybrid, but the flat partitions, seams, and tiny footprint are not the target finish.

Issue #113 is the immediate experiment. Preserve the #100 source splat and existing scene. The primary test is a reproducible manual workflow for extending the best coherent splat patch into a plausible PSX room: establish a small set of editable room modules and material treatments, compose them around the patch, create deliberate splat-to-mesh transitions, and provide explicit collision for walkable surfaces and boundaries. The extension is intentional game art, not inferred unseen geometry. Generated 2D references or materials are optional; no image or video fill is a substitute for walkable 3D. Keep the existing production eye, FOV, PSX compositor, and camera settings. Judge all headings and intermediate turns along a meaningful route, and report black pixels, floaters, seams, authored-versus-splat contribution, traversal, and runtime. A free/open model that runs locally and exports useful editable geometry may be explored as a non-blocking comparison, but do not install or integrate one just to satisfy the PoC, and do not use paid services.

The first separate authored control is `godot_walk/scenes/corridor_psx_patch_extension.tscn`, documented in `godot_walk/evidence/2026-10-13-psx-extension/REPORT.md`. It preserves the production #100 PLY, collision, alignment, camera, and compositor, adds optional generated 2D materials plus manually authored 3D room geometry, and holds the existing 4.308 m micro-route. Across 24 matched route headings it reduces mean black pixels from 7.57% to 0.00% rounded and detached floater pixels from 388 to zero, but the 54.46% mean image delta is not an authored-geometry measurement. Treat this as a promising control, not task closure: the small footprint, flat partitions, seams, and visual contribution still need review and improvement. The next #113 pass should refine the manual room-building loop and measure authored/splat contribution, transition quality, traversal, and runtime. World-generation models are optional only if a useful free/open local workflow is readily available; no model or embedding access is required.

Issue #114 follows only after #113 establishes a reproducible manual patch-to-room loop. Run a controlled initial batch of synthetic clips from the same Backrooms visual target, vary capture-motion/coverage factors systematically, and train only candidates that pass cheap capture and pose gates. Measure whether each clip yields a compact, visually reliable Gaussian patch and how much manual PSX extension work it needs. Use the findings to define a minimum-good-splat-patch capture recipe before scaling to larger video batches.

### #115 Implementation Workflow

Keep the October 13 extension as a protected control. First capture representative splat-only views and annotate the patch envelope as good, marginal, or poor; use existing black/floater metrics as supporting data rather than inventing unvalidated artifact thresholds. Then build one separate room-v2 composition, reducing long partition dominance and making authored junctions intentional. Expand traversal only with explicit collision: if the Gaussian collision ends before the authored room, add a separately named authored floor collider and teach the verifier to report support by body while retaining floor/boundary negative controls. Parameterize the existing sweep and FPS harnesses for the v2 scene and evidence directory without changing legacy defaults. Compare matched views and intermediate turns, report visual transitions and runtime, and treat contribution masks as unmeasured unless an actual segmentation/ID pass is available; RGB differences from hidden-layer captures are not provenance masks. Use measured route area and length as results, not as arbitrary pass/fail targets.

#### #115 First Pass (2026-10-13)

The active v2 scene now has a 13.067 m out-and-back route and a reproducible 17.63 m2 spawn-connected standing-area estimate from a 10 cm capsule-clearance/floor-ray grid. Its gross authored floor-collider rectangle is 22.01 m2, which overlaps existing generated floor and is not the net walkable figure. The route reports 100% floor support, zero SafetyNet contacts, and support contacts from both `GeneratedCollision` and `AuthoredFloorExtension`; removing either configured floor set or the tested east boundary makes verification fail. At the patch anchor, eight matched views reduce mean black pixels from 3.761% to 0.000% rounded and detached floaters from 20.6 mean pixels to zero. A 216-frame yaw/pitch sweep still has 0.106% mean and 2.426% maximum black pixels. Human review finds the south/southeast patch strongest, with attached ceiling smears and rough joins still visible. Keep #115 open for visual composition review; do not start #114 until the loop and composition are accepted.

This hybrid track does not change #104: #104 still measures whether the accepted #107 source can produce a fully covered Gaussian scene. Generated PSX extensions cannot be used to pass #104 or be described as reconstructed video geometry. Neither #113 nor #114 by itself closes #101.

## Shared Source For #104 And #108

Use the existing accepted source at `data/scenes/backrooms_coverage_v1/video.mp4`. It is one 1920x1080, 24 fps, 8-second clip generated from the existing Backrooms visual target and delivered by #107 for both reconstruction branches. Its prompt, generation settings, hashes, sampled frames, capture gate, COLMAP records, contact sheet, and limitations are recorded in `godot_walk/evidence/2026-10-07-coverage-source-clip/`.

This is the coverage-driven successor to #100/#103, not a new Backrooms target. #100's 182,569-splat scene remains the baseline; #103 found that post-hoc filtering made the eight-view result worse (black pixels 10.03% to 12.51%, floaters 656 to 800) and recommended retraining with added coverage and scale regularization enabled. #104 must compare its new reconstruction against that baseline at the same production-eye poses. Preserve the old asset and evidence unchanged.

For #104, there is no requirement to author another scene or generate another video. Reconstruct the accepted #107 clip as a separate Gaussian candidate, then validate alignment, collision, traversal, and production-eye views. Preserve the source and its existing evidence; keep new run outputs in a separate ignored work directory. The later controlled video batch belongs to #114, after the distinct hybrid workflow is demonstrated.

Known source limitations must remain visible in the result:

- Stage A is `ACCEPTED_WITH_WARNINGS`; camera travel is 0.942 frame widths in four directions, with a borderline rotation-dominant warning.

## #104 Attempt Result

The 2026-10-12 run used the established COLMAP/GLOMAP -> Nerfstudio Splatfacto -> Godot path and the existing #107 video. Splatfacto completed 30,000 steps with scale regularization and exported 111,812 Gaussians. The selected sparse model registered all 111 extracted frames, but registration did not mean that the exported geometry supported the full camera path.

Stage D measured the floor/ceiling scale, then rejected the candidate: opaque splats in the camera-path window ended about 5.0 m short of the camera path on one horizontal axis and 2.27 m short on the other. A dense 0.65 m plane pair was also rejected as an internal surface because it did not enclose the camera path within the existing 2 m tolerance. The alignment contract therefore did not produce a manifest, and collision, traversal, Godot staging, matched eight-heading renders, and runtime/fps checks did not run. Do not stretch the collision volume or call this a walkable result; the run and detailed measurements are in `godot_walk/evidence/2026-10-12-coverage-splatfacto/REPORT.md`.

Keep #104 open. The accepted clip was processed as directed, but this candidate does not satisfy its full-coverage requirement. Any additional source for #104 requires explicit operator direction; the controlled patch-optimization batch under #114 is a separate track and starts only after #113.
- The legacy parallax check reports 4.57 degrees versus its 6-degree threshold.
- COLMAP produced overlapping components (86 and 45 cameras); the documented GLOMAP attempt aborts on this database.
- The AI-generated floor texture drifts across frames. This is synthetic-PoC evidence, not proof of real-video generality.

These are reported limitations, not reasons to silently substitute the older corridor splat or claim unseen surfaces were reconstructed. If the accepted clip cannot produce a usable route, record the failure and evidence before proposing another capture.

## Pipeline

```text
data/scenes/backrooms_coverage_v1/video.mp4
  -> bounded capture gate and selected frames
  -> COLMAP/GLOMAP pose reconstruction, with the supported VGGT fallback
  -> Nerfstudio Splatfacto Gaussian training (scale regularization enabled)
  -> alignment manifest
  -> generated collision mesh and traversal plan
  -> staged Godot scene and production-eye verification
```

The established #77/#100 reconstruction route is COLMAP/GLOMAP -> Nerfstudio Splatfacto -> Godot. Use that route for #104; Brush is a fallback for the separate future Bevy pipeline, not the selected trainer here. The accepted clip's default GLOMAP run aborted during retriangulation; setting `GLOMAP_SKIP_RETRIANGULATION=true` has produced a single 111/111-camera model. Record the failed default and recovered model explicitly rather than treating the earlier abort as success.

Use the existing resumable driver for the active Godot proof-of-concept, with scale regularization enabled for this retraining:

```bash
GLOMAP_SKIP_RETRIANGULATION=true NS_USE_SCALE_REGULARIZATION=true \
  SPLATFACTO_BRUSH_FALLBACK=false \
  TRAIN_BACKEND=splatfacto \
  scripts/splat_pipeline/run_pipeline.sh \
  data/scenes/backrooms_coverage_v1_gaussian_splatfacto
```

The run directory should contain a link or copy of the accepted `video.mp4`; it must not overwrite `data/scenes/backrooms_coverage_v1` or the tracked #107 evidence. The #100 scene, alignment, collision, and route remain the comparison baseline. The expected per-scene output is `scene.ply`, `alignment_manifest.json`, `collision.collision.glb`, `collision_benchmark.json`, `traversal_manifest.json`, pipeline logs/state, and a staged Godot scene. Retain exact commands, tool versions, hashes, gate results, pose registration counts, resource/OOM behavior, and matched-view render/traversal evidence for #104.

## Environment

Before front-end pipeline work, enter `nix develop`, install missing GLOMAP, Brush, VGGT, and SuGaR tools with `./environment/setup-pipeline-tools.sh`, and confirm them with `./environment/setup-pipeline-tools.sh status`. COLMAP and Python/PyTorch dependencies are provided by the `nerfstudio` conda environment; activate it for pipeline commands. Binaries are installed under `$HOME/.local/bin`.

## #104 Acceptance

- Reuse and identify the #107 source clip; preserve prompt/settings and source hashes.
- Record the capture gate and selected-frame/pose coverage, including disconnected models and failed/recovered attempts.
- Produce a reproducible Gaussian scene with alignment and collision outputs, or a measured failure report if the source/toolchain cannot support it.
- Verify floor support and traversal on the intended bounded route; report SafetyNet contacts, fps/resource use, and limitations.
- Capture identical production-eye views for all eight headings and quantify black holes and visible floaters.
- Keep #101 open for operator review. Do not claim this synthetic result proves real-world generality.

## Future Bevy Integration

The intended Bevy runtime uses `bevy` 0.18, `avian3d` 0.6, `bevy-tnua` 0.31, `bevy-tnua-avian3d` 0.11, and `bevy_gaussian_splatting` 7 (`default-features = false`). The asset contract is `scene.ply` for visuals, `collision.glb` for physics, and `alignment.toml` for the identical transform applied to both. The older `splat-handoff/` notes describe this target; they are not the live Chainlink #104 execution procedure.

## References

- Active issue tree: `chainlink issue tree`
- Current pipeline: `scripts/splat_pipeline/README.md`
- Shared clip evidence: `godot_walk/evidence/2026-10-07-coverage-source-clip/REPORT.md`
- Synthetic PoC evidence: `godot_walk/evidence/2026-10-06-bounded-walk/`
- Historical Bevy asset contract and scaffolding: `splat-handoff/`
