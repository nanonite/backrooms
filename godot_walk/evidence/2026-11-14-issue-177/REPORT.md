# Issue #177 — `video-61b91dbeb9026dc7` frame extraction and mechanical seed shortlist

Status: **steps 1–3 complete (2026-11-14). Operator `select-seed` is PENDING.**
The review-source decision is already recorded as `proceed`. This run extracted a
full-resolution direct-source coverage set and computed the #169 mechanical
seed ranking. It did not run `select-seed`, `authorize-room-attempt`, Hunyuan,
Panogen, or any model/paid/API-token call. `registration_accepted` and
`scale_calibrated` remain `false`. The operator closes the issue.

## Source and gate state

| Item | Value |
|---|---|
| Source ID | `video-61b91dbeb9026dc7` |
| Source path | `data/videos/corridor_x.mp4` |
| Source SHA-256 | `61b91dbeb9026dc7b404657f7ba7e081b5588a7e7a4a2abfa553be765d1a7f04` |
| Manifest | `godot_walk/source_library/sources/video-61b91dbeb9026dc7/source_manifest-v3.json` |
| Manifest SHA-256 | `af41b7ed362728d9956d5cfb5eb3d0dc71b7f251febfff02f25b2be9dcf6259f` |
| Review-source decision | `proceed` (event sequence 3, 2026-11-14T12:57:33Z) |
| Native video | 1920x1080, 24 fps, 96 frames, 4.0 s |
| Frame batch event | sequence 4, bound to manifest hash `af41b7ed…dcf6259f` |
| Attempts used | 0 / 3 |
| Selected seed | `null` — operator step PENDING |

## Content observation

The registered clip is a single 4.0 s camera move with no cuts. Between the 17
sampled frames the mean absolute gray-level difference stays in the narrow
10.8–13.0 band and mean luminance stays between 140.1 and 144.7 of 255, with no
fade to black and no title card.

The sampled frames show a carpeted interior in the same synthetic vocabulary as
the other corridor captures: yellow-green patterned wallpaper, a suspended
ceiling grid holding rectangular fluorescent light panels, beige carpet, and
beige square pillars and freestanding wallpapered wall blocks. The camera starts
beside a large square pillar near the centre of the frame and moves forward and
to the right while turning slightly. The pillar passes out of frame on the left
by about 2.5 s. In the closing frames the view opens toward corridor-like
recesses receding past the wall blocks to the left, ahead, and to the right.

The filename suggests a cross junction with four openings, but the filename is
not evidence and the clip was not verified as such. This stage records only what
the sampled frames show: one continuous forward-right camera move through a
carpeted, wallpapered space past pillars and wall blocks. The frames do not
establish doorways, thresholds, room boundaries, or connectivity, and this stage
authors no opening or socket. The mechanical score below compares frames only
and is **not** a room-suitability assessment.

## Frame extraction

A 17-frame coverage set at 0.25 s spacing (every sixth source frame) plus the
last decodable frame spans the whole clip from 0.00 s to 3.96 s. Every frame is
a direct decode of the registered video at native 1920x1080 with no resize or
edit. The clip is a single continuous camera move, so even spacing covers the
whole observed space; the extraction does not infer room boundaries.

| Batch | Frames | Indices | Window |
|---|---:|---|---|
| `issue177-quarter-s-a` | 17 | 0–95 | 0.00–3.96 s |

Indices: `0,6,12,18,24,30,36,42,48,54,60,66,72,78,84,90,95`.

The batch appended a `direct_frame_batch_extracted` event (sequence 4) bound to
manifest hash `af41b7ed362728d9956d5cfb5eb3d0dc71b7f251febfff02f25b2be9dcf6259f`.
The extraction manifest is
`godot_walk/source_library/sources/video-61b91dbeb9026dc7/frames/issue177-quarter-s-a/extraction_manifest.json`
(SHA-256 `9880e1f51c688e1a52bf130b396e437b7f6a9d3b451fce7096d4c6dba633d48c`);
per-frame SHA-256 values live inside it. The batch occupies about 71 MB.

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
| 1 | `frame_0085` | 3.50 | 0.782831 | 1.000 | 0.917 | 0.975 |
| 2 | `frame_0013` | 0.50 | 0.772949 | 0.985 | 0.910 | 0.981 |
| 3 | `frame_0096` | 3.96 | 0.770724 | 0.990 | 0.925 | 0.980 |
| 4 | `frame_0091` | 3.75 | 0.730718 | 0.912 | 0.920 | 0.980 |
| 5 | `frame_0037` | 1.50 | 0.721943 | 0.887 | 0.900 | 0.979 |
| 6 | `frame_0007` | 0.25 | 0.704825 | 0.847 | 0.914 | 0.981 |
| 7 | `frame_0019` | 0.75 | 0.697447 | 0.836 | 0.905 | 0.980 |
| 8 | `frame_0025` | 1.00 | 0.688493 | 0.820 | 0.902 | 0.980 |
| 9 | `frame_0073` | 3.00 | 0.687243 | 0.814 | 0.906 | 0.975 |
| 10 | `frame_0061` | 2.50 | 0.686528 | 0.814 | 0.904 | 0.976 |
| 11 | `frame_0079` | 3.25 | 0.686341 | 0.809 | 0.912 | 0.975 |
| 12 | `frame_0031` | 1.25 | 0.683687 | 0.811 | 0.901 | 0.979 |

The complete 17-frame table with every component is in
`mechanical-ranking.json`. The report's `"issue": 210` field is a hardcoded
provenance value inside `run_freeview_consensus.py` (issue 210 owns the
consensus tooling); it is not this issue's number.

### Reading the scores for this source

- The scoring pipeline analyses every frame at 640x360 (`ANALYSIS_WIDTH`,
  `ANALYSIS_HEIGHT` in `seed_review_metrics.py`), and the focus component
  normalises the analysis-resolution Laplacian variance to the pool maximum.
  `frame_0085` is the maximum here (analysis variance 222.8 → `1.000`). The
  focus weight therefore ranks relative detail at analysis resolution **within
  this source**; it is not absolute sharpness. At native 1920x1080
  `frame_0013` is sharper (607.6) than `frame_0085` (407.6), and `frame_0007`
  (472.8), `frame_0001` (450.3), `frame_0037` (435.7) and `frame_0019` (433.5)
  also exceed `frame_0085`. The operator may weigh the native frames directly.
- The temporal-coverage component compares the nearest-neighbour gap to a 0.5 s
  target (`TEMPORAL_TARGET_SECONDS`). The 0.25 s sampling makes every gap
  0.208–0.25 s, so the component is capped at 0.417–0.500 and the absolute
  scores are not comparable with sparser candidate sets from other sources.
- All 17 frames come from one continuous move and the 32x32 thumbnail
  similarity is 0.975–0.981 across the top 12. Ranks 1, 3, 4, 9 and 11 are
  adjacent moments from the last second of the clip (3.00–3.96 s), not
  independent compositions; rank 10 is 2.50 s. Rank 2 (`frame_0013`, 0.50 s) and rank 5
  (`frame_0037`, 1.50 s) offer views earlier in the move while the foreground
  pillar is still prominent. For the earliest view with the pillar closest to
  centre the operator may prefer `frame_0007` (0.25 s) or `frame_0019`
  (0.75 s); for the end-of-move view with the right-hand recess widest, the
  closing frames `frame_0085` (3.50 s) or `frame_0096` (3.96 s) are the
  candidate set's widest compositions.
- The mechanical score is a comparative focus/exposure/distinctness shortlist,
  not a room-suitability rank (see
  `godot_walk/evidence/2026-11-14-issue-248/REPORT.md`).

## Contact sheets

The sheets live under the source folder because `godot_walk/evidence/**/*.jpg`
is gitignored; this keeps the operator-facing images tracked with the source.

- `godot_walk/source_library/sources/video-61b91dbeb9026dc7/candidate_sheets/top-candidates.jpg`
  — the 12 top-ranked frames, labelled with rank, frame ID, time, score, focus,
  exposure, and duplicate similarity
  (SHA-256 `f366b0d709c35c600682f1fb3602646c463a5a44b0902b5b05b853c8a212322f`).
- `godot_walk/source_library/sources/video-61b91dbeb9026dc7/candidate_sheets/coverage.jpg`
  — all 17 frames in time order for coverage of the clip
  (SHA-256 `08a6bc8716faa4191ea43d4a292b0f368e7a271a4aad4eac426e60a17a28fc8d`).

Both sheets are scaled previews for operator review only; neither is a seed and
neither may be used as a Hunyuan input. They were produced with the shared,
source-agnostic builder `godot_walk/scripts/build_issue171_candidate_sheet.py`,
which verifies every frame SHA-256 against the ranking report before drawing.

## Operator step

**`select-seed` is PENDING.** The operator selects one direct-source
full-resolution frame from `frames/issue177-quarter-s-a/` (or asks for other
moments or a fresh batch) and records it with the runner. Until then
`can_start_attempt` stays `false` and no Hunyuan stage is authorized. The
operator also decides whether this source yields a room, a cross-junction or
other topology archetype reference, or a reject; this report makes no claim
about room identity, openings, or connectivity.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-61b91dbeb9026dc7 --run-id issue177-quarter-s-a \
  --indices 0,6,12,18,24,30,36,42,48,54,60,66,72,78,84,90,95
python3 godot_walk/scripts/run_freeview_consensus.py inventory \
  --source-id video-61b91dbeb9026dc7 \
  --output godot_walk/evidence/2026-11-14-issue-177/mechanical-ranking.json
python3 godot_walk/scripts/build_issue171_candidate_sheet.py \
  --ranking godot_walk/evidence/2026-11-14-issue-177/mechanical-ranking.json \
  --output-dir godot_walk/source_library/sources/video-61b91dbeb9026dc7/candidate_sheets \
  --top 12
```

## Checks

- `python3 godot_walk/scripts/register_video_sources.py validate` — valid,
  13 registered sources.
- The focused runner/consensus/source-library tests
  (`test_source_ingestion_runner.py`, `test_freeview_consensus.py`,
  `test_video_source_library.py`) — 37 passed, 4 subtests passed in 0.48 s.
- Full `python3 -m pytest -q godot_walk/scripts` — **1495 passed, 5 skipped,
  67 subtests passed** (264.89 s). No test was changed for this stage.
- No hash-pinned file, frozen workflow, or earlier source event was edited;
  events are append-only and remain bound to the manifest hash above.
- No Python, Godot, or hash-pinned file changed for this stage; the working
  tree adds only this report, the ranking JSON, the extracted frames, the
  contact sheets, and one appended event.
