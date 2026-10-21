# Issue #148 Reproduction Commands

Run from the workspace root. Route and scene reports below are CPU-only. The Vulkan capture uses the GPU but runs no inference; the capture code performs its resource preflight.

## Rebuild Authored Assets

This overwrites only the generated #148 module assets and manifests. Re-run the independent route checks and CPU scene reports below afterward.

```bash
python3 godot_walk/evidence/2026-10-21-issue-148/early-pocket/build_early_pocket.py --replace-generated
```

After capture, regenerate the contact sheet from the report-listed views and refresh catalog hashes:

```bash
python3 godot_walk/evidence/2026-10-21-issue-148/early-pocket/build_review_contact_sheet.py
python3 godot_walk/evidence/2026-10-21-issue-148/early-pocket/register_catalog.py
```

## Catalog Validation

```bash
cargo run --release --manifest-path splat_walk/Cargo.toml --bin validate_room_catalog
```

## Independent Route Checks

Each command writes its report into this issue's evidence directory, except source route geometry paths which are read-only inputs.

```bash
timeout --signal=TERM --kill-after=10s 180s cargo run --release --manifest-path splat_walk/Cargo.toml --bin walkability_harness -- --full-harness --room-checks-only --route-report=godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column/route_report.json --report=godot_walk/evidence/2026-10-21-issue-148/tagged-reference-walkability.json
```

```bash
timeout --signal=TERM --kill-after=10s 180s cargo run --release --manifest-path splat_walk/Cargo.toml --bin walkability_harness -- --full-harness --room-checks-only --issue150 --route-report=godot_walk/evidence/2026-10-20-issue-150/route_report.json --report=godot_walk/evidence/2026-10-21-issue-148/issue150-standalone-walkability.json
```

```bash
timeout --signal=TERM --kill-after=10s 180s cargo run --release --manifest-path splat_walk/Cargo.toml --bin walkability_harness -- --full-harness --room-checks-only --route-report=godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/early_pocket_route_report.json --report=godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/early_pocket_walkability.json
```

```bash
timeout --signal=TERM --kill-after=10s 180s cargo run --release --manifest-path splat_walk/Cargo.toml --bin walkability_harness -- --full-harness --room-checks-only --route-report=godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/assembled_route_report.json --report=godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/assembled_connector_walkability.json
```

The negative controls use the same harness with their matching `*_route_report.json` and `*_walkability.json` paths under `early-pocket/generated/negative_controls/`. Both are expected to exit non-zero: `blocked_entry` and `missing_connector_floor`.

## CPU Scene Reports

```bash
cargo run --release --manifest-path splat_walk/Cargo.toml --bin walkability_harness -- --hunyuan-route-scene --issue148-standalone
cargo run --release --manifest-path splat_walk/Cargo.toml --bin walkability_harness -- --hunyuan-route-scene --issue148
```

## Walkthrough And Capture

Run either walk from the workspace root. Both play commands automatically stop after ten minutes and write a play report.

```bash
cargo run --release --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --play --issue148 --play-timeout-seconds=600 --play-report=godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/assembled-interactive-report.json
```

```bash
cargo run --release --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --play --issue148-standalone --play-timeout-seconds=600 --play-report=godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/standalone-interactive-report.json
```

The assembled eight-view Vulkan contact sheet is at `godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/captures/assembled_connector/candidate_contact_sheet.jpg`. To reproduce the capture, use an external timeout; the renderer checks RAM/VRAM headroom before it starts:

```bash
timeout --signal=TERM --kill-after=15s 600s cargo run --release --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --capture --issue148
```

## Required Rust Checks

```bash
cargo test --manifest-path splat_walk/Cargo.toml
cargo fmt --manifest-path splat_walk/Cargo.toml -- --check
cargo clippy --manifest-path splat_walk/Cargo.toml -- -D warnings
```
