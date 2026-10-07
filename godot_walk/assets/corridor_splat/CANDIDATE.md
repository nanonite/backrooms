# CANDIDATE.md — #103 cleanup candidate (`corridor_candidate.ply`)

Status: **candidate, not shipped.** The active presentation scene remains
`corridor_psx.tscn` on the #100 output (`corridor_clean.ply`). Nothing here
replaces it until someone chooses to.

## What it is

A derivative of the #100 cleanup result, produced by
`scripts/splat_pipeline/clean_candidate.py` with standard conservative
pruning:

```bash
python3 scripts/splat_pipeline/clean_candidate.py \
  --ply godot_walk/assets/corridor_splat/corridor_clean.ply \
  --manifest godot_walk/assets/corridor_splat/alignment_manifest.json \
  --baseline-report godot_walk/assets/corridor_splat/corridor_clean.report.json \
  --min-opacity 0.05 --max-extent-m 0.15 \
  --out godot_walk/assets/corridor_splat/corridor_candidate.ply \
  --report godot_walk/assets/corridor_splat/corridor_candidate.report.json
```

| | |
|---|---|
| input | `corridor_clean.ply` (#100), sha256 `88a20a95…e9d7af0`, verified against `corridor_clean.report.json` |
| splats | 124,564 → 111,454 (−13,110, 10.5%) |
| stages | extent>0.15 m: 10,646 · opacity<0.05: 2,464 · views: 0 · component: 0 |
| `node_translation_world` | `(0.2630066, 0.0055161, 1.6395417)` |
| output sha256 | in `corridor_candidate.report.json` |
| scene | `res://scenes/corridor_candidate_psx.tscn` (differs from `corridor_psx.tscn` in exactly two lines; `tests/test_candidate_scene.py` enforces this) |

Source `corridor.ply` and #100's `corridor_clean.ply` are untouched; the
three files exist side by side so any of the three can be re-rendered.

## Evidence

`godot_walk/evidence/2026-10-07-splat-cleanup-candidate/`:

- `REPORT.md` — before/after for all eight headings (black void, changed
  pixels, floaters), runtime, noise floor, limitations, and the
  cleanup-vs-new-coverage decision.
- `COMMANDS.md` — every command, including the ablation sweep.
- `ENVIRONMENT.md` — tool versions, GPU, provenance, determinism checks.
- `metrics.json`, `ablations/*.metrics.json` — the raw numbers.

Headline: black void 10.03% → 12.51% (+2.47 points), 8.83% of pixels
changed (2.00% went dark), floater pixels 656 → 800 mean, runtime
unchanged (240.96 → 240.77 fps). Rejected alternatives (component and
multi-view filters) remove visible floaters but cost +4.7 to +30.2 points
of black — see REPORT.md §2.

## Reproducing

1. `clean_candidate.py` as above (provenance check included).
2. `cd godot_walk && godot4 --headless --path . --import`
3. Capture both scenes with `capture_walk_envelope.gd --settle=200`.
4. `render_metrics.py --before before --after after --repeat before_repeat`.

The candidate PLY is gitignored (as all `.ply` assets are); the report that
records its digests and parameters is tracked. Re-run step 1 to regenerate
the byte-identical file.
