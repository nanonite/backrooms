# Issue 157 — Connector material transition review

## Scope and status

This review uses the operator-accepted #160 column-to-pocket connection inside the unchanged #156 seed-149 walkthrough. It records the affine-off renderer profile, the operator's floor-scale choice, and a visual-only ceiling-bridge candidate. `registration_accepted=false` and `scale_calibrated=false` remain unchanged. No production room geometry, visual asset, collision, connector, or runtime default was changed.

GitHub CLI returned HTTP 401 while reading #157. This work follows the local PLAN.md description: establish a shared material and transition language across modules. The ceiling bridge remains a preview candidate; it has not been promoted or added to the room catalog.

## Baseline observations

Six 1280×720 captures show both approaches, the floor threshold, ceiling/lintel, and both jambs. All use affine mapping off and 18 settle frames. Their poses are recorded in `capture_manifest.json`.

- The pocket floor has visibly denser tile repeats than the adjoining column-room floor.
- The pocket ceiling has a regular grid; the column-room ceiling is a different pale surface. A bright triangular shape projects into the doorway in ceiling-facing views. The captures do not isolate its source.
- The wall surfaces share a warm yellow palette, but their texture layouts differ. Dark authored socket trim provides a readable doorway edge.

Source inspection found a likely cause for the floor repeat difference. `issue160_room_geometry.gd` assigns column-shell slab UVs directly from XZ position, while the pocket `_textured_plane()` multiplies vertex XZ UVs by 0.25 before both use material UV scale 4. The column floor is partly covered by the Hunyuan visual, so UV density alone may not explain the full appearance.

## Floor UV candidate and operator choice

The runtime-only 16× candidate duplicates the loaded pocket floor shader material and changes its UV scale from 4×4 to 16×16. This compensates for the pocket plane's 0.25 UV factor. It changes one matching floor surface in R001 and does not alter saved assets or collision.

ODiff 4.5.0 at threshold 0.1 measured 0.0000% repeat noise across the six views. The candidate changed 0.01–0.20% of pixels per view. Those changes are measurable, but ODiff does not score quality or preference.

The operator chose to keep the current 4× scale. `operator_feedback.json` records 4× as selected and 16× as rejected. Production materials are unchanged.

## Ceiling bridge candidate — rejected by operator

The live review scene adds a runtime-only, 2.6 × 2.0 m horizontal plane centered over the tested doorway, spanning both rooms. It uses the existing `ceiling_source_video.png` at UV scale 1.3 × 1.18. Its center is 0.06 m below the ceiling-slab center so the preview plane is outside the slab surface. It adds no collider and changes no saved room or source asset. The floor remains at its selected 4× scale.

Four matched poses cover both approaches, the doorway ceiling, and a view under the bridge. Each pose has two unchanged captures and one candidate capture. ODiff reports maximum repeat noise of 0.17%. Candidate pixel changes are 0.29%, 0.81%, 0.30%, and 0.85% for `column_into_pocket`, `pocket_into_column`, `threshold_ceiling`, and `ceiling_under_bridge`; each exceeds its measured repeat noise. These are measured changes, not a quality score.

The operator reviewed the captures and said the difference was barely visible, choosing to keep the bridge off. The explicit decision is recorded under `ceiling_bridge_review` in `operator_feedback.json`. The live review scene leaves it off and no longer exposes an F9 toggle. The captured candidate remains archived for reproducibility; it was not added to either room.

Earlier preview captures are preserved as `ceiling_candidate_initial_*`, `ceiling_candidate_refined1_*`, `ceiling_candidate_v2_*`, and `ceiling_candidate_v3_*`. The first overlay sat inside the authored ceiling slab and was hidden; the next texture scale repeated too tightly. The current preview uses the cross-doorway placement and lower repeat count. The review index presents only the current candidate.

## Review bundle and verification

- `index.html` links the report, commands, source hashes, captures, and comparison sheets.
- `contact_sheet.jpg` shows the six baseline connector views.
- `floor_uv_16_comparison.jpg` compares the unchanged floor with the rejected 16× scale.
- `ceiling_source_bridge_comparison.jpg` shows repeated control, candidate, and ODiff images.
- `ceiling_candidate_manifest.json` records the runtime-only bridge size, position, texture, and UV scale.
- `ceiling_candidate_metrics.json` records per-view repeat noise and changed-pixel percentages.
- `source_hashes.json` records the project, renderer, room, texture, layout, and harness inputs.
- `resource_runs/issue157-ceiling-candidate-v4.json` records a successful guarded Vulkan run (5.172 s elapsed; peak child RSS about 2.43 GB; sampled GPU allocation increase about 566 MB). The guard found no compute applications active and sufficient GPU/RAM headroom.

The live review scene loaded headlessly. Its test verified the F8 floor comparison restores the selected 4× material and the capture harness can enable and disable the rejected ceiling preview. Python `py_compile` passed for the review-bundle builder. Vulkan runs emitted existing URSC global-parameter warnings while opening the pocket; they exited successfully and produced the captures.

## Wall material audit

The operator's bridge decision leaves wall continuity as the next review area. Source inspection found both room families assign `wallpaper_source_video.png` through the same material helper, with nearest filtering and UV scale 4×4. The column room perimeter and pocket connector walls both use `_materials.wall`, and the shared PSX preset preserves that UV scale. There is no source-level wall scale mismatch to correct.

This points to mesh geometry, per-surface UV layout, and where the Hunyuan visual remains visible as the causes of the remaining wall differences. A future wall candidate should target a specific artifact-bearing surface with authored geometry; globally changing the wallpaper scale would change both rooms without addressing the source of the mismatch. The ceiling bridge remains off.
