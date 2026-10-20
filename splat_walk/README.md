# splat_walk

## Hunyuan route walkthrough

This is an experimental first-person walkthrough, not a calibrated reconstruction.
The run-05 Hunyuan GLB supplies visuals only. The #135 authored route GLB supplies
all collision: its floor, column proxy, and edge boundaries. The playable region
is the authored loop around the column. The rest of the Hunyuan scene is not
walkable. `registration_accepted=false` and `scale_calibrated=false` remain in
the manifest.

The visual asset is stored with Git LFS at
`godot_walk/generated_mesh_scenes/hunyuan_track_a_full_run/hunyuan_layers.glb`.
The route manifest verifies its SHA-256 before launch. Run `git lfs pull` after
cloning if the working file is still an LFS pointer.

## Room catalog

The versioned module registry is `splat_walk/room_catalog/catalog.json`.
It records the tagged walkthrough as an uncalibrated bounded reference zone,
with source and asset hashes, authored collision boundaries, controller
settings, validation evidence, and CPU runtime/resource measurements. Source-
observed openings are not tested traversal connectors.

Validate the registry and every referenced file from the repository root:

```sh
cargo run --manifest-path splat_walk/Cargo.toml --bin validate_room_catalog
```

The validator is CPU-only. It rejects missing or modified files, duplicate
module IDs, invalid connector transforms, unresolved connector endpoints, and
inconsistent registration/scale flags.

Launch from the repository root (including a clean `main` worktree) after GPU
use is approved:

```sh
cargo run --release --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --play
```

Controls: `WASD` moves relative to the view, mouse looks, `Esc` releases or
recaptures the cursor, a left click recaptures it, and `R` resets to the route
start. Touching the SafetyNet also resets the player. Reset events are written
to the play report. The window displays `UNCALIBRATED` throughout the session.

The launcher checks effective available host RAM and free memory on the first
NVIDIA GPU before creating the window. It refuses to launch below 10 GiB
available RAM or 4096 MiB free VRAM. The RAM check uses both `/proc/meminfo` and
cgroup v2 limits when present. These thresholds leave margin above the #137
capture's 8.84 GiB process peak. They are minimum launch guards, not a claim that
the live session stays below those values.

After the window closes, the app writes
`godot_walk/evidence/2026-10-13-hunyuan-track-a/interactive_play_report.json`.
The report records resource preflight, asset load time, median and p95 frame
time, peak process RSS, and reset events. Use `--play-report=/path/to/report.json`
to choose another report path.

Automated GPU runs can exit and write the report after a fixed duration with
`--play-timeout-seconds=N` (1-3600). Keep an outer process timeout as a hard
watchdog, for example:

```sh
timeout --signal=TERM --kill-after=5s 30s cargo run --release \
  --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- \
  --play --play-timeout-seconds=15 --play-report=/tmp/hunyuan-play-report.json
```

Run the CPU-only input and traversal smoke check without opening a window or
using the GPU:

```sh
cargo run --release --manifest-path splat_walk/Cargo.toml --bin hunyuan_route_scene -- --play-smoke
```

The smoke report is written to
`godot_walk/evidence/2026-10-13-hunyuan-track-a/interactive_play_smoke_report.json`.
It exercises the keyboard-to-motion mapping and `R` reset, then compares route
traversal with the locked #135 metrics. Unit tests cover cursor-lock transitions
and the one-shot reset request.

The `--play` mode uses the GPU for rendering but runs no Hunyuan inference. The
CPU-only `--play-smoke` command above remains suitable for automated checks.
