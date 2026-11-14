# Issue #174 — `video-d92fc1fa764aa3a2` frame extraction and mechanical seed shortlist

Status: **steps 1–3 complete (2026-11-14). Operator `select-seed` is PENDING.**
The review-source decision is already recorded as `proceed`. This run extracted a
full-resolution direct-source coverage set and computed the #169 mechanical
seed ranking. It did not run `select-seed`, `authorize-room-attempt`, Hunyuan,
Panogen, or any model/paid/API-token call. `registration_accepted` and
`scale_calibrated` remain `false`. The operator closes the issue.

## Source and gate state

| Item | Value |
|---|---|
| Source ID | `video-d92fc1fa764aa3a2` |
| Source path | `data/videos/Angel (Joseph Cornell, 1957).mp4` |
| Source SHA-256 | `d92fc1fa764aa3a25a40910f01858def4b72dd3b51ca4af8d5d012d788567428` |
| Manifest | `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/source_manifest-v3.json` |
| Manifest SHA-256 | `28c01ed69ccbe6acc9854b659cbfb3a8b902903a6257542bb289f9a042b8f77f` |
| Review-source decision | `proceed` (event sequence 3, 2026-11-14T12:57:31Z) |
| Native video | 636x480, 29.97003 fps, 6,782 frames, 226.348 s |
| Frame batch events | sequences 4–7, all bound to manifest hash `28c01ed6…f77f` |
| Attempts used | 0 / 3 |
| Selected seed | `null` — operator step PENDING |

## Content observation

The registered clip is Joseph Cornell's 1957 short *Angel*, a blue-tinted
montage of a garden/cemetery rather than a continuous camera move. The sampled
frames show a stone angel statue among bare branches, a circular fountain and
reflecting pool with trees mirrored in the water, autumn flowers, several
inverted-camera views of the pool and fountain, and finally the statue's
silhouette against the sky. A title card occupies the first ~5 s and the last
frames are dark. No interior or bounded room appears in the sampled frames, and
this report makes no claim about room identity, openings, or connectivity.

The issue's note that Hunyuan suitability is doubtful remains the operator's
judgement; the mechanical score below compares frames only and is **not** a
room-suitability assessment.

## Frame extraction

A 47-frame coverage set at 5 s spacing spans the clip from 0.00 s to 226.26 s.
Every frame is a direct decode of the registered video at native 636x480 with no
resize or edit. The set is split into four fresh batch run IDs so each
extraction call completes in one pass; the ranking treats them as one
candidate pool. Five-second spacing gives multiple samples inside each detected
shot (scene changes at ~5, 21, 34, 45, 57, 71, 80, 102, 115, 153, 185, 200 and
207 s), so every visible section of the film is represented.

| Batch | Frames | Indices | Window |
|---|---:|---|---|
| `issue174-5s-a` | 12 | 0–1648 | 0.00–55.00 s |
| `issue174-5s-b` | 12 | 1798–3447 | 60.00–115.01 s |
| `issue174-5s-c` | 12 | 3596–5245 | 120.00–175.01 s |
| `issue174-5s-d` | 11 | 5395–6781 | 180.01–226.26 s |

Indices: `0,150,300,450,599,749,899,1049,1199,1349,1499,1648,
1798,1948,2098,2248,2398,2547,2697,2847,2997,3147,3297,3447,
3596,3746,3896,4046,4196,4346,4496,4645,4795,4945,5095,5245,
5395,5544,5694,5844,5994,6144,6294,6444,6593,6743,6781`.

Each batch appended a `direct_frame_batch_extracted` event (sequences 4–7)
bound to manifest hash `28c01ed69ccbe6acc9854b659cbfb3a8b902903a6257542bb289f9a042b8f77f`.
Extraction manifests and per-frame SHA-256 values live under
`godot_walk/source_library/sources/video-d92fc1fa764aa3a2/frames/`:

| Batch | Extraction manifest SHA-256 |
|---|---|
| `issue174-5s-a` | `5767db098c89ef86be33ee133369abaf82b1e7a8c76a8eda67bd55edca9ca07c` |
| `issue174-5s-b` | `08d7c863e3210f060709875cc8f9a3df30888f6488ae79f855c3b134c18fc8a6` |
| `issue174-5s-c` | `0dbeed6c0da940d4d38e49282dd3677ee4c35f7f35b25f3b6590acea80baccab` |
| `issue174-5s-d` | `2a8d25fb321dd2325b7907c4cedda370466fdb44903f6aaaf2274d839451dd0a` |

## Mechanical ranking

The ranking reuses the #169 scoring core (`seed_review_candidates.py`,
`seed_review_metrics.py`) through `run_freeview_consensus.py inventory`, which
validates every frame's direct-source identity, native resolution, and SHA-256
before scoring. The score weights are focus 0.50, exposure 0.25, thumbnail
distinctness 0.15, and temporal coverage 0.10. All 47 frames are in the pool;
the top three are the frames a three-frame seed review would shortlist, and the
remaining 44 are shortlist-excluded for the review limit, not rejected.

Top 12 by mechanical score (`mechanical-ranking.json`):

| Rank | Frame | Time (s) | Score | Focus | Exposure | Duplicate |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `frame_4347` | 145.01 | 0.820542 | 1.000 | 0.875 | 0.989 |
| 2 | `frame_4497` | 150.02 | 0.812239 | 0.977 | 0.885 | 0.985 |
| 3 | `frame_4197` | 140.01 | 0.780645 | 0.918 | 0.879 | 0.989 |
| 4 | `frame_2848` | 94.99 | 0.631930 | 0.610 | 0.841 | 0.889 |
| 5 | `frame_2998` | 100.00 | 0.615371 | 0.540 | 0.888 | 0.844 |
| 6 | `frame_0600` | 19.99 | 0.579935 | 0.494 | 0.926 | 0.991 |
| 7 | `frame_0301` | 10.01 | 0.577462 | 0.485 | 0.934 | 0.991 |
| 8 | `frame_0451` | 15.02 | 0.558438 | 0.447 | 0.929 | 0.980 |
| 9 | `frame_1500` | 50.02 | 0.547734 | 0.386 | 0.993 | 0.957 |
| 10 | `frame_1649` | 54.99 | 0.540158 | 0.372 | 0.992 | 0.957 |
| 11 | `frame_2399` | 80.01 | 0.536013 | 0.496 | 0.686 | 0.892 |
| 12 | `frame_2249` | 75.01 | 0.516608 | 0.389 | 0.797 | 0.848 |

The complete 47-frame table with every component is in
`mechanical-ranking.json`. The report's `"issue": 210` field is a hardcoded
provenance value inside `run_freeview_consensus.py` (issue 210 owns the
consensus tooling); it is not this issue's number.

### Reading the scores for this source

- The native frames are 636x480 and the scoring pipeline analyses at 640x360,
  so this source is effectively at the analysis floor. The strongest frame's
  analysis Laplacian variance is `452.1` and the focus component is normalised
  to the set maximum (`1.0` by construction). The focus weight therefore ranks
  relative detail **within this soft, low-resolution film**; it is not evidence
  of sharpness, and no absolute sharpness threshold was applied.
- Ranks 1–3 (`frame_4347`, `frame_4497`, `frame_4197`) are the same angel-statue
  shot at 140–150 s, only 5 s apart, with duplicate similarity 0.985–0.989.
  The mechanical shortlist therefore collapses to a single moment, not three
  independent options. The operator may prefer to widen the review to other
  observed sections: the fountain/reflecting-pool views around 35–55 s, the
  flower and inverted-pool views around 85–135 s, or the statue silhouette
  against the sky around 200–215 s.
- The black title/dissolve frames (`frame_0001` at 0.00 s and `frame_0151` at
  5.00 s) score at the floor (0.100086 and 0.101250); they were kept only to
  prove coverage of the full length.
- The mechanical score is a comparative focus/exposure/distinctness shortlist,
  not a room-suitability rank (see
  `godot_walk/evidence/2026-11-14-issue-248/REPORT.md`).

## Contact sheets

The sheets live under the source folder because `godot_walk/evidence/**/*.jpg`
is gitignored; this keeps the operator-facing images tracked with the source.

- `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/candidate_sheets/top-candidates.jpg`
  — the 12 top-ranked frames, labelled with rank, frame ID, time, score, focus,
  exposure, and duplicate similarity
  (SHA-256 `6728dfff78c09f5000d0674fd6a64ab693feb11695d0846fcb5edf8984cfbd38`).
- `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/candidate_sheets/coverage.jpg`
  — all 47 frames in time order for coverage of the film
  (SHA-256 `75699e6c5117be69db6283dc47e9d26e1112bd4c2800efc60ea205b5a74edc7f`).

Both sheets are scaled previews for operator review only; neither is a seed and
neither may be used as a Hunyuan input. They were produced with the shared,
source-agnostic builder `godot_walk/scripts/build_issue171_candidate_sheet.py`,
which verifies every frame SHA-256 against the ranking report before drawing.

## Operator step

**`select-seed` is PENDING.** The operator selects one direct-source
full-resolution frame from the extracted batches (or asks for a different
moment) and records it with the runner. Until then `can_start_attempt` stays
`false` and no Hunyuan stage is authorized. The operator also decides whether
this source yields a room at all, a garden/atmosphere reference, or a reject;
this report makes no claim about room identity, openings, or connectivity.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-d92fc1fa764aa3a2 --run-id issue174-5s-a \
  --indices 0,150,300,450,599,749,899,1049,1199,1349,1499,1648
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-d92fc1fa764aa3a2 --run-id issue174-5s-b \
  --indices 1798,1948,2098,2248,2398,2547,2697,2847,2997,3147,3297,3447
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-d92fc1fa764aa3a2 --run-id issue174-5s-c \
  --indices 3596,3746,3896,4046,4196,4346,4496,4645,4795,4945,5095,5245
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-d92fc1fa764aa3a2 --run-id issue174-5s-d \
  --indices 5395,5544,5694,5844,5994,6144,6294,6444,6593,6743,6781
python3 godot_walk/scripts/run_freeview_consensus.py inventory \
  --source-id video-d92fc1fa764aa3a2 \
  --output godot_walk/evidence/2026-11-14-issue-174/mechanical-ranking.json
python3 godot_walk/scripts/build_issue171_candidate_sheet.py \
  --ranking godot_walk/evidence/2026-11-14-issue-174/mechanical-ranking.json \
  --output-dir godot_walk/source_library/sources/video-d92fc1fa764aa3a2/candidate_sheets \
  --top 12
```

## Checks

- `python3 godot_walk/scripts/register_video_sources.py validate` — valid,
  13 registered sources.
- The focused runner/consensus/source-library tests
  (`test_source_ingestion_runner.py`, `test_freeview_consensus.py`,
  `test_video_source_library.py`) — 37 passed, 4 subtests passed in 0.46 s.
- Full `python3 -m pytest -q godot_walk/scripts` — **1495 passed, 5 skipped,
  67 subtests passed** (266.99 s). No test was changed for this stage.
- No hash-pinned file, frozen workflow, or earlier source event was edited;
  events are append-only and remain bound to the manifest hash above.
- No Python, Godot, or hash-pinned file changed for this stage; the working
  tree adds only this report, the ranking JSON, the extracted frames, the
  contact sheets, and the four appended events.
