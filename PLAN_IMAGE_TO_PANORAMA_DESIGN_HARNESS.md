# Hunyuan-to-PSX Room Completion and Walkable Design Harness

**Status:** Hunyuan evaluation #122-#126 is complete. Track B #117 now owns the
Hunyuan-to-PSX room-completion workflow; #151 is its next implementation task.
Gaussian-backed rounds in #121 remain useful precedent, not a prerequisite.
SkillOpt is deferred to #152 until operator-confirmed workflow evidence exists.

## Goal

Use the completed Hunyuan panorama/layered-mesh outputs, generated from a direct
registered frame of the original #100 source video, as a visual candidate for
manual PSX room completion. Preserve useful Hunyuan areas, author the missing
PSX-style geometry and materials, add explicit collision where needed, and
produce bounded walkable variants with matched evidence for operator review.
The goal is a plausible, enjoyable simulator, not metric recovery of unseen
geometry. The operator remains the design decision-maker.

HunyuanWorld 1.0 gets an extracted source-video frame, never a rendered Gaussian
screenshot or the Gaussian `.ply`. The completed Hunyuan output is a generated
visual candidate, not a conversion of Gaussian embeddings and not recovered or
registered geometry. The accepted Bevy walkthrough from #150 is a
gameplay-feel reference; the Gaussian-backed #100/#115 scene remains a
protected, separate reference track.

## Protected Baseline

- Use the imported Hunyuan candidate from completed #125 as the visual input
  for PSX completion. Use the accepted #150 Bevy walkthrough as a gameplay-feel
  reference, not as a geometry or scale authority.
- Keep the #100 splat, `corridor_psx.tscn`, #115 control, Hunyuan source outputs,
  and accepted #150 scene unchanged. Make new candidate scenes and evidence.
- Use `data/scenes/corridor_travel/video.mp4` as the Hunyuan image source. The
  #100 alignment manifest names this video as the source for the walked splat;
  it is 1920x1080, 24 fps, 8 seconds, SHA-256
  `ac5cd0d1aa11aadd39cc45ff460af5e00372f8417d2514fce1bfa7c7837895c4` in the
  current checkout. Do not substitute the separate #107/#104 video at
  `data/scenes/backrooms_coverage_v1/video.mp4`.
- Keep the source video and Hunyuan output provenance attached to every
  candidate. Do not use a Gaussian render or PLY as Hunyuan input.
- Keep downloaded model weights and bulky generated outputs outside tracked
  source. Commit only scripts/configuration/reports that are intentionally
  adopted. Do not overwrite production assets or current evidence.

## Parallel Tracks

### Completed Hunyuan Evaluation: Image-to-Panorama to Godot

The feasibility, direct source-frame selection, panorama generation, layered
mesh import, and visual/parallax/walkability evaluation in #122-#126 are
complete. The resulting Hunyuan candidate is useful visual input, but its
transform and scale are not accepted as calibrated. The #150 Bevy walkthrough
uses Hunyuan visuals with separately authored collision. The detailed A0-A6
steps below document the experiment and its provenance; they are not a gate
for #151 and do not imply that generated mesh geometry is registered.

**A0. Feasibility gate**

1. Pin the HunyuanWorld repository revision and record local GPU, VRAM, driver,
   Python, and CUDA versions.
2. Review the HunyuanWorld community license for the operator's territory and
   intended use before downloading weights. Confirm Hugging Face access and
   local disk/VRAM requirements. Use a separate environment; do not alter the
   Nerfstudio environment, store credentials in the repo, or use paid hosted
   inference.
3. Stop with a measured setup report if local execution or license terms do
   not permit the experiment. Do not silently substitute a hosted model.

**A1. Freeze the image input**

1. Make a contact sheet from the original `corridor_travel/video.mp4` and
   identify a sharp, representative source frame that depicts the region used
   by the good #100 patch. Extract that frame directly from the video with no
   Gaussian rendering, PSX compositor, AI restyling, crop, or rescaling. Prefer
   the existing Stage A extracted frame only after verifying its frame index
   and source-video identity; otherwise extract the selected timestamp anew.
2. Confirm the selected frame is registered in the #100 COLMAP model. If it is
   not registered, select a nearby registered frame instead of inventing a
   camera pose. Record video hash, frame number/time, frame hash, image
   dimensions, and corresponding COLMAP image/camera pose. Keep the exact
   source frame as the Hunyuan seed image; a rendered Godot screenshot is never
   substituted.
3. The source is a 2D video frame, not Gaussian data. Hunyuan receives no PLY,
   Gaussian embeddings, or splat artifacts unless those artifacts were
   already present in the original video itself.

**A2. Generate controlled panoramas**

1. Run the upstream image-to-panorama demo locally with the same image and
   fixed prompt/settings at three recorded seeds. Keep all outputs and the
   exact command/config in a run-specific evidence directory.
2. The upstream demo produces a 1920x960 equirectangular panorama and currently
   assumes an 80-degree input FOV. Derive the source-frame camera intrinsics
   from the #100 COLMAP model (or source-generation metadata if available).
   Compare the upstream 80-degree default with a run configured to the
   measured source FOV using the same seed. Record theta/phi and all other
   changes; preserve any small local wrapper/patch rather than editing an
   external checkout in place.
3. Inspect the panorama for fidelity in the original view, 360-degree seam
   continuity, duplicated or melted structures, and whether the completion
   looks like a plausible PSX Backrooms space. ODiff can show pixel changes
   when the panorama is reprojected into the source camera view, but the
   operator decides whether generated content is useful.

**A3. Preview before building geometry**

1. Add the selected panorama to a disposable Godot preview as an equirectangular
   environment/shell, with its orientation aligned to the captured camera.
2. Verify all yaw directions from the anchor with fixed screenshots. Rotate
   the camera in place only; label this result panorama-only and non-walkable.
3. Gate: the original forward view remains recognizable and the full rotation
   has no unacceptable seam, blank wedge, or obvious discontinuity. Otherwise
   stop this candidate before mesh generation.

**A4. Generate and convert the layered scene**

1. Feed the selected panorama to `demo_scenegen.py`; record foreground labels,
   class argument, seed, and all output layers. Upstream examples default to
   `outdoor`; indoor Backrooms support and useful semantic labels are an
   explicit feasibility risk, not an assumed feature.
2. Preserve the exported PLY layers as source evidence. Inspect bounds,
   axes, normals, triangle counts, vertex colors/UVs, and whether layer
   separation produces useful parallax.
3. Convert each usable triangle-mesh PLY layer to GLB with a pinned local
   converter, preserving layer names, colors/materials, and relative
   transforms where possible. Godot 4.6's documented recommended 3D scene
   interchange format is glTF 2.0; do not assume its Gaussian PLY importer
   handles ordinary triangle-mesh PLYs.
4. Import the GLB into a separate test scene, check front-face winding,
   normals, materials, coordinate axes, and bounds, then save the import
   settings and conversion command.

**A5. Match the scene and test parallax**

1. Align the generated environment's forward direction to the source frame's
   camera orientation. When the frame is registered, use its COLMAP pose and
   the existing #100 alignment contract to initialize the panorama anchor in
   Godot world coordinates.
2. The Hunyuan mesh is not registered geometry. A single image cannot
   determine its absolute scale or unique 3D structure. Fit mesh scale and any
   residual transform manually against visible landmarks and current room
   dimensions; document the fit instead of claiming reconstruction accuracy.
3. Render matched views at the anchor and at small lateral/forward offsets.
   Require convincing parallax and stable appearance before treating the mesh
   as a spatial candidate. A panorama that only works from its center remains
   a useful visual background, not a walkable world.

**A6. Test walkability separately from appearance**

1. Treat Hunyuan meshes as visual geometry until verified. Build explicit
   collision from suitable floor geometry or a separately authored proxy; do
   not make the generated panorama itself collision or trust arbitrary mesh
   topology as a floor.
2. Run the existing bounded-walk verification, boundary and floor negative
   controls, matched route captures, and FPS measurement in a new scene.
3. Report two outcomes separately: (a) visual source useful to the design
   harness; (b) geometry supports a safe walkable route. Passing (a) does not
   imply (b).

### Track B: Hunyuan-to-PSX Room Completion

This is the next design task (#151). Use the imported Hunyuan candidate from
#125 as visual input; use the accepted #150 Bevy walkthrough only as a
gameplay-feel reference. Do not restart Hunyuan generation unless a later
round explicitly needs another candidate. Do not use the Gaussian-backed
#100/#115 scene as Hunyuan input or mutate it.

**B0. Define the room-completion brief**

Preserve the useful Hunyuan visual areas and deliberately replace, cover, or
extend weak areas with authored PSX geometry and sampled/created PSX materials.
Give explicit collision only to authored, validated walkable surfaces and
boundaries; Hunyuan visual meshes remain non-colliding by default. Treat the
work as intentional room design, not reconstruction of unseen geometry. Keep
the walkthrough smooth, avoid arbitrary doors/duplicate landmarks, and use
operator feedback to refine the brief. Do not invent a numeric aesthetic score.

**B1. Make edits and variants addressable**

1. Keep the Hunyuan source assets and accepted walkthrough read-only. Create
   separate candidate scenes/specifications with stable IDs, parent IDs, and
   concise change summaries.
2. For each visible region, record a deliberate `preserve`, `cover`, or
   `replace` action and its rationale. Record which content is video-observed,
   Hunyuan-generated, authored, or inferred. Mark unknown areas as unknown.
3. Describe authored geometry, material IDs/texture sources, collision extents,
   and Hunyuan-to-authored junction treatments in a versioned room spec. Keep
   each round bounded and change one main design hypothesis at a time.
4. Produce walkable candidates with explicit collision and stable route/camera
   bookmarks. Do not silently use generated mesh topology as a floor or claim
   that its uncalibrated scale/transform is registered.

**B2. Validate and make a review bundle**

1. Reuse the existing Godot capture and walk-verification scripts where they
   apply. Keep camera poses, viewport, FOV, route, and settle settings matched
   across variants; record observed replay drift rather than assuming physics
   determinism.
2. Run route/floor/boundary checks, expected negative controls, and same-device
   performance measurements before visual review. Report ODiff and other image
   metrics with the measured repeat-noise floor; they are diagnostics, not
   provenance or quality scores.
3. Bundle runnable commands, matched captures, contact sheets, ODiff diffs and
   per-view metrics, mechanical reports, and an operator feedback form. The
   operator may choose a candidate, reject all, or request a new direction.

**B3. Log the loop for future SkillOpt evaluation**

1. Each round writes a schema-validated manifest and operator feedback record
   with stable round/variant/parent IDs; original source-video frame and Hunyuan
   asset hashes; model/tool/config/seed provenance; region decisions and
   rationale; authored geometry/material/collision changes; exact commands and
   capture settings; mechanical results; image metrics and evidence paths; and
   the operator's choices, reasons, unresolved problems, confidence, and
   next-round directives.
2. Preserve accepted round records append-only. Correct errors with a dated
   addendum or superseding record, not silent edits. Attribute every claim to
   operator text, direct observation, generated output, authored proposal, or
   inference so later evaluation can separate evidence from interpretation.
   Append each confirmed round to `godot_walk/design_rounds/hunyuan_track_record.jsonl`
   with variant hypotheses and authored changes, per-view ODiff measurement
   snapshots, mechanical evidence, operator choices, and stable directive IDs.
   Exclude pending and diagnostic-only candidates.
3. Complete an initial Hunyuan-to-PSX round and one follow-up directed by
   operator feedback. The workflow skill organizes the work and summarizes
   evidence; it never selects or promotes a design. No SkillOpt run is part of
   #151. The first two confirmed Hunyuan rounds are indexed; the Round 3
   placement diagnostic remains excluded because it has no confirmed feedback.
4. Consider SkillOpt only under #152 after at least five operator-confirmed
   rounds and 30 labeled decision items exist. Split data by round, hold out the
   latest confirmed round, and keep gathering examples if the data are weak.
   SkillOpt may improve the workflow skill, not make visual design decisions.

## Original Hunyuan Evaluation Gates

- **Input integrity:** original source-video path/hash, extracted frame index,
  timestamp/hash, registered camera pose, model/tool revisions, prompts/seeds,
  generated outputs, and hashes are recorded.
  Production #100/#115 assets remain unchanged.
- **Panorama quality:** the selected source-video frame remains recognizable
  from the aligned forward view; 360-degree rotation is visually continuous;
  the upstream 80-degree FOV default is compared with the COLMAP-measured
  source-frame FOV.
- **Godot import:** layered mesh imports through a reproducible GLB path with
  reviewed orientation, scale, materials, and bounds.
- **Spatial usefulness:** small camera translations produce stable parallax.
  If not, classify as panorama-only, not a usable walkable source.
- **Walkability:** candidate route has floor support at every probe, no
  SafetyNet contacts or boundary escapes, and expected negative controls fail.
  Compare against the current 13.067 m v2 route; report rather than silently
  lower coverage if a source cannot support it.
- **Runtime:** report same-device capped and uncapped frame timing against the
  current v2 measurements.
- **Design convergence:** for the later room-completion work, operator
  approval follows review of repeatable views and a live walk. Human review
  remains the visual acceptance gate; ODiff metrics are diagnostic evidence
  only.

## Room-Completion and Trace Gates

- Preserve the imported Hunyuan assets and source provenance; keep the
  Gaussian #100/#115 inputs unchanged and distinct from Hunyuan input.
- Label source-observed, Hunyuan-generated, authored, inferred, and unknown
  content separately. Do not turn a visually plausible generated extension
  into a claim about source-video architecture, registration, or scale.
- Every candidate has authored, validated collision for its walkable route and
  explicit boundaries. Run route/floor/boundary checks and negative controls
  before operator review; record performance on the same device.
- Every round includes matched views, contact sheets, commands, metrics with
  noise-floor context, and a schema-valid structured trace of variant changes
  and operator feedback. Keep records append-only and reproducible.
- The operator decides whether a design is useful. The workflow can organize
  evidence and propose the next bounded experiment, but cannot select or
  promote a winner.
- Do not evaluate SkillOpt until #152's confirmed-round and labeled-item
  readiness gates are met, the round-level holdout is defined, and the
  operator approves the backend and budget.

## Research Prompt

Use this prompt for the advisory research task in Chainlink #118:

> Research practical techniques that complement a human-directed Hunyuan-to-PSX
> room-completion workflow for a walkable Godot 4.6 Backrooms simulator. The
> visual input is the existing Hunyuan candidate generated from a direct frame
> of the #100 source video; the accepted Bevy walkthrough is a gameplay-feel
> reference. The work preserves useful generated areas and manually authors
> PSX geometry, materials, and collision to complete a plausible room. The goal
> is a smooth, intentional, coherent, extensible walkable place. The proposed
> loop uses addressable room
> variants, deterministic route/camera captures, mechanical walkability and
> performance checks, ODiff for same-pose pixel-change diagnostics, and
> operator selection plus specific feedback. Do not feed a Gaussian render or
> PLY to HunyuanWorld. The workflow skill organizes evidence and next steps;
> the operator chooses the design.
>
> Find 3-5 concrete, locally usable approaches that can complement this loop:
> deterministic state capture/replay and camera bookmarks; bounded or
> parametric variant generation and design-of-experiments; pairwise preference
> or structured human feedback; perceptual or region-aware visual diagnostics
> that complement (not replace) ODiff; and Godot scene/configuration or render
> test automation. Prefer maintained open-source tools, official APIs, and
> techniques with a small integration cost. For each approach, cite primary or
> official sources; state its license, local hardware/setup cost, Godot 4.6
> integration path, what it can and cannot detect, maintenance risks, and one
> minimal pilot. Separate objective gates (route support, boundary containment,
> regressions, frame time) from subjective judgments (composition, coherence,
> whether a door feels motivated, and whether the space invites exploration).
> Do not recommend paid hosted services, broad 3D world generation, new model
> training, or an automated aesthetic score as the decision-maker. Finish with
> a ranked recommendation for the smallest pilot that lets the operator
> compare three variants and give actionable feedback. Flag assumptions and
> unresolved questions.

## Research Review: Pilot Guardrails

The research feedback is actionable; use these corrections before turning its
pilot into hard acceptance criteria:

- Treat `--fixed-fps` and MovieWriter as a capture-repeatability experiment,
  not proof of deterministic physics. Godot documents physics as nondeterministic.
  Record player/camera state and support results over three route replays, and
  report observed drift. First A/B the `.png` MovieWriter output against the
  existing `get_image()` capture path; only use it if the PSX compositor and
  splat renderer match.
- Treat the three candidates as a small hypothesis comparison, not a DOE or
  statistical experiment. Start with A: current v2 control; B: make the door
  integrated and flush with its surrounding room; C: art-direct the artifact-
  facing column face. Change one primary idea in B and C, preserve the PLY, and
  report observed deltas without claiming effects or interactions. A later
  2-factor interaction test needs a clearly specified design, not three
  confounded candidates.
- Use ODiff and optionally FLIP as visual diagnostics. Define fixed
  screen-space regions of interest for the patch/column, doorway transition,
  and far room. Do not derive surface ownership or exact provenance masks from
  `both`, `splat-only`, and `authored-only` RGB captures; those passes can help
  human inspection, but RGB changes are not segmentation. Exact attribution
  needs a separately validated object-ID/depth or renderer instrumentation
  path. Try FLIP on a few known pairs, including a PSX-dithered pair, before
  adding it to the required bundle.
- Do not adopt `black <= 0.5%`, `seam gap <= 0.1%`, or `>= 60 FPS` as universal
  blocking gates from this research alone. The current v2 sweep has 2.426%
  maximum black pixels, and its capped draw-callback timing reports 60.002 FPS
  with 16.856 ms p95 and 16.923 ms p99; these measures do not establish those
  proposed thresholds. First report baseline repeat noise and same-device
  candidate deltas, retain existing walk/boundary/negative-control checks, and
  set a threshold only when its metric and acceptance meaning are validated.
- Keep the first review small: six matched views per candidate across the
  patch/column, door/transition, and far-room stations, with two useful
  headings per station. Record the three pairwise choices and reasons, randomize
  presentation order, and repeat one pair to check preference stability. Keep
  raw choices; do not fit a Bradley-Terry score from one operator and three
  candidates. Existing verifiers are enough for the pilot; defer GUT and broad
  automation unless a concrete test gap appears.

## Risks and Fallbacks

- HunyuanWorld 1.0 may require gated model downloads, a compatible local GPU,
  and a community-license review. Resolve this before spending time on setup.
- The released scene-generation examples default to outdoor classes. If
  indoor panorama completion works but indoor layered-mesh reconstruction
  does not, retain the panorama as an appearance reference and continue with
  manually authored PSX geometry and explicit collision. The Gaussian-backed
  #100/#115 work remains a separate reference track.
- Single-view generated geometry can look plausible while failing under
  translation. Do not equate a successful 360 panorama or GLB import with a
  navigable space.
- If no useful mesh survives import/parallax checks, keep the Hunyuan panorama
  or source view as a visual reference and author the walkable room explicitly.
  Do not promote the Gaussian-backed harness to the Hunyuan workflow by default.

## Chainlink Breakdown

- **#116, umbrella epic:** room library and human-directed design workflow,
  under #101. Keep it distinct from #104 reconstruction acceptance, #115's
  existing Gaussian room, and Track A module stitching.
- **#117, Track B epic:** complete the Hunyuan visual candidate as a PSX-style,
  operator-reviewed walkable room. Log each design round for future workflow
  skill evaluation.
- **#118:** research complementary techniques. Advisory and non-blocking for
  the first implementation pass.
- **#119:** define the design brief and addressable room variants.
- **#120:** build deterministic capture and ODiff review bundles; blocked by
  #119.
- **#121 (open, reference track):** preserve and continue the Gaussian-backed
  design rounds around the protected #100/#115 scene. The operator selected
  door, wall-texture, floor, ceiling, and column treatments across rounds 1-5.
  These rounds establish useful review patterns but are not Hunyuan inputs or a
  gate for #151.
- **#122, Hunyuan evaluation epic (closed):** direct registered #100 source
  frame through panorama generation, mesh import, and walkability review.
  Hunyuan output is useful visual input, not calibrated geometry.
- **#123-#126 (closed):** preflight/source selection, panorama review, layered
  mesh conversion/import, and alignment/parallax/walkability evaluation.
- **#151 (active, high):** implement the Hunyuan-to-PSX workflow, author
  bounded walkable variants and matched review bundles, and log each round in
  a schema-valid, append-only record. Initial and feedback-directed rounds are
  recorded; operator review remains pending. No SkillOpt run or automatic
  winner selection.
- **#152 (planned, blocked by #151):** evaluate SkillOpt on the workflow skill
  only after at least five operator-confirmed rounds and 30 labeled decision
  items exist, split by round with the latest round held out. Require operator
  approval for model/backend and budget; keep the operator as visual decision
  maker.

### #121 Round 1 Results (2026-10-13)

The first review bundle is `godot_walk/evidence/2026-10-13-psx-design-round-1-final/`.
The control, frame-aligned hatch, and authored end-wall candidates all pass the
13.067 m route with 100% floor support, zero SafetyNet contacts, and unchanged
collision; floor and boundary negative controls fail as expected. Three control
replays match for all 197 ticks with zero measured position drift or contact /
floor mismatches. Capped averages are about 60 FPS; p95 frame times are
16.84-16.85 ms, slightly above the 16.67 ms budget.

The frame-aligned hatch is visually subtle (0.199% mean ODiff delta versus
0.16% maximum control-repeat noise). The end-wall candidate is distinct
(9.657% mean delta) but Gaussian artifacts remain visible through its surface.
The operator selected the flush hatch from the four east-facing station views.
They noted that the right-hand wall needs smoothing and the ceiling still has
distracting Gaussian artifacts.

### #121 Round 2 Results (2026-10-13)

The feedback-driven review bundle is
`godot_walk/evidence/2026-10-13-psx-design-round-2-final/`. It compares the
selected `door_flush` baseline with `north_wall_smooth` and `clean_ceiling`.
All three pass the 13.067 m route with 100% floor support and zero SafetyNet
contacts; boundary and floor negative controls fail as expected. Repeated
`door_flush` traces match for all 197 ticks with zero measured position drift
or contact/floor mismatches. All variants sustain about 60 FPS capped, with
p95 frame times from 16.83 to 16.86 ms. Protected splat, room, route, and
collision inputs hash unchanged.

The north-wall candidate changes matched views by 3.233% mean ODiff and gives
the right-hand wall a smooth panel treatment, but creates a broad plain surface
that needs operator judgment. The lowered-ceiling candidate changes views by
0.378% mean ODiff; Gaussian ceiling artifacts remain visible, so the geometry
test did not establish a fix. Baseline repeat noise is at most 0.03%. ODiff is
only a change locator. The operator said the north-wall shape was promising
but should retain the original Backrooms texture.

### #121 Round 3 Results (2026-10-13)

The corrected source-texture review is
`godot_walk/evidence/2026-10-13-psx-design-round-3-source100/index.html`.
It compares `door_flush`, the flat `north_wall_smooth`, and the same smooth wall
with a texture crop from `data/scenes/corridor_travel/images/frame_0001.jpg`.
The frame is registered with the #100 source video; the texture is not sampled
from a Gaussian render. Crop coordinates are x=1550, y=320, width=370, height=380
pixels. The candidate preserves the smooth-wall stiles, selected flush hatch,
route, splat, and collision.

All candidates pass the 13.067 m route with 100% floor support and zero
SafetyNet contacts. Floor and boundary negative controls fail as expected.
The source-textured candidate sustains 60.0 capped FPS (p95 16.91 ms, p99
19.04 ms); the protected input hashes, including the source video, remain
unchanged. Control-repeat noise is at most 0.11%. ODiff reports 1.623% mean
change for the source-textured wall and 3.238% for the flat wall relative to
`door_flush`; these values locate changed pixels and do not rank visual quality.
Await operator judgment on wallpaper scale, color, and whether it restores the
Backrooms identity. #121 stays open for Gaussian-specific follow-up. At that
time #122 was deferred; Hunyuan evaluation #122-#126 was later completed, and
#151 now applies operator-led design iteration to the Hunyuan visual candidate.

An initial crop check mistakenly used the separate #107 coverage clip. Its
bundle, `godot_walk/evidence/2026-10-13-psx-design-round-3/`, is retained but
marked superseded and must not be used for the operator decision.

For the Hunyuan experiment, the #100 source is the original
`data/scenes/corridor_travel/video.mp4`; select a registered raw video frame.
Never substitute a Gaussian screenshot, PLY, or the separate #107/#104 video.
Any Hunyuan output is generated content, not a substitute for #104 or a claim
of splat recovery.

## References

- [HunyuanWorld 1.0](https://github.com/Tencent-Hunyuan/HunyuanWorld-1.0)
- [Image-to-panorama demo](https://github.com/Tencent-Hunyuan/HunyuanWorld-1.0/blob/main/demo_panogen.py)
- [Panorama-to-layered-mesh demo](https://github.com/Tencent-Hunyuan/HunyuanWorld-1.0/blob/main/demo_scenegen.py)
- [Godot 4.6 3D scene import formats](https://docs.godotengine.org/en/4.6/tutorials/assets_pipeline/importing_3d_scenes/available_formats.html)
- [ODiff](https://github.com/dmtrKovalenko/odiff)
- [Godot 4.6 command-line options](https://docs.godotengine.org/en/4.6/tutorials/editor/command_line_tutorial.html)
- [Godot 4.6 Movie Maker](https://docs.godotengine.org/en/4.6/tutorials/animation/creating_movies.html)
- [Godot physics introduction](https://docs.godotengine.org/en/stable/tutorials/physics/physics_introduction.html)
- [NVIDIA FLIP evaluator](https://github.com/NVlabs/flip)
- [Your Game Is A Harness](https://kylekukshtel.com/ai-harness-engineering-game-development-claude-code)
