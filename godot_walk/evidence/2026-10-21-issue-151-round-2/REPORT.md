# Chainlink #151: Hunyuan-to-PSX Round 2

Status: **awaiting operator review**. No candidate is auto-selected.

## Hypothesis

A full axis-aligned column box with a directly sampled frame-0152 face texture may read more clearly than the incomplete Hunyuan column while preserving the user's accepted floor and ceiling.

Only the column visual treatment changes. The floor, ceiling, walls, camera poses, route, room bounds, and collision are held constant. The candidate box is visual-only; the existing column obstacle remains the sole column collider.

## Provenance

The 320 x 400 column texture is a direct crop from `data/scenes/corridor_travel/images/frame_0152.jpg`, pixels x=780..1099 and y=300..699. It is not recolored or generated. `registration_accepted=false` and `scale_calibrated=false` remain unchanged.

## Mechanical Evidence

- Candidate capped FPS: 60.00; p95 16.88 ms; p99 17.12 ms.
- Both variants use the same authored room collision and bounded walk route.
- Boundary and floor negative controls are expected to fail closed.
- Replay drift is reported as measured, not treated as deterministic.

## Visual Diagnostics

ODiff threshold 0.1. Maximum baseline repeat difference: 0.0000%. A change at or below the per-view repeat-noise ceiling is inconclusive; pixel change is not a quality score.

- `patch_anchor`: 5.080% changed pixels; repeat-noise ceiling 0.000%
- `south_end`: 0.000% changed pixels; repeat-noise ceiling 0.000%
- `north_end`: 0.000% changed pixels; repeat-noise ceiling 0.000%
- `west_wall`: 12.640% changed pixels; repeat-noise ceiling 0.000%
- `east_wall`: 9.010% changed pixels; repeat-noise ceiling 0.000%
- `column_south`: 0.000% changed pixels; repeat-noise ceiling 0.000%
- `column_north`: 23.220% changed pixels; repeat-noise ceiling 0.000%
- `column_west`: 31.570% changed pixels; repeat-noise ceiling 0.000%
- `column_east`: 24.670% changed pixels; repeat-noise ceiling 0.000%

## Operator Review

Use `index.html` for the nine matched views. The form submits directly to this bundle when served with `hunyuan_review_server.py`; it does not rank or promote a candidate.

## Files

- `candidate_contact_sheet.jpg` — matched control/candidate captures.
- `review_metrics.json` — ODiff values and measured repeat noise.
- `round_manifest.json` — provenance, variant specs, mechanics, and run record.
- `operator_feedback.json` — pending until operator submission.
- `candidate_layout.svg` — authored, uncalibrated column-only diagram.
