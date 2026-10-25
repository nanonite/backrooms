# Review and reproduce

Run from the repository root. Current engine: `godot4`4.6.3, Vulkan Forward+.
Mouse look/WASD; Escape releases mouse; click recaptures it. F6 toggles the
packaged material effects; the existing native post effect stays enabled.

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/library_column_room.tscn
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/library_pocket_room.tscn
```

Append `-- --native-baseline` to start with native materials. Neither scene
changes the project's default launch scene.

Before each GPU capture/performance run:

```bash
python3 -c 'import sys; sys.path.insert(0,"godot_walk/scripts"); from psx_design_round_resources import check_capture_headroom; print(check_capture_headroom())'
timeout 100 godot4 --fixed-fps 60 --path godot_walk --rendering-driver vulkan --resolution 960x540 --disable-vsync --script res://scripts/capture_library_rooms.gd
python3 godot_walk/evidence/2026-10-21-issue-155-godot-library/build_review.py
```

Mechanical checks (`column` can be replaced by `pocket`):

```bash
timeout 90 godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/library_column_room.tscn --out-dir=res://evidence/2026-10-21-issue-155-godot-library/mechanics/column
```

Append `--break=floor` or `--break=boundary` for negative controls; both must
exit1 with support/escape failures. The pocket has no column obstacle.

```bash
timeout 60 godot4 --headless --path godot_walk --script res://scripts/test_library_rooms.gd
timeout 60 godot4 --headless --path godot_walk --script res://scripts/test_hunyuan_psx_column_box.gd
timeout 60 godot4 --headless --path godot_walk --script res://scripts/test_hunyuan_psx_round1.gd
timeout 60 godot4 --headless --path godot_walk --script res://scripts/test_hunyuan_psx_round2.gd
python3 -m unittest discover -s godot_walk/scripts -p 'test_*.py'
```

Performance sweep, after preflight (replace `column` with `pocket` for room2):

```bash
timeout 60 /usr/bin/time -v godot4 --path godot_walk --rendering-driver vulkan --resolution 960x540 --disable-vsync --max-fps 60 --script res://scripts/measure_bounded_fps.gd -- --capped --scene=res://scenes/library_column_room.tscn --out-dir=res://evidence/2026-10-21-issue-155-godot-library/mechanics/column --label=candidate
```

Use `--label=native --native-baseline` instead for the native comparison. Logs
are under `logs/`; frame measurements/screenshots under `mechanics/`.
