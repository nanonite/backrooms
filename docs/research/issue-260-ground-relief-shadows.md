# Issue 260: Ground relief and shadows for open-world inputs

## Evidence and problem

The snow-garden v2 is a bounded, authored 20 × 16 courtyard, not a reconstructed open world. Its ten decorative drift specifications become flattened spheres above a flat visual floor and box collider; tree trunks have separate colliders ([room.gd](../../godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/room.gd)). The #255 comparison describes simple ellipsoids with no real shadows, a panorama with a more realistic park, and unshaded, fog-disabled project shaders whose authored geometry does not respond to the scene's dynamic lights; drift layout and scale are authored, not measured ([report, sections 5–6](../../godot_walk/evidence/2026-11-17-issue-255-room-candidate/REPORT.md)). The issue identifies drift shading and long tree shadows in the panorama as the visual target; their direction and physical accuracy have not been measured here.

The report's pending-review status is historical: the later [operator review](../../godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/operator_review.json) accepts that exact candidate as a bounded standalone room, not catalog admission, connectivity, registration or metric scale. Its [accepted reference](../../godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json) binds contract v3 and leaves `registration_accepted` and `scale_calibrated` false; the [v4 freeze](../../godot_walk/room_catalog/contract_freeze_v4.json) also records both flags false. The [source-library README](../../godot_walk/source_library/README.md) describes separate operator approval and catalog admission, immutable candidate/decision linkage, and ledger requirements. A new open-world experiment must not silently modify or inherit approval for this accepted room.

## Options

Costs and risks below are estimates, not benchmarks. Agent verification means checks feasible without model runs or a GPU; visual approval belongs to the operator.

| Option | Change | Estimated cost and risk | Agent can verify | Operator must judge |
| --- | --- | --- | --- | --- |
| Authored relief and shadow shapes | Create a separate small terrain mesh with irregular, shallow drifts and authored dark polygons or texture regions aligned with tree positions and a chosen light direction. Keep an explicitly declared, simple collision surface initially. | Low–medium authoring and testing cost. Shadows are static and may look detached; visual terrain and collision can disagree. Authored forms must not be presented as measured reconstruction. | Mesh bounds, deterministic geometry, shadow direction and placement, collision policy, fixture provenance and regression checks. | Whether relief and shadows read naturally against the reference and whether visual/collision mismatch is acceptable. |
| Lit terrain with cast shadows | Use a separately authored relief mesh and lighting-responsive materials, with a directional light and tree shadow casters in an isolated scene. | Medium–high integration and rendering cost; changing the material approach may conflict with the established unshaded look, and shadow quality/performance are unknown. Engine rendering capabilities and settings are unverified here. | Scene configuration, geometry/collision and deterministic structural tests; render results only where a supported renderer is available. | Visual quality, coherence with the style, shadow artifacts and acceptable performance on target hardware. |
| Video-derived terrain and lighting | Investigate recovering terrain and illumination from multiple source views, retaining confidence and provenance, then generate geometry and shadows from the result. | High research, compute and review cost; snow texture, occlusion, camera motion and baked illumination may make the reconstruction ambiguous. Tool/model capabilities are unverified; no particular pipeline is assumed viable. | Input/provenance checks and validation of any supplied outputs; no inference or accuracy claim without a real run and reference. | Authorize any model/GPU spend and judge reconstruction fidelity, uncertainty and whether it is useful. |

## Recommendation

Start with an isolated authored-relief fixture and static shadow shapes. It directly tests the two visual gaps while keeping the current unshaded material approach and avoiding a dependency on inferred geometry or lighting. It is a visual approximation, not source registration, physical illumination, or a general open-world solution. The outcome should inform the separate open-world contract before a production pipeline is chosen.

### Ready-to-file first slice

**Title:** Prototype authored ground relief and tree shadows in an isolated open-world fixture

**Scope:** Build one small, deterministic, standalone test fixture outside the accepted room and frozen catalog. Use a shallow irregular terrain surface and static tree-shadow shapes with one documented assumed direction. Use local authored data only; record provenance and the intended collision policy. Do not change existing accepted or hash-pinned files, flags, or catalog decisions. No model, GPU run, download, or external service is part of this slice.

**Acceptance:**

1. The fixture visibly contains more varied relief than flattened ellipsoids and long tree shadows that originate at their corresponding trees and share the documented direction. Treat both as authored approximations.
2. State explicitly whether collision follows the relief or stays flat, and bound the visible-to-collision height difference so traversal implications are reviewable. Do not imply measured scale.
3. Provide reproducible local fixture generation or scene data and checks for deterministic bounds, shadow/tree pairing, common direction, collision policy, and absence of edits to accepted assets. Preserve `registration_accepted=false` and `scale_calibrated=false`.
4. Supply a comparison plan using named, repeatable viewpoints and request operator review of the visual result. A structural test alone cannot approve appearance or catalog admission.

**Verification:** Run relevant CPU-only structural tests and document commands and results. If a supported rendering environment is available under its own authorization, capture matching views and report actual conditions and outcomes; otherwise explicitly leave rendering and visual review outstanding. Operator compares the reference and fixture for drift shape, shadow continuity/direction, style, and traversal plausibility. Any later lit or reconstructed approach requires its own design and authorization.

## Unknowns not tested

- Actual panorama shadow direction, length, softness, ground elevations, and whether visual shading corresponds to geometry.
- Generalization to other open-world videos, including changing light, moving objects, snowless terrain, and weak camera coverage.
- Terrain mesh resolution, collision tolerances, character traversal, and visual-to-collision mismatch acceptable to the operator.
- Whether the target Godot renderer, project material setup, and target hardware can produce suitable dynamic shadows at acceptable cost; no render, GPU or performance test was run for this research.
- Feasibility, accuracy, compute cost, licensing or availability of any external reconstruction or lighting tool; all such tool capability claims would be unverified absent local evidence.
- An open-world contract, admission criteria, and permission for future model or GPU work; this document grants none.
