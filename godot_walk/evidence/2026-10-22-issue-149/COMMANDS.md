# #149 Review Commands

Run from `/mnt/sharedOs/backrooms-workspace`.

## Review In Browser

Open `godot_walk/evidence/2026-10-22-issue-149/index.html`. It contains the generated map and the matched #160 regression/seed-149 captures.

## Walk Seed 149

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/issue149_generated_walkthrough.tscn -- \
  --layout=res://evidence/2026-10-22-issue-149/layout_seed_149.json
```

WASD and mouse move/look; press `R` to reset to the safe spawn. This is the 1280x720 interactive display command; the recorded FPS result is at 960x540.

## Select Another Seed

Generate a separate layout file, then pass its `res://` path to the same scene:

```bash
python3 godot_walk/scripts/generate_issue149_layout.py --seed 0 --placements 10 \
  --out godot_walk/evidence/2026-10-22-issue-149/layout_seed_0_south.json

godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 \
  res://scenes/issue149_generated_walkthrough.tscn -- \
  --layout=res://evidence/2026-10-22-issue-149/layout_seed_0_south.json
```

## Run CPU/Headless Checks

```bash
python3 godot_walk/scripts/validate_issue149_layout.py
python3 godot_walk/scripts/validate_issue149_layout.py \
  --layout godot_walk/evidence/2026-10-22-issue-149/layout_seed_0_south.json
python3 godot_walk/scripts/test_issue149_layout.py
godot4 --headless --path godot_walk --script res://scripts/test_issue149_runtime.gd
godot4 --headless --path godot_walk --script res://scripts/test_issue149_runtime.gd -- \
  --layout=res://evidence/2026-10-22-issue-149/layout_seed_0_south.json
```

Run the route/collision verifier for the generated candidate:

```bash
godot4 --headless --path godot_walk --script res://scripts/verify_bounded_psx.gd -- \
  --scene=res://scenes/issue149_generated_walkthrough.tscn \
  --out-dir=res://evidence/2026-10-22-issue-149/mechanics/generated-seed-149-final
```

Use `--break=connector`, `--break=floor`, or `--break=boundary` for intentional negative controls. Each should produce a failing verifier result.

## Guarded GPU Evidence

Capture and FPS tools check GPU/RAM headroom, refuse active compute jobs, and enforce a timeout. Do not bypass the guard or run alongside another GPU workload.

```bash
python3 godot_walk/scripts/run_issue149_gpu.py --label=captures-seed149 \
  --timeout-seconds=300 -- godot4 --fixed-fps 60 --path godot_walk \
  --rendering-driver vulkan --resolution 960x540 --disable-vsync \
  --script res://scripts/capture_issue149.gd

python3 godot_walk/scripts/run_issue149_gpu.py --label=fps-capped-seed149 \
  --timeout-seconds=180 -- godot4 --path godot_walk --rendering-driver vulkan \
  --resolution 960x540 --disable-vsync --max-fps 60 \
  --script res://scripts/measure_bounded_fps.gd -- --capped \
  --scene=res://scenes/issue149_generated_walkthrough.tscn \
  --out-dir=res://evidence/2026-10-22-issue-149/mechanics/generated-seed-149-final \
  --label=issue149_seed149
```
