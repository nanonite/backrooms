# Issue #178 — `video-f657e9bc27813df8` frame extraction and mechanical seed shortlist

Status: **steps 1–3 complete (2026-11-14). Operator `select-seed` is PENDING.**
The review-source decision is already recorded as `proceed`. This run extracted a
full-resolution direct-source coverage set and computed the #169 mechanical
seed ranking. It did not run `select-seed`, `authorize-room-attempt`, Hunyuan,
Panogen, or any model/paid/API-token call. `registration_accepted` and
`scale_calibrated` remain `false`. The operator closes the issue.

## Source and gate state

| Item | Value |
|---|---|
| Source ID | `video-f657e9bc27813df8` |
| Source path | `data/videos/dead_end.mp4` |
| Source SHA-256 | `f657e9bc27813df8759acf720d7dd57060320d18270acf80c15c42c7cc7f3770` |
| Manifest | `godot_walk/source_library/sources/video-f657e9bc27813df8/source_manifest-v3.json` |
| Manifest SHA-256 | `ce413b916cca14a1c00bc898275e23e97a20c26be70890a9b2de0e3039fd7c7d` |
| Review-source decision | `proceed` (event sequence 3, 2026-11-14T12:57:34Z) |
| Native video | 1920x1080, 24 fps, 96 frames, 4.0 s |
| Frame batch event | sequence 4, bound to manifest hash `ce413b91…d7c7d` |
| Attempts used | 0 / 3 |
| Selected seed | `null` — operator step PENDING |

The runner reports `source_decision=proceed`, `selected_seed=null`,
`attempts_used=0`, `can_start_attempt=false`, and `next_worker_actions`
`extract-frames`, `select-seed`. The extraction stage is now complete; only the
operator seed selection remains before any room attempt can be authorized.

## Content observation

The registered clip is a single 4.0 s camera move with no cuts. A full decode of
all 96 frames at 160x90 gives consecutive mean absolute gray-level differences
of 1.10–4.15 (mean 2.62), with no spike that would indicate a cut, flash, or
title card. Sampled native-resolution luminance rises from 141.4 at 0.00 s to a
peak of 145.0 at 1.50 s, then falls smoothly to 122.1 at 3.96 s as the camera
nears the closing wall; there is no fade to black.

The sampled frames show a carpeted interior in the same synthetic Backrooms
vocabulary as the other captures: yellow-green chevron-patterned wallpaper,
a suspended ceiling grid with rectangular fluorescent light panels, beige
carpet, and beige-painted square columns and baseboards.

- At 0.00–0.75 s the camera stands in an open area facing a large square
  column near the centre of the frame. To the right, a receding row of
  freestanding wallpapered wall blocks separates aisle-like gaps lit by ceiling
  panels. To the left, a shadowed region sits behind a nearer wall block.
- From 1.00 s the camera moves forward and pans right. The central column
  drifts to the left edge and is out of frame by about 2.25 s. A wide
  wallpapered wall block with a small electrical outlet near its base comes to
  dominate the centre of the view.
- From 2.50 s the move continues toward that wall block. The right edge of the
  frame shows gaps between successive wall blocks with further wallpapered
  surfaces beyond.
- By 3.75–3.96 s the wall fills almost the entire frame, with the outlet at the
  lower centre and the baseboard running across the bottom. The clip ends
  facing a flat wall at close range.

The filename suggests a dead end with one opening, but the filename is not
evidence and the clip was not verified as such. This stage records only what
the sampled frames show: one continuous forward-right camera move across a
carpeted, wallpapered space past a column and wall blocks, ending close to a
flat wall. The frames do not establish room boundaries, doorways, thresholds,
or connectivity, and this stage authors no opening or socket. The mechanical
score below compares frames only and is **not** a room-suitability assessment.

## Frame extraction

A 17-frame coverage set at 0.25 s spacing (every sixth source frame) plus the
last decodable frame spans the whole clip from 0.00 s to 3.96 s. Every frame is
a direct decode of the registered video at native 1920x1080 with no resize or
edit. The clip is a single continuous camera move, so even spacing covers the
whole observed space; the extraction does not infer room boundaries.

| Batch | Frames | Indices | Window |
|---|---:|---|---|
| `issue178-quarter-s-a` | 17 | 0–95 | 0.00–3.96 s |

Indices: `0,6,12,18,24,30,36,42,48,54,60,66,72,78,84,90,95`.

The batch appended a `direct_frame_batch_extracted` event (sequence 4) bound to
manifest hash `ce413b916cca14a1c00bc898275e23e97a20c26be70890a9b2de0e3039fd7c7d`.
The extraction manifest is
`godot_walk/source_library/sources/video-f657e9bc27813df8/frames/issue178-quarter-s-a/extraction_manifest.json`
(SHA-256 `24e74cf402e8fd21a163fb4fec387702059b12c5a414f545cc8418bfebda1899`);
per-frame SHA-256 values live inside it. The batch occupies about 63 MB.

## Mechanical ranking

The ranking reuses the #169 scoring core (`seed_review_candidates.py`,
`seed_review_metrics.py`) through `run_freeview_consensus.py inventory`, which
validates every frame's direct-source identity, native resolution, and SHA-256
before scoring. The score weights are focus 0.50, exposure 0.25, thumbnail
distinctness 0.15, and temporal coverage 0.10. All 17 frames are in the pool;
the top three are the frames a three-frame seed review would shortlist, and the
remaining 14 are shortlist-excluded for the review limit, not rejected.

Top 12 by mechanical score (`mechanical-ranking.json`):

| Rank | Frame | Time (s) | Score | Focus | Exposure | Duplicate |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `frame_0096` | 3.96 | 0.787783 | 1.000 | 0.970 | 0.976 |
| 2 | `frame_0085` | 3.50 | 0.759293 | 0.923 | 0.976 | 0.974 |
| 3 | `frame_0007` | 0.25 | 0.734269 | 0.908 | 0.913 | 0.987 |
| 4 | `frame_0013` | 0.50 | 0.730438 | 0.902 | 0.909 | 0.986 |
| 5 | `frame_0091` | 3.75 | 0.729615 | 0.883 | 0.971 | 0.976 |
| 6 | `frame_0001` | 0.00 | 0.712123 | 0.862 | 0.917 | 0.987 |
| 7 | `frame_0079` | 3.25 | 0.693920 | 0.785 | 0.990 | 0.974 |
| 8 | `frame_0019` | 0.75 | 0.681014 | 0.806 | 0.902 | 0.982 |
| 9 | `frame_0025` | 1.00 | 0.646845 | 0.739 | 0.896 | 0.979 |
| 10 | `frame_0073` | 3.00 | 0.635098 | 0.675 | 0.971 | 0.966 |
| 11 | `frame_0037` | 1.50 | 0.634535 | 0.717 | 0.889 | 0.974 |
| 12 | `frame_0043` | 1.75 | 0.625217 | 0.696 | 0.891 | 0.971 |

The complete 17-frame table with every component is in
`mechanical-ranking.json`. The report's `"issue": 210` field is a hardcoded
provenance value inside `run_freeview_consensus.py` (issue 210 owns the
consensus tooling); it is not this issue's number.

### Reading the scores for this source

- The scoring pipeline analyses every frame at 640x360 (`ANALYSIS_WIDTH`,
  `ANALYSIS_HEIGHT` in `seed_review_metrics.py`), and the focus component
  normalises the analysis-resolution Laplacian variance to the pool maximum.
  `frame_0096` is the maximum here (analysis variance 208.9 → `1.000`). The
  focus weight therefore ranks relative detail at analysis resolution **within
  this source**; it is not absolute sharpness. At native 1920x1080,
  `frame_0001` (403.8), `frame_0013` (385.6), `frame_0007` (383.7),
  `frame_0019` (262.9), `frame_0037` (221.9), `frame_0025` (220.0) and
  `frame_0085` (218.5) all exceed `frame_0096` (173.7). The operator may weigh
  the native frames directly.
- The temporal-coverage component compares the nearest-neighbour gap to a 0.5 s
  target (`TEMPORAL_TARGET_SECONDS`). The 0.25 s sampling makes every gap
  0.208–0.25 s, so the component is capped at 0.417–0.500 and the absolute
  scores are not comparable with sparser candidate sets from other sources.
- All 17 frames come from one continuous move and the 32x32 thumbnail
  similarity is 0.961–0.987 across the pool. Ranks 1, 2, 5, 7 and 10 are
  adjacent moments from the last second of the clip (3.00–3.96 s), not
  independent compositions. The mechanical score favours the late, close,
  evenly lit wall-facing frames; the earlier frames carry more of the room
  composition (central column, receding wall blocks, aisle lights) but score
  lower on focus/exposure. Ranks 3, 4 and 6 (`frame_0007` 0.25 s,
  `frame_0013` 0.50 s, `frame_0001` 0.00 s) are the strongest early views;
  `frame_0019` (0.75 s) and `frame_0025` (1.00 s) show the column closest to
  centre before it leaves frame.
- The mechanical score is a comparative focus/exposure/distinctness shortlist,
  not a room-suitability rank (see
  `godot_walk/evidence/2026-11-14-issue-248/REPORT.md`).

## Contact sheets

The sheets live under the source folder because `godot_walk/evidence/**/*.jpg`
is gitignored; this keeps the operator-facing images tracked with the source.

- `godot_walk/source_library/sources/video-f657e9bc27813df8/candidate_sheets/top-candidates.jpg`
  — the 12 top-ranked frames, labelled with rank, frame ID, time, score, focus,
  exposure, and duplicate similarity
  (SHA-256 `6d13f63c0f2bc5d9886f36938f31cef85fb4953c644b28fccf33834c4921993f`).
- `godot_walk/source_library/sources/video-f657e9bc27813df8/candidate_sheets/coverage.jpg`
  — all 17 frames in time order for coverage of the clip
  (SHA-256 `d123db9ba7f18be14f31e8b9fcd5753cd1e29eabe8837900ba1f918c9f9e38d0`).

Both sheets are scaled previews for operator review only; neither is a seed and
neither may be used as a Hunyuan input. They were produced with the shared,
source-agnostic builder `godot_walk/scripts/build_issue171_candidate_sheet.py`,
which verifies every frame SHA-256 against the ranking report before drawing.

## Operator step

**`select-seed` is PENDING.** The operator selects one direct-source
full-resolution frame from `frames/issue178-quarter-s-a/` (or asks for other
moments or a fresh batch) and records it with the runner. Until then
`can_start_attempt` stays `false` and no Hunyuan stage is authorized. The
operator also decides whether this source yields a room, a dead-end or other
topology archetype reference, or a reject; this report makes no claim about
room identity, openings, or connectivity.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-f657e9bc27813df8 --run-id issue178-quarter-s-a \
  --indices 0,6,12,18,24,30,36,42,48,54,60,66,72,78,84,90,95
python3 godot_walk/scripts/run_freeview_consensus.py inventory \
  --source-id video-f657e9bc27813df8 \
  --output godot_walk/evidence/2026-11-14-issue-178/mechanical-ranking.json
python3 godot_walk/scripts/build_issue171_candidate_sheet.py \
  --ranking godot_walk/evidence/2026-11-14-issue-178/mechanical-ranking.json \
  --output-dir godot_walk/source_library/sources/video-f657e9bc27813df8/candidate_sheets \
  --top 12
```

## Checks

- `python3 godot_walk/scripts/register_video_sources.py validate` — valid,
  13 registered sources.
- Focused runner/consensus/source-library tests
  (`test_source_ingestion_runner.py`, `test_freeview_consensus.py`,
  `test_video_source_library.py`) — 37 passed, 4 subtests passed in 0.46 s.
- Full `python3 -m pytest -q godot_walk/scripts` — **1495 passed, 5 skipped,
  67 subtests passed** (258.40 s). No test was changed for this stage.
- No hash-pinned file, frozen workflow, or earlier source event was edited;
  events are append-only and remain bound to the manifest hash above.
- No Python, Godot, or hash-pinned file changed for this stage; the working
  tree adds only this report, the ranking JSON, the extracted frames, the
  contact sheets, and one appended event.
