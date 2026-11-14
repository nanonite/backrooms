# Issue 210 — FreeView-style view-consensus selection for seed frames

Status: **blocked on local DINOv2 weights**. The weight audit ran first; no
usable DINOv2 weights are present. No download, package install, Hunyuan run,
or model call of any kind was performed. The deterministic scoring, cache and
offline embedding boundary were implemented and tested; the retrospective
consensus ranking was **not** produced because it needs embeddings.

## Blocker and exact need

The operator direction for this run says: check for local DINOv2 weights first,
do not download or install from the network, and stop if none are usable. The
audit found none, so the paper's embedding step and the retrospective ranking
are blocked.

What is needed, exactly:

| Item | Value |
|------|-------|
| Recommended model | `facebook/dinov2-base` |
| Weights size | ~346 MB single file |
| Source | <https://huggingface.co/facebook/dinov2-base> |
| Files | `config.json` plus `model.safetensors` (or `pytorch_model.bin`) |
| Placement | Any local directory, passed as `--model-dir` |
| Interpreter | A Python with `torch` and `transformers` |

Alternatives, if a smaller or larger embedding is preferred:

| Model | CLS dimension | Weights |
|-------|---------------|---------|
| `facebook/dinov2-small` | 384 | ~88 MB |
| `facebook/dinov2-base` | 768 | ~346 MB |
| `facebook/dinov2-large` | 1024 | ~1.2 GB |

The interpreter is a second decision. `/usr/bin/python3` has numpy, Pillow and
pytest but no torch. The `nerfstudio` conda env has torch 2.3.1+cu121 and timm
0.6.7 but no transformers. The nix store has python3.12-torch-2.5.1 and
python3.12-transformers-4.46.2 as separate packages, but no combined
environment. The recorded Hunyuan runtime
(`/mnt/sharedOs/backrooms-track-a-runtime`) is absent. The operator needs to
choose the model and the interpreter before the next attempt can run `rank`.

## Weight audit

The full machine-readable record is
[`weight-audit.json`](weight-audit.json). Summary:

| Location | Result |
|----------|--------|
| `~/.cache/huggingface/hub` | 76 cached repositories; no `models--facebook--dinov2-*` |
| `~/.cache/torch/hub/checkpoints` | no DINOv2 checkpoint; vgg16, alexnet, inception, spynet, NAFNet, ESRGAN, SwinIR, stylegan only |
| `~/.cache/clip` | OpenAI CLIP `ViT-B-32.pt` only, not DINOv2 |
| `/nix/store` | Transformers source, tests and docs only; no DINOv2 weight file |
| `/home/goya/nix/store` | no DINOv2 package or checkpoint |
| `/mnt/sharedOs/backrooms-track-a-runtime` | path absent |
| `build/vggt` | code checkout only; no checkpoint |
| repository `data/` and other caches | no DINOv2 weights |

The machine *does* have OpenAI CLIP weights (ViT-B/32, and Hugging Face
ViT-L/14-336 and CLIP-ViT-H-14 caches). They are not DINOv2 and were not
substituted: the issue names DINOv2 CLS tokens and the operator direction
forbids improvising a different model.

## What was implemented

All new files are advisory and outside the frozen v1 path.

| File | Purpose |
|------|---------|
| `godot_walk/scripts/freeview_consensus.py` | local-consensus score, deterministic ranks, Otsu-style appearance-outlier flag |
| `godot_walk/scripts/freeview_embedding_cache.py` | text-only cache keyed by frame SHA-256 and full model identity |
| `godot_walk/scripts/freeview_embeddings.py` | deterministic DINOv2 CLS preprocessing, local-snapshot discovery, offline-only torch/transformers reader |
| `godot_walk/scripts/run_freeview_consensus.py` | `weights`, `inventory` and `rank` commands |
| `godot_walk/seed_review/WORKFLOW_V1_1_ADDENDUM.md` | version 1.1.0 advisory addendum |
| `godot_walk/scripts/test_freeview_consensus.py` | scoring, order-independence, tie-break and outlier tests |
| `godot_walk/scripts/test_freeview_embedding_cache.py` | sha256 keying, model identity, merge and refusal tests |
| `godot_walk/scripts/test_freeview_embeddings.py` | preprocessing, discovery, cache-reuse and exact-need tests |
| `godot_walk/scripts/test_freeview_frozen_workflow.py` | byte freeze for the five v1 workflow files |

The consensus score is `score_i(k) = mean of the k largest cosine similarities
between view i and every other view`, swept over `k = 3, 5, 8`. The effective
`k` is capped at `N - 1`; a single view scores `0.0` with no peers. Ranks are
score-descending with frame ID as the tie-break, and the tests assert that
permuting the frame order returns an identical report. No RNG is used.

The outlier flag uses the top-consensus view as the reference and a
one-dimensional Otsu split on relevance-to-reference, accepted only when the
class means differ by at least 0.15 cosine and the split explains at least 0.85
of the variance. These thresholds are conservative design defaults; they are
not validated against labelled data. This is the paper's appearance cue only;
the geometry-aware cue is not implemented.

The cache header binds `model_id`, `weights_sha256`, `embedding_dim` and
`preprocessing_version`; entries are keyed by the frame SHA-256. The cache is
JSON, merges under an exclusive lock, refuses to replace a hash with a different
vector, and stores L2-normalized values to seven decimals. Embedding extraction
is CPU-only and sets `HF_HUB_OFFLINE` and `TRANSFORMERS_OFFLINE`; there is no
download path.

The frozen v1 workflow was not modified. The addendum is a separate versioned
record, and the v1 runner does not read it.

## Checks run

- `python3 -m pytest -q godot_walk/scripts` — **1464 passed, 5 skipped, 67
  subtests passed** (428 s).
- The four new test files alone — **50 passed, 9 subtests passed**.
- `ruff check` on all new Python files — clean.
- `black --check` on all new Python files — clean.
- `git diff --name-only` for `godot_walk/seed_review/workflow.v1.json`,
  `WORKFLOW_V1.md` and the three v1 schemas — empty. The freeze test also
  verifies their SHA-256 values.
- `python3 godot_walk/scripts/run_freeview_consensus.py weights` — reports
  `status: missing`, `local_weights: []`, runtime `torch: null`,
  `transformers: null`.
- No model call, no paid service, no download, no package install, no Hunyuan
  run.

## Mechanical baseline (no embeddings)

These are the existing mechanical scores for every unique direct-source frame
in the two sources with operator-approved video seeds. They are recorded as the
comparison half of the retrospective table; the consensus columns are absent
because the embeddings could not be computed.

Source `video-ccf9722164a0bdc8`, 17 unique frames from four extracted batches
(`seed-check-36s`, `issue168-zone-context`, `issue168-room-references`,
`issue168-seed-152s`). Full record:
[`mechanical-ranking-industrial.json`](mechanical-ranking-industrial.json).

| Rank | Frame | Score | Focus | Exposure | Dup | Temporal | Note |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | `frame_4486` | 0.810018 | 1.0000 | 0.7326 | 0.8209 | 1.0000 |  |
| 2 | `frame_1100` | 0.678210 | 0.8566 | 0.9562 | 0.9720 | 0.0667 |  |
| 3 | `frame_4336` | 0.675720 | 0.6517 | 0.8980 | 0.8308 | 1.0000 |  |
| 4 | `frame_1097` | 0.651104 | 0.8198 | 0.9050 | 0.9446 | 0.0667 | approved seed, replaced |
| 5 | `frame_1099` | 0.639245 | 0.7845 | 0.9445 | 0.9720 | 0.0667 |  |
| 6 | `frame_1094` | 0.631793 | 0.8145 | 0.8542 | 0.9712 | 0.0667 |  |
| 7 | `frame_4560` | 0.630890 | 0.5789 | 0.8682 | 0.8373 | 1.0000 | approved seed, current |
| 8 | `frame_1096` | 0.625732 | 0.7816 | 0.8851 | 0.9533 | 0.0667 |  |
| 9 | `frame_1098` | 0.620629 | 0.7542 | 0.9208 | 0.9554 | 0.0667 |  |
| 10 | `frame_1095` | 0.617751 | 0.7804 | 0.8616 | 0.9635 | 0.0667 |  |
| 11 | `frame_1092` | 0.610758 | 0.7736 | 0.8553 | 0.9768 | 0.0667 |  |
| 12 | `frame_1090` | 0.602294 | 0.7584 | 0.8530 | 0.9790 | 0.0667 |  |
| 13 | `frame_1093` | 0.596956 | 0.7457 | 0.8524 | 0.9712 | 0.0667 |  |
| 14 | `frame_1091` | 0.587490 | 0.7279 | 0.8549 | 0.9790 | 0.0667 |  |
| 15 | `frame_4786` | 0.532746 | 0.3469 | 0.9396 | 0.8373 | 1.0000 |  |
| 16 | `frame_4636` | 0.507667 | 0.2977 | 0.9357 | 0.8341 | 1.0000 |  |
| 17 | `frame_4936` | 0.284782 | 0.0757 | 0.4363 | 0.7477 | 1.0000 |  |

Source `video-b9161c467ed2d30a`, 5 unique frames from two extracted batches
(`issue169-seed-91s`, `issue169-room-context-001`). Full record:
[`mechanical-ranking-viola.json`](mechanical-ranking-viola.json).

| Rank | Frame | Score | Focus | Exposure | Dup | Temporal | Note |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | `frame_0820` | 0.830208 | 1.0000 | 0.9028 | 0.9699 | 1.0000 |  |
| 2 | `frame_4642` | 0.796999 | 0.9368 | 0.9072 | 0.9881 | 1.0000 |  |
| 3 | `frame_2731` | 0.699556 | 0.9341 | 0.9034 | 0.9999 | 0.0667 | approved seed, current |
| 4 | `frame_2730` | 0.698304 | 0.9315 | 0.9034 | 0.9999 | 0.0667 |  |
| 5 | `frame_2732` | 0.692141 | 0.9193 | 0.9028 | 0.9993 | 0.0667 |  |

Two mechanical quirks are visible and are not evidence for or against the
paper's method: the temporal term rewards the sparse later frames over the
tight 36.3-36.6 s burst, and the duplicate term penalizes the three near
identical Viola frames. A representative-frame score could plausibly behave
differently, which is exactly what the blocked consensus run would measure.

## Retrospective validation — not run

The agreed ground truth is:

- `video-ccf9722164a0bdc8`: `frame_4560` (current, event 32) and `frame_1097`
  (selected at event 4, replaced by the later selection). Both were operator
  approved at their time.
- `video-b9161c467ed2d30a`: `frame_2731` (event 4).
- The registered picture set `picture-set-d160eaa3cc847d5c` is **not**
  validation data: the 2026-11-13 note says it has no approved seed and is owned
  by #246.

No consensus rank exists for any frame. The report deliberately does not claim
that the approved seeds rank in the top few or that off-scene frames are
flagged; that question remains open. Once weights and an interpreter are
approved, the comparison is one command per source:

```bash
python3 godot_walk/scripts/run_freeview_consensus.py rank \
  --source-id video-ccf9722164a0bdc8 \
  --model-dir <local dinov2 snapshot> \
  --ground-truth frame_4560 --ground-truth frame_1097 \
  --output godot_walk/evidence/2026-11-13-issue-210/view-consensus-industrial.json

python3 godot_walk/scripts/run_freeview_consensus.py rank \
  --source-id video-b9161c467ed2d30a \
  --model-dir <local dinov2 snapshot> \
  --ground-truth frame_2731 \
  --output godot_walk/evidence/2026-11-13-issue-210/view-consensus-viola.json
```

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

## What this spike does and does not establish

Established:

- No DINOv2 weights are available locally; the exact model, size, source and
  interpreter requirement are recorded.
- The consensus score, cache and offline embedding boundary are implemented
  and deterministic; the frozen v1 workflow is untouched.
- The mechanical comparison baseline for both approved-seed video sources is
  recorded.

Not established:

- Whether the FreeView consensus score ranks the approved seeds better than the
  mechanical score.
- Whether any frame in these small, single-take video pools is an off-scene
  outlier. The Otsu flag may have nothing meaningful to reject here; the real
  distractor test would be a mixed picture collection, which has no approved
  ground truth yet.
- Whether the unvalidated outlier thresholds are useful. They are conservative
  defaults and must be checked against the real ranking before being trusted.

## Next attempt

1. Operator decision: approve or decline the DINOv2 download, choose the model
   (`small`, `base` or `large`) and the interpreter.
2. Run the two `rank` commands above. The `rank` command never downloads; it
   requires `--model-dir` to be a local snapshot.
3. Compare the approved seeds' consensus ranks with the mechanical baseline
   recorded here, and check whether any frame is flagged.
4. Only if step 3 shows value, file the optional geometry-aware cue (VGGT) for
   picture collections as a separate follow-up. Do not start Hunyuan or VGGT
   reconstruction here.

No push, no issue closure and no catalog action were performed.
