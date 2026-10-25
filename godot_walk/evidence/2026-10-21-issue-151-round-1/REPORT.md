# Chainlink #151: Hunyuan-to-PSX Round 1

Status: **operator review recorded**. No candidate is auto-selected or promoted.

## Review

Open `index.html` for nine matched views of two treatments. Choose a candidate per view, record both variant decisions, and download `operator_feedback.json`. Rejecting both candidates is valid.

## Scope And Provenance

The visual input is the existing issue-147 Hunyuan GLB, generated from a direct frame-0152 source-video seed. No inference, retraining, or video generation ran. Frames 0085-0192 do not establish room count or unseen layout.

Issue-150 bounds are an **uncalibrated design convention** only. `registration_accepted=false` and `scale_calibrated=false`. Hunyuan remains visual-only; collision is authored and separately validated.

## Mechanical Evidence

Toolchain: Godot 4.6.3.stable.official.7d41c59c4, Python 3.12.3, odiff-bin@4.5.0.
- `preserve_hunyuan`: 0 verifier failures; 0 SafetyNet contacts.
- `source_surface_cleanup`: 0 verifier failures; 0 SafetyNet contacts.
- Capped `res://scenes/hunyuan_psx_round1.tscn` sample: 60.00 FPS, p95 16.79 ms, p99 16.90 ms over 719 intervals.
- Boundary and floor mutations are expected negative controls under `mechanics/negative_controls/`.
- Route replay drift is measured and reported, not assumed deterministic.

## Visual Diagnostics

ODiff threshold 0.1; maximum preserve-control repeat difference is 0.0000% of pixels. Per-view deltas at or below the matched repeat-noise ceiling are inconclusive. Pixel change is not a quality score.

The contact sheet and diff images provide evidence; they do not rank aesthetics.

## Operator Review

The operator kept `preserve_hunyuan` as a reference and marked `source_surface_cleanup` for iteration. Per-view feedback selected `preserve_hunyuan` twice, `source_surface_cleanup` twice, `tie` once, and `none` four times; the four `none` choices are concentrated on incomplete column views and the east wall. The next iteration should define the column geometry first, then use a source texture that matches the visible face. The operator considers the ceiling and floor good enough to leave unchanged for that iteration.

This feedback records direction, not approval of a winning variant. No room geometry was changed as part of capturing the review.

## Files

- `candidate_contact_sheet.jpg` — paired captures.
- `review_metrics.json` — matched ODiff deltas and repeat noise.
- `round_manifest.json` — provenance and execution record.
- `operator_feedback.json` — confirmed per-view choices, variant decisions, and next-round direction.
- `COMMANDS.md` — reproduction and walkthrough commands.
