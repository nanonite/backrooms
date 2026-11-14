# Issue 246 — Picture-set consensus test with Mip-NeRF 360 `room` and known distractors

Status: **computed** (2026-11-14), CPU only, with the operator-approved
`facebook/dinov2-base` snapshot and the committed FreeView consensus tooling.
No Hunyuan run, no VGGT run, no download, no package install and no paid or
API-token call was made. Nothing was registered as a source; the room scene is
not in `godot_walk/source_library`.

The short result is mixed and is reported as such:

- **Ranking works well on this data.** Distractors never enter the top quartile
  of a collection at any tested `k`. The rank AUC of scene versus distractor is
  0.977–1.000 across all mixes.
- **The committed adaptive outlier flag does not work as a distractor filter.**
  It fires on two of three seeds and misses every distractor on the third; when
  it fires it also rejects 74% of the scene views. Its flag precision is 12.5%
  at a 10% mix, 31% at 25% and 58% at 50%.
- **The result does not generalise to near-miss or coherent rival scenes.** The
  57 distractors are visually unrelated photos (mean scene-to-distractor cosine
  0.020), so this is an easy separation. A coherent foreign cluster was not
  available to test.
- **VGGT is not warranted by this evidence.** The failure is flag calibration,
  not insufficient appearance separation. A geometry cue addresses a different
  failure (near-miss viewpoints of the same-looking place), which this test
  could not exercise.

## Data and environment

| Item | Value |
|------|-------|
| Scene | Mip-NeRF 360 `room`, `/home/goya/datasets/mipnerf360/room` (outside git) |
| Scene images | 311 at `images_4`, 779x519 px, sha256 verified against the local dataset manifest |
| Scene manifest | `/home/goya/datasets/mipnerf360/room-manifest.json`, sha256 `0a80ead3584cf0c26d05a1f64ad53f46bb238ea53185068f3ed12d347383443f` |
| Distractors | 57 unrelated photos, `data/pictures/single_backrooms_esq` (gitignored, not copied) |
| Distractor manifest | `godot_walk/source_library/sources/picture-set-d160eaa3cc847d5c/source_manifest-v3.json`, sha256 `6123576ee0bc0bfb31026c9c2bf49d80a73435978b1e915216db06a4a1f994c5` |
| Model | `facebook/dinov2-base`, 768-d CLS |
| Weights | `/home/goya/models/dinov2-base/model.safetensors`, sha256 `d73036b56966966d07975d696bde331762f37297e2f095de8cea0040c3aa0841` |
| Interpreter | `/home/goya/.venvs/freeview/bin/python` |
| Runtime | torch 2.15.0+cpu, transformers 5.23.0, device CPU |
| Preprocessing | `dinov2-cls-resize256-centercrop224-imagenet-v1` (unchanged from #210) |

The dataset license is unconfirmed, so only text is tracked: exact file lists,
hashes, embeddings, scores and flags. No image bytes were copied into git.

## Method

### Collections (`collections.json`)

All collections are deterministic, exact file lists with a role label
(`scene` or `distractor`) and a per-image sha256. Selection uses a SHA-256
ordering salted with the integer seed, not a random-number generator, so a
collection is reproducible independently of the Python version. Each collection
also has a `collection_sha256` over its canonical image list. Fifteen
collections were built:

| Collection | Seed | Scene | Distractor | Realized distractor share | SHA-256 (first 12) |
|---|---:|---:|---:|---:|---|
| `clean-full` | – | 311 | 0 | 0.0% | `a0911f1e30fe` |
| `clean-seed-2461` | 2461 | 57 | 0 | 0.0% | `ee20de648081` |
| `mixed-10-seed-2461` | 2461 | 57 | 6 | 9.5% | `8a883893c332` |
| `mixed-25-seed-2461` | 2461 | 57 | 19 | 25.0% | `e613f98d3878` |
| `mixed-50-seed-2461` | 2461 | 57 | 57 | 50.0% | `192b8a657a10` |
| `clean-seed-2462` | 2462 | 57 | 0 | 0.0% | `ae44f624803b` |
| `mixed-10-seed-2462` | 2462 | 57 | 6 | 9.5% | `286359ce6ad3` |
| `mixed-25-seed-2462` | 2462 | 57 | 19 | 25.0% | `ad48b9d31efa` |
| `mixed-50-seed-2462` | 2462 | 57 | 57 | 50.0% | `a3e499b9879c` |
| `clean-seed-2463` | 2463 | 57 | 0 | 0.0% | `7d724f7425b0` |
| `mixed-10-seed-2463` | 2463 | 57 | 6 | 9.5% | `3ffa98663d0d` |
| `mixed-25-seed-2463` | 2463 | 57 | 19 | 25.0% | `545cc45f757f` |
| `mixed-50-seed-2463` | 2463 | 57 | 57 | 50.0% | `8573d8bbc1c9` |
| `mixed-all` | – | 311 | 57 | 15.5% | `2b8559ec3d2f` |
| `distractor-only` | – | 0 | 57 | 100.0% | `f29bd3441074` |

A 57-view room sample is used for the seed sweep so that a true 50% mix is
possible with only 57 distractor images. The 10% mix realizes 9.5% (6
distractors); 25% and 50% are exact. Distractor subsets are nested across mix
levels for a given seed, so the 10% subset is a prefix of the 25% subset.

The full per-image path/sha256/width/height lists are in
[`collections.json`](collections.json), not repeated here.

### Scoring

The committed scores were used unchanged: `score_i(k)` is the mean cosine
similarity between view `i` and its `k` most similar other views, and the
outlier flag is the committed Otsu-style split on relevance to the top-consensus
reference, with its existing 0.85 explained-variance and 0.15 class-separation
guards. The `k` sweep is 3, 5, 8 plus **15 and 30**. The larger values are
justified because the room sample has 57 views: `k = 15` and `k = 30` probe
larger neighbourhoods while staying below the dominant cluster size, and show
whether the flag's behaviour is a small-`k` artefact. It is not: `k = 30`
produces the worst clean-collection false-positive rate (see below).

No frozen file was edited. No source was registered. The room scene is held
only as an in-memory labelled collection.

### Metrics

For each collection and `k`:

- **scene keep rate** = scene views not flagged / scene views.
- **distractor rejection rate** = distractors flagged / distractors.
- **flag precision** = distractors flagged / all flagged views.
- **rank percentile** = `rank / N` (lower is better).
- **rank AUC** = probability that a randomly chosen scene view outranks a
  randomly chosen distractor (ties count half).

### Picture mechanical score

The full `picture_seed_review_v1` review path loads a **registered** picture
set, so it cannot be pointed at the room scene without registering it. It was
not registered. The nearest clean equivalent, the same
`evaluate_and_rank_images` scoring core used by that review path (focus,
exposure and duplicate terms), was applied in memory with a clearly labelled
advisory record (`source_id: advisory-unregistered-246`). Nothing was written
to the source library.

## Results

### 1. DINOv2 similarity structure

| Pair | Pairs | Mean | Median | p10 | p90 |
|---|---:|---:|---:|---:|---:|
| scene to scene | 96,410 | 0.370 | 0.331 | 0.112 | 0.713 |
| distractor to distractor | 3,192 | 0.099 | 0.071 | -0.017 | 0.256 |
| scene to distractor | 17,727 | 0.020 | 0.015 | -0.042 | 0.083 |

Nearest-neighbour role mix:

| Images | Count | Nearest is other role | Nearest own (median) | Nearest other (median) |
|---|---:|---:|---:|---:|
| scene | 311 | 0 / 311 (0.0%) | 0.921 | 0.187 |
| distractor | 57 | 1 / 57 (1.8%) | 0.467 | 0.110 |

This is an **easy** separation. The room is a tight, highly redundant cluster
(nearest-neighbour median 0.921, consistent with sequential frames of one
sweep); the distractors are mutually dissimilar and almost orthogonal to the
room. Only one distractor photo has a room view as its nearest neighbour. The
test therefore exercises "unrelated foreign photos", not "a coherent wrong
scene" or "near-miss viewpoints of another similar room".

### 2. Mixed collections: ranking versus the flag

Pooled across the three seeds (rates are pooled counts, not means of rates):

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

What the table means:

- The **ranking** is consistently good: AUC 0.977–1.000, reference is always a
  scene view, and no distractor reaches the top quartile (below).
- The **rejection rate alone is misleading**. It is 66.7% because two seeds fire
  the flag and reject *all* of their distractors; the third seed fires nothing
  and rejects none. The flag's precision is low because it throws away most of
  the room along with the distractors.
- **Threshold acceptance is seed-dependent and non-monotonic in `k`.** Seeds
  2461 and 2463 accept the split at `k = 3/5/8`; seed 2462 never accepts it at
  any `k`. `mixed-all` accepts at `k = 3/8/15/30` but **not** at `k = 5`.
  There is no `k` at which the flag is reliable across collections.

### 3. Where distractors rank

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

No distractor appears in the top decile or top quartile of any mixed collection
at any tested `k`. The 50% mix is the hardest because it contains all 57
distractors: three of them are mutually similar (top distractor score 0.600),
which puts the best of them at about the 44th percentile, above the lowest room
close-up frames (0.332–0.441 in 57-frame samples). The 10% mix happens to
sample six mutually dissimilar distractors, so every one lands at the 90th
percentile or worse. The change across mixes is a subset-composition effect,
not a change in the score.

### 4. The adaptive flag on clean collections

| Collection | k | Reference | Threshold | Scene flagged | Scene keep rate |
|---|---:|---|---:|---:|---:|
| `clean-full` | 3 | `DSCF4702.JPG` | n/a | 0 / 311 | 100.0% |
| `clean-full` | 5 | `DSCF4701.JPG` | n/a | 0 / 311 | 100.0% |
| `clean-full` | 8 | `DSCF4702.JPG` | n/a | 0 / 311 | 100.0% |
| `clean-full` | 15 | `DSCF4702.JPG` | n/a | 0 / 311 | 100.0% |
| `clean-full` | 30 | `DSCF4726.JPG` | 0.433 | **226 / 311** | **27.3%** |
| `clean-seed-2461` | 3 | `DSCF4701.JPG` | 0.436 | **43 / 57** | **24.6%** |
| `clean-seed-2461` | 5 | `DSCF4733.JPG` | 0.375 | **42 / 57** | **26.3%** |
| `clean-seed-2461` | 8 | `DSCF4733.JPG` | 0.375 | **42 / 57** | **26.3%** |
| `clean-seed-2461` | 15 | `DSCF4820.JPG` | n/a | 0 / 57 | 100.0% |
| `clean-seed-2461` | 30 | `DSCF4822.JPG` | n/a | 0 / 57 | 100.0% |
| `clean-seed-2462` | 3 | `DSCF4700.JPG` | n/a | 0 / 57 | 100.0% |
| `clean-seed-2462` | 5 | `DSCF4702.JPG` | n/a | 0 / 57 | 100.0% |
| `clean-seed-2462` | 8 | `DSCF4681.JPG` | n/a | 0 / 57 | 100.0% |
| `clean-seed-2462` | 15 | `DSCF4676.JPG` | n/a | 0 / 57 | 100.0% |
| `clean-seed-2462` | 30 | `DSCF4823.JPG` | n/a | 0 / 57 | 100.0% |
| `clean-seed-2463` | 3 | `DSCF4701.JPG` | 0.419 | **42 / 57** | **26.3%** |
| `clean-seed-2463` | 5 | `DSCF4701.JPG` | 0.419 | **42 / 57** | **26.3%** |
| `clean-seed-2463` | 8 | `DSCF4734.JPG` | 0.386 | **41 / 57** | **28.1%** |
| `clean-seed-2463` | 15 | `DSCF4734.JPG` | 0.386 | **41 / 57** | **28.1%** |
| `clean-seed-2463` | 30 | `DSCF4822.JPG` | n/a | 0 / 57 | 100.0% |

This is the decisive table. On a collection with **no distractors at all**, the
flag rejects 74% of the room at `k = 3/5/8` for two of three seeds and 73% of
the full room at `k = 30`. The "outlier" class is not foreign content; it is the
part of the room that differs most from the chosen reference frame. The flag is
also silent for the third seed at every `k`, and silent for the full room at
`k = 3/5/8/15`. It is a relevance-to-reference split, not a scene-membership
test.

The kept 15 frames on `mixed-50-seed-2461` are exactly the frames above the
same 0.375 relevance threshold that keeps 15 frames of `clean-seed-2461` — the
distractors do not move the threshold. This is why the rejection rate looks
perfect when the flag fires: the split was determined by room-internal variation
and every distractor sits far below it.

### 5. Sanity: 57 unrelated photos alone

| k | Reference | Threshold | Flagged | Score mean | Score max |
|---|---|---:|---:|---:|---:|
| 3 | `bafkreiaavhom7z343dfvrk3drox6fgapnv4cv2swagu4tm3fbkdyk7b27q.webp` | n/a | 0 / 57 | 0.372 | 0.659 |
| 5 | `bafkreiaavhom7z343dfvrk3drox6fgapnv4cv2swagu4tm3fbkdyk7b27q.webp` | n/a | 0 / 57 | 0.328 | 0.600 |
| 8 | `bafkreiaavhom7z343dfvrk3drox6fgapnv4cv2swagu4tm3fbkdyk7b27q.webp` | n/a | 0 / 57 | 0.288 | 0.532 |
| 15 | `bafkreidqgnov2ttem62wkdeda3f77kjmebphr4jtieynh3atbbnsojyy6m.webp` | n/a | 0 / 57 | 0.235 | 0.449 |
| 30 | `bafkreidqgnov2ttem62wkdeda3f77kjmebphr4jtieynh3atbbnsojyy6m.webp` | n/a | 0 / 57 | 0.169 | 0.330 |

The adaptive flag accepts no split, so it reports "no outliers" for a collection
that has no coherent subset. The score **level** does show the incoherence, as
the next table shows, but the flag does not convert a level into a verdict.

### 6. Score level: coherent scene versus unrelated photos

| k | `clean-full` scene mean | `clean-full` scene min | `distractor-only` mean | `distractor-only` max |
|---|---:|---:|---:|---:|
| 3 | 0.888 | 0.696 | 0.372 | 0.659 |
| 5 | 0.870 | 0.666 | 0.328 | 0.600 |
| 8 | 0.848 | 0.608 | 0.288 | 0.532 |
| 15 | 0.813 | 0.524 | 0.235 | 0.449 |
| 30 | 0.765 | 0.424 | 0.169 | 0.330 |

At `k = 3/5/8` the full clean room's minimum is above the distractor-only
maximum, but the margin is small (0.037 at `k = 3`, 0.066 at `k = 5`). It is
**not** a safe fixed cut: a 57-frame room sample contains detail views as low as
0.332 at `k = 5`, while the distractor pool contains a mutually similar trio
reaching 0.600. An absolute threshold would misclassify both. Ranking within a
collection is the sound signal; an absolute threshold would need per-collection
calibration that this test cannot provide.

### 7. Highest-ranked room views and plausibility

`clean-full`, top five at `k = 5` (full five at every `k` are in
[`TABLES.md`](TABLES.md)):

| Rank | Image | Score | Mechanical rank |
|---:|---|---:|---:|
| 1 | `DSCF4701.JPG` | 0.978 | 18 |
| 2 | `DSCF4702.JPG` | 0.978 | 40 |
| 3 | `DSCF4724.JPG` | 0.977 | 24 |
| 4 | `DSCF4721.JPG` | 0.976 | 10 |
| 5 | `DSCF4725.JPG` | 0.974 | 15 |

I viewed a contact sheet of these frames (built in `/tmp`, not committed). They
are wide shots of the same room: piano, window, bookshelves, plants, lamp and
door, all from the same corner of the room. They are plausible representative
frames. The lowest-ranked room views are `DSCF4973`, `DSCF4939`, `DSCF4936`,
`DSCF4894` and `DSCF4972` (scores 0.666–0.699) — close-ups of a shelf, desk,
floor and sofa corner. The ranking tracks viewpoint breadth/centrality, not
whether a frame belongs to the room; every one of these is the same room.
Operator judgement of picture quality remains **PENDING**; the agent can only
describe what is visible.

### 8. Picture mechanical score comparison

| Collection | Scene rank percentile (median) | Distractor rank percentile (median) | Rank AUC | Spearman vs consensus k5 |
|---|---:|---:|---:|---:|
| `clean-full` | 0.502 | n/a | n/a | 0.494 |
| `mixed-10-seed-2461` | 0.508 | 0.484 | 0.509 | 0.104 |
| `mixed-25-seed-2461` | 0.513 | 0.487 | 0.536 | 0.087 |
| `mixed-50-seed-2461` | 0.526 | 0.447 | 0.488 | -0.051 |
| `mixed-10-seed-2462` | 0.476 | 0.952 | 0.760 | -0.053 |
| `mixed-25-seed-2462` | 0.474 | 0.789 | 0.609 | -0.052 |
| `mixed-50-seed-2462` | 0.518 | 0.421 | 0.495 | -0.104 |
| `mixed-10-seed-2463` | 0.508 | 0.603 | 0.535 | 0.043 |
| `mixed-25-seed-2463` | 0.513 | 0.368 | 0.517 | 0.040 |
| `mixed-50-seed-2463` | 0.526 | 0.430 | 0.485 | -0.066 |
| `mixed-all` | 0.508 | 0.351 | 0.475 | 0.055 |
| `distractor-only` | n/a | 0.509 | n/a | -0.156 |

The mechanical score is close to chance at separating the room from the
distractors: median rank percentiles are near 0.5 for both roles, rank AUC is
0.475–0.760 (only one 10% seed sample reaches 0.76), and its correlation with
the consensus rank is near zero. This is expected — it measures focus,
exposure and duplicate similarity, not scene membership — but it confirms that
the consensus ordering is carrying different information, not re-deriving the
existing quality rank.

## Verdict

### Does consensus reject distractors well enough to be a pre-Hunyuan filter?

**Not in its committed form.** The committed adaptive outlier flag is not a
distractor filter:

- it missed all 57 distractors on one of three seeds and all 18 at `k = 30`;
- when it fired, it rejected 74% of the scene as well (flag precision 12.5% at
  a 10% mix, 31% at 25%, 58% at 50%);
- on a clean room with no distractors it rejected 74% of the scene for two of
  three seeds, and 73% of the full room at `k = 30`;
- its threshold acceptance changes with the seed and with `k` in a
  non-monotonic way.

As a **ranking/shortlist score**, the result is much better on this data: no
distractor entered the top quartile, rank AUC was 0.977–1.000, and the
reference was always a scene view. But this is an easy set (unrelated photos,
mean cross cosine 0.020). A coherent foreign cluster was not available, so this
does not demonstrate the paper's harder claim. In particular, local consensus
rewards tightness: a coherent cluster of foreign photos can score as highly as
the scene. A test for that case is the obvious next experiment, not a conclusion
from this one.

### Is the optional geometry-aware cue (VGGT) warranted?

**Not from this evidence.** The binding failure is the uncalibrated relevance
split, not a lack of appearance separation. VGGT would help distinguish "same
appearance, different place" or near-miss viewpoints; those were not present.
The appropriate next steps are (1) treat consensus as a ranking signal, not the
current flag, and (2) test a **coherent rival scene** or same-style near-miss
distractors before paying for a geometry cue. VGGT was not run.

### What this adds beyond #210

#210 showed that appearance-only consensus selects the majority room in a
two-room video pool and rejects the operator-approved minority seed. This run
confirms the same mechanism with **labelled foreign photos** and a much larger
scene: the flag's split is room-internal viewpoint variation, not foreign
content. It also quantifies the good news that #210 could not: the ranking
score itself cleanly separates unrelated foreign photos on this dataset.

## Limitations

1. **Easy distractors.** 57 unrelated web photos, mean cross cosine 0.020, only
   one nearest-neighbour cross. A coherent wrong room or near-miss frames were
   not available. Do not generalise the AUC to them.
2. **Video-derived scene.** The 311 `images_4` frames are sequential frames from
   one capture, with nearest-neighbour median 0.921. They are much more
   redundant than a hand-collected picture set, which inflates the scene cluster
   tightness. The 57-frame samples reduce but do not remove this.
3. **Unvalidated flag thresholds.** The Otsu guards (0.85 explained variance,
   0.15 separation) are design defaults, not fitted; this run shows they are
   not a distractor classifier.
4. **Single embedding model.** One DINOv2 CLS preprocessing contract at 224 px.
   No other model or resolution was tested.
5. **Resolution.** `images_4` is 779x519. The downstream Hunyuan question is not
   addressed here.
6. **No registered source, no picture review path.** The full
   `picture_seed_review_v1` review requires a registered source, so it was not
   run; only its mechanical scoring core was reused in memory. State stays
   `registration_accepted: false`, `scale_calibrated: false`.
7. **Operator judgement PENDING.** The agent viewed a contact sheet to describe
   the top frames; whether they are the operator's preferred seed is not
   decided here.

## Files and artifacts

New code (all advisory, outside the frozen v1 workflow):

- `godot_walk/scripts/freeview_image_collections.py` — deterministic labelled
  collection builder, manifest verification, seeded SHA-256 sampling.
- `godot_walk/scripts/freeview_collection_evaluation.py` — role-aware keep,
  reject, precision, rank-AUC, similarity and mechanical comparison metrics.
- `godot_walk/scripts/freeview_collection_summary.py` — markdown table renderer.
- `godot_walk/scripts/run_freeview_picture_consensus.py` — `build`, `run`,
  `summary` and `weights` commands.
- Tests: `test_freeview_image_collections.py`,
  `test_freeview_collection_evaluation.py`,
  `test_freeview_picture_consensus.py`.

New evidence:

- [`collections.json`](collections.json) — 15 collections, exact file lists and
  sha256, manifests verified (311 scene, 57 distractor).
- [`results.json`](results.json) — every view's score, rank, relevance,
  outlier flag and threshold for every collection and `k`, plus similarity
  diagnostics and mechanical comparisons.
- [`TABLES.md`](TABLES.md) — the generated tables, including the full
  per-collection appendix and all `k` top views.
- `embeddings-facebook-dinov2-base-d73036b56966.json` — text-only embedding
  cache, 368 images, keyed by image sha256 and bound to the weight sha256 above.

No image bytes are tracked. The transient `*.json.lock` file is ignored.

## Reproduction

```bash
python3 godot_walk/scripts/run_freeview_picture_consensus.py build \
  --scene-dir /home/goya/datasets/mipnerf360/room/images_4 \
  --distractor-dir data/pictures/single_backrooms_esq \
  --scene-manifest /home/goya/datasets/mipnerf360/room-manifest.json \
  --scene-resolution images_4 \
  --distractor-manifest godot_walk/source_library/sources/picture-set-d160eaa3cc847d5c/source_manifest-v3.json \
  --output godot_walk/evidence/2026-11-14-issue-246/collections.json

/home/goya/.venvs/freeview/bin/python godot_walk/scripts/run_freeview_picture_consensus.py run \
  --collections godot_walk/evidence/2026-11-14-issue-246/collections.json \
  --model-dir /home/goya/models/dinov2-base \
  --output godot_walk/evidence/2026-11-14-issue-246/results.json

python3 godot_walk/scripts/run_freeview_picture_consensus.py summary \
  --results godot_walk/evidence/2026-11-14-issue-246/results.json \
  --output godot_walk/evidence/2026-11-14-issue-246/TABLES.md
```

A warm rerun reuses all 368 cached embeddings (`encoded: 0`). The results file
is written deterministically and is not rewritten when unchanged.

## Checks run

- `python3 -m pytest -q godot_walk/scripts` — **1495 passed, 5 skipped, 67
  subtests passed** (430.50 s).
- `ruff check` and `black --check` on all seven new Python files — clean.
- `build` run twice — second returned `status: unchanged`; exact file lists and
  hashes are stable.
- Re-ran the build after adding capacity validation — `status: unchanged`;
  collections did not move.
- Warm rerun of `run` returned `status: unchanged`, `encoded: 0`,
  `reused: 368`; the results file was not rewritten.
- The frozen-workflow hash test is part of the suite and passed; no frozen file
  was edited.
- `git status` shows only new files under `godot_walk/evidence/2026-11-14-issue-246/`,
  the new scripts/tests, and one `.gitignore` line for evidence cache locks.
- No Hunyuan run, no VGGT run, no download, no package install, no paid or
  API-token call, no source registration.

## PENDING (operator)

- Review the top-ranked frames and confirm whether they are representative for
  the intended room; this report can describe them but cannot approve them.
- Decide whether the consensus ranking is worth promoting to a versioned
  workflow. It is **not** proposed for promotion here, and the committed
  adaptive flag should not be used as an automatic filter.
- If the harder claim is wanted, approve a coherent rival-scene or near-miss
  distractor set (and only then consider VGGT).
