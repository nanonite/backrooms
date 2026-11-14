# Issue #172 — `video-22909eb734e4d8e2` frame extraction and mechanical seed shortlist

Status: **steps 1–3 complete (2026-11-14). Operator `select-seed` is PENDING.**
The review-source decision is already recorded as `proceed`. This run extracted a
full-resolution direct-source coverage set and computed the #169 mechanical
seed ranking. It did not run `select-seed`, `authorize-room-attempt`, Hunyuan,
Panogen, or any model/paid/API-token call. `registration_accepted` and
`scale_calibrated` remain `false`. The operator closes the issue.

## Source and gate state

| Item | Value |
|---|---|
| Source ID | `video-22909eb734e4d8e2` |
| Source path | `data/videos/Antelope Canyon in 4K - World's Most Iconic Slot Canyon - UHD 4K.mp4` |
| Source SHA-256 | `22909eb734e4d8e2feede084e0305ae0aecefcc6dd5b46ca7ef884277e2a274a` |
| Manifest | `godot_walk/source_library/sources/video-22909eb734e4d8e2/source_manifest-v3.json` |
| Manifest SHA-256 | `1d3a4137c56a40949f178d8b295bb4087bc0bbb12f66aa27c6398156f1c03f83` |
| Review-source decision | `proceed` (event sequence 3, 2026-11-14T12:57:30Z) |
| Native video | 1280x720, 29.97003 fps, 1,541 frames, 51.479 s |
| Attempts used | 0 / 3 |
| Selected seed | `null` — operator step PENDING |

## Frame extraction

A 27-frame coverage set at ~1.97 s spacing spans the whole clip from 0.00 s to
51.38 s, including the first and last decodable frames. Every frame is a direct
decode of the registered video at native 1280x720 with no resize or edit. The
source is a single continuous camera move through one slot canyon, so even
spacing covers the whole space rather than separate rooms; the extraction does
not infer room boundaries.

| Batch | Frames | Indices | Window |
|---|---:|---|---|
| `issue172-2s-a` | 27 | 0–1540 | 0.00–51.38 s |

Indices: `0,59,118,178,237,296,355,415,474,533,592,652,711,770,829,888,948,
1007,1066,1125,1185,1244,1303,1362,1422,1481,1540`.

The batch appended a `direct_frame_batch_extracted` event (sequence 4) bound to
manifest hash `1d3a4137c56a40949f178d8b295bb4087bc0bbb12f66aa27c6398156f1c03f83`.
The extraction manifest is
`godot_walk/source_library/sources/video-22909eb734e4d8e2/frames/issue172-2s-a/extraction_manifest.json`
(SHA-256 `03bf05a8669035515c664f0e39db46991d0b2ca3076eae78331651c5284ca177`);
per-frame SHA-256 values live inside it.

## Mechanical ranking

The ranking reuses the #169 scoring core (`seed_review_candidates.py`,
`seed_review_metrics.py`) through
`run_freeview_consensus.py inventory`, which validates every frame's
direct-source identity, native resolution, and SHA-256 before scoring. The
score weights are focus 0.50, exposure 0.25, thumbnail distinctness 0.15, and
temporal coverage 0.10. All 27 frames are in the pool; the top three are the
frames a three-frame seed review would shortlist, and the remaining 24 are
shortlist-excluded for the model-review limit, not rejected.

Top 12 by mechanical score
(`mechanical-ranking.json`):

| Rank | Frame | Time (s) | Score | Focus | Exposure | Duplicate |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `frame_1363` | 45.45 | 0.673438 | 1.000 | 0.266 | 0.953 |
| 2 | `frame_1304` | 43.48 | 0.417917 | 0.500 | 0.250 | 0.963 |
| 3 | `frame_0297` | 9.88 | 0.410810 | 0.411 | 0.406 | 0.974 |
| 4 | `frame_0593` | 19.75 | 0.385416 | 0.360 | 0.405 | 0.971 |
| 5 | `frame_0179` | 5.94 | 0.375215 | 0.292 | 0.501 | 0.973 |
| 6 | `frame_0119` | 3.94 | 0.361709 | 0.267 | 0.497 | 0.973 |
| 7 | `frame_0060` | 1.97 | 0.361543 | 0.271 | 0.485 | 0.969 |
| 8 | `frame_0653` | 21.76 | 0.353491 | 0.283 | 0.423 | 0.958 |
| 9 | `frame_0356` | 11.85 | 0.334762 | 0.307 | 0.313 | 0.981 |
| 10 | `frame_0889` | 29.63 | 0.308217 | 0.146 | 0.524 | 0.972 |
| 11 | `frame_0238` | 7.91 | 0.305924 | 0.219 | 0.373 | 0.980 |
| 12 | `frame_0712` | 23.72 | 0.294823 | 0.133 | 0.498 | 0.973 |

The complete 27-frame table with every component is in
`mechanical-ranking.json`. The report's `"issue": 210` field is a hardcoded
provenance value inside `run_freeview_consensus.py` (issue 210 owns the
consensus tooling); it is not this issue's number.

### Reading the scores for this source

This clip is a deliberately dark slot-canyon film. Mean luminance across the
non-black frames is 0.04–0.16, so the exposure term penalises almost every frame and the
absolute scores sit lower than the bright outdoor clips of the same batch.
`frame_0001` (0.00 s) and `frame_1541` (51.38 s) are the black fade frames at
the clip ends and score near zero; they are kept only to prove coverage of the
full length. The mechanical score is a comparative
focus/exposure/distinctness shortlist, not a room-suitability rank (see
`godot_walk/evidence/2026-11-14-issue-248/REPORT.md`).

The source also carries a burned-in `CENTERSTAR` watermark in the lower-left
corner of most frames. It is part of the source pixels; nothing was cropped or
edited. The operator should weigh it when choosing a seed, because a Hunyuan
room built from a watermarked frame would reproduce (or need to hide) that
mark. The report does not propose a crop.

## Contact sheets

The sheets live under the source folder because `godot_walk/evidence/**/*.jpg`
is gitignored; this keeps the operator-facing images tracked with the source.

- `godot_walk/source_library/sources/video-22909eb734e4d8e2/candidate_sheets/top-candidates.jpg`
  — the 12 top-ranked frames, labelled with rank, frame ID, time, score, focus,
  exposure, and duplicate similarity.
- `godot_walk/source_library/sources/video-22909eb734e4d8e2/candidate_sheets/coverage.jpg`
  — all 27 frames in time order for coverage of the camera move.

Both sheets are scaled previews for operator review only; neither is a seed
and neither may be used as a Hunyuan input. They were produced with the shared,
source-agnostic builder `godot_walk/scripts/build_issue171_candidate_sheet.py`,
which verifies every frame SHA-256 against the ranking report before drawing.

## Operator step

**`select-seed` is PENDING.** The operator selects one direct-source
full-resolution frame from the extracted batch (or asks for a different
moment) and records it with the runner. Until then `can_start_attempt` stays
`false` and no Hunyuan stage is authorized. This run makes no claim about room
identity, openings, or connectivity; the video shows one continuous slot-canyon
travel and that is all that is observed.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-22909eb734e4d8e2 --run-id issue172-2s-a \
  --indices 0,59,118,178,237,296,355,415,474,533,592,652,711,770,829,888,948,1007,1066,1125,1185,1244,1303,1362,1422,1481,1540
python3 godot_walk/scripts/run_freeview_consensus.py inventory \
  --source-id video-22909eb734e4d8e2 \
  --output godot_walk/evidence/2026-11-14-issue-172/mechanical-ranking.json
python3 godot_walk/scripts/build_issue171_candidate_sheet.py \
  --ranking godot_walk/evidence/2026-11-14-issue-172/mechanical-ranking.json \
  --output-dir godot_walk/source_library/sources/video-22909eb734e4d8e2/candidate_sheets \
  --top 12
```

## Checks

- `python3 godot_walk/scripts/register_video_sources.py validate` — valid,
  13 registered sources.
- `python3 -m pytest -q godot_walk/scripts` — **1495 passed, 5 skipped, 67
  subtests passed** (255.44 s). No test was changed for this stage.
- The focused runner/consensus/source-library tests
  (`test_source_ingestion_runner.py`, `test_freeview_consensus.py`,
  `test_video_source_library.py`) — 37 passed, 4 subtests passed in 0.51 s.
- `ruff check` and `black --check` on the reused
  `godot_walk/scripts/build_issue171_candidate_sheet.py` — clean.
- No hash-pinned file, frozen workflow, or earlier source event was edited;
  events are append-only and remain bound to the manifest hash above.
- No Python, Godot, or hash-pinned file changed for this stage; the working
  tree adds only this report, the ranking JSON, the extracted frames, the
  contact sheets, and the appended event.
