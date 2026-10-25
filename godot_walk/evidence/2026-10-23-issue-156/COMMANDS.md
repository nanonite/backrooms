# Issue #156: Launch and reproduction commands

Run commands from `/mnt/sharedOs/backrooms-workspace`.

## Walk the streamed candidate

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue156_streamed_walkthrough.tscn
```

Press `R` to reset to the spawn. The scene loads the finite seed-149 graph and streams the player-centered window. This command runs the already serialized candidate; it does not regenerate rooms.

## Validate the serialized candidate

```bash
python3 godot_walk/scripts/validate_issue149_layout.py --layout godot_walk/evidence/2026-10-23-issue-156/layout_seed_149.json
```

The candidate is reproducible from its seed and current catalog snapshot with:

```bash
python3 godot_walk/scripts/generate_issue149_layout.py --seed 149 --placements 10 --bounded-streaming --out godot_walk/evidence/2026-10-23-issue-156/layout_seed_149.json --snapshot-out godot_walk/evidence/2026-10-23-issue-156/catalog_snapshot.json
```

Regenerating rewrites the layout, catalog snapshot, and layout sidecar in this evidence directory. Compare the hashes before replacing reviewed evidence.

## Run CPU-only checks

```bash
python3 -m unittest discover -s godot_walk/scripts -p 'test_issue149_layout.py' -v
python3 godot_walk/scripts/validate_issue149_layout.py --layout godot_walk/evidence/2026-10-23-issue-156/layout_seed_149.json
python3 godot_walk/scripts/record_issue156_integrity.py
timeout 120s godot4 --headless --path godot_walk --script res://scripts/test_issue149_runtime.gd
timeout 120s godot4 --headless --path godot_walk --script res://scripts/test_issue156_streaming.gd
timeout 120s godot4 --headless --path godot_walk --script res://scripts/test_issue156_negative_controls.gd
```

## Reproduce guarded Vulkan captures and performance

These runs require GPU capacity. The wrapper checks GPU/RAM headroom, fails closed, applies a timeout, and writes its measurements under `resource_runs/`.

```bash
python3 godot_walk/scripts/run_issue149_gpu.py --label issue156-captures --timeout-seconds 300 --evidence-dir godot_walk/evidence/2026-10-23-issue-156 -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --disable-vsync --script res://scripts/capture_issue156.gd
python3 godot_walk/scripts/run_issue149_gpu.py --label issue156-performance --timeout-seconds 180 --evidence-dir godot_walk/evidence/2026-10-23-issue-156 -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --disable-vsync --script res://scripts/measure_issue156_streaming.gd
python3 godot_walk/scripts/build_issue156_review.py
```

Do not run a capture or performance pass if the guard reports insufficient headroom or another GPU workload is active.
