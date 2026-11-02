# Debris-window rock room candidate

Run from the workspace root:

```bash
godot4 --path godot_walk res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/room.tscn
```

Press **R** to return to the safe spawn. Movement uses the shared Godot player controller.

Headless validation:

```bash
godot4 --headless --path godot_walk --script res://source_library/sources/video-ccf9722164a0bdc8/rooms/debris-window-rock-room-v1/test_room.gd
```

The recorded Vulkan capture/profile command is preserved in `capture_resource_run_final.json`. It is guarded by the repository GPU lock and fails rather than overwriting existing capture evidence.
