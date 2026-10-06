# Exact commands — #100 PSX cleanup

All commands run from `/workspace/backrooms-workspace` unless stated.

## 1. Quantify the artifact (no GPU)

```bash
python3 - <<'PY'
# splats inside the observed room vs outside, and the opacity of the outside set
import sys; sys.path.insert(0, "scripts/splat_pipeline")
import numpy as np, splat_ply, splat_frame
c = splat_frame.FrameContract.load("godot_walk/assets/corridor_splat/alignment_manifest.json")
d = splat_ply.read_columns("godot_walk/assets/corridor_splat/corridor.ply",
                           ("x","y","z","opacity"))
raw = d[:, :3]; op = 1/(1+np.exp(-d[:,3]))
world = (c.ply_to_world.rotation() @ (raw - np.array(c.ply_to_world.origin_ply_units)).T).T \
        * c.ply_to_world.metres_per_unit
lo, hi = map(np.array, (c.splat_bounds.observed_min, c.splat_bounds.observed_max))
inside = np.all((world >= lo) & (world <= hi), axis=1)
print("inside", inside.mean(), "outside opacity median", np.median(op[~inside]))
PY
```

Result: 43.2% inside; outside opacity median 0.995 — so `alpha_cutoff` cannot
remove the floaters.

## 2. Produce the filtered derivative + report (no GPU)

```bash
python3 scripts/splat_pipeline/clean_splat.py \
    --ply godot_walk/assets/corridor_splat/corridor.ply \
    --manifest godot_walk/assets/corridor_splat/alignment_manifest.json \
    --out godot_walk/assets/corridor_splat/corridor_clean.ply \
    --report godot_walk/assets/corridor_splat/corridor_clean.report.json \
    --margin-m 0.5 --max-extent-m 0.30
```

Result: `source=182569 kept=124564 removed=58005`, bounds 56,437, extent 1,568,
opacity 0; `node_translation_world=(0.2404, 0.0082, 1.5605)`.

## 3. Import

```bash
cd godot_walk
godot4 --headless --path . --import
```

## 4. Real-GPU captures (forward/reverse at identical poses)

```bash
cd godot_walk
DISPLAY=:1 godot4 --path . --rendering-driver vulkan --resolution 1280x720 \
    --script res://scripts/screenshot_scene.gd -- res://scenes/corridor.tscn
DISPLAY=:1 godot4 --path . --rendering-driver vulkan --resolution 1280x720 \
    --script res://scripts/screenshot_scene.gd -- res://scenes/corridor_psx.tscn
DISPLAY=:1 godot4 --path . --rendering-driver vulkan --resolution 1280x720 \
    --script res://scripts/screenshot_scene.gd -- res://scenes/corridor_psx.tscn --no-psx
```

`spawn_pov` / `spawn_pov_reverse` were added to the harness: the true player view
from the contract's `PlayerSpawn` at eye height. The `player_pov` /
`player_pov_reverse` poses are the #74/#91 room-extreme poses and are kept
unchanged so before/after is strictly comparable. PNGs are under
`screenshots/{before,after,after_no_psx}/`; logs under `logs/capture_*.log`.

## 5. Frame rate

```bash
cd godot_walk
# vsync-capped (the #91 harness):
DISPLAY=:1 godot4 --path . --rendering-driver vulkan --resolution 1280x720 \
    --script res://scripts/measure_fps.gd -- \
    --scene=res://scenes/corridor_psx.tscn --frames=300 --warmup=60 --orbit-radius=1.0
# uncapped, to price the cleanup and the PSX pass:
DISPLAY=:1 godot4 --path . --disable-vsync --rendering-driver vulkan --resolution 1280x720 \
    --script res://scripts/measure_fps.gd -- \
    --scene=res://scenes/corridor_psx.tscn --frames=300 --warmup=60 --orbit-radius=1.0
```

## 6. Peak resources (same harness as #91)

```bash
export PATH="/home/user/anaconda3/envs/nerfstudio/bin:/home/user/.local/bin:$PATH"
DISPLAY=:1 python3 scripts/splat_pipeline/benchmark_reconstruction.py render \
    --project godot_walk --scene res://scenes/corridor_psx.tscn \
    --resolution 1280x720 --frames 300 --warmup 60 --orbit-radius 1.0 \
    --splat godot_walk/assets/corridor_splat/corridor_clean.ply \
    --label render_psx_clean --log logs/bench_psx.log --report logs/bench_report.json
```

## 7. Verifiers

```bash
cd godot_walk
godot4 --headless --path . --script res://scripts/verify_alignment.gd
godot4 --headless --path . --script res://scripts/verify_traversal.gd
# the presentation scene carries byte-identical collision; walk it too.
# It writes its own assets/corridor_splat/traversal_run_corridor_psx.log,
# leaving the accepted traversal_run.log for corridor.tscn untouched:
godot4 --headless --path . --script res://scripts/verify_traversal.gd -- --scene=res://scenes/corridor_psx.tscn
godot4 --headless --path . --script res://scripts/test_splat_alignment.gd
godot4 --headless --path . --script res://scripts/verify_scene.gd
godot4 --headless --path . --script res://scripts/test_psx_scene.gd
cd ..
python3 -m pytest scripts/splat_pipeline/tests/test_splat_cleanup.py -q
```
