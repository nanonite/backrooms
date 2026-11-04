# Issue 196 — Variant-0 loss funnel and lever study

Date: 2026-11-04

This is a CPU-only measurement. No generator source, kept map, room artifact, or approval record was changed. All monkeypatches ran in scratch Python processes. No GPU work was done.

## Method

For each seed 1–300 and cell count 12 and 20, I built an in-memory `gmap-0.6.1` map with `MAX_SITE_LAYOUT_VARIANTS = 1`, so the successful layout is always variant 0. The seeded budget, tree RNG, module/catalog inputs, and later map stages were unchanged except where a row names a scratch lever. I separately built the same seed and cell count with `gmap-0.6.0` for the layout-similarity baseline.

The loss funnel counts **unfilled link-budget slots** (`budget - used`) on final maps. Explicit released reservations are counted first, then a qualifying retry loss, then the successful attempt's site outcome. A qualifying retry means a failed attempt had reserved sites and the immediately following attempt had fewer. “Other” means at least one site try found a valid placement, but the final map still had an unfilled slot. Each `zero-option try` means every frontier parent returned zero from `_all_site_options` on that try.

The rectangle-similarity score is the fraction of all 0.6.0 cell envelope polygons, including void cells, whose coordinates also occur in the same-seed 0.6.1 map. Scores are averaged equally over 300 seeds. Full-budget percentage uses only the 200 seeds with budget ≥1; two-link percentage uses all 300 seeds. Distribution entries are counts of `(budget, used)` among all 300.

The scratch driver is [`/tmp/issue196_lever_study.py`](/tmp/issue196_lever_study.py), SHA-256 `e69d2ac5a1b6df648d7c02ea571179a9dc472c25ea55a0d95c7029eece1bf002`. The 0.6.0 baseline cache and run outputs are also under `/tmp`. Example commands:

```bash
python3 /tmp/issue196_lever_study.py --funnel-only
python3 /tmp/issue196_lever_study.py --snap-only
python3 /tmp/issue196_lever_study.py --followup-only
python3 /tmp/issue196_lever_study.py --snapcap-only
```

## Task 1 — Where variant 0 loses links

| Cells | Budget-positive maps | Maps with missing links | Lost slots | No try | No options | Retry | Released | Other |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 12 | 200 | 153 | 199 | 1 (0.5%) | 182 (91.5%) | 0 (0%) | 0 (0%) | 16 (8.0%) |
| 20 | 200 | 103 | 127 | 0 (0%) | 101 (79.5%) | 0 (0%) | 0 (0%) | 26 (20.5%) |

The percentages use lost slots as the denominator. The site gate fired **732** times at 12 cells; **665** tries had no options and **67** found options. At 20 cells it fired **1,087** times; **948** had no options and **139** found options. At least one no-option try occurred in 196/200 budget-positive 12-cell maps and 197/200 20-cell maps. Every try had zero options in 136/200 and 77/200 maps, respectively.

| Loss reason | 12-cell examples | 20-cell examples | What the examples show |
|---|---|---|---|
| No try | 268 | None | Seed 268 had budget 1 and no site try in its successful attempt. |
| No options | 2, 3, 4 | 3, 4, 10 | Site tries fired, but every try found no legal site on any frontier parent. |
| Retry | None | None | No failed attempt with reservations was followed by an attempt with fewer reservations. There are no qualifying retry-loss examples. |
| Released | None | None | No reservation was released by `apply_links_v61`; there is no later-stage release reason to attribute. |
| Other | 7, 31, 41 | 2, 7, 8 | Each had budget 2, one reservation, one realized link, and no released reservation. A valid site existed, but no second site was reserved before growth ended. |

The funnel points to **site availability over the growth trajectory**. Increasing the chance to try cannot create geometry where the exhaustive legal placement set is empty. Later mutation stages are not the measured cause: no release was recorded, and no qualifying retry loss occurred.

## Task 2 — Scratch levers

Times are mean CPU wall-clock milliseconds per `build_map` over 300 maps. They include the scratch instrumentation. The early probability/force sweeps overlapped a separate CPU-bound pytest process for part of the run, so their timing comparisons are indicative, not a controlled benchmark. Snap and four-variant follow-ups ran without that competing test process. Rates and distributions are deterministic and unaffected by the timing contention.

### 12 cells

| Scratch setting | Full budget | Two links / 300 | `(budget, used)` counts | Mean similarity | ms/map |
|---|---:|---:|---|---:|---:|
| Variant 0, p=0.35 | 47/200 (23.5%) | 4 (1.3%) | (0,0):100; (1,0):91; (1,1):43; (2,0):46; (2,1):16; (2,2):4 | 40.8% | 120.7 |
| L1: p=0.60 | 56/200 (28.0%) | 6 (2.0%) | (0,0):100; (1,0):84; (1,1):50; (2,0):41; (2,1):19; (2,2):6 | 40.5% | 184.5 |
| L1: p=1.00 | 71/200 (35.5%) | 8 (2.7%) | (0,0):100; (1,0):71; (1,1):63; (2,0):34; (2,1):24; (2,2):8 | 40.3% | 279.6 |
| L1: force last 2 steps | 71/200 (35.5%) | 8 (2.7%) | (0,0):100; (1,0):71; (1,1):63; (2,0):34; (2,1):24; (2,2):8 | 40.3% | 280.4 |
| L1: force last 4 steps | 71/200 (35.5%) | 8 (2.7%) | (0,0):100; (1,0):71; (1,1):63; (2,0):34; (2,1):24; (2,2):8 | 40.3% | 276.5 |
| L2: re-arm after an empty try | 70/200 (35.0%) | 7 (2.3%) | (0,0):100; (1,0):71; (1,1):63; (2,0):34; (2,1):25; (2,2):7 | 40.3% | 256.1 |
| L3: explicit integer corner snap | 47/200 (23.5%) | 4 (1.3%) | (0,0):100; (1,0):91; (1,1):43; (2,0):46; (2,1):16; (2,2):4 | 40.8% | 74.7 |
| L5: force last 4 + re-arm | 71/200 (35.5%) | 8 (2.7%) | (0,0):100; (1,0):71; (1,1):63; (2,0):34; (2,1):24; (2,2):8 | 40.3% | 278.0 |
| L5: force last 4 + corner snap | 71/200 (35.5%) | 8 (2.7%) | (0,0):100; (1,0):71; (1,1):63; (2,0):34; (2,1):24; (2,2):8 | 40.3% | 161.1 |
| Best gate + cap 4 variants | 161/200 (80.5%) | 29 (9.7%) | (0,0):100; (1,0):2; (1,1):132; (2,0):3; (2,1):34; (2,2):29 | 35.6% | 662.5 |
| Best gate + snap + cap 4 | 161/200 (80.5%) | 29 (9.7%) | (0,0):100; (1,0):2; (1,1):132; (2,0):3; (2,1):34; (2,2):29 | 35.6% | 378.8 |

### 20 cells

| Scratch setting | Full budget | Two links / 300 | `(budget, used)` counts | Mean similarity | ms/map |
|---|---:|---:|---|---:|---:|
| Variant 0, p=0.35 | 97/200 (48.5%) | 16 (5.3%) | (0,0):100; (1,0):53; (1,1):81; (2,0):24; (2,1):26; (2,2):16 | 38.7% | 308.6 |
| L1: p=0.60 | 112/200 (56.0%) | 20 (6.7%) | (0,0):100; (1,0):42; (1,1):92; (2,0):20; (2,1):26; (2,2):20 | 38.5% | 461.9 |
| L1: p=1.00 | 132/200 (66.0%) | 28 (9.3%) | (0,0):100; (1,0):30; (1,1):104; (2,0):16; (2,1):22; (2,2):28 | 38.4% | 660.5 |
| L1: force last 2 steps | 132/200 (66.0%) | 28 (9.3%) | (0,0):100; (1,0):30; (1,1):104; (2,0):16; (2,1):22; (2,2):28 | 38.4% | 658.5 |
| L1: force last 4 steps | 132/200 (66.0%) | 28 (9.3%) | (0,0):100; (1,0):30; (1,1):104; (2,0):16; (2,1):22; (2,2):28 | 38.4% | 657.3 |
| L2: re-arm after an empty try | 127/200 (63.5%) | 23 (7.7%) | (0,0):100; (1,0):30; (1,1):104; (2,0):16; (2,1):27; (2,2):23 | 38.4% | 630.2 |
| L3: explicit integer corner snap | 97/200 (48.5%) | 16 (5.3%) | (0,0):100; (1,0):53; (1,1):81; (2,0):24; (2,1):26; (2,2):16 | 38.7% | 192.6 |
| L5: force last 4 + re-arm | 132/200 (66.0%) | 28 (9.3%) | (0,0):100; (1,0):30; (1,1):104; (2,0):16; (2,1):22; (2,2):28 | 38.4% | 649.9 |
| L5: force last 4 + corner snap | 132/200 (66.0%) | 28 (9.3%) | (0,0):100; (1,0):30; (1,1):104; (2,0):16; (2,1):22; (2,2):28 | 38.4% | 393.9 |
| Best gate + cap 4 variants | 195/200 (97.5%) | 61 (20.3%) | (0,0):100; (1,1):134; (2,1):5; (2,2):61 | 36.3% | 1065.5 |
| Best gate + snap + cap 4 | 195/200 (97.5%) | 61 (20.3%) | (0,0):100; (1,1):134; (2,1):5; (2,2):61 | 36.3% | 620.0 |

**L3 interpretation:** the snap probe enumerates integer child rectangles whose corner is exactly 1 m diagonally from an eligible existing-cell corner, then applies the existing placement and site filters. Every legal site is already in the original exhaustive integer placement set, so snapping adds no new valid site options. It keeps the same rates and similarity while pruning irrelevant placement checks. A separate half-metre-grid probe was attempted but failed when a fractional rectangle reached the existing integer-only `range()` placement code; it did not alter repository files or produce candidate metrics. The explicit integer snap probe is the compatible alternative.

## Recommendation for lead selection

No tested variant-0 lever reaches 60% full budget at 12 cells. Forcing attempts in the last four growth steps is the strongest useful variant-0 gate lever: 35.5% at 12 and 66.0% at 20. Re-arming after empty searches does not improve it. Exact corner snapping preserves outcomes and reduces measured candidate-generation time.

Combining the last-four-step gate with a four-layout cap reaches **80.5%** at 12 cells and **97.5%** at 20 cells. Adding exact snap enumeration keeps those results while reducing measured generation time by about 43% at 12 cells and 42% at 20 cells versus the same cap without snap. This meets the 60% full-budget target at both sizes, but two-link rate at 12 cells is 9.7%, below 15%; at 20 cells it is 20.3%. It also reduces 0.6.0 layout similarity to 35.6% and 36.3%.

If preserving layout similarity takes priority, variant 0 with p=0.35 remains the most similar measured configuration (40.8% / 38.7%), but misses the full-budget target. The lead should choose whether the four-variant candidate’s higher link rate justifies the lower similarity. No scratch lever has been applied to the committed or uncommitted generator paths.

## Lead correction (2026-11-04)

The scratch driver sets `draft._study_target` only after `grow()` returns. During growth, `remaining_steps` is therefore always 1, so `force_last` fires on every step. The rows labelled "force last 2/4 steps", and every combination built on them, actually measure p = 1.0; their numbers match the p = 1.0 row exactly. The conclusion is unchanged, since even always trying caps variant 0 at 35.5% (12 cells). The driver is kept as `lever_study.py`.
