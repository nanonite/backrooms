# Reproduction

Run from the workspace root. GPU captures require `DISPLAY=:1` and the
Vulkan-capable Godot binary. They reuse the committed #100 scene and its
existing PLY/collision assets.

```bash
godot4 --headless --editor --path godot_walk --import --quit
godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/corridor_psx_patch_extension.tscn --out-dir=res://evidence/2026-10-13-psx-extension
```

Matched baseline/candidate captures at all three route positions:

```bash
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_walk_envelope.gd -- --scene=res://scenes/corridor_psx.tscn --out=res://evidence/2026-10-13-psx-extension/baseline/x0.50_z1.70 --settle=200 --camera-position=0.5,-0.09214848,1.7
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_walk_envelope.gd -- --scene=res://scenes/corridor_psx_patch_extension.tscn --out=res://evidence/2026-10-13-psx-extension/candidate/x0.50_z1.70 --settle=200 --camera-position=0.5,-0.09214848,1.7
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_walk_envelope.gd -- --scene=res://scenes/corridor_psx.tscn --out=res://evidence/2026-10-13-psx-extension/baseline/x0.50_z2.90 --settle=200 --camera-position=0.5,-0.04249024,2.9
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_walk_envelope.gd -- --scene=res://scenes/corridor_psx_patch_extension.tscn --out=res://evidence/2026-10-13-psx-extension/candidate/x0.50_z2.90 --settle=200 --camera-position=0.5,-0.04249024,2.9
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_walk_envelope.gd -- --scene=res://scenes/corridor_psx.tscn --out=res://evidence/2026-10-13-psx-extension/baseline/x-0.65_z2.90 --settle=200 --camera-position=-0.65,-0.04249024,2.9
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_walk_envelope.gd -- --scene=res://scenes/corridor_psx_patch_extension.tscn --out=res://evidence/2026-10-13-psx-extension/candidate/x-0.65_z2.90 --settle=200 --camera-position=-0.65,-0.04249024,2.9
```

Metrics use the existing fixed thresholds (black max-channel <20; changed
max-channel delta >32):

```bash
python scripts/splat_pipeline/render_metrics.py --before godot_walk/evidence/2026-10-13-psx-extension/baseline/x0.50_z1.70 --after godot_walk/evidence/2026-10-13-psx-extension/candidate/x0.50_z1.70 --out godot_walk/evidence/2026-10-13-psx-extension/metrics/x0.50_z1.70.json
python scripts/splat_pipeline/render_metrics.py --before godot_walk/evidence/2026-10-13-psx-extension/baseline/x0.50_z2.90 --after godot_walk/evidence/2026-10-13-psx-extension/candidate/x0.50_z2.90 --out godot_walk/evidence/2026-10-13-psx-extension/metrics/x0.50_z2.90.json
python scripts/splat_pipeline/render_metrics.py --before godot_walk/evidence/2026-10-13-psx-extension/baseline/x-0.65_z2.90 --after godot_walk/evidence/2026-10-13-psx-extension/candidate/x-0.65_z2.90 --out godot_walk/evidence/2026-10-13-psx-extension/metrics/x-0.65_z2.90.json
```

Scene contract checks:

```bash
godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/test_psx_scene.gd
godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/verify_alignment.gd
```

The extension runs without changing the project's main scene:

```bash
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/corridor_psx_patch_extension.tscn
```
