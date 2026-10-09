# Exact commands -- #101 bounded-walk assessment

All commands run from `/workspace/backrooms-workspace` unless stated.

## 1. Envelope + enclosure measurement (no GPU)

```bash
python3 scripts/splat_pipeline/volume_map.py \
    --manifest godot_walk/assets/corridor_splat/alignment_manifest.json \
    --report scripts/splat_pipeline/collision_benchmark.json \
    --glb godot_walk/assets/corridor_splat/collision/corridor_splat.collision.glb \
    --ply godot_walk/assets/corridor_splat/corridor.ply \
    --clean-ply godot_walk/assets/corridor_splat/corridor_clean.ply \
    --out godot_walk/evidence/2026-10-06-bounded-walk/volume_map.json
```

## 2. Import after the player.tscn edit (no GPU)

```bash
cd godot_walk
godot4 --headless --path . --import
```

## 3. Production-eye heading captures (real GPU, Vulkan, 1280x720)

```bash
cd godot_walk
DISPLAY=:1 godot4 --path . --rendering-driver vulkan --resolution 1280x720 \
    --script res://scripts/capture_walk_envelope.gd -- \
    --scene=res://scenes/corridor_psx.tscn --out=res://evidence/2026-10-06-bounded-walk/psx
```

NOTE: the shipped run passed `--scene <path>` (space form), which the script
does not parse -- it only accepts `--scene=<path>` / `--out=<path>`. The
captures therefore landed in the script default
`res://evidence/walk_envelope/spawn_headings/` (overwriting the stale
ceiling-clip captures there, which was the intent anyway) on the default scene
`corridor_psx.tscn`, and were copied into `2026-10-06-bounded-walk/` for the
report. Re-run with the `=` form to write directly to a fresh directory. The
script now reads the eye height from the production `Head` node either way.

## 4. Rendered black-void fractions (no GPU)

```bash
python3 - <<'PY'
from PIL import Image
import glob, os, json
out = {}
for p in sorted(glob.glob("godot_walk/evidence/2026-10-06-bounded-walk/spawn_headings/spawn_*.png")):
    im = Image.open(p).convert("RGB")
    px = list(im.getdata()); n = len(px)
    black = sum(1 for r,g,b in px if r<20 and g<20 and b<20)
    out[os.path.basename(p)] = {"black_void_pct": round(100*black/n,1)}
json.dump(out, open("godot_walk/evidence/2026-10-06-bounded-walk/heading_black_fraction.json","w"), indent=1)
PY
```

## 5. Synthetic-gate status (no GPU)

```bash
python3 scripts/splat_pipeline/capture_gate.py data/scenes/corridor_travel/video.mp4 --target-frames 30 --max-candidates 60
python3 scripts/splat_pipeline/capture_gate.py data/videos/corridor_x.mp4 --target-frames 30 --max-candidates 60
python3 scripts/splat_pipeline/capture_gate.py data/videos/room_large.mp4 --target-frames 30 --max-candidates 60
```

## 6. Verifiers

```bash
cd godot_walk
godot4 --headless --path . --script res://scripts/verify_alignment.gd
godot4 --headless --path . --script res://scripts/test_psx_scene.gd
godot4 --headless --path . --script res://scripts/verify_scene.gd
godot4 --headless --path . --script res://scripts/verify_traversal.gd
godot4 --headless --path . --script res://scripts/verify_traversal.gd -- --scene=res://scenes/corridor_psx.tscn
cd ..
python3 -m pytest scripts/splat_pipeline/tests/test_volume_map.py scripts/splat_pipeline/tests/test_splat_cleanup.py scripts/splat_pipeline/tests/test_traversal_plan.py scripts/splat_pipeline/tests/test_splat_frame.py -q
python3 -m pytest scripts/splat_pipeline/tests/ -q   # full suite: 6 pre-existing failures, same as #88/#99
```

## 7. Frame rate (real GPU)

```bash
cd godot_walk
DISPLAY=:1 godot4 --path . --rendering-driver vulkan --resolution 1280x720 \
    --script res://scripts/measure_fps.gd -- \
    --scene=res://scenes/corridor_psx.tscn --frames=300 --warmup=60 --orbit-radius=1.0
```
