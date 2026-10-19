# Image-to-Panorama and Walkable Design Harness

**Status:** decomposed under Chainlink epic #116. Track B is the active first
track; Track A is deferred and blocked until the first Track B iteration round
is useful.

## Goal

Test whether a direct frame from the video that produced the current #100
Gaussian splat can seed a HunyuanWorld panorama and layered-mesh candidate,
import into Godot, and serve as an alternate visual source for the PSX
walkable-simulator workflow. In parallel, make room-design iteration
repeatable so variants can be compared and revised from operator feedback
until one is accepted.

HunyuanWorld 1.0 gets an extracted source-video frame, never a rendered Gaussian
screenshot or the Gaussian `.ply`. It documents image-to-panorama followed by
panorama-to-layered-mesh export. This is a generated scene candidate, not a
conversion of Gaussian embeddings and not recovered geometry. The design
harness starts with the existing Gaussian walkthrough as its baseline; both
source types can later use the same review loop.

## Protected Baseline

- Use the current `corridor_psx_room_v2.tscn` walkthrough as the starting
  experience and keep the #100 splat, `corridor_psx.tscn`, and #115 control
  unchanged.
- Use `data/scenes/corridor_travel/video.mp4` as the Hunyuan image source. The
  #100 alignment manifest names this video as the source for the walked splat;
  it is 1920x1080, 24 fps, 8 seconds, SHA-256
  `ac5cd0d1aa11aadd39cc45ff460af5e00372f8417d2514fce1bfa7c7837895c4` in the
  current checkout. Do not substitute the separate #107/#104 video at
  `data/scenes/backrooms_coverage_v1/video.mp4`.
- Keep the Gaussian walkthrough as the design-harness baseline, not as
  Hunyuan input. Record its scene commit and capture settings when generating
  variant comparisons.
- Keep downloaded model weights and bulky generated outputs outside tracked
  source. Commit only scripts/configuration/reports that are intentionally
  adopted. Do not overwrite production assets or current evidence.

## Parallel Tracks

### Track A: HunyuanWorld Image-to-Panorama to Godot

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

### Track B: PSX Design-Iteration Harness

This track starts immediately on the current Gaussian-splat walkthrough. The
Hunyuan panorama or imported GLB becomes another selectable source only after
Track A produces it.

**B0. Write the first-pass design brief**

Use the operator's current review as the initial brief: walking is smooth and
must stay that way; the room should feel intentionally composed and extendable;
doors and landmarks should feel integrated rather than arbitrary; splat
artifacts may remain when they read as intentional PSX texture, but obvious
broken faces and raw joins need a considered treatment. Keep this brief
editable and refine it from the operator's selections, not from an invented
numeric aesthetic score.

**B1. Make variants addressable**

1. Keep the current room scene as a read-only baseline. Move only the design
   knobs needed for experiments out of hardcoded construction code into a
   small versioned room specification loaded by a separate candidate scene.
2. Begin with a bounded schema for source type, room/transition layout,
   doorway policy, column-face treatment, splat-to-authored junction treatment,
   PSX material IDs, and collision extents. Every candidate gets a unique ID,
   parent baseline, seed (where relevant), and change summary.
3. Generate three intentionally different candidates per review round, each
   expressing a clear hypothesis. Change one major design idea at a time so
   operator feedback identifies what helped. Do not mutate the production
   scene or generate unbounded random rooms.

**B2. Make comparison repeatable**

1. Reuse the existing Godot capture and walk-verification scripts. Standardize
   viewport, 75-degree FOV, camera eye positions, headings, settle frames, and
   route. Capture the patch anchor, transition, column, and far-room views,
   plus the same deterministic walkthrough for every variant.
2. Run the `odiff` CLI on matching same-size screenshots. Save its diff image
   and per-view changed-pixel count/percentage alongside a contact sheet.
   First confirm repeat captures of the baseline are stable; if not, identify
   renderer/splat noise before setting any comparison thresholds.
3. Use ODiff to locate visual changes and catch accidental regressions, not to
   grade room quality, infer surface ownership, or automatically choose a
   winner. Its pixel comparison cannot decide whether a door feels motivated
   or a route feels like a place worth exploring.
4. Run mechanical checks before review: route support, boundary containment,
   floor/boundary negative controls, black/floater metrics, and capped/uncapped
   frame timing. Keep subjective judgments in a short review record.

**B3. Human-in-the-loop iteration**

1. Present the three candidates as matched contact sheets plus a runnable
   scene/command. Ask the operator to select, rank, or reject them and record
   specific notes such as "keep this transition," "remove the service door,"
   or "carry the column treatment forward."
2. Use those notes to create the next small batch, inheriting only selected
   traits. After each round, keep the best candidate as the new review parent;
   retain rejected variants and their evidence for comparison.
3. Run design-iteration rounds against the current Gaussian-backed walkable
   scene first. Once Track A passes its scene-import gate, add the generated
   Hunyuan scene as an alternate source and rerun the same camera bank, route,
   report, and review questions. This isolates source quality from design
   quality; the Gaussian scene is never fed to the panorama model.
4. Converge only when the operator explicitly approves a candidate and its
   walkability/performance checks pass. The harness organizes the search; it
   does not pretend a scalar image score captures the operator's idea of a
   walkable simulator.

## Shared Acceptance Gates

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
- **Design convergence:** operator approves the final variant after reviewing
  repeatable views and a live walk. Human review remains the visual acceptance
  gate; ODiff metrics are diagnostic evidence only.

## Research Prompt

Use this prompt for the advisory research task in Chainlink #118:

> Research practical techniques that complement a human-directed PSX room
> design-iteration harness for a walkable Godot 4.6 Backrooms simulator. The
> baseline is the current Gaussian-backed `corridor_psx_room_v2.tscn`, with
> manually authored PSX room extensions. The goal is a smooth, intentional,
> coherent, extensible walkable place. The proposed loop uses addressable room
> variants, deterministic route/camera captures, mechanical walkability and
> performance checks, ODiff for same-pose pixel-change diagnostics, and
> operator selection plus specific feedback. Track B starts from the Gaussian
> walkthrough; do not feed a Gaussian render or PLY to HunyuanWorld.
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
  does not, retain the panorama as an optional appearance reference and
  continue the PSX geometry workflow around the Gaussian patch.
- Single-view generated geometry can look plausible while failing under
  translation. Do not equate a successful 360 panorama or GLB import with a
  navigable space.
- If no useful mesh survives import/parallax checks, close the Hunyuan branch
  with its evidence and keep the Gaussian-backed harness as the main path.

## Chainlink Breakdown

- **#116, umbrella epic:** PSX design harness and source-video panorama
  experiment, under #101. Keep this distinct from #104 reconstruction
  acceptance and #115's existing room-v2 review.
- **#117, Track B epic (first):** establish the PSX design-iteration harness
  around the current Gaussian-backed walkthrough.
- **#118:** research complementary techniques. Advisory and non-blocking for
  the first implementation pass.
- **#119:** define the design brief and addressable room variants.
- **#120:** build deterministic capture and ODiff review bundles; blocked by
  #119.
- **#121 (in progress):** run Gaussian-backed design-iteration rounds after
  #120. Round 1 operator review selected the frame-aligned hatch and identified
  the right-hand wall and ceiling artifacts as remaining issues. Round 2
  carries the selected hatch forward and compares a smooth north-wall treatment
  with a lowered PSX ceiling grid around the same splat, route, and collision.
  Round 3 carries forward the smooth wall shape and compares its flat finish
  with a source-video wallpaper crop from the registered #100 input. Review
  mechanically passing candidates with the operator; continue from selected
  traits or reject all until a useful candidate is explicitly approved.
- **#122, Track A epic (deferred):** evaluate HunyuanWorld from the direct
  #100 source-video frame and import the result into Godot; blocked by #121.
- **#123:** preflight Hunyuan and select a registered source-video frame;
  blocked by #121.
- **#124:** generate and inspect panorama candidates; blocked by #123.
- **#125:** convert layered meshes and import a separate Godot candidate;
  blocked by #124.
- **#126:** evaluate alignment, parallax, and walkability in the harness;
  blocked by #125 and #121.

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
Backrooms identity. #121 stays open; #122 remains deferred.

An initial crop check mistakenly used the separate #107 coverage clip. Its
bundle, `godot_walk/evidence/2026-10-13-psx-design-round-3/`, is retained but
marked superseded and must not be used for the operator decision.

The #100 source for Track A is the original `data/scenes/corridor_travel/video.mp4`;
select a registered raw video frame. Never substitute a Gaussian screenshot,
PLY, or the separate #107/#104 video. Any Hunyuan output is a generated
alternative, not a substitute for #104 or a claim of splat recovery.

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
