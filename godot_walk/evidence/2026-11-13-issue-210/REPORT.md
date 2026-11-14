# Issue 210 — FreeView-style view-consensus selection for seed frames

Status: **retrospective computed** (2026-11-14) with the operator-approved
`facebook/dinov2-base` snapshot and CPU interpreter. The result is mixed and is
reported honestly: one approved seed ranks near the top, the current industrial
seed does not, and the Viola seed is in a near-tie with its neighbours. No
Hunyuan run, VGGT run, paid service, download or package install was performed
in this attempt.

## Weight and runtime status (resolved)

The operator decision of 2026-11-14 approved the model download and a uv-managed
interpreter. The previously recorded blocker is closed.

| Item | Value |
|------|-------|
| Model | `facebook/dinov2-base`, 768-d CLS |
| Snapshot | `/home/goya/models/dinov2-base` (outside the repo) |
| Weight file | `model.safetensors`, 346,345,912 bytes |
| Weight SHA-256 | `d73036b56966966d07975d696bde331762f37297e2f095de8cea0040c3aa0841` |
| Interpreter | `/home/goya/.venvs/freeview/bin/python` |
| Runtime | torch 2.15.0+cpu, transformers 5.23.0 |
| Device | CPU only |

`run_freeview_consensus.py weights --model-dir /home/goya/models/dinov2-base`
reports `status: available` and the identity above. The earlier machine-wide
audit is kept in [`weight-audit.json`](weight-audit.json) as history; it is no
longer the current state.

One code correction was needed for the official snapshot. Its `config.json`
records the pretraining `image_size: 518`, while this contract runs inference at
224. DINOv2 is patch-based and interpolates its position embeddings, so the
snapshot check now validates the patch size and the 224 grid instead of
requiring `image_size == 224`. The fixed preprocessing is unchanged
(`dinov2-cls-resize256-centercrop224-imagenet-v1`), so the cache contract is the
same.

Two small tooling changes came out of the run. `weights` now accepts
`--model-dir`, because the approved snapshot lives outside the Hugging Face hub
cache. The `rank` report now records only the stable cache path and entry count;
the per-run `created`/`encoded`/`reused` counters are printed to stdout instead.
That keeps the evidence JSON idempotent: a warm rerun returns `unchanged` and
does not rewrite the file.

## Method as implemented

All new files are advisory and outside the frozen v1 path.

| File | Purpose |
|------|---------|
| `godot_walk/scripts/freeview_consensus.py` | local-consensus score, deterministic ranks, appearance-outlier flag |
| `godot_walk/scripts/freeview_embedding_cache.py` | text-only cache keyed by frame SHA-256 and full model identity |
| `godot_walk/scripts/freeview_embeddings.py` | deterministic DINOv2 CLS preprocessing and offline-only local-snapshot reader |
| `godot_walk/scripts/run_freeview_consensus.py` | `weights`, `inventory` and `rank` commands |
| `godot_walk/seed_review/WORKFLOW_V1_1_ADDENDUM.md` | version 1.1.0 advisory addendum |
| `godot_walk/scripts/test_freeview_*.py` | scoring, cache, embedding and frozen-workflow tests |

The consensus score is `score_i(k) = mean of the k largest cosine similarities
between view i and every other view`, swept over `k = 3, 5, 8`. The effective
`k` is capped at `N - 1`; a single view scores `0.0` with no peers. Ranks are
score-descending with frame ID as the tie-break, so permuting the input order
returns an identical result. No RNG is used.

The outlier flag uses the top-consensus view as the reference and a
one-dimensional Otsu split on relevance-to-reference, accepted only when the
class means differ by at least 0.15 cosine and the split explains at least 0.85
of the variance. These thresholds are conservative design defaults, not
validated against labelled data. This is the paper's appearance cue only; the
geometry-aware cue is not implemented.

Embeddings are cached as JSON under
`godot_walk/source_library/sources/<source>/freeview/`. The cache header binds
`model_id`, `weights_sha256`, `embedding_dim` and `preprocessing_version`;
entries are keyed by the frame SHA-256. The cache is text-only, merges under an
exclusive lock, refuses to replace a hash with a different vector, and stores
L2-normalized values to seven decimals.

The frozen v1 workflow was not modified. The addendum is a separate versioned
record, and the v1 runner does not read it.

## Retrospective validation

The agreed ground truth is:

| Source | Approved frame | Role |
|--------|----------------|------|
| `video-ccf9722164a0bdc8` | `frame_1097` | industrial-hall seed, selected at event 4, replaced at event 32 |
| `video-ccf9722164a0bdc8` | `frame_4560` | debris-window-rock-room seed, event 32, current |
| `video-b9161c467ed2d30a` | `frame_2731` | Bill Viola room seed, event 4, current |

The registered picture set `picture-set-d160eaa3cc847d5c` is **not** validation
data: the 2026-11-13 note says it has no approved seed and is owned by #246.

### Industrial source (`video-ccf9722164a0bdc8`, 17 unique frames)

Full record: [`view-consensus-industrial.json`](view-consensus-industrial.json).
Rows are ordered by the existing mechanical score. "Outlier" is the appearance
flag at k3/k5/k8.

| Mech rank | Frame | Mech score | k3 score | k3 rank | k5 score | k5 rank | k8 score | k8 rank | Outlier |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | `frame_4486` | 0.810018 | 0.660570 | 15 | 0.653765 | 14 | 0.644244 | 14 | yes/yes/yes |
| 2 | `frame_1100` | 0.678210 | 0.984413 | 3 | 0.973812 | 4 | 0.955669 | 5 | -/-/- |
| 3 | `frame_4336` | 0.675720 | 0.743714 | 12 | 0.717411 | 13 | 0.693370 | 13 | yes/yes/yes |
| 4 | `frame_1097` | 0.651104 | 0.979457 | 4 | **0.974736** | **1** | 0.961303 | 2 | -/-/- |
| 5 | `frame_1099` | 0.639245 | 0.986461 | 1 | 0.973950 | 3 | 0.955330 | 6 | -/-/- |
| 6 | `frame_1094` | 0.631793 | 0.966377 | 7 | 0.958201 | 7 | 0.949760 | 7 | -/-/- |
| 7 | `frame_4560` | 0.630890 | 0.663751 | 14 | 0.620189 | 16 | 0.570300 | 16 | yes/yes/yes |
| 8 | `frame_1096` | 0.625732 | 0.975804 | 5 | 0.972006 | 5 | 0.962953 | 1 | -/-/- |
| 9 | `frame_1098` | 0.620629 | 0.985342 | 2 | 0.974139 | 2 | 0.956985 | 4 | -/-/- |
| 10 | `frame_1095` | 0.617751 | 0.971051 | 6 | 0.963371 | 6 | 0.957289 | 3 | -/-/- |
| 11 | `frame_1092` | 0.610758 | 0.962870 | 10 | 0.953406 | 10 | 0.942937 | 11 | -/-/- |
| 12 | `frame_1090` | 0.602294 | 0.956348 | 11 | 0.951553 | 11 | 0.943486 | 9 | -/-/- |
| 13 | `frame_1093` | 0.596956 | 0.964691 | 9 | 0.955070 | 9 | 0.943461 | 10 | -/-/- |
| 14 | `frame_1091` | 0.587490 | 0.964823 | 8 | 0.957465 | 8 | 0.947929 | 8 | -/-/- |
| 15 | `frame_4786` | 0.532746 | 0.743568 | 13 | 0.729469 | 12 | 0.716799 | 12 | yes/yes/yes |
| 16 | `frame_4636` | 0.507667 | 0.651134 | 16 | 0.627087 | 15 | 0.609305 | 15 | yes/yes/yes |
| 17 | `frame_4936` | 0.284782 | 0.554991 | 17 | 0.529896 | 17 | 0.509146 | 17 | yes/yes/yes |

The two clusters are temporal as well as visual. The 11 hall frames
(`frame_1090`–`frame_1100`) come from the `seed-check-36s` burst at 36.3–36.7 s;
the six flagged frames come from the later `issue168-*` batches at 144.5–164.5 s.
The existing mechanical score is not a subject ranker either: its industrial #1
`frame_4486` is a later-room frame, helped by the temporal term's reward for the
sparse later samples.

Per-`k` summary:

| k | Reference | Outlier threshold | Flagged frames | Top three |
|---:|---|---:|---|---|
| 3 | `frame_1099` | 0.797093 | `4336`, `4486`, `4560`, `4636`, `4786`, `4936` | `1099`, `1098`, `1100` |
| 5 | `frame_1097` | 0.812358 | same six | `1097`, `1098`, `1099` |
| 8 | `frame_1096` | 0.822223 | same six | `1096`, `1097`, `1095` |

### Viola source (`video-b9161c467ed2d30a`, 5 unique frames)

Full record: [`view-consensus-viola.json`](view-consensus-viola.json).

| Mech rank | Frame | Mech score | k3 score | k3 rank | k5 score | k5 rank | k8 score | k8 rank | Outlier |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | `frame_0820` | 0.830208 | 0.967013 | 4 | 0.963502 | 4 | 0.963502 | 4 | -/-/- |
| 2 | `frame_4642` | 0.796999 | 0.952946 | 5 | 0.952585 | 5 | 0.952585 | 5 | -/-/- |
| 3 | `frame_2731` | 0.699556 | 0.987698 | 2 | 0.978649 | 3 | 0.978649 | 3 | -/-/- |
| 4 | `frame_2730` | 0.698304 | 0.988320 | 1 | 0.979210 | 1 | 0.979210 | 1 | -/-/- |
| 5 | `frame_2732` | 0.692141 | 0.987018 | 3 | 0.978761 | 2 | 0.978761 | 2 | -/-/- |

Because `N = 5`, the effective `k` for `k = 8` is 4, so the k5 and k8 columns
are identical by construction. No Otsu boundary was accepted at any `k`
(`outlier_threshold: null`), which is the intended guard: all five frames are
one continuous, near-identical take.

### Sweep over k

| Source | Frame | Mechanical rank | k3 | k5 | k8 | Consensus best | Mechanical best |
|---|---|---:|---:|---:|---:|---:|---:|
| industrial | `frame_1097` (approved, earlier) | 4 / 17 | 4 | 1 | 2 | **1** | 4 |
| industrial | `frame_4560` (approved, current) | 7 / 17 | 14 | 16 | 16 | 14 | 7 |
| viola | `frame_2731` (approved, current) | 3 / 5 | 2 | 3 | 3 | **2** | 3 |

No single `k` is best for both sources. `k = 5` is the best match for the
industrial pool because the dominant hall cluster has 11 frames: `k = 5` stays
inside it, while `k = 8` starts mixing in the six-frame later room. The Viola
pool is too small and too uniform for `k` to matter; k5 and k8 collapse to the
same effective value.

### What the numbers say

1. **`frame_1097` (earlier approved industrial seed): yes.** It ranks 4 / 1 / 2
   of 17 and 1st at k5, improving on its mechanical rank of 4. This is the
   paper's intended behaviour: a view supported by a coherent cluster rises to
   the top.
2. **`frame_4560` (current approved industrial seed): no.** It ranks 14 / 16 /
   16 of 17, worse than its mechanical rank of 7. It is not a near-miss; its
   relevance to the consensus reference is 0.43–0.47 cosine, against 0.91–1.00
   for the hall frames. Inspection confirms the cause: `frame_1097` is the large
   open hall (the approved `industrial-hall-panorama-v1` seed), while
   `frame_4560` is a small debris-filled room (the approved
   `debris-window-rock-room-v1` seed). The pool contains 11 hall frames and 6
   room frames, so the local-consensus score treats the hall as the
   representative view. It is selecting the majority appearance cluster, not
   the operator's chosen subject. The mechanical score does not surface
   `frame_4560` either (rank 7; its top three are `4486`, `1100` and `4336`,
   two of them later-room frames), so this is not a unique failure of consensus
   — but consensus makes it worse, not better.
3. **`frame_2731` (Viola): nominally yes, practically a tie.** It ranks 2 / 3 /
   3 of 5. The top two (`2730`, `2731`) differ by less than 0.001 cosine at k3;
   the whole collection spans 0.035. A rank over near-duplicates is not a
   meaningful quality preference.
4. **Outlier flag:** in the industrial pool it flags exactly the six later-room
   frames at every `k`, including the approved `frame_4560`. In the Viola pool
   it flags nothing. There are no labelled foreign or off-scene frames in
   either source, so this does **not** demonstrate distractor rejection. It
   demonstrates that the appearance cue separates different rooms/views, and it
   would reject an operator-approved seed when that seed is the minority view.
5. **Reference selection (the paper's actual output):** the chosen references
   are `1099` / `1097` / `1096` for the industrial pool and `2730` for Viola.
   Only `1097` at k5 coincides with an approved seed. The current industrial
   seed would never be proposed by this method on this pool.

### Verdict against the issue's success criterion

The criterion was: approved seeds rank in the top few, and off-scene frames are
flagged. The result is **partially met**:

- 2 of 3 approved seeds are in the top few on their own pool (`1097` top-5 at
  all k, `2731` top-3 at all k), and `1097` is 1st at k5.
- The current industrial seed `frame_4560` ranks 14–16 of 17 at the three `k`
  values and would be rejected by the flag. This is a real failure, not noise.
- No labelled off-scene frames exist in either pool, so the rejection half of
  the criterion is untested. The one split the flag found is a subject/viewpoint
  split, and it rejects an approved seed.

Consequence for the pipeline: the appearance-only consensus score is useful as
a **viewpoint-cluster descriptor**, not as an automatic seed ranker or
pre-Hunyuan filter. Using it to reject views before a panorama attempt would
have discarded the current approved industrial seed. The paper's geometry-aware
second cue is the component that is supposed to distinguish "different but
relevant view" from "off-scene"; that remains the optional follow-up, gated on
this result, and was not run.

## Resolution question

Full record: [`resolution-audit.json`](resolution-audit.json).

| Source | Seed | Selected | Native | Hunyuan attempts | Requested panorama | Result |
|--------|------|----------|--------|------------------|--------------------|--------|
| `video-ccf9722164a0bdc8` | `frame_1097` | event 4, replaced at event 32 | 1280x720 | 001, 002 | 768x384 | failed |
| `video-ccf9722164a0bdc8` | `frame_1097` | same | 1280x720 | 003 | 512x256 | failed |
| `video-ccf9722164a0bdc8` | `frame_1097` | same | 1280x720 | 004 | 512x256 | preflight blocked (RAM) |
| `video-ccf9722164a0bdc8` | `frame_1097` | same | 1280x720 | 004-retry-001 | 512x256 | resource stopped |
| `video-ccf9722164a0bdc8` | `frame_1097` | same | 1280x720 | 005 | 512x256 | produced |
| `video-ccf9722164a0bdc8` | `frame_4560` | event 32, current | 1280x720 | 006 | 512x256 | produced |
| `video-b9161c467ed2d30a` | `frame_2731` | event 4, current | 1280x720 | 001 | 512x256 | produced |

What the record supports:

- All three approved seeds are 1280x720 native PNGs.
- The repository passes the seed path to the Hunyuan launcher unchanged; no
  repository code resizes, crops or composites it.
- `attempt_config.json` `width`/`height` are the requested **panorama output**
  dimensions, not the seed input. Every produced panorama is 512x256. The two
  768x384 requests failed and produced nothing.
- For video attempts the runtime does not record an accepted input width or
  height. Only picture-set GPU guards record `seed_image_width` and
  `seed_image_height`. The upstream Panogen preprocessing cannot be inspected
  now because the runtime path is absent.

What the record does **not** answer: whether a sharper or larger seed frame
improves a panorama. That needs GPU attempts and operator authorization; it is
an open question, not a conclusion from this paper.

## Checks run

- `python3 -m pytest -q godot_walk/scripts` — **1467 passed, 5 skipped, 67
  subtests passed** (433.82 s).
- `ruff check` and `black --check` on all new and changed Python files — clean.
- Second `rank` run on the warm cache printed `status: unchanged`, `encoded: 0`,
  `reused: 17`; the `consensus_variants`, `views` and `ground_truth` blocks were
  identical and the report file was not rewritten.
- Recomputing the industrial consensus from the cached embeddings under three
  seeded frame permutations produced an identical `evaluate_consensus` report.
- `git diff --name-only` for `godot_walk/seed_review/workflow.v1.json`,
  `WORKFLOW_V1.md` and the three v1 schemas — empty; the freeze test verifies
  their SHA-256 values.
- `run_freeview_consensus.py weights --model-dir /home/goya/models/dinov2-base`
  — `status: available`, 768-d, weight hash recorded above.
- No Hunyuan run, no VGGT run, no download, no package install, no paid service,
  no model call beyond the local DINOv2 CPU embedding extraction.

## Files and artifacts

New evidence:

- [`view-consensus-industrial.json`](view-consensus-industrial.json) — 17-frame
  consensus report, all k and ground truth.
- [`view-consensus-viola.json`](view-consensus-viola.json) — 5-frame report.
- [`mechanical-ranking-industrial.json`](mechanical-ranking-industrial.json) and
  [`mechanical-ranking-viola.json`](mechanical-ranking-viola.json) — the
  embedding-free baseline retained for comparison.

New tracked embedding caches (text-only JSON, keyed by frame SHA-256 and bound
to the weight hash above):

- `godot_walk/source_library/sources/video-ccf9722164a0bdc8/freeview/embeddings-facebook-dinov2-base-d73036b56966.json`
- `godot_walk/source_library/sources/video-b9161c467ed2d30a/freeview/embeddings-facebook-dinov2-base-d73036b56966.json`

The transient `*.json.lock` files are ignored by `.gitignore`.

## Reproduction

```bash
/home/goya/.venvs/freeview/bin/python godot_walk/scripts/run_freeview_consensus.py weights \
  --model-dir /home/goya/models/dinov2-base

/home/goya/.venvs/freeview/bin/python godot_walk/scripts/run_freeview_consensus.py rank \
  --source-id video-ccf9722164a0bdc8 \
  --model-dir /home/goya/models/dinov2-base \
  --ground-truth frame_4560 --ground-truth frame_1097 \
  --output godot_walk/evidence/2026-11-13-issue-210/view-consensus-industrial.json

/home/goya/.venvs/freeview/bin/python godot_walk/scripts/run_freeview_consensus.py rank \
  --source-id video-b9161c467ed2d30a \
  --model-dir /home/goya/models/dinov2-base \
  --ground-truth frame_2731 \
  --output godot_walk/evidence/2026-11-13-issue-210/view-consensus-viola.json
```

## Open questions and follow-ups

1. **Geometry-aware cue (optional, separate issue).** Combine the appearance
   relevance with VGGT late-layer spatial features, as the paper does, and test
   it on a mixed picture collection. The single-take video result above shows
   why appearance alone is not enough. The registered picture set has no
   approved seed yet, so it is not validation data.
2. **Resolution question.** Whether a sharper or larger seed frame improves a
   Hunyuan panorama is untested. It needs GPU attempts and operator
   authorisation; the paper does not answer it.
3. **Promotion into the review workflow.** Not done and not proposed. The
   number stays advisory; promoting it requires a new versioned workflow with
   its own schemas, hash freeze and operator approval.

## What this spike establishes

Established:

- The local-consensus score is implemented, deterministic, order-independent
  and cached by frame SHA-256; the frozen v1 workflow is untouched.
- On the industrial pool the earlier approved seed ranks 1st at k5 and top-5 at
  every k; on the Viola pool the approved seed is top-3 but tied with its
  neighbours.
- On the industrial pool the current approved seed ranks 14–16 of 17, and the
  appearance-outlier flag rejects it. Appearance-only consensus selects the
  majority room, not the operator's chosen room.

Not established:

- That the method can reject genuinely off-scene/foreign frames. No labelled
  distractor set has been run.
- That the unvalidated Otsu thresholds generalise. They behaved conservatively
  here (no split on the uniform Viola pool) but rejected an approved seed on the
  two-room industrial pool.
- That consensus-based selection improves a Hunyuan panorama. No GPU attempt
  was run.
