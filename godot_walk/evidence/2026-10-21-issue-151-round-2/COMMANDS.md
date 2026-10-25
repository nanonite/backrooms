# Chainlink #151 Round 2

## Run

From the workspace root:

```bash
python3 godot_walk/scripts/run_hunyuan_psx_round2.py
```

The runner uses the GPU headroom guard before every capture and FPS run, applies a 300-second timeout, measures resource peaks, and refuses to overwrite an existing evidence folder.

## Review

The review server serves the bundle locally and accepts validated feedback directly into this folder:

```bash
python3 godot_walk/scripts/hunyuan_review_server.py --bundle-dir godot_walk/evidence/2026-10-21-issue-151-round-2
```

Open `http://127.0.0.1:8765/` and use **Submit feedback to workspace**. No variant is auto-selected.

## Walkthrough

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/hunyuan_psx_round2.tscn -- --variant=preserve_hunyuan
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/hunyuan_psx_round2.tscn -- --variant=column_box_source_face
```

