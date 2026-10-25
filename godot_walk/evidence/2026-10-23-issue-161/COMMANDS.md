# Issue 161 review commands

Run from the workspace root.

## Live A/B walkthrough

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue161_render_profile_review.tscn
```

Use the normal movement/look controls. The walkthrough starts with the operator-selected profile B. Press **F7** to switch between:

- **A / affine on** — affine mapping on, nearest filtering, vertex snap 1.
- **B / affine off** — project default: affine mapping off; nearest filtering and vertex snap stay unchanged.

Judge whether wall, floor, ceiling, and column textures appear to stay attached as you turn and walk. Do not treat the view label or ODiff percentage as a recommendation.

## Open the captured comparison

Open `godot_walk/evidence/2026-10-23-issue-161/index.html` in a browser. The page links the matched contact sheet, per-view ODiff values, repeat-noise results, and the report.

## Rebuild the review page from existing captures

```bash
python3 godot_walk/scripts/build_issue161_review.py
```

## Recapture or rerun performance

These commands use the shared fail-closed GPU/RAM guard and stop after three minutes. Run them only when the GPU is otherwise idle.

```bash
python3 godot_walk/scripts/run_issue149_gpu.py --label issue161-captures --timeout-seconds 180 --evidence-dir godot_walk/evidence/2026-10-23-issue-161 -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --disable-vsync --script res://scripts/capture_issue161.gd
python3 godot_walk/scripts/build_issue161_review.py
```

```bash
python3 godot_walk/scripts/run_issue149_gpu.py --label issue161-profile-performance --timeout-seconds 180 --evidence-dir godot_walk/evidence/2026-10-23-issue-161 -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --disable-vsync --script res://scripts/measure_issue161_profiles.gd
```

The project-default capture is also reproducible through the guard:

```bash
python3 godot_walk/scripts/run_issue149_gpu.py --label issue161-default-render-check --timeout-seconds 180 --evidence-dir godot_walk/evidence/2026-10-23-issue-161 -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --disable-vsync --script res://scripts/capture_issue161_default.gd
```

