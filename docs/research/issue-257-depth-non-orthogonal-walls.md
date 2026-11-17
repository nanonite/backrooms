# Issue 257: depth and non-orthogonal walls from panoramas

## Problem and evidence

The operator accepted the slot-canyon candidate as a bounded standalone room, while describing weak depth perception and smoothing of walls that are not necessarily horizontal as areas to improve. Acceptance covers the reviewed appearance and traversal, not registration, metric scale, connectivity, or catalog admission (`godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/operator_review.json`). The nested-light corridor was also accepted and received very positive feedback, but this is not a controlled comparison (`godot_walk/source_library/sources/video-d857abe7a94da9d1/rooms/nested-light-corridor-v1/operator_review.json`).

Three distinct constraints may contribute:

- **Footprint contract:** the candidate records a simple orthogonal XZ polygon and an authored L shape, explicitly a stand-in for the curved canyon (`godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/adaptation_candidate.json`). The active polygon validator rejects nonorthogonal edges (`godot_walk/scripts/video_adaptation_polygon.py`); the v4 freeze identifies that validator and preserves its v3 ancestry (`godot_walk/room_catalog/contract_freeze_v4.json`). This constrains the plan-view boundary, but does not by itself prove that every visual wall must be flat or vertical.
- **Available spatial evidence:** the candidate describes its 512×256 panorama as a camera-centered background without spatial parallax, not a mesh or collision source. Its surface crops come from the seed frame; dimensions and hidden geometry are unknown (`godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/adaptation_candidate.json`). A single image can provide perspective cues but does not uniquely determine metric depth or unseen surfaces. The library likewise cautions against inferring hidden geometry or connectivity from the source (`godot_walk/source_library/README.md`).
- **Authoring choices:** the candidate uses six wall boxes and three rock obstacles (`godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/room.gd`). The snow-garden revision demonstrates a separate authoring approach: added visual detail with an unchanged collidable footprint, while explicitly recording invented details and remaining panorama limitations (`godot_walk/evidence/2026-11-17-issue-255-room-candidate/REPORT.md`). It does not establish that the same approach will fix canyon depth.

These observations support all three hypotheses; they do not apportion blame between contract, source, and authoring. A sloped or irregular wall silhouette in elevation is also a different requirement from a non-orthogonal footprint in plan; each needs its own test.

## Options

### 1. Controlled authored-detail comparison within the existing contract

- **Change:** Create a separate canyon candidate with the same seed, panorama, footprint, camera settings and traversal boundaries as the accepted candidate. Add authored, non-colliding rock relief and occlusion cues within the boundary; document where they are invented and keep the baseline intact. Capture matched viewpoints and a short walk path. Assess vertical silhouette separately from plan shape.
- **Cost:** Low to medium: scene authoring, matched captures and mechanical checks. No model or contract migration is required for the proposed comparison.
- **Risk:** Visual relief may obscure the path, disagree with collision, or make invented structure look measured. A single candidate may not generalize; changing several cues at once cannot identify their individual effects.
- **Agent can verify:** Same declared footprint, unchanged baseline, no escape or blocked spawn, matching capture positions, provenance and false calibration flags. **Operator only:** Judge whether depth and wall character improve during viewing/walking, and whether the visual/collision mismatch is acceptable.

### 2. New contract version for a non-orthogonal footprint

- **Change:** Design a separately versioned representation for finite simple XZ polygons with arbitrary straight edges, plus explicit containment, collision and socket rules. Keep frozen v1–v4 behavior and fixtures intact. Curves would still require an approximation or a later representation; arbitrary XZ edges do not alone describe sloping or overhanging walls.
- **Cost:** High: specification, validation and compatibility design, geometry edge cases, fixtures, scene and traversal tests, and migration review. The existing orthogonal validator is part of the v4 freeze (`godot_walk/room_catalog/contract_freeze_v4.json`, `godot_walk/scripts/video_adaptation_polygon.py`).
- **Risk:** Self-intersection, near-zero edges, numerical tolerance, containment, wall/collider alignment and socket placement can cause unsafe or inconsistent rooms. More expressive geometry still has to be authored; it does not recover missing depth.
- **Agent can verify:** Version dispatch, old fixture regression, invalid polygon rejection, floor and boundary coverage, collision and traversal tests. **Operator only:** Decide whether a representative angled candidate looks and feels better and whether the additional contract complexity is worthwhile.

### 3. Seed-frame depth estimation as authoring guidance

- **Change:** In a future, separately authorized experiment, estimate relative depth for the selected direct seed frame; record input identity, tool/version, parameters, output and uncertainty. Use it as a reference for a manually authored comparison, not a source of calibrated dimensions or hidden geometry. Preserve the existing operator seed and panorama gates (`godot_walk/source_library/README.md`).
- **Cost:** Medium to high and uncertain: tool selection, installation, compute, reproducibility and interpretation. Availability, hardware requirements, accuracy and licenses of any particular depth model are **unverified**; no external tool or paper is assumed here.
- **Risk:** Single-view estimates can mistake texture or lighting for geometry, have unknown scale, omit occluded surfaces and bias an author toward false precision. A seed-only estimate covers its field of view, not the whole panorama or an established walkable volume.
- **Agent can verify:** Input/output provenance, file dimensions, reproducibility if the tool permits it, and that outputs remain labeled as estimates. **Operator only:** Judge whether estimated ordering corresponds to the source and improves a matched playable candidate. Neither result alone validates metric accuracy.

## Recommendation

Start with option 1. It tests whether authoring can improve the reported perception without first changing a frozen contract or introducing an unvalidated estimator. A positive result supports a practical authoring route, not proof that the contract is sufficient for curved boundaries. If the operator still needs a non-orthogonal traversable boundary, specify option 2 independently; consider option 3 only when a concrete tool and compute environment can be evaluated. The existing separate acceptance and provenance boundaries remain relevant (`godot_walk/source_library/README.md`, `godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/operator_review.json`).

## Ready-to-file first implementation slice

**Title:** Compare authored canyon depth cues inside the existing footprint

**Scope:** Create a new standalone slot-canyon variant based on the accepted candidate, retaining its seed, panorama, declared XZ footprint, spawn, collidable boundaries, scale and camera settings. Add a bounded set of documented visual-only rock relief/occlusion cues, including an irregular vertical silhouette where feasible. Preserve the original candidate and frozen contracts. Do not infer metric geometry or change registration or calibration status. Record every authored assumption and any visible collision mismatch. This is an experiment, not catalog admission.

**Acceptance:** A separate candidate and provenance record identify the baseline and variant; matched captures from at least the existing spawn, bend and wall viewpoints plus a repeatable walk path support comparison. Automated checks confirm unchanged declared footprint, working spawn, traversal and boundary containment, and no new collidable obstacles. A negative control demonstrates the boundary check can detect an escape or missing boundary. The operator reviews both variants and records whether perceived depth and wall character improved, worsened or stayed unchanged, including any objection to collision mismatch. No improvement is presumed by a passing mechanical check.

**Verification:** Run the applicable candidate validator and room traversal tests for both variants; record commands and results. Verify input identities, matched camera poses, collision policy and unchanged frozen artifacts. Give the operator paired captures and a playable walk for the subjective decision; record the decision separately from mechanical results. If rendering or operator access is unavailable, report that limitation and leave the visual decision pending.

## Unknowns not tested

- No new render, traversal, matched-view comparison, perceptual study or operator review was performed for this research. The relative contribution of authoring, contract and source remains unknown.
- Whether decorative relief within the current footprint improves canyon depth, whether its collision mismatch is acceptable, and which individual visual cues matter are untested.
- Whether a non-orthogonal footprint or vertical wall profile improves this room, and the performance and compatibility cost of a new contract, are untested.
- No depth estimator, model, paper, hardware requirement, license, numerical accuracy or reproducibility claim was checked. No model or GPU was run and no download was made.
- True canyon dimensions, camera pose, hidden surfaces and metric depth remain unknown; the candidate explicitly treats its units as authored and uncalibrated (`godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/adaptation_candidate.json`).
