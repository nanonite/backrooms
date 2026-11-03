# Bill Viola single-room candidate

Run from `/mnt/sharedOs/backrooms-workspace`.

Play the candidate:

```bash
godot4 --path godot_walk res://source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/room.tscn
```

Use WASD to walk, mouse to look, Escape to release the mouse, and **R** to reset to the safe spawn facing the dresser. The room is a bounded authored interpretation; its dimensions and unobserved walls are not measured source facts.

Run standalone movement, boundary, floor, obstacle, and negative-control checks. Use a fresh report path each time because the harness refuses overwrites:

```bash
godot4 --headless --path godot_walk \
  --script res://source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/test_room.gd \
  -- --report=/tmp/issue169-bill-viola-room-review-002.json
```

Validate the adaptation record without launching Godot:

```bash
python3 godot_walk/scripts/video_adaptation_runner.py validate \
  --bundle godot_walk/source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/adaptation_candidate.json
```

To recapture views, select unused output and receipt paths. The shared runner checks GPU/RAM headroom, holds the GPU job lock, and records resource peaks:

```bash
python3 godot_walk/evidence/2026-11-02-issue-168-two-room/run_capture_guarded.py \
  --label issue169-bill-viola-room-review-001 \
  --output-dir godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/room-captures-review-001 \
  --report godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/capture_resource_run_review_001.json \
  --timeout-seconds 240 -- godot4 --path godot_walk \
  --script res://source_library/sources/video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/capture_room.gd \
  -- --out-dir=res://evidence/2026-11-02-issue-169-bill-viola-seed-91s/room-captures-review-001
```

Current captures and their guarded resource receipt are under `godot_walk/evidence/2026-11-02-issue-169-bill-viola-seed-91s/room-captures-v4/` and `capture_resource_run_v4.json`. The comparison is `room_comparison_v2.jpg`; open the evidence folder's `index.html` for the review bundle.
