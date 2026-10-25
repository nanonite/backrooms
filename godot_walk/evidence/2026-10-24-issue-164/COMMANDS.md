# Issue 164 commands

Run these from `/mnt/sharedOs/backrooms-workspace`.

## Play the three-room candidate

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue164_three_room_walkthrough.tscn
```

Use WASD and mouse to walk. Press `R` to reset to the safe spawn in the column room.

## Open the review bundle

Open `godot_walk/evidence/2026-10-24-issue-164/index.html` in Firefox. The page links the contact sheet, layout diagram, report, and commands.

## Re-run CPU checks

```bash
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/test_issue164_layout.py
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/test_issue149_layout.py
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/validate_issue164_layout.py
godot4 --headless --path godot_walk --script res://scripts/test_issue164_runtime.gd
godot4 --headless --path godot_walk --script res://scripts/test_issue164_physics_controls.gd
```

The physics control script checks a clear and blocked connector, a present and removed floor, a closed and removed boundary, and the source-room column obstacle. The full route and boundary sweep commands used for the report are:

```bash
godot4 --headless --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/issue160_bounded_column_room.tscn --out-dir=res://evidence/2026-10-24-issue-164/mechanics/standalone_column
godot4 --headless --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/issue160_bounded_pocket_room.tscn --out-dir=res://evidence/2026-10-24-issue-164/mechanics/standalone_pocket
godot4 --headless --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/issue164_room_large_baseline.tscn --out-dir=res://evidence/2026-10-24-issue-164/mechanics/standalone_large_baseline
godot4 --headless --path godot_walk --script res://scripts/verify_bounded_psx.gd -- --scene=res://scenes/issue164_three_room_walkthrough.tscn --out-dir=res://evidence/2026-10-24-issue-164/mechanics/assembled
```

## Rebuild the reproducible layout

```bash
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/build_issue164_layout.py --validate-only --mark-mechanically-validated
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/validate_issue164_layout.py
```

The checked-in candidate layout is already marked mechanically validated and remains `operator_status=review_pending`. `--refresh-provisional --mark-mechanically-validated` is only for regenerating this candidate before an operator review; it refuses to run after an `operator_review.json` appears.

## Reproduce GPU captures and performance sample

Both commands run the shared GPU/RAM preflight, refuse concurrent Hunyuan/QEMU/GPU compute work, and have a 240-second child timeout.

```bash
python3 godot_walk/scripts/run_issue149_gpu.py --label issue164_capture --timeout-seconds 240 --evidence-dir godot_walk/evidence/2026-10-24-issue-164 -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/capture_issue164.gd
python3 godot_walk/scripts/run_issue149_gpu.py --label issue164_fps_uncapped --timeout-seconds 240 --evidence-dir godot_walk/evidence/2026-10-24-issue-164 -- godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 --script res://scripts/measure_bounded_fps.gd -- --scene=res://scenes/issue164_three_room_walkthrough.tscn --out-dir=res://evidence/2026-10-24-issue-164/mechanics/assembled --label=issue164_uncapped
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/build_issue164_review.py
```

The performance sample is uncapped. The legacy measurement script's `--capped` option reduces frames sampled per pose; it does not set Godot's runtime frame cap.

## Verify preserved inputs

```bash
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/verify_issue164_protected.py
```
