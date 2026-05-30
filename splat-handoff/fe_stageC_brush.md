## Goal (Front-end Stage C — train the Gaussian splat with Brush)
Train the splat (`scene.ply`) — the VISUAL asset — from the COLMAP-format dataset.

## Why Brush
Brush (ArthurBrussee/brush) is a Rust + wgpu + Burn Gaussian-splatting trainer. Chosen
because it shares Bevy's GPU stack (wgpu), needs NO CUDA, runs cross-platform, and
ingests COLMAP format natively. It auto-grows/prunes splats (MCMC-style), so splat
count needs no manual tuning.

## Prereqs / Blockers
- Depends on Stage B (either path): `scene_dir/sparse/` + `scene_dir/images/`.
- Install Brush from prebuilt binaries: https://github.com/ArthurBrussee/brush/releases

## Commands
```bash
# Brush finds COLMAP data when given a dir containing images/ + sparse/
brush scene_dir/ --total-steps 30000 --export-path scene_dir/scene.ply
# --max-splats <N> optionally caps memory (useful when the Bevy target is VRAM-limited)
```

## Tuning notes
- Monitor in Brush's viewer; STOP when visual quality plateaus (typically 7k–30k steps).
- WATCH THE SPLAT COUNT. Each Gaussian costs VRAM + fill-rate at RUNTIME in Bevy.
  1–3M splats = comfortable; 10M+ will strain the Bevy renderer. Use `--max-splats`
  to cap if needed. This is a runtime-performance lever, decided HERE at train time.

## Files to create
- `scripts/splat_pipeline/train_brush.sh` — wraps the call, parameterized on
  `scene_dir`, with `--total-steps` and optional `--max-splats` as args.

## Acceptance criteria
- `scene_dir/scene.ply` produced.
- Opens in Brush's viewer and looks like the captured scene from viewpoints near the
  camera path.
- Splat count recorded; if >~3M, note it and consider re-export with `--max-splats`.

## Escalation conditions
- Quality never plateaus / looks smeared everywhere → upstream pose problem; revisit
  Stage B (try the other path) rather than training longer.
- Smears only when viewed from far off the camera path → expected (splat valid only
  near captured viewpoints); enforce player confinement downstream, not more training.
- VRAM blowout during training on 12GB → cap with `--max-splats`, lower resolution.

## Output
`scene_dir/scene.ply` — the VISUAL asset. Copied to
`splat_walk/assets/splats/<scene_name>/scene.ply` at integration.
