# Issue 248 — Single-image picture input: limits and usefulness

Status: **evidence gathered and layout proposed (2026-11-14). The layout
decision is PENDING operator approval; no folder was added, nothing was moved,
and no source was registered or reviewed.** No Hunyuan, Panogen, VGGT, or
model call ran. No paid or API-token call was made. `registration_accepted` and
`scale_calibrated` remain false. The operator closes the issue.

The paired layout proposal is
[`LAYOUT_PROPOSAL.md`](LAYOUT_PROPOSAL.md). It recommends Option B — a reserved
`data/pictures/singles/` folder plus a distinct `single_image` source kind — and
lists the exact operator decisions that are still open. This report records
what the existing evidence says about single-image input; it does not assume
the proposed kind already exists.

## 1. Short answer

A single photo is **operationally usable as one Hunyuan/Panogen seed image**:
the current generation contract already takes exactly one image and produces a
2:1 panorama, and an operator can inspect and approve that exact image. A single
photo is **not a scene source**: it has no peers, no sequence, no pose, no
intrinsics, and no coverage. It cannot establish scale, room dimensions, hidden
boundaries, openings, connectivity, or multi-view consistency. The committed
appearance-consensus path returns score `0.0` with no peers for one view, so it
cannot evaluate a single image at all.

The mechanical score does not rescue this. On a batch of unrelated photos it is
a comparative focus/exposure/duplicate ranking, not a room-suitability test; on
one image alone it is degenerate (focus `1.0`, duplicate `0.0`, rank `1/1`, and
the score becomes exposure-only). In the current 57-photo collection the three
top mechanical candidates — selected for focus, exposure, and thumbnail
non-duplication — are an outdoor station platform, bare trees, and a glass
transit corridor, not ordinary room interiors. Seven of the 57 photos are below
the Hunyuan 1024-px long-side guard,
and one of those (550×413) ranks fifth in the batch. A high mechanical score is
therefore not a green light for Hunyuan.

Downstream usefulness is **unmeasured**. There is no operator-approved picture
seed, the registered photo collection is still `pending_operator_review`, and
there are zero picture-set Hunyuan attempts. Any claim that a single photo
produces a good room would be speculation.

## 2. Evidence base

| Item | Value |
|---|---|
| Registered photo collection | `picture-set-d160eaa3cc847d5c`, 57 unrelated webp photos |
| Collection path | `data/pictures/single_backrooms_esq` (gitignored; images not tracked) |
| Image-set SHA-256 | `d160eaa3cc847d5cc7bfb621b59ab6925ec03067ed06336b80b1c188a22c1b6c` |
| Manifest | `godot_walk/source_library/sources/picture-set-d160eaa3cc847d5c/source_manifest-v3.json` |
| Manifest SHA-256 | `6123576ee0bc0bfb31026c9c2bf49d80a73435978b1e915216db06a4a1f994c5` |
| Review spec | `picture_seed_review_v1` (frozen; not edited) |
| Dry-run review request SHA-256 | `731365ea083a61a37a177a53f44cd27a6e6559265efc0b59cdd84a823c2f9053` |
| Source-library index | schema 2, index_version 24: 12 `video` + 1 `picture_set` + 0 `single_image` |
| True multi-view reference | Mip-NeRF 360 `room`, 311 photos, COLMAP poses in `sparse/0`, outside git, not registered |
| Multi-view manifest SHA-256 | `0a80ead3584cf0c26d05a1f64ad53f46bb238ea53185068f3ed12d347383443f` |
| DINOv2 for the single-view check | `facebook/dinov2-base`, 768-d CLS, weights `d73036b56966966d07975d696bde331762f37297e2f095de8cea0040c3aa0841` |

The photo collection's manifest is text-only evidence. No image bytes were
copied into git. The 57 photos stay where the operator put them.

## 3. What the current pipeline actually consumes

The Hunyuan/Panogen source path takes **one seed image**, not a set:

- `run_source_panogen.py` has a single `--seed-frame` argument plus the exact
  seed hash; there is no multi-image seed argument.
- All eight recorded attempts in the source library use one video frame each.
  Output profiles are `768×384` or `512×256` (both 2:1). None is a
  `picture_set` attempt: `hunyuan_attempts = 8, picture_set = 0`.
- The picture guard binds the exact source image, image ID, path, dimensions,
  and the operator's picture-seed decision. It rejects an approved image below
  1024 px on the long side (`picture_seed_review_decisions_v1.py`; test
  `test_low_resolution_approval_is_flagged_but_guard_rejects_it`).
- The accepted Bill Viola room (`video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/`)
  was authored from one selected seed frame. Its adaptation record says
  plainly: “A single-view source does not establish room dimensions, hidden
  boundaries, openings, or connectivity.” That is the same one-view limit a
  single photo has; the video supplied other context frames and a sequence,
  but the seed contract was still one image.

So the question is not “can Hunyuan accept one photo?” — it can, in principle.
The question is “what can one photo justify?” The answer is one seed view, not
a validated room.

## 4. Mechanical score evidence

### 4.1 The registered 57-photo collection as one review batch

`run_picture_seed_review.py --source-id picture-set-d160eaa3cc847d5c --dry-run --json`
scored all 57 originals with the frozen `picture_seed_review_v1` path and made
no model call (84 s CPU, 513 MB peak RSS). The dry-run wrote no receipt and
authorized nothing.

| Metric | Value |
|---|---:|
| Images | 57 |
| Distinct dimensions | 38 |
| Candidate images sent to model review (limit 3) | 3 |
| Excluded images | 54 |
| `resolution_warning: true` (<1024 px long side) | 7 |
| Mechanical score min / median / max | 0.056902 / 0.280024 / 0.770108 |

Top three candidates:

| Rank | Image | Dimensions | Score | Resolution warning |
|---:|---|---:|---:|---|
| 1 | `img_0049` | 2000×1428 | 0.770108 | false |
| 2 | `img_0041` | 2624×3852 | 0.750270 | false |
| 3 | `img_0005` | 3000×4000 | 0.455003 | false |

The top three are not a room set. I viewed downscaled PNG copies in `/tmp`
(not tracked; visible-content description only, not a quality judgement):
`img_0049` is an outdoor railway station platform, `img_0041` is bare trees
against the sky, and `img_0005` is a glass-walled pedestrian corridor. None is
an ordinary enclosed room; the first two are outdoor and the third is a transit
space. The operator may still find them useful as liminal references, but the
mechanical score did not select them for room suitability — it selected
sharpness, exposure, and thumbnail non-duplication.

The seven low-resolution images are:

| Image | Dimensions | Batch rank |
|---|---:|---:|
| `img_0038` | 550×413 | 5 |
| `img_0034` | 900×675 | 12 |
| `img_0026` | 720×960 | 22 |
| `img_0008` | 453×604 | 23 |
| `img_0024` | 500×374 | 27 |
| `img_0030` | 583×800 | 32 |
| `img_0037` | 750×1000 | 36 |

`img_0038` at 550×413 ranks fifth of 57 (score 0.451124). Resolution is
explicitly not a ranking term, so a high score can point at an image the
Hunyuan guard will reject. The full rows are in
`mechanical_review_summary.json`.

### 4.2 The same images scored one at a time

The frozen review core was also applied to each photo as a one-image in-memory
record (no registered source, no file written). The result is degenerate:

- `focus_score` is `1.0` for all 57, because the image is its own maximum.
- `duplicate_similarity` is `0.0` for all 57, because there are no peers.
- `mechanical_rank` is `1` of `1` for all 57.
- The score collapses to `0.722222 + 0.277778 × exposure_score`.

| Metric | Value |
|---|---:|
| Score min / median / max | 0.735476 / 0.897482 / 0.997802 |
| Top image by score | `img_0026` (720×960, low resolution), 0.997802 |
| Second | `img_0008` (453×604, low resolution), 0.995755 |
| Third | `img_0005` (3000×4000), 0.993194 |

The ranking depends on the company an image keeps, not just on the image:

| Image | Batch rank | Batch score | Alone rank | Alone score |
|---|---:|---:|---:|---:|
| `img_0049` | 1 | 0.770108 | 1 | 0.986222 |
| `img_0041` | 2 | 0.750270 | 1 | 0.895643 |
| `img_0005` | 3 | 0.455003 | 1 | 0.993194 |
| `img_0026` | 22 | 0.305534 | 1 | 0.997802 |
| `img_0008` | 23 | 0.304196 | 1 | 0.995755 |

(`Alone rank` is always 1/1; the column is there to make the set-relative
collapse obvious.) Two of the three highest one-image scores are below the
1024-px guard. The score cannot be used as an absolute per-image quality
measure, and it certainly cannot choose a room seed.

### 4.3 What this means

The mechanical score is a **relative batch shortlist tool** for focus,
exposure, and thumbnail duplication. It is not a scene-membership test and not
a resolution test. On the 57 unrelated photos it ranks sharp, well-exposed
images first regardless of whether they are rooms. On one image it returns
high scores across the board (median 0.897482, minimum 0.735476) because it has
no peers. Any single-image review must present the image and its absolute
measurements to the operator; the one-image mechanical rank should not be
presented as a decision.

## 5. Multi-view consensus evidence

The FreeView consensus contract already states the single-view case: with
`N = 1`, the effective `k` is `0`, the score is `0.0`, and there are no peers
(`WORKFLOW_V1_1_ADDENDUM.md`). I confirmed this with one real
`facebook/dinov2-base` embedding from the #246 text-only cache:

| k | effective k | score | reference | outlier threshold | outliers |
|---:|---:|---:|---|---|---|
| 3 | 0 | 0.0 | the image itself | null | none |
| 5 | 0 | 0.0 | the image itself | null | none |
| 8 | 0 | 0.0 | the image itself | null | none |

This is the intended mathematical result, not a bug. Consensus needs at least
two related views. A single image cannot be ranked, flagged, or checked for
consistency by this path.

For contrast, #246 ran the same consensus core on a real multi-view set: the
Mip-NeRF 360 `room` scene, 311 photos of one place, plus 57 unrelated
distractors. The ranking score separated the easy distractors well (rank AUC
0.977–1.000, no distractor in the top quartile), but the committed adaptive
outlier flag was not a usable filter: it rejected 74% of clean scene views when
it fired, missed every distractor on one seed, and had flag precision 12.5% /
31% / 58% at 10% / 25% / 50% distractor mixes. That result is evidence about
multi-view ranking, not about single-image input; it does not transfer to a
one-view source.

The 57 photos alone produced no accepted split and no outlier flags in #246 —
consistent with “no coherent subset”. They are not a multi-view scene.

## 6. Resolution, aspect, and content

| Property | Current 57-photo collection |
|---|---|
| Images | 57 |
| Distinct dimensions | 38 |
| Long side range | 500–4000 px |
| Below 1024 px long side | 7 / 57 (12.3%) |
| Orientation | 27 portrait, 27 landscape, 3 square |
| Aspect range (width/height) | 0.6665–2.1645 |
| Captured-at timestamps present | 0 / 57 |
| Camera poses present | 0 / 57 |
| Intrinsics / lens / camera model | all null |
| Scale status | `uncalibrated` |
| Lighting status | `unknown`; the worked overlay is an agent-proposed estimate, approved only as an estimate, not a measurement |

The current Hunyuan diagnostic output is 2:1 (`512×256`; earlier attempts also
used `768×384`). The guard checks the long side, not the aspect. A portrait,
square, or ultra-wide seed is accepted if it is large enough, and the model
extrapolates a 2:1 panorama; no experiment here measures how much the seed
aspect or the unseen part costs in quality. That is a known unknown, not a
measured result. Do not claim a resolution/aspect threshold beyond the existing
1024-px rule.

Content is the larger uncertainty. A single photo can show one wall, a detail,
or something that is not a room at all. The top three mechanical candidates in
this collection illustrate the risk. A true multi-view set at least gives
overlapping views of one place, and a video gives a sequence; a single photo
gives neither.

## 7. Single photo versus video frame versus multi-view set

| Question | Single photo | Video frame | True multi-view picture set |
|---|---|---|---|
| Hunyuan seed input | One image, supported in principle | One frame, already used | One selected image, supported |
| Candidate selection | None if it is its own source; a batch ranking is comparative only | Temporal sweep; many candidate frames | Multiple views of one scene; consensus ranking possible |
| Sequence / temporal context | None | Frames and timestamps | Photo order may exist; COLMAP poses possible |
| Multi-view consistency | Impossible with N=1 (score 0.0, no peers) | Possible across frames if sampled, but no explicit pose set unless reconstructed | Possible; consensus and COLMAP-style geometry |
| Camera intrinsics / pose | All null unless separately supplied | Video metadata; per-frame pose not recorded here | COLMAP poses in `sparse/0` for the Mip-NeRF room |
| Scale | Uncalibrated; generic estimate only | Uncalibrated | Potentially calibratable with poses/anchors |
| Coverage / hidden surfaces | One viewpoint | More coverage over time, still limited | Overlapping views; more coverage |
| Resolution guard | 7/57 current photos fail <1024 | 1280×720 seeds pass | Full-res 3114×2075 or `images_2` 1557×1038 pass; `images_4` 779×519 would fail as a seed |
| Main risk | Content may not be a room; one view only | Sequence may still be one view of one room | Needs labels/poses and a coherent scene; not a single image |

The `images_4` note is important: the #246 CPU consensus test deliberately used
779×519 copies, which are fine for embeddings but would be rejected by the
Hunyuan 1024-px guard if used directly as a seed. A real multi-view set can
provide full-resolution views; the downscaled test copies are not the seed.

## 8. What a single image can and cannot give

**Can give**

- A content-addressed, dimension-probed source record with no invented
  timestamp or pose.
- Absolute focus and exposure measurements, and a resolution warning.
- One exact-bytes operator review and one Hunyuan/Panogen seed image.
- An appearance reference for one panorama or one room candidate, if the
  operator accepts the one-view limits.

**Cannot give**

- Multi-view consistency, consensus rank, or outlier rejection (N=1 returns
  0.0 with no peers).
- Room dimensions, absolute scale, hidden boundaries, openings, or
  connectivity. The accepted Bill Viola adaptation records the same limit for
  a single selected frame.
- Any evidence about surfaces the photo does not show.
- A reliable seed choice from mechanical score alone: for one image the score
  is exposure-only, and for a batch of unrelated photos the ranking is not
  scene suitability.
- A guarantee that a high-scoring image even passes the 1024-px guard.

**Unmeasured**

- End-to-end picture → Hunyuan/Panogen room quality. There is no approved
  picture seed and no `picture_set` attempt. The operator has not authorized
  one, and this issue does not.
- The effect of seed aspect, portrait framing, or unseen geometry on the
  generated panorama. No experiment here measures it.
- Whether the operator finds any of the 57 photos suitable as a room seed.
  Visual/quality approval is PENDING.

## 9. Usefulness verdict

Single-image input is **useful as a one-shot appearance seed** and as a way to
try a specific room look without a video, when the operator has inspected the
photo and accepts that only that one view is evidenced. It is **not sufficient
as a scene source** for a walkable room, and it should not be treated as a
substitute for video or a true multi-view set in the reconstruction path.

The honest recommendation is:

1. Keep single images as their own input type (Option B in
   [`LAYOUT_PROPOSAL.md`](LAYOUT_PROPOSAL.md)); do not call them picture sets.
2. Require operator visual approval per image; do not promote the one-image
   mechanical score to a decision.
3. Do not use the consensus/outlier path on a single image; it has no peers.
4. Keep the 57 unrelated photos separate from the Mip-NeRF multi-view room and
   from any future true multi-view set.
5. If end-to-end usefulness is to be measured, the next step is a separately
   authorized single-image seed review plus one Hunyuan attempt. It was not run
   here.

## 10. Layout proposal summary

The full proposal is [`LAYOUT_PROPOSAL.md`](LAYOUT_PROPOSAL.md). In brief:

- **Recommended:** a reserved, flat `data/pictures/singles/` folder where each
  direct supported file is one `single_image` source (`single-image-<sha16>`),
  with a new manifest schema v4 and index schema v3.
- Multi-view sets stay `picture_set`: two or more views of one place, one
  source, optionally with poses. New one-image `picture_set` registrations
  should be refused or routed to the single-image kind.
- The existing `picture-set-d160eaa3cc847d5c` record and its 57 photos stay
  untouched. Migration is a later, separately reviewed decision.
- The Mip-NeRF `room` scene stays outside git and is never placed in
  `singles/`.

The decision is **PENDING operator approval**. No folder was created. The only
committed-file changes are two test adjustments: the state-aware batch gate
assertion and a sampled elevation sweep, both described in §13. No production
file, source record, manifest, or pinned file was changed.

## 11. Files and artifacts

New evidence, all text:

- [`LAYOUT_PROPOSAL.md`](LAYOUT_PROPOSAL.md) — options, recommended layout,
  contract sketch, implementation checklist, PENDING decisions.
- [`mechanical_review_summary.json`](mechanical_review_summary.json) — all 57
  rows from the dry-run `picture_seed_review_v1` review, with the exact source
  hashes, scores, ranks, dimensions, and resolution warnings.
- [`single_image_alone_mechanical.json`](single_image_alone_mechanical.json) —
  the same 57 photos scored one at a time, showing the degenerate focus,
  duplicate, rank, and exposure-only score.
- [`single_view_consensus.json`](single_view_consensus.json) — one real
  DINOv2 embedding through the committed consensus core at `N=1`.
- [`source_audit.json`](source_audit.json) — index counts, picture-source
  gates, and the eight existing Hunyuan attempt configs (all video, one seed
  frame each, 2:1 output).

No image bytes are tracked. No source, manifest, or frozen file was edited by
this task. Two test files were updated: `test_template_batch_ingest.py` makes
its gate assertion state-aware after the lead/operator recorded `proceed` for
the #195 videos, and `test_gmap_elevation.py` samples the 1..300 V10 sweep at
every 20th seed plus 279 to keep the default verification tractable. See §13.
No source was registered and no event was appended for the picture source by
this task. Eight video `source_suitability_decision` events were appended
concurrently by the lead/operator for the #195 batch; they are untouched (see
§13).

## 12. Reproduction

Dry-run the existing picture review (no model call):

```bash
python3 godot_walk/scripts/run_picture_seed_review.py \
  --source-id picture-set-d160eaa3cc847d5c --dry-run --json \
  > /tmp/picture_review_dryrun_248.json
```

One-image in-memory scoring and the single-view consensus check were run with
the committed modules; the exact commands and inputs are recorded in the JSON
`method`/`source` fields and in the `REPORT.md` text above. No new script was
committed for this issue.

## 13. Checks run

- Dry-run `picture_seed_review_v1` over all 57 photos: 57 scored, 3 candidates,
  54 excluded, 7 resolution warnings, model not invoked, no receipt written,
  `operator_decision_recorded: false`, `next_stage_authorized: false`.
- `python3 godot_walk/scripts/source_ingestion_runner.py status picture-set-d160eaa3cc847d5c`:
  `source_decision: null`, `attempts_used: 0`, `can_start_attempt: false`,
  `next_worker_actions: ["review-source"]`.
- Source-library scan: 13 sources (12 video, 1 picture_set, 0 single_image);
  8 Hunyuan attempt configs, all video, all one seed frame, output 2:1; zero
  picture-set attempts.
- FreeView consensus on one real DINOv2 embedding: `view_count: 1`,
  `effective_k: 0`, score `0.0` at k=3/5/8, no threshold, no outliers.
- `python3 godot_walk/scripts/register_video_sources.py validate`: valid,
  13 registered sources.
- `python3 godot_walk/scripts/register_picture_sources.py validate`: valid,
  13 registered sources.
- `python3 -m json.tool` on all four new JSON evidence files: valid.
- `python3 -m pytest -q godot_walk/scripts`: **1495 passed, 5 skipped, 67
  subtests passed**. The first full pass after the gate fix took 1213.01 s;
  after sampling the 300-seed elevation sweep (16 seeds) it took 1026.17 s.
  Both runs were under an external `qemu-aarch64` job that occupied 23 of 24
  cores (load average ~65); the same suite has taken ~421 s under normal load.
  The failure that was fixed was
  `test_template_batch_ingest.py::test_v3_manifest_is_readable_by_the_runner_and_seed_review`,
  which hard-coded `next_worker_actions == ["review-source"]` for the first
  #195 batch source. The lead/operator concurrently appended
  `source_suitability_decision: proceed` events for the eight #195 videos
  (including `video-c9115d943f6c3fe4`) at 2026-11-14T12:57 UTC, so the live
  status is now `["extract-frames", "select-seed"]`. The test assertion was
  updated to require `review-source` only when `source_decision` is null and
  to require that `review-source` is absent once a decision exists. The
  operator events were left untouched. 12/12 tests now pass in
  `test_template_batch_ingest.py`.
- The elevation sweep now samples `range(1, 301, 20)` plus seed 279; it still
  validates every sampled map and reaches every elevation level and both
  ramp/drop edges. This is a verification-time optimisation, not a production
  change. A full 300-seed run remains possible manually.
- `git status` shows the new `godot_walk/evidence/2026-11-14-issue-248/`
  files and the two test-file changes from this task, plus the pre-existing
  untracked evidence folders and the concurrent operator event edits.
- No frozen or hash-pinned file was edited; `WORKFLOW_V1` and
  `SEED_REVIEW_PICTURE_SET_V1` were not touched.

## 14. PENDING (operator)

1. Approve the single-image layout (recommended Option B: `data/pictures/singles/`
   plus `single_image` source kind), or choose another option.
2. Confirm the folder name, ID prefix, and manifest/index versioning.
3. Confirm that a one-image source has no batch mechanical rank, only absolute
   measurements and operator review.
4. Confirm that new one-image `picture_set` registrations are refused or routed
   to `single_image`.
5. Decide the legacy 57-photo collection's future; do not move it until then.
6. Separately authorize any single-image seed review or Hunyuan attempt. None
   was run here.
7. Visual/quality approval of any single photo remains a human step; the agent
   only described visible content.
