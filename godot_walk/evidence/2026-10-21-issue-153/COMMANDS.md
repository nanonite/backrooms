# Chainlink #153 Commands

Run these from `/mnt/sharedOs/backrooms-workspace`.

## Open The Review

```bash
firefox godot_walk/evidence/2026-10-21-issue-153/index.html
```

## Inspect In The Walkthrough

This starts the accepted #150 route with the optional Blender overlay. It exits and writes an interactive report after two minutes.

```bash
cargo run --release --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --issue153 --play --play-timeout-seconds=120
```

## Rebuild The Visual Asset

```bash
python3 godot_walk/evidence/2026-10-21-issue-153/authoring/extract_source_crops.py
timeout 300s blender --background --python godot_walk/evidence/2026-10-21-issue-153/authoring/build_column_repair.py
```

## Recapture The Two Candidate Views

The Python headroom guard checks Hunyuan/QEMU jobs, GPU processes, RAM, and VRAM. The Bevy runner also checks available RAM/VRAM and active compute processes. The shell timeout bounds the run.

```bash
python3 -c 'import json,sys; sys.path.insert(0,"godot_walk/scripts"); from psx_design_round_resources import check_capture_headroom; print(json.dumps(check_capture_headroom(),sort_keys=True))'
timeout 600s cargo run --release --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --issue153 --capture --capture-dir=godot_walk/evidence/2026-10-21-issue-153/captures/candidate
python3 godot_walk/evidence/2026-10-21-issue-153/authoring/build_review_contact_sheet.py
```

For a fresh baseline, use the same two poses without `--issue153` and write to `captures/baseline`:

```bash
timeout 600s cargo run --release --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --issue150 --capture --capture-poses=godot_walk/evidence/2026-10-21-issue-153/capture_poses.json --capture-dir=godot_walk/evidence/2026-10-21-issue-153/captures/baseline
```

The delivered review reuses the existing accepted #150 captures as the matched baseline.
