# Issue 168 walkthrough commands

Run from the workspace root.

Play the assembled two-room candidate:

```bash
godot4 --path godot_walk res://scenes/issue168_two_room_walkthrough.tscn
```

Press **R** to reset to the safe spawn in the industrial hall. The candidate starts facing the authored doorway.

Run standalone and assembled traversal/negative-control checks:

```bash
godot4 --headless --path godot_walk --script res://scripts/test_issue168_two_room_walkthrough.gd -- --report=res://evidence/2026-11-02-issue-168-two-room/mechanics/replay-003.json
```

The report path is create-new and unused. Choose a new filename on later reruns because the test intentionally refuses to overwrite receipts.

Validate the accepted adaptation bundle without launching Godot:

```bash
python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle godot_walk/source_library/sources/video-ccf9722164a0bdc8/rooms/issue168-two-room-connection-v1/adaptation_accepted_v1.json
```

The captured bundle is protected against overwrite. To make a new guarded capture, use a new output directory and receipt filename with `run_capture_guarded.py`; the reviewed captures live under `captures-v3/`.
