# Issue 262: sky, horizon and parallax research

## Evidence and problem

The snow-garden v2 report describes a camera-centred 512×256 equirectangular panorama, a closed 20×16 design-unit courtyard, and no real horizon geometry or sky parallax. Its wall ring and positions are authored; the tree line and sky establish no connectivity or metric scale. The report also says its PSX shaders are unshaded and fog-disabled, so changing light energy does not shade the authored geometry. These are reported observations, not measurements made for this research. (`godot_walk/evidence/2026-11-17-issue-255-room-candidate/REPORT.md`, sections 2, 3 and 6.)

The report records the candidate as pending at report time; a separate later artifact records v2 as `accepted_reference`, with `registration_accepted` and `scale_calibrated` false. Standalone reference acceptance does not itself establish catalog admission or measured registration. (`godot_walk/evidence/2026-11-17-issue-255-room-candidate/REPORT.md`, sections 6–7; `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json`.) The accepted slot-canyon reference likewise describes a bounded outdoor stand-in, with both flags false and no inferred metric scale (`godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/adaptation_standalone_accepted_v1.json`). These are examples, not evidence that all open-world sources have the same horizon.

The v3 freeze pins contract and implementation artifacts and records both calibration flags as false (`godot_walk/room_catalog/contract_freeze_v3.json`). The source library describes immutable manifest versions, source-local room outputs, and operator review and catalog admission gates (`godot_walk/source_library/README.md`). A visual experiment should therefore be a separate, explicitly authored candidate; it must not imply a change to the frozen contract, the accepted references, physical scale, or a navigable destination.

## Options

Costs below are relative estimates, not benchmarks. Agent checks are mechanical evidence; operator review is needed for visual and source-fidelity judgments.

1. **Keep the panorama and add a finite authored horizon ring.** Place simple silhouette meshes at fixed world positions beyond the playable boundary, leaving the sky background in place. Camera translation should change their projected position relative to the sky. Cost: low to moderate authoring and testing. Risk: repeated silhouettes, visible seams, clipping or an apparent destination; depth and shapes are invented. An agent can inspect scene structure, bounds and collision settings and compare repeatable camera positions; the operator must judge whether movement, composition and source resemblance are convincing.
2. **Layer several authored horizon planes or curved bands at different depths.** Separate foreground trees, distant terrain and sky into independently placed layers. Cost: moderate: layer authoring, sorting and capture setup. Risk: edges, transparency artifacts, inconsistent occlusion and exaggerated depth; layers may incorrectly suggest observed geometry. An agent can verify placements, resource references and repeatable camera tests; the operator must judge depth, artifacts and fidelity from moving and still views. Engine-specific rendering behavior is unverified here.
3. **Reconstruct distant scene geometry from additional source views.** Build a spatial backdrop from source evidence, retaining an authored fallback for unseen areas. Cost: high and uncertain, including source review, reconstruction and validation; any model or GPU work needs separate operator authorization. Risk: sparse coverage, invented or unstable geometry and false scale or registration claims. An agent can check provenance, artifacts and reproducible mechanical tests once inputs and authorization exist; only the operator can assess visual fidelity and approve use. The suitability and performance of any reconstruction method are unverified here.

## Recommendation

Start with option 1 in an isolated, non-colliding test scene. It provides an observable depth cue with a small, reversible authored surface area and no reconstruction or model dependency. It retains the panorama for the far sky while making the limitation explicit: a finite silhouette is an interpretation, not recovered terrain. Option 2 is a follow-up only if a single ring cannot produce acceptable depth without artifacts; option 3 needs separately reviewed evidence and resources.

### Ready-to-file first slice

**Title:** Prototype a finite, authored horizon for an open-world reference

**Scope:** Create a new standalone experimental scene and evidence outside existing accepted room folders and pinned files. Use the snow-garden reference as visual context (`godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json`). Retain a static sky background and add a small fixed-world silhouette ring, labeled authored and visual-only. Do not add traversal, sockets, inferred scale or registration, change the source reference, modify the contract/catalog, or run models. Preserve `registration_accepted=false` and `scale_calibrated=false` in any experiment metadata. Do not claim source fidelity or approval based on a test pass.

**Acceptance:** The standalone experiment has finite world-fixed horizon geometry, no horizon collision or implied route, a documented bounded camera path, and a baseline with the ring disabled. Record geometry placement and authorship, source references, limitations and both false flags. Provide comparable views at two separated camera positions with the same orientation, plus an in-place rotation view; the finite horizon should shift relative to the background under translation while the baseline has no finite horizon. Record any seams, clipping or occlusion failures. No accepted artifact or pinned file changes. Operator review decides whether the effect and source interpretation are acceptable; no automatic admission or acceptance follows.

**Verification:** Run available scene/resource and collision checks and a deterministic headless test of fixed geometry, camera positions and disabled baseline. Under a separately authorized rendering environment, capture the paired views and a short movement sequence with recorded camera transforms and settings; inspect them and request operator judgment. If rendering is unavailable, report that limitation and leave visual acceptance pending. Compare the working-tree changes against the allowed new experiment files and verify the existing freeze and accepted references remain unchanged.

## Unknowns not tested

- No scene was built or run for this research; parallax magnitude, ring distance, camera path, clipping, collision behavior, seams, transparency and performance are unknown.
- No captures or moving views were produced or visually reviewed; neither source fidelity nor operator acceptance of any option is established.
- No source video coverage, recoverable horizon depth, metric scale, registration or destination was measured.
- No reconstruction tools, algorithms, engine APIs, GPU workloads, model calls or downloads were evaluated; feasibility and costs are estimates.
- Compatibility of a future experiment with the frozen validator and any eventual open-world contract remains to be tested; no contract migration is proposed here.
