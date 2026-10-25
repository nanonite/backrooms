# Hunyuan Column Face Iteration

Run these from `/mnt/sharedOs/backrooms-workspace`.

## Rebuild The Source Crop

```bash
python3 godot_walk/evidence/2026-10-21-issue-151-round-3/authoring/extract_column_face.py
```

This extracts the full visible column face from source-video frame 0152. It does not use a Hunyuan render as the texture source.

## Capture The Matched Views

The capture uses Vulkan. Check headroom before running; do not run alongside Hunyuan, QEMU, or another GPU job. It captures the control and candidate at two fixed views and exits.

```bash
python3 -c 'import json,sys; sys.path.insert(0,"godot_walk/scripts"); from psx_design_round_resources import check_capture_headroom; print(json.dumps(check_capture_headroom(),sort_keys=True))'
timeout 300s godot4 --fixed-fps 60 --path godot_walk --rendering-driver vulkan --resolution 960x540 --disable-vsync --script res://scripts/capture_hunyuan_psx_round3.gd -- --out=res://evidence/2026-10-21-issue-151-round-3/captures
```

The first capture is retained as a placement diagnostic. The visual-alignment pass is a separate capture, based on the rendered column silhouette and not on accepted registration:

```bash
python3 -c 'import json,sys; sys.path.insert(0,"godot_walk/scripts"); from psx_design_round_resources import check_capture_headroom; print(json.dumps(check_capture_headroom(),sort_keys=True))'
timeout 300s godot4 --fixed-fps 60 --path godot_walk --rendering-driver vulkan --resolution 960x540 --disable-vsync --script res://scripts/capture_hunyuan_psx_round3.gd -- --out=res://evidence/2026-10-21-issue-151-round-3/captures_aligned
```

The final fit pass narrows the offset and fits the source face to the visible column silhouette. Earlier captures remain unchanged.

```bash
python3 -c 'import json,sys; sys.path.insert(0,"godot_walk/scripts"); from psx_design_round_resources import check_capture_headroom; print(json.dumps(check_capture_headroom(),sort_keys=True))'
timeout 300s godot4 --fixed-fps 60 --path godot_walk --rendering-driver vulkan --resolution 960x540 --disable-vsync --script res://scripts/capture_hunyuan_psx_round3.gd -- --out=res://evidence/2026-10-21-issue-151-round-3/captures_fitted
python3 godot_walk/evidence/2026-10-21-issue-151-round-3/authoring/build_review.py
```

## Verify Walkability

The variant adds no collision. This rechecks the same authored route and obstacle proxy in the candidate scene:

```bash
timeout 300s godot4 --fixed-fps 60 --path godot_walk --headless --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/hunyuan_psx_round3.tscn --variant=column_face_extrusion --out-dir=res://evidence/2026-10-21-issue-151-round-3/mechanics/column_face_extrusion_fitted
```

## Live Walkthrough

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/hunyuan_psx_round3.tscn -- --variant=column_face_extrusion
```

Controls are WASD and mouse; Escape releases the pointer.
