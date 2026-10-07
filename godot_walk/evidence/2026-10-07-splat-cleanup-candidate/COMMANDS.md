# Commands — #103 cleanup candidate

All commands run from the repository root unless noted. `godot4` is Godot
4.6.3 on `PATH`; captures need a display (`DISPLAY=:1` on this machine).

## 1. Build the candidate (reproducible)

```bash
python3 scripts/splat_pipeline/clean_candidate.py \
  --ply godot_walk/assets/corridor_splat/corridor_clean.ply \
  --manifest godot_walk/assets/corridor_splat/alignment_manifest.json \
  --baseline-report godot_walk/assets/corridor_splat/corridor_clean.report.json \
  --min-opacity 0.05 --max-extent-m 0.15 \
  --out godot_walk/assets/corridor_splat/corridor_candidate.ply \
  --report godot_walk/assets/corridor_splat/corridor_candidate.report.json
```

Expected stdout: `input=124564 kept=111454 removed=13110` with
`{"views": 0, "component": 0, "extent": 10646, "opacity": 2464}` and
`node_translation_world=(0.2630, 0.0055, 1.6395)`.

The `--baseline-report` check refuses to run if the input PLY is not the
shipped #100 output (sha256 mismatch → exit).

## 2. Import the new asset into Godot

```bash
cd godot_walk && godot4 --headless --path . --import
```

## 3. Fixed-view captures (all eight headings)

```bash
# before (baseline scene, #100 output)
DISPLAY=:1 godot4 --path . --rendering-driver vulkan --resolution 1280x720 \
  --script res://scripts/capture_walk_envelope.gd -- \
  --scene=res://scenes/corridor_psx.tscn \
  --out=res://evidence/2026-10-07-splat-cleanup-candidate/before --settle=200

# after (candidate scene) — identical camera, fov 75, same spawn
DISPLAY=:1 godot4 --path . --rendering-driver vulkan --resolution 1280x720 \
  --script res://scripts/capture_walk_envelope.gd -- \
  --scene=res://scenes/corridor_candidate_psx.tscn \
  --out=res://evidence/2026-10-07-splat-cleanup-candidate/after --settle=200

# noise floor: second capture of the SAME baseline scene
# (... --scene=res://scenes/corridor_psx.tscn --out=.../before_repeat --settle=200)

# convergence probes: same baseline scene at other settle values
# (... --out=.../convergence_settle5 --settle=5)
# (... --out=.../convergence_settle0 --settle=0)
```

## 4. Metrics

```bash
python3 scripts/splat_pipeline/render_metrics.py \
  --before godot_walk/evidence/2026-10-07-splat-cleanup-candidate/before \
  --after  godot_walk/evidence/2026-10-07-splat-cleanup-candidate/after \
  --repeat godot_walk/evidence/2026-10-07-splat-cleanup-candidate/before_repeat \
  --out    godot_walk/evidence/2026-10-07-splat-cleanup-candidate/metrics.json
```

Same command with `--after ablations/<name>` produced every ablation's
`ablations/<name>.metrics.json`.

## 5. Runtime

```bash
for scene in corridor_psx corridor_candidate_psx; do
  DISPLAY=:1 godot4 --path . --rendering-driver vulkan --resolution 1280x720 \
    --script res://scripts/measure_fps.gd -- \
    --scene=res://scenes/${scene}.tscn --frames=300 --warmup=60
done
# FPS_JSON baseline 240.96 fps / candidate 240.77 fps
```

## 6. Ablations (stage comparison)

Each ablation is `clean_candidate.py` with different thresholds, written to
`godot_walk/assets/corridor_splat/ablation_<name>.ply` (gitignored) plus
`ablations/<name>.report.json` (tracked), imported, captured with
`--splat=… --splat-translation=…` overrides of the baseline scene, then run
through `render_metrics.py`. Example:

```bash
python3 scripts/splat_pipeline/clean_candidate.py \
  --ply godot_walk/assets/corridor_splat/corridor_clean.ply \
  --manifest godot_walk/assets/corridor_splat/alignment_manifest.json \
  --baseline-report godot_walk/assets/corridor_splat/corridor_clean.report.json \
  --min-component-splats 2 --voxel-m 0.08 \
  --out godot_walk/assets/corridor_splat/ablation_component2.ply \
  --report godot_walk/evidence/2026-10-07-splat-cleanup-candidate/ablations/component2.report.json

cd godot_walk && godot4 --headless --path . --import
DISPLAY=:1 godot4 --path . --rendering-driver vulkan --resolution 1280x720 \
  --script res://scripts/capture_walk_envelope.gd -- \
  --scene=res://scenes/corridor_psx.tscn \
  --out=res://evidence/2026-10-07-splat-cleanup-candidate/ablations/component2 \
  --settle=200 \
  --splat=res://assets/corridor_splat/ablation_component2.ply \
  --splat-translation=0.xxxx,0.yyyy,0.zzzz   # from that report's node_translation_world
```

View-count stages additionally need the local (gitignored) inputs:

```bash
  --min-views 50 \
  --colmap data/scenes/corridor_travel/sparse/0 \
  --dataparser outputs/corridor_travel_v1/splatfacto/2026-07-10_163955/dataparser_transforms.json
```

## 7. Tests

```bash
python3 -m pytest scripts/splat_pipeline/tests/ -q
# new for #103: test_clean_candidate.py, test_candidate_scene.py,
#                test_render_metrics.py (incl. floater labelling)
```
