# Issue #150 Commands

Run from the workspace root. Interactive and capture invocations have hard timeouts; the play window closes and writes a report after ten minutes.

## Live Walkthrough

```bash
timeout --signal=TERM --kill-after=10s 610s cargo run --release \
  --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- \
  --play --issue150 --play-timeout-seconds=600
```

WASD moves, mouse looks, `R` resets, `Esc` releases the cursor. The scene uses the same fixed-step controller as the #147 candidate.

The automated release smoke run loaded the scene successfully. On this X11 session, however, both #150 and the #147 baseline reported cursor-grab errors and approximately 1 s eligible frame intervals. This shared environment result is not a performance pass; judge the live movement on the normal desktop session.

## CPU Room Checks

```bash
timeout --signal=TERM --kill-after=10s 180s cargo run \
  --manifest-path splat_walk/Cargo.toml --bin walkability_harness -- \
  --full-harness --issue150 --room-checks-only
```

This checks the room route out and back, floor support, the column obstacle, and each named room boundary. It does not use the GPU.

The missing-floor, missing-column, and missing-boundaries controls are reproducible with:

```bash
for control in missing_floor missing_column missing_boundaries; do
  timeout --signal=TERM --kill-after=10s 120s cargo run \
    --manifest-path splat_walk/Cargo.toml --bin walkability_harness -- \
    --full-harness --issue150 --room-checks-only \
    --route-report="godot_walk/evidence/2026-10-20-issue-150/negative_controls/${control}_route_report.json" \
    --report="godot_walk/evidence/2026-10-20-issue-150/negative_controls/${control}_walkability_report.json"
done
```

Each command is expected to exit nonzero because the intentionally incomplete room cannot pass validation.

## Captures

```bash
timeout --signal=TERM --kill-after=10s 300s cargo run \
  --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- \
  --capture --issue150
python3 godot_walk/evidence/2026-10-20-issue-150/build_candidate_contact_sheet.py
```

The capture command checks available RAM/VRAM and refuses to run while a GPU compute process is active. It writes nine fixed views and a capture report under `captures/bevy/`.

## Rebuild Authored Assets

```bash
python3 godot_walk/evidence/2026-10-20-issue-150/build_room_candidate.py --replace-generated
```

This is CPU-only. It rebuilds the collision GLB, route report, manifest, and capture poses. It never changes the #147 visual or any tagged reference asset.
