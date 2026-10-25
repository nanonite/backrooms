# #160 Review and Reproduction Commands

Run from the workspace root (`/mnt/sharedOs/backrooms-workspace`).

## Walkthrough

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue160_assembled_walkthrough.tscn
```

Use the mouse to look and WASD to walk. The review bundle is available at
`godot_walk/evidence/2026-10-22-issue-160/index.html`; open it in a browser to
compare the standalone rooms, connector directions, and capture contact sheet.

## CPU checks

```bash
python3 -m unittest godot_walk/scripts/test_issue160_glb.py
timeout 90 godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/test_issue160.gd
timeout 180 godot4 --headless --fixed-fps 60 --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/issue160_assembled_walkthrough.tscn --out-dir=res://evidence/2026-10-22-issue-160/mechanics/assembly-rerun
```

The column and pocket can be passed to the same verifier by replacing
`issue160_assembled_walkthrough.tscn` with `issue160_bounded_column_room.tscn`
or `issue160_bounded_pocket_room.tscn`, and changing the output directory.

## Rebuild review metadata

```bash
python3 godot_walk/evidence/2026-10-22-issue-160/build_issue160_readiness.py
python3 godot_walk/evidence/2026-10-22-issue-160/build_review.py
```

The final capture and FPS commands use the fail-closed headroom/resource
wrapper. Do not launch them while another GPU workload is active:

```bash
python3 godot_walk/scripts/run_issue160_gpu.py --label=captures-reviewed --timeout-seconds=180 -- godot4 --fixed-fps 60 --path godot_walk --rendering-driver vulkan --resolution 960x540 --disable-vsync --script res://scripts/capture_issue160.gd
```

The FPS wrapper invocations and their exact arguments are recorded in
`resource_runs/fps-column.json`, `fps-pocket.json`, and `fps-assembly.json`.
