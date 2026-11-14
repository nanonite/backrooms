# Issue #171 — video-c9115d943f6c3fe4 frame extraction and mechanical seed shortlist

Status: **steps 1–3 complete (2026-11-14). Operator `select-seed` is PENDING.**
The review-source decision is already recorded as `proceed`. This run extracted a
full-resolution direct-source coverage set and computed the #169 mechanical
seed ranking. It did not run `select-seed`, `authorize-room-attempt`, Hunyuan,
Panogen, or any model/paid/API-token call. `registration_accepted` and
`scale_calibrated` remain `false`. The operator closes the issue.

## Source and gate state

| Item | Value |
|---|---|
| Source ID | `video-c9115d943f6c3fe4` |
| Source path | `data/videos/Backrooms - Found Footage #55 (Hills of Synthetic Verdure).mp4` |
| Source SHA-256 | `c9115d943f6c3fe46fbe79b826c8c76e6378c8339736ae885e7a5a3d21ee9fae` |
| Manifest | `godot_walk/source_library/sources/video-c9115d943f6c3fe4/source_manifest-v3.json` |
| Manifest SHA-256 | `ae6eee3881e287d56b2a2ba65881daff635a0e906b5c1d7eb1a701a87f4a433e` |
| Review-source decision | `proceed` (event sequence 3, 2026-11-14T12:57:30Z) |
| Native video | 1280x720, 23.976024 fps, 13,937 frames, 581.381 s |
| Attempts used | 0 / 3 |
| Selected seed | `null` — operator step PENDING |

## Frame extraction

A 36-frame coverage set at 16 s spacing spans the whole clip from 12.01 s to
571.90 s. Every frame is a direct decode of the registered video at native
1280x720 with no resize or edit. The set is split into three fresh batch run
IDs so each extraction call completes in one pass; the ranking below treats
them as one candidate pool.

| Batch | Frames | Indices | Window |
|---|---:|---|---|
| `issue171-16s-a` | 12 | 288–4507 | 12.01–187.98 s |
| `issue171-16s-b` | 12 | 4890–9109 | 203.95–379.98 s |
| `issue171-16s-c` | 12 | 9493–13712 | 395.94–571.90 s |

Each batch appended a `direct_frame_batch_extracted` event bound to manifest
hash `ae6eee3881e287d56b2a2ba65881daff635a0e906b5c1d7eb1a701a87f4a433e`
(events 4–6). Extraction manifests and per-frame SHA-256 values live under
`godot_walk/source_library/sources/video-c9115d943f6c3fe4/frames/`.

## Mechanical ranking

The ranking reuses the #169 scoring core (`seed_review_candidates.py`,
`seed_review_metrics.py`) through
`run_freeview_consensus.py inventory`, which validates every frame's
direct-source identity, native resolution, and SHA-256 before scoring. The
score weights are focus 0.50, exposure 0.25, thumbnail distinctness 0.15, and
temporal coverage 0.10. All 36 frames are in the pool; the top three are the
frames a three-frame seed review would shortlist, and the remaining 33 are
shortlist-excluded for the model-review limit, not rejected.

Top 12 by mechanical score
(`mechanical-ranking.json`):

| Rank | Frame | Time (s) | Score | Focus | Exposure | Duplicate |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `frame_6426` | 267.98 | 0.815901 | 1.000 | 0.840 | 0.961 |
| 2 | `frame_5658` | 235.94 | 0.716675 | 0.799 | 0.845 | 0.961 |
| 3 | `frame_4508` | 187.98 | 0.711108 | 0.846 | 0.695 | 0.902 |
| 4 | `frame_4891` | 203.95 | 0.650919 | 0.675 | 0.813 | 0.931 |
| 5 | `frame_10645` | 443.94 | 0.625648 | 0.824 | 0.365 | 0.851 |
| 6 | `frame_11412` | 475.93 | 0.615142 | 0.810 | 0.335 | 0.823 |
| 7 | `frame_11028` | 459.92 | 0.614707 | 0.582 | 0.809 | 0.858 |
| 8 | `frame_7960` | 331.96 | 0.573467 | 0.542 | 0.775 | 0.943 |
| 9 | `frame_0672` | 27.99 | 0.531359 | 0.472 | 0.741 | 0.933 |
| 10 | `frame_9494` | 395.94 | 0.523505 | 0.429 | 0.802 | 0.942 |
| 11 | `frame_4124` | 171.96 | 0.512642 | 0.392 | 0.832 | 0.944 |
| 12 | `frame_13713` | 571.90 | 0.476739 | 0.555 | 0.370 | 0.957 |

The complete 36-frame table with every component is in
`mechanical-ranking.json`.

## Contact sheets

The sheets live under the source folder because `godot_walk/evidence/**/*.jpg`
is gitignored; this keeps the operator-facing images tracked with the source.

- `godot_walk/source_library/sources/video-c9115d943f6c3fe4/candidate_sheets/top-candidates.jpg`
  — the 12 top-ranked frames, labelled with rank, frame ID, time, score, focus,
  exposure, and duplicate similarity.
- `godot_walk/source_library/sources/video-c9115d943f6c3fe4/candidate_sheets/coverage.jpg`
  — all 36 frames in time order for space coverage.

Both sheets are scaled previews for operator review only; neither is a seed
and neither may be used as a Hunyuan input. The mechanical score is a
comparative focus/exposure/distinctness shortlist, not a room-suitability
rank (see `godot_walk/evidence/2026-11-14-issue-248/REPORT.md`). The coverage
sheet shows the clip moving among different outdoor and interior views; the
top mechanical frames are bright outdoor views, while the lower-ranked frames
include interior views. The operator chooses the seed frame and the room
identity; this report does not rank rooms, infer room boundaries, or claim
openings or connectivity.

## Operator step

**`select-seed` is PENDING.** The operator selects one direct-source
full-resolution frame from the extracted batches (or asks for a different
moment) and records it with the runner. Until then `can_start_attempt` stays
`false` and no Hunyuan stage is authorized.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-c9115d943f6c3fe4 --run-id issue171-16s-a \
  --indices 288,671,1055,1438,1822,2205,2589,2973,3356,3740,4123,4507
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-c9115d943f6c3fe4 --run-id issue171-16s-b \
  --indices 4890,5274,5657,6041,6425,6808,7192,7575,7959,8342,8726,9109
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-c9115d943f6c3fe4 --run-id issue171-16s-c \
  --indices 9493,9877,10260,10644,11027,11411,11794,12178,12561,12945,13329,13712
python3 godot_walk/scripts/run_freeview_consensus.py inventory \
  --source-id video-c9115d943f6c3fe4 \
  --output godot_walk/evidence/2026-11-14-issue-171/mechanical-ranking.json
python3 godot_walk/scripts/build_issue171_candidate_sheet.py \
  --ranking godot_walk/evidence/2026-11-14-issue-171/mechanical-ranking.json \
  --output-dir godot_walk/source_library/sources/video-c9115d943f6c3fe4/candidate_sheets \
  --top 12
```

## Checks

- `python3 godot_walk/scripts/register_video_sources.py validate` — valid,
  13 registered sources.
- `python3 -m pytest -q godot_walk/scripts` — **1495 passed, 5 skipped, 67
  subtests passed** (863.36 s). No test was changed for this stage.
- The focused runner/consensus/candidate/batch tests — 53 passed, 4 subtests
  passed in 30.70 s.
- `ruff check` and `black --check` on
  `godot_walk/scripts/build_issue171_candidate_sheet.py` — clean.
- No hash-pinned file, frozen workflow, or source event was edited; events are
  append-only and remain bound to the manifest hash above.
