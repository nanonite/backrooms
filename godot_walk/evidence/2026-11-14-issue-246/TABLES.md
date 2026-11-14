# Issue 246 collection results

## DINOv2 similarity diagnostics

| Pair | Pairs | Mean | Median | p10 | p90 |
|---|---:|---:|---:|---:|---:|
| scene to scene | 96410 | 0.370 | 0.331 | 0.112 | 0.713 |
| distractor to distractor | 3192 | 0.099 | 0.071 | -0.017 | 0.256 |
| scene to distractor | 17727 | 0.020 | 0.015 | -0.042 | 0.083 |

Nearest-neighbour role mix (one nearest neighbour per image):

| Images | Count | Nearest is other role | Nearest own (median) | Nearest other (median) |
|---|---:|---:|---:|---:|
| scene | 311 | 0 / 311 (0.0%) | 0.921 | 0.187 |
| distractor | 57 | 1 / 57 (1.8%) | 0.467 | 0.110 |

## Collections

| Collection | Seed | Scene | Distractor | Realized distractor share | Collection SHA-256 (first 12) |
|---|---:|---:|---:|---:|---|
| clean-full | n/a | 311 | 0 | 0.0% | `a0911f1e30fe` |
| clean-seed-2461 | 2461 | 57 | 0 | 0.0% | `ee20de648081` |
| mixed-10-seed-2461 | 2461 | 57 | 6 | 9.5% | `8a883893c332` |
| mixed-25-seed-2461 | 2461 | 57 | 19 | 25.0% | `e613f98d3878` |
| mixed-50-seed-2461 | 2461 | 57 | 57 | 50.0% | `192b8a657a10` |
| clean-seed-2462 | 2462 | 57 | 0 | 0.0% | `ae44f624803b` |
| mixed-10-seed-2462 | 2462 | 57 | 6 | 9.5% | `286359ce6ad3` |
| mixed-25-seed-2462 | 2462 | 57 | 19 | 25.0% | `ad48b9d31efa` |
| mixed-50-seed-2462 | 2462 | 57 | 57 | 50.0% | `a3e499b9879c` |
| clean-seed-2463 | 2463 | 57 | 0 | 0.0% | `7d724f7425b0` |
| mixed-10-seed-2463 | 2463 | 57 | 6 | 9.5% | `3ffa98663d0d` |
| mixed-25-seed-2463 | 2463 | 57 | 19 | 25.0% | `545cc45f757f` |
| mixed-50-seed-2463 | 2463 | 57 | 57 | 50.0% | `8573d8bbc1c9` |
| mixed-all | n/a | 311 | 57 | 15.5% | `2b8559ec3d2f` |
| distractor-only | n/a | 0 | 57 | 100.0% | `f29bd3441074` |

## Clean collections (scene only)

| Collection | k | Reference | Threshold | Scene flagged | Scene keep rate |
|---|---:|---|---:|---:|---:|
| clean-full | 3 | `DSCF4702.JPG` | n/a | 0 / 311 | 100.0% |
| clean-full | 5 | `DSCF4701.JPG` | n/a | 0 / 311 | 100.0% |
| clean-full | 8 | `DSCF4702.JPG` | n/a | 0 / 311 | 100.0% |
| clean-full | 15 | `DSCF4702.JPG` | n/a | 0 / 311 | 100.0% |
| clean-full | 30 | `DSCF4726.JPG` | 0.433 | 226 / 311 | 27.3% |
| clean-seed-2461 | 3 | `DSCF4701.JPG` | 0.436 | 43 / 57 | 24.6% |
| clean-seed-2461 | 5 | `DSCF4733.JPG` | 0.375 | 42 / 57 | 26.3% |
| clean-seed-2461 | 8 | `DSCF4733.JPG` | 0.375 | 42 / 57 | 26.3% |
| clean-seed-2461 | 15 | `DSCF4820.JPG` | n/a | 0 / 57 | 100.0% |
| clean-seed-2461 | 30 | `DSCF4822.JPG` | n/a | 0 / 57 | 100.0% |
| clean-seed-2462 | 3 | `DSCF4700.JPG` | n/a | 0 / 57 | 100.0% |
| clean-seed-2462 | 5 | `DSCF4702.JPG` | n/a | 0 / 57 | 100.0% |
| clean-seed-2462 | 8 | `DSCF4681.JPG` | n/a | 0 / 57 | 100.0% |
| clean-seed-2462 | 15 | `DSCF4676.JPG` | n/a | 0 / 57 | 100.0% |
| clean-seed-2462 | 30 | `DSCF4823.JPG` | n/a | 0 / 57 | 100.0% |
| clean-seed-2463 | 3 | `DSCF4701.JPG` | 0.419 | 42 / 57 | 26.3% |
| clean-seed-2463 | 5 | `DSCF4701.JPG` | 0.419 | 42 / 57 | 26.3% |
| clean-seed-2463 | 8 | `DSCF4734.JPG` | 0.386 | 41 / 57 | 28.1% |
| clean-seed-2463 | 15 | `DSCF4734.JPG` | 0.386 | 41 / 57 | 28.1% |
| clean-seed-2463 | 30 | `DSCF4822.JPG` | n/a | 0 / 57 | 100.0% |

## Mixed collections, pooled across seeds

| Mix | k | Reference role (scene / distractor) | Scene kept | Distractors rejected | Flag precision | Rank AUC | Threshold accepted |
|---|---:|---|---:|---:|---:|---:|---:|
| 10% | 3 | 3 / 0 | 86 / 171 (50.3%) | 12 / 18 (66.7%) | 12 / 97 (12.4%) | 0.999 | 2 / 3 |
| 10% | 5 | 3 / 0 | 87 / 171 (50.9%) | 12 / 18 (66.7%) | 12 / 96 (12.5%) | 1.000 | 2 / 3 |
| 10% | 8 | 3 / 0 | 88 / 171 (51.5%) | 12 / 18 (66.7%) | 12 / 95 (12.6%) | 1.000 | 2 / 3 |
| 10% | 15 | 3 / 0 | 130 / 171 (76.0%) | 6 / 18 (33.3%) | 6 / 47 (12.8%) | 1.000 | 1 / 3 |
| 10% | 30 | 3 / 0 | 171 / 171 (100.0%) | 0 / 18 (0.0%) | n/a | 1.000 | 0 / 3 |
| 25% | 3 | 3 / 0 | 87 / 171 (50.9%) | 38 / 57 (66.7%) | 38 / 122 (31.1%) | 0.988 | 2 / 3 |
| 25% | 5 | 3 / 0 | 88 / 171 (51.5%) | 38 / 57 (66.7%) | 38 / 121 (31.4%) | 0.989 | 2 / 3 |
| 25% | 8 | 3 / 0 | 88 / 171 (51.5%) | 38 / 57 (66.7%) | 38 / 121 (31.4%) | 0.992 | 2 / 3 |
| 25% | 15 | 3 / 0 | 130 / 171 (76.0%) | 19 / 57 (33.3%) | 19 / 60 (31.7%) | 0.999 | 1 / 3 |
| 25% | 30 | 3 / 0 | 171 / 171 (100.0%) | 0 / 57 (0.0%) | n/a | 1.000 | 0 / 3 |
| 50% | 3 | 3 / 0 | 88 / 171 (51.5%) | 114 / 171 (66.7%) | 114 / 197 (57.9%) | 0.982 | 2 / 3 |
| 50% | 5 | 3 / 0 | 88 / 171 (51.5%) | 114 / 171 (66.7%) | 114 / 197 (57.9%) | 0.984 | 2 / 3 |
| 50% | 8 | 3 / 0 | 88 / 171 (51.5%) | 114 / 171 (66.7%) | 114 / 197 (57.9%) | 0.984 | 2 / 3 |
| 50% | 15 | 3 / 0 | 130 / 171 (76.0%) | 57 / 171 (33.3%) | 57 / 98 (58.2%) | 0.986 | 1 / 3 |
| 50% | 30 | 3 / 0 | 171 / 171 (100.0%) | 0 / 171 (0.0%) | n/a | 0.991 | 0 / 3 |
| all (15.5%) | 3 | 1 / 0 | 84 / 311 (27.0%) | 57 / 57 (100.0%) | 57 / 284 (20.1%) | 1.000 | 1 / 1 |
| all (15.5%) | 5 | 1 / 0 | 311 / 311 (100.0%) | 0 / 57 (0.0%) | n/a | 1.000 | 0 / 1 |
| all (15.5%) | 8 | 1 / 0 | 84 / 311 (27.0%) | 57 / 57 (100.0%) | 57 / 284 (20.1%) | 1.000 | 1 / 1 |
| all (15.5%) | 15 | 1 / 0 | 84 / 311 (27.0%) | 57 / 57 (100.0%) | 57 / 284 (20.1%) | 1.000 | 1 / 1 |
| all (15.5%) | 30 | 1 / 0 | 87 / 311 (28.0%) | 57 / 57 (100.0%) | 57 / 281 (20.3%) | 1.000 | 1 / 1 |

## Distractor ranking

| Mix | k | Distractor rank percentile (median) | Best distractor percentile | Distractors in top decile | Distractors in top quartile |
|---|---:|---:|---:|---:|---:|
| 10% | 3 | 0.960 | 0.905 | 0 | 0 |
| 10% | 5 | 0.960 | 0.921 | 0 | 0 |
| 10% | 8 | 0.960 | 0.921 | 0 | 0 |
| 10% | 15 | 0.960 | 0.921 | 0 | 0 |
| 10% | 30 | 0.960 | 0.921 | 0 | 0 |
| 25% | 3 | 0.877 | 0.671 | 0 | 0 |
| 25% | 5 | 0.882 | 0.671 | 0 | 0 |
| 25% | 8 | 0.882 | 0.711 | 0 | 0 |
| 25% | 15 | 0.882 | 0.737 | 0 | 0 |
| 25% | 30 | 0.882 | 0.763 | 0 | 0 |
| 50% | 3 | 0.751 | 0.439 | 0 | 0 |
| 50% | 5 | 0.754 | 0.447 | 0 | 0 |
| 50% | 8 | 0.754 | 0.439 | 0 | 0 |
| 50% | 15 | 0.754 | 0.439 | 0 | 0 |
| 50% | 30 | 0.754 | 0.456 | 0 | 0 |
| all (15.5%) | 3 | 0.924 | 0.848 | 0 | 0 |
| all (15.5%) | 5 | 0.924 | 0.848 | 0 | 0 |
| all (15.5%) | 8 | 0.924 | 0.848 | 0 | 0 |
| all (15.5%) | 15 | 0.924 | 0.848 | 0 | 0 |
| all (15.5%) | 30 | 0.924 | 0.848 | 0 | 0 |

## Sanity: distractor-only collection

| k | Reference | Threshold | Flagged | Score mean | Score max |
|---|---|---:|---:|---:|---:|
| 3 | `bafkreiaavhom7z343dfvrk3drox6fgapnv4cv2swagu4tm3fbkdyk7b27q.webp` | n/a | 0 / 57 | 0.372 | 0.659 |
| 5 | `bafkreiaavhom7z343dfvrk3drox6fgapnv4cv2swagu4tm3fbkdyk7b27q.webp` | n/a | 0 / 57 | 0.328 | 0.600 |
| 8 | `bafkreiaavhom7z343dfvrk3drox6fgapnv4cv2swagu4tm3fbkdyk7b27q.webp` | n/a | 0 / 57 | 0.288 | 0.532 |
| 15 | `bafkreidqgnov2ttem62wkdeda3f77kjmebphr4jtieynh3atbbnsojyy6m.webp` | n/a | 0 / 57 | 0.235 | 0.449 |
| 30 | `bafkreidqgnov2ttem62wkdeda3f77kjmebphr4jtieynh3atbbnsojyy6m.webp` | n/a | 0 / 57 | 0.169 | 0.330 |

## Score levels: coherent scene vs unrelated photos

| k | Clean-full scene mean | Clean-full scene min | Distractor-only mean | Distractor-only max |
|---|---:|---:|---:|---:|
| 3 | 0.888 | 0.696 | 0.372 | 0.659 |
| 5 | 0.870 | 0.666 | 0.328 | 0.600 |
| 8 | 0.848 | 0.608 | 0.288 | 0.532 |
| 15 | 0.813 | 0.524 | 0.235 | 0.449 |
| 30 | 0.765 | 0.424 | 0.169 | 0.330 |

## Picture mechanical score comparison

| Collection | Scene rank percentile (median) | Distractor rank percentile (median) | Rank AUC | Spearman vs consensus k5 |
|---|---:|---:|---:|---:|
| clean-full | 0.502 | n/a | n/a | 0.494 |
| clean-seed-2461 | 0.509 | n/a | n/a | 0.512 |
| mixed-10-seed-2461 | 0.508 | 0.484 | 0.509 | 0.104 |
| mixed-25-seed-2461 | 0.513 | 0.487 | 0.536 | 0.087 |
| mixed-50-seed-2461 | 0.526 | 0.447 | 0.488 | -0.051 |
| clean-seed-2462 | 0.509 | n/a | n/a | 0.415 |
| mixed-10-seed-2462 | 0.476 | 0.952 | 0.760 | -0.053 |
| mixed-25-seed-2462 | 0.474 | 0.789 | 0.609 | -0.052 |
| mixed-50-seed-2462 | 0.518 | 0.421 | 0.495 | -0.104 |
| clean-seed-2463 | 0.509 | n/a | n/a | 0.406 |
| mixed-10-seed-2463 | 0.508 | 0.603 | 0.535 | 0.043 |
| mixed-25-seed-2463 | 0.513 | 0.368 | 0.517 | 0.040 |
| mixed-50-seed-2463 | 0.526 | 0.430 | 0.485 | -0.066 |
| mixed-all | 0.508 | 0.351 | 0.475 | 0.055 |
| distractor-only | n/a | 0.509 | n/a | -0.156 |

## Highest-ranked scene views (clean-full)

| k | Rank | Image | Score | Mechanical rank | Outlier |
|---|---:|---|---:|---:|---|
| 3 | 1 | `DSCF4702.JPG` | 0.980 | 40 | - |
| 3 | 2 | `DSCF4724.JPG` | 0.980 | 24 | - |
| 3 | 3 | `DSCF4701.JPG` | 0.979 | 18 | - |
| 3 | 4 | `DSCF4721.JPG` | 0.979 | 10 | - |
| 3 | 5 | `DSCF4722.JPG` | 0.978 | 23 | - |
| 5 | 1 | `DSCF4701.JPG` | 0.978 | 18 | - |
| 5 | 2 | `DSCF4702.JPG` | 0.978 | 40 | - |
| 5 | 3 | `DSCF4724.JPG` | 0.977 | 24 | - |
| 5 | 4 | `DSCF4721.JPG` | 0.976 | 10 | - |
| 5 | 5 | `DSCF4725.JPG` | 0.974 | 15 | - |
| 8 | 1 | `DSCF4702.JPG` | 0.974 | 40 | - |
| 8 | 2 | `DSCF4724.JPG` | 0.973 | 24 | - |
| 8 | 3 | `DSCF4701.JPG` | 0.973 | 18 | - |
| 8 | 4 | `DSCF4721.JPG` | 0.971 | 10 | - |
| 8 | 5 | `DSCF4722.JPG` | 0.969 | 23 | - |
| 15 | 1 | `DSCF4702.JPG` | 0.965 | 40 | - |
| 15 | 2 | `DSCF4701.JPG` | 0.964 | 18 | - |
| 15 | 3 | `DSCF4724.JPG` | 0.964 | 24 | - |
| 15 | 4 | `DSCF4726.JPG` | 0.961 | 13 | - |
| 15 | 5 | `DSCF4700.JPG` | 0.961 | 9 | - |
| 30 | 1 | `DSCF4726.JPG` | 0.944 | 13 | - |
| 30 | 2 | `DSCF4700.JPG` | 0.944 | 9 | - |
| 30 | 3 | `DSCF4725.JPG` | 0.942 | 15 | - |
| 30 | 4 | `DSCF4724.JPG` | 0.942 | 24 | - |
| 30 | 5 | `DSCF4702.JPG` | 0.941 | 40 | - |

## Per-collection appendix

| Collection | N | Ref k3 | Ref k5 | Ref k8 | k5 scene kept | k5 distractors rejected | k5 AUC | k15 AUC | k30 AUC |
|---|---:|---|---|---|---:|---:|---:|---:|---:|
| clean-full | 311 | scene | scene | scene | 100.0% | n/a | n/a | n/a | n/a |
| clean-seed-2461 | 57 | scene | scene | scene | 26.3% | n/a | n/a | n/a | n/a |
| mixed-10-seed-2461 | 63 | scene | scene | scene | 26.3% | 100.0% | 1.000 | 1.000 | 1.000 |
| mixed-25-seed-2461 | 76 | scene | scene | scene | 26.3% | 100.0% | 0.982 | 0.998 | 1.000 |
| mixed-50-seed-2461 | 114 | scene | scene | scene | 26.3% | 100.0% | 0.980 | 0.986 | 0.991 |
| clean-seed-2462 | 57 | scene | scene | scene | 100.0% | n/a | n/a | n/a | n/a |
| mixed-10-seed-2462 | 63 | scene | scene | scene | 100.0% | 0.0% | 1.000 | 1.000 | 1.000 |
| mixed-25-seed-2462 | 76 | scene | scene | scene | 100.0% | 0.0% | 0.986 | 0.998 | 1.000 |
| mixed-50-seed-2462 | 114 | scene | scene | scene | 100.0% | 0.0% | 0.989 | 0.983 | 0.986 |
| clean-seed-2463 | 57 | scene | scene | scene | 26.3% | n/a | n/a | n/a | n/a |
| mixed-10-seed-2463 | 63 | scene | scene | scene | 26.3% | 100.0% | 1.000 | 1.000 | 1.000 |
| mixed-25-seed-2463 | 76 | scene | scene | scene | 28.1% | 100.0% | 1.000 | 1.000 | 1.000 |
| mixed-50-seed-2463 | 114 | scene | scene | scene | 28.1% | 100.0% | 0.983 | 0.989 | 0.994 |
| mixed-all | 368 | scene | scene | scene | 100.0% | 0.0% | 1.000 | 1.000 | 1.000 |
| distractor-only | 57 | distractor | distractor | distractor | n/a | 0.0% | n/a | n/a | n/a |

