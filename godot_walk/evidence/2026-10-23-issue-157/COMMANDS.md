# Issue 157 review commands

Run from the workspace root.

## Live connector review

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue157_transition_review.tscn
```

This loads the accepted #156 layout with affine mapping off. Walk through the column-to-pocket connector. **F8** toggles the pocket floor between its selected 4×4 scale and the rejected 16×16 comparison. The rejected ceiling bridge remains off in the live review scene; its archived captures are available in the comparison sheet.

## Open the captured review bundle

Open `godot_walk/evidence/2026-10-23-issue-157/index.html` in a browser. The contact sheet and candidate comparison use matched poses from both approaches to the connector.

## Rebuild the review page from current captures

```bash
python3 godot_walk/scripts/build_issue157_transition_review.py
```

## Check the live candidate toggle without rendering

```bash
godot4 --headless --path godot_walk --script res://scripts/test_issue157_transition_review.gd
```

## Reproduce guarded captures

The wrapper checks GPU/RAM headroom, fails closed, and stops after three minutes. Run only when the GPU is otherwise idle.

```bash
python3 godot_walk/scripts/run_issue149_gpu.py --label issue157-transition-captures --timeout-seconds 180 --evidence-dir godot_walk/evidence/2026-10-23-issue-157 -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --disable-vsync --script res://scripts/capture_issue157_transition.gd
python3 godot_walk/scripts/run_issue149_gpu.py --label issue157-floor-candidate --timeout-seconds 180 --evidence-dir godot_walk/evidence/2026-10-23-issue-157 -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --disable-vsync --script res://scripts/capture_issue157_floor_candidate.gd
python3 godot_walk/scripts/run_issue149_gpu.py --label issue157-ceiling-candidate-v4 --timeout-seconds 180 --evidence-dir godot_walk/evidence/2026-10-23-issue-157 -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --disable-vsync --script res://scripts/capture_issue157_ceiling_candidate.gd
python3 godot_walk/scripts/build_issue157_transition_review.py
```

The ceiling capture takes two unchanged repeats and one bridge capture for each of four poses. The GPU guard fails closed if headroom is low or another GPU workload is active. The review candidate is not an approved room change.

