# Issue 261: boundary treatment for open-world sources

## Problem and evidence

The room contract freeze records versioned validators and their hashes; v4 retains contract version 3.0.0 and identifies v3 as its ancestor (`godot_walk/room_catalog/contract_freeze_v4.json`). Its semantic validation uses finite orthogonal walkable and render polygons, render bounds, floor elevation, collision declarations and a spawn capsule inside the walkable polygon (`godot_walk/scripts/video_adaptation_semantics.py`). These are useful room checks, but a polygon describing the area for which there is evidence should not automatically assert that a physical wall exists at its edge.

The snow-garden v2 report describes the panorama as an unbounded park and its candidate as a bounded courtyard; it explicitly calls the wall ring and its details authored, not measured, and says scenery does not establish connectivity (`godot_walk/evidence/2026-11-17-issue-255-room-candidate/REPORT.md`, section 6). The report describes the candidate's state at report time. The later accepted record identifies the exact candidate as an accepted bounded standalone reference, with `registration_accepted` and `scale_calibrated` still false (`godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json`). Another accepted standalone room is recorded at `godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/adaptation_standalone_accepted_v1.json`. These records do not establish an open-world contract or make their authored dimensions observations.

The source library distinguishes operator room acceptance and catalog admission from automated work, and describes decision-record and event validation (`godot_walk/source_library/README.md`). An open-world variant should preserve those gates and existing room decisions, while explicitly separating observed obstacles, finite supported traversal, and unknown space. “Unbounded” here describes the source's unknown continuation, not a promise of infinite generated terrain or safe traversal everywhere.

## Options

Costs are relative design estimates, not measurements. Agent verification below means deterministic local checks on fixtures and records; visual and experiential judgments remain with the operator.

1. **No edge intervention.** Declare an open boundary and remove the wall ring; keep only supported ground and observed obstacles. Cost: low contract and scene work. Risk: a player can leave supported ground or fall; an absent edge is not evidence of continued terrain. An agent can check the declaration, absence of boundary collider entries, and spawn/support fixtures. The operator must assess the scene's appearance, traversal and acceptable failure behavior.
2. **Explicit nonphysical coverage boundary with a stop or return policy.** Record a finite support/coverage region and an unknown exterior separately from observed geometry. At its edge, stop movement or return the player with a clearly labeled coverage-limit indication, without drawing or claiming a wall. Cost: medium; requires a variant, runtime behavior, feedback and tests. Risk: an invisible stop can feel like an invented barrier; a return can disorient, and finite evidence may be mistaken for a measured world boundary. An agent can verify the boundary classification, deterministic crossing behavior, supported spawn, and no invented wall geometry in fixtures. The operator must decide whether the intervention and presentation are acceptable in the actual scene and whether the supported area is faithful to the source.
3. **Continue via authored or generated terrain.** Extend ground and scenery beyond observed coverage, marked as extrapolated, with transitions or streaming. Cost: high in authoring, evaluation and possible compute. Risk: invented geography or false continuity, inconsistent scale, and performance; a larger area does not establish source truth. An agent can validate provenance labels, transition behavior and resource budgets in fixtures; the operator must judge fidelity, continuity, and whether any generation or model expenditure is authorized.
4. **End the walk at a visible, explicitly labeled coverage edge.** Use a visual coverage-limit marker and stop before unsupported space, without representing it as source geometry. Cost: medium for presentation and interaction. Risk: disrupts immersion and still limits travel. An agent can verify that the marker and stop are classified as interface/coverage treatment, not observed collision, and test crossing. The operator must judge legibility, immersion and placement.

## Recommendation

Start with option 2 as an explicit contract distinction, leaving the stop versus return and its presentation for operator review. It keeps unknown continuation honest, makes the finite safe area testable, and does not require invented architecture or claim generated continuity. It does not resolve the experiential cost of a traversal limit. Do not retrofit the accepted snow-garden record or infer calibration from its acceptance (`godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json`).

### Ready-to-file first slice

**Title:** Define and validate an open-scene coverage boundary variant

**Scope:** Add a separately versioned open-scene contract and CPU-only synthetic fixtures. Specify a finite supported coverage footprint, a safe spawn, an explicitly unknown exterior, and separately classified observed obstacles. Specify that a coverage edge is not observed wall geometry. Preserve existing room-contract behavior and accepted records. Define a machine-readable traversal policy as `stop` or `return`, including its declared player-facing coverage indication; defer actual runtime behavior and selection between policies to a later operator-reviewed slice. No source scene retrofit, model run, or claim of calibrated scale is part of this slice.

**Acceptance:**

- A valid open-scene fixture with finite support and unknown exterior passes without a wall ring or boundary collider. It declares one of the two policies and an indication; it makes no assertion of safe ground outside coverage.
- Missing or contradictory exterior classification, unsupported spawn, unclassified boundary geometry, and absent policy or indication fail with actionable diagnostics. Observed obstacle declarations require provenance; the coverage edge cannot be represented as an observed obstacle without separate evidence.
- Existing room fixtures keep their current results; accepted records and frozen files remain untouched. The new variant cannot silently reinterpret the old room contract. Both calibration flags remain false in synthetic fixtures.
- Document how an operator reviews coverage and the eventual traversal intervention; validation alone cannot approve fidelity or admission.

**Verification:** Run the relevant CPU-only contract validator tests, including positive and negative synthetic fixtures and regression tests for the current room variant. Inspect the diff for unchanged accepted records and frozen files. Record exact commands and results. Operator review of real source coverage and later runtime behavior remains a separate gate.

## Unknowns not tested

- No actual traversal, edge stop, return, user-interface indication, falling behavior, or accessibility was tested.
- No coverage footprint, source geometry, obstacle provenance, metric scale, or registration was measured for an open-world video.
- No compatibility, migration, performance, or regression test was run for the proposed variant; it does not yet exist.
- No operator evaluated the proposed policies or approved a new scene or contract. The report's historical pending state and later accepted record refer to different points in time (`godot_walk/evidence/2026-11-17-issue-255-room-candidate/REPORT.md`; `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json`).
- No external tool or paper behavior was researched or verified; no model, GPU, download, or new capture was used.
