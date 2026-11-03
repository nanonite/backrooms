# Video -> Walkable Backrooms

**Long-term target:** a first-person Godot Backrooms simulator assembled from a growing library of individually tested, PSX-ready rooms. Source videos inform visual content and layout; collision remains explicit, validated geometry. A seeded room graph and later bounded streaming extend the walk while preserving backtracking.

## Current Execution Context

Operator direction on 2026-10-21 selects **Godot as the active runtime**. The Bevy implementation and its historical validation remain preserved but deferred. Earlier Bevy-specific milestones and issue descriptions below are historical context, not instructions to switch engines. First complete and approve PSX treatment on two independent Godot rooms, then validate their connection before seeded generation. Keep `data/scenes/corridor_travel/` and the #100 scene protected. Current Chainlink #104 is **Capture and reconstruct a fully covered synthetic Backrooms walkthrough**, not the former BE-4 alignment task.

## Working Milestone: Video To Walkable

`milestone/video-to-walkable-working` points to commit `d785651` and is merged into local `main`. It is the first operator-played Bevy walkthrough from the #100 source: a run-05 Hunyuan GLB supplies visuals only, while the exact #135 authored collision GLB supplies the floor, column proxy, and edge boundaries. The shared player controller moves the player around the authored loop. The evidence and launch command are documented in `splat_walk/README.md` and `godot_walk/evidence/2026-10-13-hunyuan-track-a/`.

This is a working, uncalibrated playable zone, not a metric reconstruction of the whole source video. The route is deliberately authored. Hunyuan geometry does not provide collision. `registration_accepted=false` and `scale_calibrated=false` remain locked. The tag is the baseline for extending the simulator, not a claim that room discovery, module stitching, or procedural generation is done.

## Roadmap: Room Library To Generator

1. **Inventory the footage.** Map the rooms, corridors, columns, doorways, and transitions that the #100 source actually shows. Record frame ranges, camera coverage, visible openings, and unknown areas. Propose a 2D layout with evidence-backed and authored parts distinguished. #145 is now approved and closed as an inventory only; room count, connectivity, and scale remain unknown.
2. **Define a room module.** Give each module a stable ID, source-video/frame provenance, visual asset, separate collision asset, coordinate/scale status, connector sockets, exposed-boundary rules, playability report, and resource measurements. Register the tagged walkthrough as an uncalibrated reference zone, not a surveyed full room. Keep source-observed openings distinct from authored connector sockets and traversal-tested connectors.
3. **Build rooms one at a time.** Select a room from the reviewed inventory. Create its visual candidate and explicit collision route. Run it standalone in Bevy with the shared fixed-step controller, boundary and obstacle controls, and operator visual review. Do not add a module to the catalog before it passes. #150 is accepted as a playable later-bay design baseline: the core source perspective is useful, while the room shell and collision are authored and need not precisely reconstruct the video. The column far side remains room-specific art polish, not a video-pipeline blocker.
4. **Stitch verified modules.** Place at least two approved rooms through compatible connectors. Test doorway clearance, floor-height transitions, collision seams, continuous traversal, and exposed edges. Reject a layout if a room works alone but its connector does not. #150's operator review is complete. In #148, catalog it as an uncalibrated standalone candidate and evaluate an explicitly authored connector to the tagged reference zone; #145 does not establish that the zones connect. Do not describe an authored connection as video evidence.
5. **Generate layouts.** Once the catalog contains multiple validated modules, generate a deterministic 2D grid or room graph from compatible connectors. Use a seed and explicit topology constraints for loops, dead ends, reachability, and exits. The generator places approved modules; it does not invent untested collision.

Track A (#144) owns room inventory, module contracts, standalone Bevy validation, stitching, and layout generation. Track B (#117) continues the human-directed PSX visual/design loop in parallel. Track B can inform the visual grammar and transitions, but it is not a gate for Track A. WorldMirror is optional research, not a prerequisite for a playable room library.

## Current Chainlink Build Order

| Issue | Current goal | State / dependency |
|-------|--------------|-------------------|
| #78 | Deliver a reproducible video-to-walkable-scene pipeline | Parent epic |
| #101 | Verify the synthetic Backrooms PoC as a PSX-scale walking simulator | Open; #116 now carries the room-library and design-iteration direction |
| #116 | Backrooms room library, design iteration, and layout generation | Open umbrella; starts from `milestone/video-to-walkable-working` |
| #111 | Audit committed Backrooms artifacts for unnecessary binaries | Open; inventory and reference-check before any cleanup; user design work is out of scope |
| #117 | Track B: establish the Hunyuan-to-PSX room-completion workflow | Open; #167/#168 prove bounded ingestion and a two-room source adaptation; #169 adds an admitted standalone Bill Viola room but has not proven the model worker/reviewer or integration-suggestion loop |
| #121 | Continue Gaussian-backed PSX design iterations as a reference | Open; preserves the #100/#115 feedback history, not a Hunyuan prerequisite |
| #151 | Build the Hunyuan-to-PSX room-completion workflow | Closed; structured workflow examples and supervised transfer are preserved; SkillOpt remains deferred |
| #153 | Assess PSX Retro Tools against the native Godot workflow | Assessment complete; current Godot materials and compositor cover demonstrated needs; no code port or new plugin justified |
| #154 | Build a focused PSX rendering plugin for the Bevy walkthrough | Deferred; revisit only if the Godot workflow demonstrates a missing render effect |
| #163 | Build another PSX-ready room from a distinct source video | Closed through the accepted #164 module; source-textured authored baseline accepted, Hunyuan produced no panorama, calibration remains false |
| #164 | Package the accepted third room and connect a three-room Godot walkthrough | Closed after operator accepted the playable three-room assembly |
| #165 | Prove a video-adaptive Godot PSX room workflow with a reusable spatial contract | Closed after the corridor transfer and validation contract were accepted; supervised pilot only |
| #166 | Connect the accepted #165 corridor to the #164 three-room layout | Closed after operator accepted the exact four-room comparison; new adapters remain outside the shared catalog |
| #167 | Create a per-video room library and bounded Hunyuan-first ingestion loop | Completed; bounded Hunyuan-first pilot produced the operator-accepted industrial hall, source-scoped catalog records, guards, receipts, and append-only history |
| #168 | Build and stitch multiple room modules from one source video | Closed after the operator accepted a second playable room and its explicitly authored two-room connection; no source-video connectivity inferred |
| #169 | Automate video seed selection, PSX room review, and module integration proposals | Open under #117; Bill Viola manual room accepted and cataloged as standalone-only; worker/reviewer automation and integration suggestions remain unproven |
| #152 | Evaluate SkillOpt for the PSX workflow skill | Deferred under #117 until enough operator-confirmed examples exist for evaluation |
| #157 | Establish a shared Backrooms material and transition language across modules | Active under #144; 4× pocket floor retained; operator rejected the ceiling bridge and it remains off; wall materials already share texture and 4× UV scale, so next repair must target geometry/coverage |
| #161 | Compare affine texture mapping profiles for the Godot PSX rooms | Operator selected affine-off after live review; project default updated and default render matches the accepted capture |
| #156 | Stream connected Backrooms modules for effectively endless walking | Closed at the operator-accepted finite bounded-streaming milestone; general expansion deferred to #162 |
| #162 | Scale seeded room streaming after the approved room library and workflow mature | Deferred low priority under #144; blocked by #151, #155, and #149 until workflow and room catalog are ready |
| #144 | Track A: build a verified room catalog and modular Bevy scenes | Open; children #145-#149; #150 is a follow-up under #147 |
| #145 | Inventory #100 source footage and propose a room plan | Closed after operator approval as inventory only; room count, connectivity, and scale remain unknown |
| #146 | Define the validated Bevy room-module contract | Complete; versioned catalog, file/hash/connector/calibration validator, and tagged walkthrough reference entry |
| #147 | Build and validate the first additional room module | Closed as the accepted iteration baseline; remains uncalibrated |
| #150 | Accept the later-bay walkthrough as a playable design baseline | Closed after operator acceptance; core perspective accepted, authored shell is intentionally approximate, column far side remains non-blocking art polish; not yet catalog-admitted |
| #148 | Stitch verified room modules through tested connectors | Active; #150 admitted and both candidates pass standalone checks, but their shared later-bay convention overlaps and #145 leaves connectivity unknown; connector withheld pending operator direction |
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

The proposal in `PLAN_IMAGE_TO_PANORAMA_DESIGN_HARNESS.md` is decomposed under #116. Hunyuan evaluation #122-#126 is complete using a registered frame directly from the #100 source video; it produced useful but uncalibrated visual output. Track B #117 now focuses on completing Hunyuan candidates as PSX-style walkable rooms. The accepted Bevy walkthrough is a gameplay-feel reference, not a geometry authority. Keep #121's Gaussian-backed rounds as separate, useful design history; they are not an input to Hunyuan or a prerequisite for #151. Treat replay as measured repeatability, not guaranteed determinism; use visual metrics as diagnostics, not provenance or unvalidated pass/fail gates. #151 must log provenance, authored changes, mechanical/render evidence, and operator decisions in structured round records. Defer SkillOpt to #152 until there are at least five operator-confirmed rounds and 30 labeled decision items, split by round; if the evidence is insufficient, continue collecting it. Every Hunyuan candidate must start from a direct frame of its original source video, never a Gaussian or rendered image; record the source and keep registration/scale claims separate. This does not change #104's reconstruction criteria or replace the protected #115 baseline.

### Track B Authoring Path (Updated 2026-10-24)

The live deliverable is PSX-ready Godot room modules. The accepted four-sided column remains the first room's visual repair; the surrounding room still needs its PSX readiness review. Blender PSX Retro Tools by Fawkek is optional offline asset preparation, not a Godot runtime dependency. Its installed license permits game assets but prohibits copying or adapting its code. Use the public feature descriptions only to assess a Godot-native separation of geometry/texture preparation, per-material filtering, and the existing pixelation/color-quantization/dither compositor. Do not enable vertex wobble or snapping without a demonstrated visual need and a separate operator-reviewed candidate.

The #153 assessment is complete: existing Godot-native materials and the PSX compositor cover the demonstrated needs, so no Blender code port or new plugin is justified. The authored, source-textured #163 room is an accepted baseline; Hunyuan did not produce a panorama for it. #165/#166 demonstrated a supervised transfer and connection to the accepted three-room layout. #167 established the per-video source library and bounded Hunyuan-first path; its low-resolution panorama was accepted as a broad layout reference, and its authored industrial hall was cataloged. #168 added a second playable room from that same GoPro source and an operator-accepted authored connection. These results prove a useful supervised ingestion workflow, not unattended or universal ingestion. #169's manually authored Bill Viola room is visually accepted and admitted in catalog v0.5.0 as a standalone module. It has no sockets, is not eligible for automatic layout generation, and has no tested connection to other rooms. The operator stopped further free-model calls; the manual fallback does not prove model seed selection or worker/reviewer automation. Keep calibration and registration false. Defer #154 unless a specific rendering gap appears, and keep SkillOpt #152 deferred until enough confirmed workflow examples exist.

#### Per-video source library and worker-assisted ingestion (#167)

Use `data/videos/` as the current local intake folder. Put the central index at `godot_walk/source_library/index.json` and source records under `godot_walk/source_library/sources/<source_id>/`, with frames, Hunyuan attempts, and room adaptations grouped beneath each record. Keep the exact input path and SHA-256 in its source manifest. The newly supplied videos are ignored local assets: do not stage, commit, move, or rewrite them during inventory. Register existing #163 `room_large.mp4` and #165 `corridor_corner.mp4` by canonical path/hash without rewriting their historical decisions. One source may yield zero, one, or several separately versioned rooms; each room retains authored geometry/material/collision provenance, validation evidence, and its own operator decision.

Automate repeatable work as resumable, source-scoped stages that workers can execute independently. A worker receives one source manifest, a unique run ID, and a constrained output folder; it validates hashes, refuses overwrites, appends stage receipts, and cannot modify protected assets or another source's workspace. CPU-only inventory/extraction can run in parallel across sources. Hunyuan inference and GPU capture must serialize through an exclusive job lock and the existing GPU/RAM guard. Workers may prepare candidates and run objective checks, but must pause for operator decisions at source suitability/seed selection, after each Hunyuan result, before manual fallback, at final visual review, and before catalog admission. Workers do not decide taste, select winners, or promote rooms.

For each suitable source, try the local Hunyuan image-to-panorama path first using a seed frame decoded directly from that source video. Run the guard and a bounded timeout before every inference. The proposed pilot cap is three invocations per source total: one initial attempt plus at most two operator-feedback revisions. Seed, resolution, prompt, and setting changes count toward the same cap. Stop earlier if two consecutive outputs receive operator feedback of no improvement, a repeated failure has no plausible next step, or preflight blocks. A guard block is a recorded stop, not permission to bypass the guard or silently proceed to manual art. Each attempt keeps its exact configuration, resource receipt, output hash/status, and feedback; there is no automatic retry loop.

After the cap or a blocked/unavailable run, present the evidence and wait for the operator to reject the source or choose a clearly labeled manual fallback. Any budget increase requires explicit approval before another inference. Preserve `registration_accepted=false` and `scale_calibrated=false`; Hunyuan output remains visual input, while room geometry and collision are explicit authored work. Catalog admission, source-video connectivity, and connector approval remain separate decisions. This is a supervised worker-assisted pilot, not unattended ingestion.

#### Multiple room modules from one source (#168)

The accepted GoPro source `video-ccf9722164a0bdc8` now has two separately authored and reviewed playable rooms: the industrial hall based on direct-source frame 1097 and the debris/window room based on frame 4560 (index 4559, PTS 151.966667 s, SHA-256 `7a2b3dd1b43478fa491447731c06b0f36fce71e2b80cbb089d3744cb02abcd0f`). The latter used accepted Hunyuan attempt-006 as visual reference; both rooms use explicitly authored geometry and collision. The operator accepted the two-room authored connection and walkable assembly. It is a game-design connection only; the source footage does not establish connectivity. Their source-scoped adaptation and connector records are in catalog v0.4.0's `source_video_adaptations`, separate from generic layout-generation inputs. The report and review bundle are `godot_walk/evidence/2026-11-02-issue-168-two-room/REPORT.md` and `index.html`.

#### Model-assisted ingestion and design iteration (#169)

Use the existing `chainlink-loop` CLI from the OpenCode Chainlink loop plugin as the worker/reviewer orchestrator; the plugin already runs bounded one-shot OpenCode sessions and feeds reviewer findings back to the worker. Keep project changes, prompts, structured observations, decisions, and artifacts in this repository. Do not modify the plugin repository as part of the initial workflow. For each source, sample candidate frames directly from the video, rank technical quality and temporal diversity, and have a configured vision-capable model select or abstain with frame-indexed rationale. Produce a compact room brief that separates visible evidence, proposed PSX design, and unknown/occluded areas. Hunyuan remains the first panorama path when suitable, under the source-specific attempt cap and existing GPU guard.

After a candidate is playable, the reviewer compares direct-source frames, any accepted panorama, and matched Godot captures. It returns structured, actionable feedback with evidence paths and uncertainty; the next worker iteration receives that feedback. Mechanical validation remains blocking and separate from visual review. The loop is capped and logs model/provider, version, prompt, response, usage/cost, edits, checks, and operator interventions. The operator has prohibited further free-model calls; no free model may be invoked. Model calls are disabled by default and require an explicit operator-selected provider/model. Any paid call also requires an enforceable per-run cost ceiling and reliable usage accounting. A local/manual path must remain usable without model calls. Model output never promotes or accepts a room. Use `chainlink-loop --no-close`; issue closure and catalog admission remain operator actions. SkillOpt #152 can consume the confirmed workflow logs later, after enough examples exist.

The first free vision smoke check is recorded in `godot_walk/evidence/2026-11-02-issue-169-model-smoke/`. The model described one source frame with visible/uncertain fields. An 11-tile contact-sheet ranking timed out after 120 seconds, while a separate three-frame comparison selected the already accepted frame 4560 at confidence 2/5 and called the differences minimal. This supports testing small candidate groups and low-confidence abstention; it does not prove general seed ranking. No Hunyuan inference ran.

The first CPU seed-review runner validates direct-frame hashes, produces mechanical measurements, supports dry-run and append-only replay/live receipts, and invokes an OpenCode model only when explicitly enabled. Historical free-model replays showed unstable confidence and provider quota/timeout failures; these receipts remain for reference, but the operator has since prohibited further free-model calls. No further model calls are authorized by default. At that point the runner slice had 53 passing tests and the full Python suite had 212 passing tests. Those checks were instrumentation and regression evidence only: they did not authorize Hunyuan or create a room. Newly registered sources still require operator suitability decisions. #169 remains open; see `godot_walk/evidence/2026-11-02-issue-169-model-smoke/REPORT.md` for historical receipts and commands.

Bill Viola's `The Sleep of Reason` is the current #169 fixture. The operator directed use of the direct-source frame at 91.0 s (frame index 2730, `frame_2731.png`) and then instructed that no further free models be tried. Two earlier free vision calls returned HTTP 429 without a selection. One guarded Hunyuan attempt produced a 512×256 panorama, but it depicts a bright glass-walled space and omits the dresser-centered source composition; it is retained as a rejected visual match. A manually authored, bounded Godot room uses direct-source crops and was visually accepted by the operator. Its dimensions and unseen boundaries are authored assumptions. The room is admitted in catalog v0.5.0 as a source-scoped standalone module with no sockets, no tested connectors, and `layout_eligible=false`; it does not alter the original visual decision or imply source connectivity. Runtime checks and guarded captures passed. This fallback delivers a playable adaptation example but does not prove automated model seed selection or worker/reviewer iteration; #169 remains open. See `godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/REPORT.md`, its `index.html` review bundle, and the room's `CATALOG_ADMISSION.md` for provenance and scope.

The automated workflow in #169 should admit a standalone room when its candidate passes mechanical validation and receives operator approval, even when the source does not show a traversable opening. Such a module remains outside automatic layout generation unless it has validated authored sockets. After admission, the workflow should produce zero or more integration proposals against exact catalog module versions. Each proposal should name the target modules, candidate placement, compatible sockets or required authored adapter, clearance and collision work, uncertainty, and supporting evidence. A valid outcome is to keep the module standalone. Proposals must not claim source-video connectivity, open boundaries, or tested traversal; authored adapters require a new version and separate runtime and operator review. Log the proposal and operator disposition for later SkillOpt data.

Track B #121 preserves the Gaussian-backed design loop as a reference. Round 1 selected the frame-aligned
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
`godot_walk/evidence/2026-10-14-psx-design-round-4-final/index.html`; #121
remains open for Gaussian-specific follow-up. This round was created while
#122 was deferred; Hunyuan evaluation #122-#126 has since completed, with #151
now responsible for room completion from the Hunyuan visual input. An earlier
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
trim, so it is not selected as a fix. Keep #121's matched views and live walk
as operator-reviewed Gaussian design evidence; the next implementation loop is
the Hunyuan-to-PSX workflow in #151.

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
