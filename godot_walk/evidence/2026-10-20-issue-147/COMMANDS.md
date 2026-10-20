# Reproduction And Review

Run from the repository root. Rendering commands use Vulkan; their resource guard requires at least 10 GiB available RAM and 4096 MiB free VRAM. Capture also refuses to start while `nvidia-smi` reports a compute process. The Bevy visual GLB is visual-only; collision checks use the authored collision GLB.

## Fresh Clone

The repository does not carry the 307 MB visual GLB (`hunyuan_layers.glb`, gitignored), the source video, or the Track-A Hunyuan PLY layers. What a fresh clone can do:

- **Mechanical checks work as-is** after `git lfs pull`: `--full-harness --issue147` reads only `route_report_v2.json` and `authored_route_collision_v2.glb`.
- **Play and capture need local inputs**, because they load `module_manifest.json`, which hash-checks the visual GLB and the source evidence:
  1. Copy the #100 video to `data/scenes/corridor_travel/video.mp4` and its registered frame to `data/scenes/corridor_travel/images/frame_0152.jpg` (hashes in `module_manifest.json`).
  2. Copy the two SceneGen layers listed in `hunyuan_conversion.json` (`mesh_layer0.ply`, `mesh_layer1.ply`; hashes recorded there) and rebuild the GLB. Write metadata to a scratch path so the committed record is not overwritten:

```bash
python scripts/splat_pipeline/convert_hunyuan_layers.py \
  --input <track-a>/hunyuan/scene-frame-0152-attempt-02/mesh_layer0.ply <track-a>/hunyuan/scene-frame-0152-attempt-02/mesh_layer1.ply \
  --output godot_walk/evidence/2026-10-20-issue-147/hunyuan_layers.glb \
  --metadata /tmp/hunyuan_conversion_check.json
sha256sum godot_walk/evidence/2026-10-20-issue-147/hunyuan_layers.glb  # expect 5b3e879c…3a23bf
```

If the rebuilt hash differs, the manifest will refuse to load; do not edit the pinned hash without recording why.

## Operator Review

Open these files first:

- `godot_walk/evidence/2026-10-20-issue-147/candidate_contact_sheet.jpg`
- `godot_walk/evidence/2026-10-20-issue-147/source_pipeline_contact_sheet.jpg`
- `godot_walk/evidence/2026-10-20-issue-147/candidate_layout.svg`

Timed standalone walkthrough, capped at ten minutes:

```bash
timeout --signal=TERM --kill-after=10s 610s cargo run --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --play --issue147 --play-timeout-seconds=600
```

## Mechanical Checks

Re-run the full CPU-only controller suite, including the candidate route, column block, 18 lateral boundary pushes, and shared floor-loss/open-ledge controls:

```bash
timeout --signal=TERM --kill-after=10s 300s cargo run --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --full-harness --issue147 --route-report=godot_walk/evidence/2026-10-20-issue-147/route_report_v2.json --report=godot_walk/evidence/2026-10-20-issue-147/walkability_report.json
```

Three asset-integrity negatives are expected to exit nonzero before simulation:

```bash
timeout --signal=TERM --kill-after=10s 300s cargo run --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --full-harness --issue147 --route-report=godot_walk/evidence/2026-10-20-issue-147/negative_controls/missing_floor_route_report.json --report=godot_walk/evidence/2026-10-20-issue-147/negative_controls/missing_floor_walkability.json
timeout --signal=TERM --kill-after=10s 300s cargo run --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --full-harness --issue147 --route-report=godot_walk/evidence/2026-10-20-issue-147/negative_controls/missing_column_route_report.json --report=godot_walk/evidence/2026-10-20-issue-147/negative_controls/missing_column_walkability.json
timeout --signal=TERM --kill-after=10s 300s cargo run --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --full-harness --issue147 --route-report=godot_walk/evidence/2026-10-20-issue-147/negative_controls/missing_boundaries_route_report.json --report=godot_walk/evidence/2026-10-20-issue-147/negative_controls/missing_boundaries_walkability.json
```

The negative GLBs can be regenerated without overwriting existing evidence:

```bash
python godot_walk/evidence/2026-10-20-issue-147/build_authored_collision.py --negative-control missing_floor
python godot_walk/evidence/2026-10-20-issue-147/build_authored_collision.py --negative-control missing_column
python godot_walk/evidence/2026-10-20-issue-147/build_authored_collision.py --negative-control missing_boundaries
```

## Captures

The guarded capture command reproduces the 17 visual-only Bevy views and writes a resource report:

```bash
timeout --signal=TERM --kill-after=10s 300s cargo run --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --capture --issue147
```

It writes to `godot_walk/evidence/2026-10-20-issue-147/captures/bevy/`. Capture-pose and asset hashes are checked from `module_manifest.json` before the renderer starts.
