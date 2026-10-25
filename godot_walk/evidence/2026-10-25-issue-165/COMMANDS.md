# Chainlink #165 commands

Run these from the workspace root (`/mnt/sharedOs/backrooms-workspace`). The
interactive command opens the pending transfer candidate with the project's
Godot 4.6.3 controller and Vulkan renderer:

```bash
godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 res://scenes/issue165_corridor_corner_transfer.tscn
```

Controls: WASD to move, mouse to look, Escape to release the mouse, and `R` to
reset to the safe spawn. The room is an authored proposal in uncalibrated
design units; it has no tested socket or connector.

Read-only adaptation validation:

```bash
python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle godot_walk/room_catalog/adaptations/room-large-v1.json
python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle godot_walk/room_catalog/adaptations/corridor-corner-v2.json
```

Relevant workflow tests and the Godot script parse check:

```bash
python3 -m pytest -q godot_walk/scripts/test_psx_design_round_resources.py godot_walk/scripts/test_video_adaptation_workflow.py
godot4 --headless --path godot_walk --check-only --script res://scripts/capture_issue165.gd
```

The bounded route, six-wall perimeter, obstacle, floor-removal and boundary-
removal results are recorded under
`godot_walk/evidence/2026-10-25-issue-165/mechanics/runner_v3/`. Their commands
and output hashes are in the v2 adaptation record's fingerprint-bound stage
receipts. The two negative controls intentionally exit with status 1 when the
verifier detects the broken room; the stage runner records that expected result
as a passed negative control.

The nine 1280×720 captures and the uncapped 14-pose performance sample were run
through `godot_walk/scripts/run_issue149_gpu.py`, which checks GPU/RAM headroom
and applies a 240-second timeout. Resource reports are in `resource_runs/`.
The exact capture and FPS commands are stored in the stage receipts under
`godot_walk/room_catalog/adaptations/stage_receipts/corridor-corner-authored-l-corridor-v2/`.

The workflow runner refuses existing declared outputs and existing stage
receipts. For another run, use a new stage ID and fresh output paths; do not
point a run at the evidence paths above.
