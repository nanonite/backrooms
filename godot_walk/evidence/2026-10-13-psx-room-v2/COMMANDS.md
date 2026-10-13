# Reproduction Commands

Run from the repository root. Captures use the production #100 splat and a real
GPU display; physics and scene checks can run headlessly.

## Physics And Area

```bash
godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/corridor_psx_room_v2.tscn --out-dir=res://evidence/2026-10-13-psx-room-v2
godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/corridor_psx_room_v2.tscn --out-dir=res://evidence/2026-10-13-psx-room-v2 --break=boundary
godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/corridor_psx_room_v2.tscn --out-dir=res://evidence/2026-10-13-psx-room-v2 --break=floor
```

The normal command exits 0. Both `--break` commands should exit 1.
`physics_candidate.json` includes route, boundary, floor-support, and
spawn-connected area results.

## Matched Views

The baseline set is the patch anchor. The v2 captures use the same production
eye coordinates and 200-frame settle:

```bash
DISPLAY=:1 godot4 --fixed-fps 60 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_walk_envelope.gd -- --scene=res://scenes/corridor_psx.tscn --out=res://evidence/2026-10-13-psx-room-v2/baseline/patch_anchor --camera-position=0.5,-0.042088,1.7 --settle=200
DISPLAY=:1 godot4 --fixed-fps 60 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_walk_envelope.gd -- --scene=res://scenes/corridor_psx_room_v2.tscn --out=res://evidence/2026-10-13-psx-room-v2/candidate/patch_anchor --camera-position=0.5,-0.042088,1.7 --settle=200
DISPLAY=:1 godot4 --fixed-fps 60 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_walk_envelope.gd -- --scene=res://scenes/corridor_psx_room_v2.tscn --out=res://evidence/2026-10-13-psx-room-v2/candidate/transition --camera-position=1.25,-0.042088,1.7 --settle=200
DISPLAY=:1 godot4 --fixed-fps 60 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_walk_envelope.gd -- --scene=res://scenes/corridor_psx_room_v2.tscn --out=res://evidence/2026-10-13-psx-room-v2/candidate/annex --camera-position=3.5,-0.042088,0.2 --settle=200
```

Splat-only probes use the same capture script with
`--hide-node=AuthoredBoundaries`. Layer-hidden RGB deltas are not provenance.
The matched anchor metrics use the existing metric definitions:

```bash
python3 scripts/splat_pipeline/render_metrics.py --before godot_walk/evidence/2026-10-13-psx-room-v2/baseline/patch_anchor --after godot_walk/evidence/2026-10-13-psx-room-v2/candidate/patch_anchor --out godot_walk/evidence/2026-10-13-psx-room-v2/matched_patch_metrics.json
```

## Sweep And FPS

```bash
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --disable-vsync --script res://scripts/capture_bounded_sweep.gd -- --scene=res://scenes/corridor_psx_room_v2.tscn --out-dir=res://evidence/2026-10-13-psx-room-v2 --positions-dir=res://evidence/2026-10-13-psx-room-v2 --positions=route --stations=2,3,6 --settle=20
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --disable-vsync --script res://scripts/measure_bounded_fps.gd -- --scene=res://scenes/corridor_psx_room_v2.tscn --out-dir=res://evidence/2026-10-13-psx-room-v2 --label=room_v2
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --max-fps 60 --disable-vsync --script res://scripts/measure_bounded_fps.gd -- --scene=res://scenes/corridor_psx_room_v2.tscn --out-dir=res://evidence/2026-10-13-psx-room-v2 --label=room_v2 --capped
```

## Interactive Preview

```bash
DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/corridor_psx_room_v2.tscn
```

## Regression Checks

```bash
godot4 --headless --editor --path godot_walk --import --quit
godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/test_psx_scene.gd
godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/verify_alignment.gd
godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/verify_scene.gd
git diff --check
```
