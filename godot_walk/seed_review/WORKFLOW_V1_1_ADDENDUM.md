# Seed-review workflow v1.1.0 addendum: FreeView-consensus advisory

Status: experimental, advisory sidecar for issue #210. Version 1.1.0. It does
not change `workflow.v1.json`, `WORKFLOW_V1.md`, the three v1 JSON schemas, or
their hashes. The v1 runner neither reads this addendum nor the consensus
report. Nothing here selects a seed, admits a catalog module, starts Hunyuan,
or authorizes an issue closure.

## What the addendum adds

| Module | Role |
|--------|------|
| `scripts/freeview_consensus.py` | local-consensus score, deterministic ranks, appearance-outlier flag |
| `scripts/freeview_embedding_cache.py` | text-only JSON cache keyed by frame SHA-256 and model identity |
| `scripts/freeview_embeddings.py` | deterministic DINOv2 CLS preprocessing and offline-only local-snapshot reader |
| `scripts/run_freeview_consensus.py` | `weights`, `inventory` and `rank` commands |

The output is a separate JSON report. It sits beside the mechanical score; it
is not inserted into a v1 request, prompt, or receipt.

## Consensus score

For `N` views with L2-normalized DINOv2 CLS embeddings `e_i`:

```text
S_ij       = e_i · e_j
score_i(k) = mean of the k largest S_ij for j != i
```

`k` is swept over 3, 5 and 8. The effective `k` is `min(k, N - 1)`; a
single-view set has score `0.0` and no peers. Ranks are score-descending with
frame ID as the tie-break, so the input frame order never changes the result.
No random seed is used because the score contains no randomness.

## Appearance-outlier flag

The reference is the top-consensus view for the same `k`. Every view's
relevance is its cosine similarity to that reference. A one-dimensional Otsu
split proposes the rejection boundary, and the boundary is accepted only when
the lower class is separated from the upper class by at least `0.15` cosine
and the split explains at least `0.85` of the score variance. Otherwise the
flag is off. These thresholds are conservative defaults from the #210 design,
not values validated against labelled data.

This is the paper's appearance cue only. The geometry-aware cue, which needs
VGGT late-layer features, is not implemented; the issue keeps it as a
separate follow-up that is gated on the retrospective result.

## Embedding cache

The cache is a JSON object with `schema_version`, a `model` block
(`model_id`, `weights_sha256`, `embedding_dim`, `preprocessing_version`) and an
`entries` object keyed by the frame SHA-256. Values are L2-normalized floats
written with seven decimals. The cache merges under an exclusive lock and
refuses to replace an existing hash with a different vector. All values are
text; no binary blobs are written.

Preprocessing is fixed in code, not taken from a processor configuration:
resize the short edge to 256 pixels with bicubic resampling, center-crop
224x224, convert to RGB, scale to `[0, 1]`, and apply the ImageNet mean and
standard deviation. The version string is
`dinov2-cls-resize256-centercrop224-imagenet-v1`.

## Local-weights policy

No download path exists. `weights` scans the Hugging Face hub cache and the
torch hub checkpoint directory, and also resolves an explicit `--model-dir`
snapshot (a snapshot outside the hub cache is normal); `rank` requires
`--model-dir` pointing at a local Hugging Face snapshot with `config.json` and
`model.safetensors` (or `pytorch_model.bin`). Both `HF_HUB_OFFLINE` and
`TRANSFORMERS_OFFLINE` are set before the model is loaded.

DINOv2 is patch-based: the official `facebook/dinov2-base` config records
`image_size: 518`, while this contract runs inference at 224 and lets the model
interpolate its position embeddings. The snapshot check therefore validates the
patch size and the 224-pixel grid, not the pretraining image size.

The accepted model families and approximate single-file sizes are:

| Model | CLS dimension | Weights |
|-------|---------------|---------|
| `facebook/dinov2-small` | 384 | ~88 MB |
| `facebook/dinov2-base` | 768 | ~346 MB |
| `facebook/dinov2-large` | 1024 | ~1.2 GB |

Frames are read on CPU only in this slice. A GPU path is intentionally absent
so the existing GPU/RAM guard cannot be bypassed.

## Commands

Report local weights without calling a model:

```bash
python3 godot_walk/scripts/run_freeview_consensus.py weights \
  --model-dir /path/to/local/dinov2-base
```

List candidate frames and the existing mechanical ranks; no embeddings and no
model call:

```bash
python3 godot_walk/scripts/run_freeview_consensus.py inventory \
  --source-id video-ccf9722164a0bdc8 \
  --ground-truth frame_4560 \
  --output godot_walk/evidence/2026-11-13-issue-210/mechanical-ranking-industrial.json
```

Compute the consensus report from an approved local snapshot. `rank` needs an
interpreter that provides torch and transformers; the system `python3` does not.
The operator-approved environment for issue #210 is
`/home/goya/.venvs/freeview/bin/python`:

```bash
/home/goya/.venvs/freeview/bin/python godot_walk/scripts/run_freeview_consensus.py rank \
  --source-id video-ccf9722164a0bdc8 \
  --model-dir /path/to/local/dinov2-base \
  --ground-truth frame_4560 --ground-truth frame_1097 \
  --output godot_walk/evidence/2026-11-13-issue-210/view-consensus-industrial.json
```

## First validation result (2026-11-14)

The retrospective run used the operator-approved `facebook/dinov2-base` snapshot
(weight SHA-256 `d73036b5…`, 768-d CLS) and the approved CPU interpreter. It was
computed over the two direct-source video pools that have operator-approved
seeds, sweeping `k = 3, 5, 8`.

The result is mixed and is recorded in full in
`evidence/2026-11-13-issue-210/REPORT.md`:

- The earlier approved industrial seed `frame_1097` ranked 4 / 1 / 2 of 17
  (mechanical rank 4), so it is top-five at every `k`.
- The current approved industrial seed `frame_4560` ranked 14 / 16 / 16 of 17
  (mechanical rank 7). It belongs to a second, visibly different room; the
  score and the outlier flag both select the majority room instead.
- The Viola seed `frame_2731` ranked 2 / 3 / 3 of 5 (mechanical rank 3), but all
  five frames are near-identical and the top two differ by less than 0.001
  cosine, so the rank is not a meaningful preference.

The appearance-outlier flag flagged the six later-room industrial frames,
including the approved `frame_4560`. No labelled foreign/off-scene frames exist
in either pool, so this run does not demonstrate distractor rejection. The
appearance cue must not be used as an automatic pre-Hunyuan filter: it splits
on viewpoint/scene change, not on relevance to the operator's chosen subject.
The geometry-aware cue remains the separate, optional follow-up.

## Boundary with v1

Version 1.0.0 remains the only workflow the runner accepts. This addendum is a
record of an evaluation path; promoting any part of it into the review request,
the prompt, or a receipt requires a new versioned workflow with its own
schemas, hash freeze, and operator approval.
