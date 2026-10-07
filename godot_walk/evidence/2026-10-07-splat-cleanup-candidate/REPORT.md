# #103 cleanup candidate — fixed-view before/after report

Date: 2026-10-07 · Baseline: `ad2f1af` (#100) · Candidate: `corridor_candidate.ply`

## 1. What was run

One candidate derived from the shipped #100 result, then the same eight
fixed production-eye captures (fov 75, player `Head` eye, headings
e/ne/n/nw/w/sw/s/se, 1280x720, `--settle=200`) before and after:

- **Before** — `res://scenes/corridor_psx.tscn` (#100 output, untouched).
- **After** — `res://scenes/corridor_candidate_psx.tscn`, which differs from
  the baseline scene in exactly two lines: the splat resource and the
  splat node's `node_translation_world`
  (structural diff enforced by `test_candidate_scene.py`).

Both source PLYs (`corridor.ply`, `corridor_clean.ply`) are unmodified; the
candidate is a separate file with its own provenance report.

## 2. Candidate configuration (and why)

`clean_candidate.py --min-opacity 0.05 --max-extent-m 0.15`

| stage | removed |
|---|---|
| extent > 0.15 m | 10,646 |
| opacity < 0.05 | 2,464 |
| **total** | **13,110 of 124,564 (10.5%)** |

Provenance is *checked*: the input PLY's sha256 must equal the digest in
`corridor_clean.report.json` (it does: `88a20a95…e9d7af0`), and the report
records input/output digests, per-stage counts and the node translation
`(0.2630066, 0.0055161, 1.6395417)` that keeps the room fixed after GDGS
re-centres the smaller cloud.

Conservative opacity/scale pruning was chosen over the alternatives because
every alternative measured worse on the production eye:

| ablation (all captured, all measured) | removed | mean black Δ | mean changed | mean floater px |
|---|---|---|---|---|
| views (min 1) | 0 | +0.00 | 0.00% | 656 → 656 |
| **opacity_extent (extent 0.2 + opacity 0.05)** | **6,584** | **+1.18** | **3.58%** | 656 → 747 |
| **scale_opacity = candidate (extent 0.15 + opacity 0.05)** | **13,110** | **+2.47** | **8.83%** | 656 → 801 |
| extent only (0.15) | 10,646 | +2.45 | 8.80% | 656 → 787 |
| component ≥ 2 splats (voxel 0.08 m) | 13,483 | +4.66 | 13.07% | 656 → 2,553 |
| extent 0.15 + opacity + component | 23,111 | +7.44 | 20.16% | 656 → 3,180 |
| views ≥ 50 | 25,160 | +23.41 | 29.23% | 656 → 1,854 |
| component ≥ 1,000 | 37,184 | +21.46 | 35.55% | 656 → 437 |
| component ≥ 8,000 | 48,018 | +30.21 | 42.04% | 656 → 102 |

- **Spatial (component) filtering** removes detached blobs — including the
  visible ones — but only by cutting the corridor structure apart: at
  `min_component ≥ 2` the north view alone grows from 2,438 to 4,884
  floater pixels and +7.9 points of black, because the removed structure
  re-appears as new detached fragments and holes.
- **Multi-view filtering** is worse: `min_views ≥ 50` costs +23 points of
  black (n: 27% → 74%) and still leaves *more* floater pixels than it
  started with. `min_views ≥ 1` removes 0 splats — every surviving #100
  splat is already seen from ≥1 training view, so the stage is a no-op at
  any floor that doesn't destroy the room. (View counts came from the
  local COLMAP model + dataparser transforms; median 113, min 3.)
- **Training-time regularisation** was compared only on its recorded
  settings: the splatfacto run that produced the baseline records
  `use_scale_regularization: false` (`config.yml`), and retraining would
  change the entire scene rather than clean it, so the fixed-view
  comparison stays on post-hoc filters. No claim is made about what a
  retrained model would look like.

The candidate sits between `opacity_extent` (gentler, half the removal) and
the rejected stages. It was chosen as the standard cleanup that removes the
largest non-destructive share: 10.5% of splats for +2.5 points of black,
with per-heading black deltas between +0.1 (se) and +4.9 (n).

## 3. Before/after, all eight headings

Mean over headings (full per-heading data in `metrics.json`):

| metric | before | after | Δ |
|---|---|---|---|
| black void | 10.03% | 12.51% | **+2.47** |
| changed pixels | — | — | 8.83% (of which 2.00% went dark) |
| floater pixels | 656 | 800 | +144 |
| floater blobs | 0.75 | 1.75 | +1 |

Per heading:

| heading | black before → after | changed | floaters px before → after |
|---|---|---|---|
| e | 6.8 → 8.2 (+1.4) | 7.03% | 2,031 → 2,031 |
| ne | 8.1 → 10.4 (+2.2) | 6.21% | 779 → 779 |
| n | 27.4 → 32.2 (+4.9) | 11.34% | 2,438 → 2,438 |
| nw | 19.3 → 21.9 (+2.6) | 9.23% | 0 → 0 |
| w | 11.9 → 15.9 (+4.0) | 14.43% | 0 → 570 |
| sw | 4.1 → 6.7 (+2.6) | 12.04% | 0 → 368 |
| s | 2.6 → 4.7 (+2.1) | 8.67% | 0 → 214 |
| se | 0.0 → 0.1 (+0.1) | 1.67% | 0 → 0 |

Floater definition (fixed in `render_metrics.py`, not a CLI knob): a
foreground component that is neither the frame's largest component nor
touching the frame border, ≥ 100 px. Reported for both captures so the
candidate is credited with what it removed and charged for what its holes
created.

## 4. Runtime

`measure_fps.gd --frames=300 --warmup=60`, same machine, same resolution:

| scene | fps | elapsed / 300 frames |
|---|---|---|
| `corridor_psx.tscn` (before) | 240.96 | 1.245 s |
| `corridor_candidate_psx.tscn` (after) | 240.77 | 1.246 s |

The 13,110 removed splats (10.5%) change frame time by ~0.1 ms — below the
run-to-run resolution of this measurement. Cleanup is **not** a performance
lever here; the scene is GPU-bound on the compositor/PSX pass, not on
splat count.

## 5. Noise floor and convergence

- Two `--settle=200` captures of the *same* scene: **0.000% changed** in
  every heading — the pipeline is deterministic at this setting, so every
  non-zero number above is the cleanup, not the renderer.
- `--settle=5` capture vs `--settle=200`: 0.018% changed — the default is
  also effectively converged.
- First frame (`--settle=0`) vs converged: 7.73% changed — the GDGS render
  does need a few frames; captures used for evidence are all at 200.

## 6. Limitations

1. **Unseen surfaces cannot be recovered.** Cleanup only deletes. Where a
   removed splat covered nothing behind it, the pixel becomes background
   void — that is the entire +2.47 points of black. No authored mesh
   shell, fake background, or camera/FOV masking was used or is claimed.
2. **The visible floaters in e/ne/n survive every conservative filter.**
   They are made of splats that pass the opacity and extent thresholds, so
   only the destructive stages remove them — and those stages open more
   black than they close. The candidate does not claim to have fixed them;
   it added small fragments in w/sw/s (570/368/214 px) where its own
   deletions exposed void.
3. **Eight fixed headings from one spawn** — a walking player sees other
   angles; the numbers bound this evidence, not the whole corridor.
4. **fps measured at one resolution** (1280x720) on one machine.
5. View-count stages depend on local COLMAP/dataparser files that are
   gitignored; the reports record their paths (`sources.colmap_model`,
   `sources.dataparser`) but the files themselves are not in the repo, so
   those two ablations are reproducible only on a machine that still has
   the training run.

## 7. Decision: cleanup or new video coverage?

**Cleanup is exhausted for this capture.** The evidence says the trade is
one-directional: post-hoc filtering of the existing #100 result buys
removal of low-opacity/oversized splats at the cost of exposing void, and
the floaters a player actually sees cannot be deleted without cutting the
room open (component/views stages: +4.7 to +30.2 points of black for the
same floater pixels). The candidate is worth shipping as a modest standard
cleanup — fewer junk splats, no runtime cost, honest +2.5 points of black —
but it does not and cannot make the walk *look* better.

**Recommendation: new video coverage** of the corridor (the north end
first — n/nw are 19–27% black and hold 4.4k floater px even before
cleanup), retrained with scale regularisation enabled. That is the only
lever measured here that can both fill the voids and let aggressive
floater removal stop being destructive: floaters exist because surfaces
were under-observed, and filtering pixels cannot invent observations.

The candidate stays available for A/B (`corridor_candidate_psx.tscn`);
nothing replaces #100 until someone chooses to.
