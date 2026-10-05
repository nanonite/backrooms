# Exact commands — end-to-end acceptance gate (#91)

All commands run from `/workspace/backrooms-workspace` unless stated.
Environment prepended for every pipeline invocation:

```bash
export PATH="/home/user/anaconda3/envs/nerfstudio/bin:/home/user/.local/bin:/home/user/.nvm/versions/node/v22.5.1/bin:$PATH"
export PYTHONNOUSERSITE=1                     # select conda gsplat prebuilt csrc.so
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1     # ns-export on torch 2.6+
export CONVERT_SCENES_ROOT="$PWD/data/scenes" # one-command scenes root
export SPLAT_TRANSFORM_NODE_MODULES="$PWD/scripts/splat_pipeline/node_modules"
```

## 1. Capture gate — one per fixture

```bash
python3 scripts/splat_pipeline/capture_gate.py data/videos/room_large.mp4 \
    --target-frames 150 --staging-dir /tmp/opencode/gates/room_large \
    --json /tmp/opencode/gates/room_large/gate.json
# repeat for corridor_x, corridor_straight, corridor_corner, corridor_t, dead_end
python3 scripts/splat_pipeline/capture_gate.py data/scenes/corridor_travel/video.mp4 \
    --target-frames 150 --staging-dir /tmp/opencode/gate_corridor_travel \
    --json /tmp/opencode/gate_corridor_travel/gate.json
```

## 2. One-command pipeline — synthetic `room_large` (fresh)

```bash
./scripts/splat_pipeline/convert_video.sh data/videos/room_large.mp4 room_large_e2e
```

Result: Stage A accepted (50 frames extracted); Stage B default path failed
(`glomap not found`); VGGT fallback failed (`PIL.UnidentifiedImageError` on
`images/frames.json`). Exit 1. Log: `logs/pipeline_room_large_fresh.log`.

## 3. One-command pipeline — synthetic `room_large` (resume, VGGT glob worked around)

```bash
mv data/scenes/room_large_e2e/images/frames.json data/scenes/room_large_e2e/frames_manifest.json
./scripts/splat_pipeline/run_pipeline.sh data/scenes/room_large_e2e
```

Result: Stage A skipped (recorded success); Stage B default path failed
(`glomap not found`); VGGT fallback reached model inference and OOM'd
(`torch.cuda.OutOfMemoryError`, peak GPU 11757 MiB). Exit 1.
Log: `logs/pipeline_room_large_resume.log`.

## 4. One-command pipeline — synthetic `corridor_x` (fresh + resume)

```bash
./scripts/splat_pipeline/convert_video.sh data/videos/corridor_x.mp4 corridor_x_e2e
mv data/scenes/corridor_x_e2e/images/frames.json data/scenes/corridor_x_e2e/frames_manifest.json
./scripts/splat_pipeline/run_pipeline.sh data/scenes/corridor_x_e2e
```

Result: Stage A accepted (31 frames); Stage B default path failed; VGGT OOM'd
(31 frames, peak GPU 11805 MiB). Exit 1.
Log: `logs/pipeline_corridor_x.log`.

## 5. GLOMAP prerequisite install attempt (the documented fix)

```bash
nix develop --command bash -c './environment/setup-pipeline-tools.sh install-glomap'
```

Result: nix dev shell evaluated; GLOMAP 1.2.0 cloned; `cmake` configuration
failed (`cmake/FindDependencies.cmake` → `CMakeLists.txt:23`,
`Configuring incomplete`). No `glomap` binary produced. Log:
`logs/glomap_install.log`.

## 6. Production-controller physics path (#85) — fresh re-run

```bash
cd godot_walk
godot4 --headless --path . --script res://scripts/verify_traversal.gd
```

Result: exit 0, `OK: traversal verified -- route both directions, blocking,
openings, corners, clearance, spawn and safety net all hold`. Log:
`logs/verify_traversal.log`.

## 7. Real-GPU render benchmark (walking fps at 1280x720)

```bash
DISPLAY=:1 python3 scripts/splat_pipeline/benchmark_reconstruction.py render \
    --project godot_walk --scene res://scenes/corridor.tscn \
    --resolution 1280x720 --frames 300 --warmup 60 --orbit-radius 1.0 \
    --splat godot_walk/assets/corridor_splat/corridor.ply
```

Result: exit 0, **58.94 fps at 1280x720**, 182,569 splats, stage VRAM 0.28 GiB,
stage RAM 0.63 GiB. Log: `logs/render_benchmark_corridor.log`.

## 8. Real-GPU screenshots (walkable scene)

```bash
cd godot_walk
DISPLAY=:1 godot4 --path . --rendering-driver vulkan --resolution 1280x720 \
    --script res://scripts/screenshot_scene.gd -- res://scenes/corridor.tscn
```

Result: exit 0; four non-blank PNGs (`overhead_orbit`, `player_pov`,
`player_pov_reverse`, `top_down`); `SPLAT_AABB: name=CorridorSplatNode
pos=(-97.7875, -62.1061, -101.8175) size=(139.4696, 97.0061, 134.5244)`.
Log: `logs/screenshot_corridor.log`; PNGs in `screenshots/`.

## 9. Pipeline integration tests (resumability + invalidation)

```bash
python3 -m pytest scripts/splat_pipeline/tests/test_pipeline_integration.py -q
```

Result: 4 passed in 5.92 s. Log: `logs/pytest_integration.log`.

## 10. Downstream verifier unit tests

```bash
python3 -m pytest scripts/splat_pipeline/tests/test_collision.py \
    scripts/splat_pipeline/tests/test_traversal_plan.py \
    scripts/splat_pipeline/tests/test_splat_frame.py -q
```

Result: see `logs/pytest_collision_traversal_frame.log`.
