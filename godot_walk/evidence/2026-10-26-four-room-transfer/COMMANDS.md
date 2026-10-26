# Reproduce the four-room candidate

Run from `/mnt/sharedOs/backrooms-workspace` with Godot 4.6.3.

## Play

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue166_four_room_walkthrough.tscn
```

The scene loads seed 166 by default. Use WASD to walk, mouse to look, and `R` to reset. To select the serialized candidate layout explicitly:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue166_four_room_walkthrough.tscn -- --layout=res://evidence/2026-10-26-four-room-transfer/layout_four_room.json
```

## CPU runtime checks

The following commands do not run GPU capture or inference. The connection-control script refuses to overwrite its report; bounded route verifiers write into their selected folders, so choose fresh folder names if you want to preserve these recorded runs.

```bash
godot4 --headless --path godot_walk --script res://scripts/test_issue166_four_room_candidate.gd -- --output=res://evidence/2026-10-26-four-room-transfer/mechanics/connection_controls_final.json
godot4 --headless --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/issue166_room_large_dual_socket_standalone.tscn --out-dir=res://evidence/2026-10-26-four-room-transfer/mechanics/large_room_standalone_final_v2
godot4 --headless --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/issue166_transfer_room_socket_standalone.tscn --out-dir=res://evidence/2026-10-26-four-room-transfer/mechanics/corridor_standalone_final_v2
godot4 --headless --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/issue166_four_room_walkthrough.tscn --out-dir=res://evidence/2026-10-26-four-room-transfer/mechanics/assembled_final_v3 --trace-state
godot4 --headless --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/issue164_three_room_walkthrough.tscn --out-dir=res://evidence/2026-10-26-four-room-transfer/mechanics/issue164_regression_verified
python3 godot_walk/scripts/analyze_issue166_traversal.py --physics godot_walk/evidence/2026-10-26-four-room-transfer/mechanics/assembled_final_v3/physics_candidate.json --controls godot_walk/evidence/2026-10-26-four-room-transfer/mechanics/connection_controls_final.json --output godot_walk/evidence/2026-10-26-four-room-transfer/mechanics/traversal_analysis_final_v2.json
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/validate_issue166_layout.py --layout godot_walk/evidence/2026-10-26-four-room-transfer/layout_four_room.json
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/test_issue166_layout_validation.py
```

## Adaptation contract

To write and validate the adaptation bundle after its mechanical evidence exists:

```bash
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/write_issue166_adaptation_record.py
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle godot_walk/evidence/2026-10-26-four-room-transfer/corridor_socket_adaptation_v3.json
```

## Guarded Vulkan review and profiling

The two guarded runs have completed. Their receipts preserve the preflight headroom, command, timeout, elapsed time, peak process RSS, and GPU-memory change. Earlier blocked attempts are retained as failed receipts; the successful files are separate.

```bash
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/run_issue149_gpu.py --label issue166_review_captures_final --timeout-seconds 240 --evidence-dir godot_walk/evidence/2026-10-26-four-room-transfer -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_issue166_review_views.gd -- --out-dir=res://evidence/2026-10-26-four-room-transfer/captures_final
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/run_issue149_gpu.py --label issue166_four_room_fps_retry1 --timeout-seconds 240 --evidence-dir godot_walk/evidence/2026-10-26-four-room-transfer -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/measure_bounded_fps.gd -- --scene=res://scenes/issue166_four_room_walkthrough.tscn --out-dir=res://evidence/2026-10-26-four-room-transfer/mechanics/assembled_final_v3 --label=issue166_four_room
```

The first command wrote [`captures_final/`](captures_final/) and `capture_manifest.json`. Godot 4.6.3 reported scene-ready at 2,352 ms. The second run sampled 10,199 uncapped frames at 34 poses: 239.86 average FPS, p95 4.287 ms and p99 4.403 ms. Capture/profile resource receipts are [`issue166_review_captures_final.json`](resource_runs/issue166_review_captures_final.json) and [`issue166_four_room_fps_retry1.json`](resource_runs/issue166_four_room_fps_retry1.json); frame samples are in [`fps_issue166_four_room.json`](mechanics/assembled_final_v3/fps_issue166_four_room.json). The captured images and measurements are evidence for this exact candidate, not catalog admission or general performance guarantees.
