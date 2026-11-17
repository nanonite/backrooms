# Issue 263: lighting open-world PSX adaptations

## Problem and evidence

The snow-garden v2 report describes a bounded, authored courtyard, with dusk baked into albedo because its PSX shaders are unshaded and fog-disabled; dynamic light settings therefore do not shade the authored geometry. It also identifies flat canopy crops and snow drifts without real shadows. Its six views are evidence of a candidate, not proof of video scale or connectivity. At report time the candidate was pending review. (`godot_walk/evidence/2026-11-17-issue-255-room-candidate/REPORT.md`, sections 5–6.)

The later standalone record identifies snow-garden v2 as `accepted_reference`, but `candidate_not_admitted`, and repeats the shader limitation; it keeps `registration_accepted` and `scale_calibrated` false. Its warm key and cool fill do not establish that lighting shades these materials. The record lists the room scene and both library shaders among hashed dependencies. (`godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json`.) The report's pending state and the later accepted-reference record describe different stages, not catalog admission.

Both `godot_walk/shaders/library_psx_vertex.gdshader` and `godot_walk/shaders/library_psx_textured.gdshader` define `UNSHADED` and `FOG_DISABLED`; `godot_walk/vendor/ursc/common.gdshaderinc` maps those definitions to render modes and supplies the albedo paths. The frozen v3 contract manifest pins contract, schema, compatibility and catalog snapshot files by hash (`godot_walk/room_catalog/contract_freeze_v3.json`). The source library specifies immutable intake snapshots, append-only events, operator room acceptance and catalog admission, and versioned successors (`godot_walk/source_library/README.md`). A lighting experiment must not silently rewrite those records or the accepted room and its dependencies.

## Options

Costs are qualitative estimates for a bounded prototype, not measured timings. Agent verification below means CPU/static checks and any available non-GPU validation; final visual judgments need the operator on suitable hardware. Godot rendering behavior beyond the local shader evidence is unverified.

| Option | Change | Cost and risk | Agent can verify | Operator must verify |
| --- | --- | --- | --- | --- |
| 1. Retain authored albedo | Record baked lighting as an explicit adaptation limitation and author separate palettes for each lighting condition. Keep existing materials. | Low engineering cost; repeated art work, inconsistent illumination, no responsive shadows or time-of-day. Recoloring may remove source cues. | Check proposed metadata, provenance and unchanged hashes; compare authored palette values. | Judge source resemblance, readability and whether fixed dusk is acceptable in movement. |
| 2. Opt-in lit PSX material variants | Create separate vertex-color and textured shader variants and an isolated test scene; explore removing `UNSHADED` while retaining the PSX path. Treat fog as a separate, explicitly controlled choice. Do not alter the accepted shaders or room. | Medium cost; lighting may wash out the existing palette, affect transparency or double-sided surfaces, or change the PSX appearance. Engine-specific lighting and fog behavior is unverified. | Inspect variant isolation and parameters; run available import/validation tests and check frozen hashes. | Compare fixed views and motion with lights on/off, textured and solid materials, shadows, and performance on the target renderer. |
| 3. Author a separate stylized illumination layer | Prototype a controllable directional tint or quantized shading term in new materials, independently of engine lights; leave baked palettes as the baseline. | Medium to high cost; custom shading can misrepresent light direction, ignore occlusion or double-tint already baked colors. Shader math and renderer compatibility are unverified. | Check configuration bounds, shader resource isolation and deterministic inputs; validate imports where possible. | Judge whether the stylization and loss of physical cues are acceptable across views and lighting conditions. |
| 4. New baked lighting assets | Produce separate, versioned room/material assets with light and shadow information baked for each intended environment; retain the accepted reference. | High authoring and storage cost; light changes require rebaking and source captures may already contain illumination. Tool support and bake quality are unverified. | Check asset provenance, references, reproducibility records and hashes. | Assess baked shadows, seams, source fidelity and traversal appearance. |

## Recommendation

Start with option 2 in a disposable, opt-in fixture. It tests whether controllable light can coexist with the existing PSX treatment while preserving the accepted reference as a baseline. Test solid and textured paths separately: success on one does not prove the other. Keep fog independent so a lighting comparison does not change two variables at once. Option 1 remains the fallback if the operator prefers the existing appearance; do not infer approval from a mechanical pass. The relative visual and performance outcomes remain unverified.

### Ready-to-file first slice

**Title:** Prototype opt-in lit PSX materials in an isolated open-world fixture

**Scope:** Add separate experimental solid-color and textured PSX material variants and a small standalone fixture with representative surfaces and a controllable light. Preserve the current fog setting for the initial comparison. Include a baseline using the current unshaded materials and document exact camera, light and material settings. Do not modify the accepted room, existing shader dependencies, frozen contracts, catalog or source records; do not change calibration or registration flags. This slice does not implement a day/night cycle, source relighting, catalog admission or a production migration.

**Acceptance:** Both material paths can be selected independently in the fixture; the baseline remains available. The fixture exposes a repeatable light-on/light-off comparison and records whether geometry visibly responds, without claiming success in advance. Document shader choices, limitations, and any material or rendering regressions. Verify existing pinned files remain byte-identical. Keep operator visual approval separate from technical checks; no inference of scale, registration or scene connectivity.

**Verification:** Run relevant project import and validation tests available without a GPU, record commands and results, and compare hashes of affected frozen and accepted dependencies before and after. On operator-approved hardware, capture matched baseline and variant views with identical camera and settings, then compare light-on/light-off behavior, solid and textured surfaces, transparency, double-sided geometry, shadows, PSX character and performance. Record renderer, settings, observations and operator decision; failures remain open findings. GPU capture requires the existing guard and exclusive lock (`godot_walk/source_library/README.md`), plus operator authorization for this work.

## Unknowns not tested

- Whether a lit variant compiles or renders correctly in the project's configured renderer, or which Godot lighting APIs and render modes are appropriate.
- Whether light energy, shadows, transparency, double-sided surfaces, vertex colors and textures behave acceptably with the PSX material and post-processing paths.
- Whether fog should be enabled, how it interacts with the proposed lighting, or whether it improves the scene.
- Whether existing baked colors can be reused without double lighting, or require separately authored neutral albedos.
- Visual fidelity, performance, lighting consistency across open-world videos, and operator preference; no captures or GPU/model runs were performed for this research.
- Whether a future contract or catalog version needs lighting metadata, and how any migration should be approved. No external tool or paper claims were verified.
