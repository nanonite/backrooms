# Environment — #103 cleanup candidate evidence

Captured 2026-10-07 on the machine running this repository.

| component | value |
|---|---|
| git HEAD (baseline) | `ad2f1af` (#100) |
| Godot | 4.6.3.stable.7d41c59c4 (`godot4`) |
| renderer / driver | Forward+, Vulkan 1.4.329 |
| GPU | NVIDIA GeForce RTX 4070 Ti, driver 595.91.07 |
| display | `DISPLAY=:1` (X11), captures 1280x720 |
| Python | 3.12.3 |
| numpy / Pillow | 2.5.3 / 10.2.0 |
| splat renderer | GDGS addon (in-repo, `godot_walk/addons/gdgs`) |
| scene under test | `corridor_psx.tscn` vs `corridor_candidate_psx.tscn` (PSX compositor pass on, fov 75) |

## Provenance of the input

- Source: `data/scenes/corridor_travel` video → GLOMAP/COLMAP → splatfacto
  (`outputs/corridor_travel_v1/splatfacto/2026-07-10_163955`) → #100
  `clean_splat.py` → `godot_walk/assets/corridor_splat/corridor_clean.ply`
  (sha256 `88a20a95dd4df4dde98203f7fb934d17db93a9cb5d98f9e8c1625d478e9d7af0`,
  verified against `corridor_clean.report.json` by the candidate run).
- Alignment contract: `godot_walk/assets/corridor_splat/alignment_manifest.json`
  (5.128383849229126 m per unit), unchanged.
- The baseline splatfacto `config.yml` records
  `use_scale_regularization: false` — the training-time regularisation
  comparison in REPORT.md §2 is based on that record, not a retrain.

## Determinism

- Two `--settle=200` captures of the same scene: 0.000% of pixels differ
  (`before` vs `before_repeat`, `metrics.json` noise floor).
- `--settle=5` vs `--settle=200`: 0.018% differ. `--settle=0`: 7.73% differ.
  All before/after evidence uses `--settle=200`.

## Not available / not used

- `scipy` cannot be imported in this environment (wheel built against
  numpy 1.x, numpy 2.5.3 installed) — connected-component labelling in
  `render_metrics.py` is pure numpy (RLE + union-find) because of it.
- Local-only inputs (gitignored, their paths are recorded in the reports
  that used them — `sources.colmap_model` / `sources.dataparser`):
  `data/scenes/corridor_travel/sparse/0` (COLMAP),
  `outputs/corridor_travel_v1/splatfacto/2026-07-10_163955/dataparser_transforms.json`.
- No retraining was run for this issue; no mesh shell, fake background or
  camera/FOV masking exists anywhere in the evidence path.
