# Video -> Walkable Backrooms

**Long-term target:** a first-person Bevy 0.18 Backrooms simulator assembled from a library of individually tested rooms. Source video informs each room's visual content and layout; collision remains explicit, validated geometry. A deterministic 2D room graph can later generate maze-like runs from approved modules.

## Current Execution Context

The workspace contains both the established Godot prototype/pipeline and the Bevy 0.18 crate in `splat_walk/`. Keep `data/scenes/corridor_travel/` and the #100 scene as protected reference inputs. Current Chainlink #104 is **Capture and reconstruct a fully covered synthetic Backrooms walkthrough**, not the former BE-4 alignment task. Do not reuse the old issue-number mapping.

## Working Milestone: Video To Walkable

`milestone/video-to-walkable-working` points to commit `d785651` and is merged into local `main`. It is the first operator-played Bevy walkthrough from the #100 source: a run-05 Hunyuan GLB supplies visuals only, while the exact #135 authored collision GLB supplies the floor, column proxy, and edge boundaries. The shared player controller moves the player around the authored loop. The evidence and launch command are documented in `splat_walk/README.md` and `godot_walk/evidence/2026-10-13-hunyuan-track-a/`.

This is a working, uncalibrated playable zone, not a metric reconstruction of the whole source video. The route is deliberately authored. Hunyuan geometry does not provide collision. `registration_accepted=false` and `scale_calibrated=false` remain locked. The tag is the baseline for extending the simulator, not a claim that room discovery, module stitching, or procedural generation is done.

## Roadmap: Room Library To Generator

1. **Inventory the footage.** Map the rooms, corridors, columns, doorways, and transitions that the #100 source actually shows. Record frame ranges, camera coverage, visible openings, and unknown areas. Propose a 2D layout with evidence-backed and authored parts distinguished.
2. **Define a room module.** Give each module a stable ID, source-video/frame provenance, visual asset, separate collision asset, coordinate/scale status, connector sockets, exposed-boundary rules, playability report, and resource measurements. Register the tagged walkthrough as an uncalibrated reference zone, not a surveyed full room.
3. **Build rooms one at a time.** Select a room from the reviewed inventory. Create its visual candidate and explicit collision route. Run it standalone in Bevy with the shared fixed-step controller, boundary and obstacle controls, and operator visual review. Do not add a module to the catalog before it passes.
4. **Stitch verified modules.** Place at least two approved rooms through compatible connectors. Test doorway clearance, floor-height transitions, collision seams, continuous traversal, and exposed edges. Reject a layout if a room works alone but its connector does not.
5. **Generate layouts.** Once the catalog contains multiple validated modules, generate a deterministic 2D grid or room graph from compatible connectors. Use a seed and explicit topology constraints for loops, dead ends, reachability, and exits. The generator places approved modules; it does not invent untested collision.

Track A (#144) owns room inventory, module contracts, standalone Bevy validation, stitching, and layout generation. Track B (#117) continues the human-directed PSX visual/design loop in parallel. Track B can inform the visual grammar and transitions, but it is not a gate for Track A. WorldMirror is optional research, not a prerequisite for a playable room library.

## Current Chainlink Build Order

| Issue | Current goal | State / dependency |
|-------|--------------|-------------------|
| #78 | Deliver a reproducible video-to-walkable-scene pipeline | Parent epic |
| #101 | Verify the synthetic Backrooms PoC as a PSX-scale walking simulator | Open; #116 now carries the room-library and design-iteration direction |
| #116 | Backrooms room library, design iteration, and layout generation | Open umbrella; starts from `milestone/video-to-walkable-working` |
| #111 | Audit committed Backrooms artifacts for unnecessary binaries | Open; inventory and reference-check before any cleanup; user design work is out of scope |
| #117 | Track B: establish the PSX design-iteration harness | Open; parallel to Track A, not a gate |
| #121 | Run the first Gaussian-backed design iteration rounds | Open; operator-reviewed feedback loop under #117 |
| #144 | Track A: build a verified room catalog and modular Bevy scenes | Open; children #145-#149 |
| #145 | Inventory #100 source footage and propose a room plan | Open; first Track A step; operator reviews layout |
| #146 | Define the validated Bevy room-module contract | Open; blocked by #145 |
| #147 | Build and validate the first additional room module | Open; blocked by #146 and room approval |
| #148 | Stitch verified room modules through tested connectors | Open; blocked by #147 |
| #149 | Generate seeded 2D Backrooms layouts from verified modules | Open; blocked by #148 |
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

The proposal in `PLAN_IMAGE_TO_PANORAMA_DESIGN_HARNESS.md` is decomposed under #116. Start with Track B, #117, and its design brief, deterministic capture, and first human-directed iteration tasks (#119-#121); #118 research is advisory. Treat replay as measured repeatability, not guaranteed determinism; use visual metrics as diagnostics, not provenance or unvalidated pass/fail gates. Track A, #122-#126, is blocked until #121 demonstrates a useful loop. Hunyuan input must be a registered raw frame from the #100 source video, never a Gaussian render; this does not change #104's reconstruction criteria or replace the #115 baseline.

Track B #121 remains active after #120. Round 1 selected the frame-aligned
`door_flush` hatch. Round 2 found the `north_wall_smooth` wall shape promising,
but it lost the Backrooms wallpaper; the lowered ceiling did not resolve its
splat artifacts. Round 3 sampled wallpaper from registered frame 1 of the
actual #100 source video (`data/scenes/corridor_travel/video.mp4`). The operator
then confirmed the preference is angle-dependent: `north_wall_source_texture`
helps on several patch-anchor and column views, while `door_flush` retains the
native wall texture better from transition-west and far-room-west. The
walkthrough reads as a room with a column and smaller door hallway; movement is
consistent with no falls through the floor. Remaining work is to complete
artifact-heavy wall corners and column faces, and smooth/cover the ceiling and
floor without applying one wall candidate universally.

Round 4 is the next separate review candidate. It keeps `door_flush` as control
and adds a visual-only source-frame texture wrap for the north wall, ceiling,
floor, and column; it leaves the far door wall in place and preserves the #100
PLY, collision, route, camera, and compositor. The 13.067 m route has 100% floor
support and zero SafetyNet contacts; floor and boundary negative controls fail
as expected. Capped performance is 60.00 FPS (p95 16.85 ms, p99 16.94 ms),
protected inputs are unchanged, and control repeat noise is at most 0.07%.
ODiff changes are diagnostics, not a quality score. Review at
`godot_walk/evidence/2026-10-14-psx-design-round-4-final/index.html`; keep #121
open and #122 deferred until the operator reviews the new candidate. An earlier
round-3 source check used the separate #107 video and is marked superseded in
its evidence directory.

Round 4 review identified an accidental second column: its source-textured cover
was placed at z=2.55 m instead of over the existing column on the far-room
z=0.2 m centerline. Round 5 preserves round 4 and compares the `door_flush`
control with two new visual-only candidates: source-textured floor plus a single
aligned column, and those surfaces plus a lower source-textured ceiling, fitted
visible wall meshes, and square perimeter trim. The #100 PLY, collision, route,
door, and camera remain fixed. Evidence:
`godot_walk/evidence/2026-10-14-psx-design-round-5-final/index.html`.

Round 5 passes the 13.067 m route with 100% floor support, zero SafetyNet
contacts, expected boundary/floor negative-control failures, and capped 60 FPS.
The corrected column cover reads as one column in the far-room comparison. The
lower-ceiling variant still has visible Gaussian/bright artifacts and stronger
trim, so it is not selected as a fix. Keep #121 open for the operator to review
matched views and the live walk before choosing a next wall/ceiling iteration.

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
