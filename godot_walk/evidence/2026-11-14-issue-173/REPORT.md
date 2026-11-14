# Issue #173 — `video-d857abe7a94da9d1` frame extraction and mechanical seed shortlist

Status: **steps 1–3 complete (2026-11-14). Operator `select-seed` is PENDING.**
The review-source decision is already recorded as `proceed`. This run extracted a
full-resolution direct-source coverage set and computed the #169 mechanical
seed ranking. It did not run `select-seed`, `authorize-room-attempt`, Hunyuan,
Panogen, or any model/paid/API-token call. `registration_accepted` and
`scale_calibrated` remain `false`. The operator closes the issue.

## Source and gate state

| Item | Value |
|---|---|
| Source ID | `video-d857abe7a94da9d1` |
| Source path | `data/videos/Max Cooper - Repetition (Official Video By Kevin McGloughlin).mp4` |
| Source SHA-256 | `d857abe7a94da9d19a4a1410a707e7632c32df6f3ded1ddd4d77317df1732bb8` |
| Manifest | `godot_walk/source_library/sources/video-d857abe7a94da9d1/source_manifest-v3.json` |
| Manifest SHA-256 | `87bc8e05cbdd34bb8cfc9a016b05dd17a552a5b0a69711215999b0453f7cd93e` |
| Review-source decision | `proceed` (event sequence 3, 2026-11-14T12:57:31Z) |
| Native video | 1280x720, 24 fps, 8,556 frames, 356.566 s |
| Attempts used | 0 / 3 |
| Selected seed | `null` — operator step PENDING |

## Content observation

The registered clip is a 356 s music video assembled as a montage of built
spaces and repetition patterns, not a single continuous camera move. Visible
sections include glass curtain-wall facades, terraced housing blocks, a white
lattice shell, striped facades with moving figures, a lattice canopy, a wind
turbine field, woven ribbons, a mirrored library rotunda, a scale-model city,
motorway interchanges, container stacks, and a lit tunnel interior near 280 s.
The final ~16 s are black credit frames.

The issue records that this source's value may be **rhythm and repetition
rules for the generative map rather than a literal room**. That remains the
operator's judgement. This run does not force a room, does not infer room
boundaries from the montage, and claims no openings or connectivity.

## Frame extraction

A 37-frame coverage set at 10 s spacing spans the whole clip from 0.00 s to
356.46 s. Every frame is a direct decode of the registered video at native
1280x720 with no resize or edit. The set is split into three fresh batch run
IDs so each extraction call completes in one pass; the ranking below treats
them as one candidate pool.

| Batch | Frames | Indices | Window |
|---|---:|---|---|
| `issue173-10s-a` | 12 | 0–2640 | 0.00–110.00 s |
| `issue173-10s-b` | 12 | 2880–5520 | 120.00–230.00 s |
| `issue173-10s-c` | 13 | 5760–8555 | 240.00–356.46 s |

Indices: `0,240,480,720,960,1200,1440,1680,1920,2160,2400,2640,
2880,3120,3360,3600,3840,4080,4320,4560,4800,5040,5280,5520,
5760,6000,6240,6480,6720,6960,7200,7440,7680,7920,8160,8400,8555`.

Each batch appended a `direct_frame_batch_extracted` event (sequences 4–6)
bound to manifest hash `87bc8e05cbdd34bb8cfc9a016b05dd17a552a5b0a69711215999b0453f7cd93e`.
Extraction manifests and per-frame SHA-256 values live under
`godot_walk/source_library/sources/video-d857abe7a94da9d1/frames/`:

| Batch | Extraction manifest SHA-256 |
|---|---|
| `issue173-10s-a` | `ad8b7ef8a0b2333d40cd674f601a2c613a1c19e073ac25343fd5b3fe3b577851` |
| `issue173-10s-b` | `dc74b848a2dd1c4ff2564b25e66a8495b07661882f50ff1048a1508a7eddde10` |
| `issue173-10s-c` | `bacd03315c4558c189d5b8e59cb94d903309e9f27353f091cad4cd2ca4feec09` |

## Mechanical ranking

The ranking reuses the #169 scoring core (`seed_review_candidates.py`,
`seed_review_metrics.py`) through
`run_freeview_consensus.py inventory`, which validates every frame's
direct-source identity, native resolution, and SHA-256 before scoring. The
score weights are focus 0.50, exposure 0.25, thumbnail distinctness 0.15, and
temporal coverage 0.10. All 37 frames are in the pool; the top three are the
frames a three-frame seed review would shortlist, and the remaining 34 are
shortlist-excluded for the model-review limit, not rejected.

Top 12 by mechanical score
(`mechanical-ranking.json`):

| Rank | Frame | Time (s) | Score | Focus | Exposure | Duplicate |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `frame_3841` | 160.00 | 0.819758 | 1.000 | 0.844 | 0.941 |
| 2 | `frame_5281` | 220.00 | 0.660472 | 0.905 | 0.397 | 0.942 |
| 3 | `frame_5761` | 240.00 | 0.656660 | 0.601 | 0.965 | 0.900 |
| 4 | `frame_6001` | 250.00 | 0.592361 | 0.528 | 0.872 | 0.931 |
| 5 | `frame_2401` | 100.00 | 0.578882 | 0.515 | 0.853 | 0.948 |
| 6 | `frame_1201` | 50.00 | 0.572508 | 0.607 | 0.611 | 0.891 |
| 7 | `frame_3361` | 140.00 | 0.564253 | 0.422 | 0.959 | 0.909 |
| 8 | `frame_6241` | 260.00 | 0.548723 | 0.439 | 0.874 | 0.929 |
| 9 | `frame_3601` | 150.00 | 0.547053 | 0.339 | 0.986 | 0.794 |
| 10 | `frame_2641` | 110.00 | 0.540711 | 0.450 | 0.832 | 0.948 |
| 11 | `frame_4321` | 180.00 | 0.511950 | 0.474 | 0.642 | 0.903 |
| 12 | `frame_4561` | 190.00 | 0.457965 | 0.312 | 0.751 | 0.905 |

The complete 37-frame table with every component is in
`mechanical-ranking.json`. The report's `"issue": 210` field is a hardcoded
provenance value inside `run_freeview_consensus.py` (issue 210 owns the
consensus tooling); it is not this issue's number.

### Reading the scores for this source

- Rank 1 (`frame_3841`, 160 s) is a close-up of a corrugated facade. Its
  near-perfect focus score reflects high-frequency texture, not room depth.
- Rank 2 (`frame_5281`, 220 s) is a tangle of dark ribbons against blue; it is
  high-detail but not room-like.
- The mirrored library rotunda at 180 s (`frame_4321`, rank 11) is an
  interior-looking space.
- The lit tunnel interior at 280 s (`frame_6721`) ranks 29 with score
  `0.384868` (focus `0.156`, exposure `0.702`, duplicate `0.792`) because most
  of the frame is dark. It is recorded here as an observation only: the
  operator may prefer it as a literal corridor seed even though the mechanical
  score does not shortlist it.
- `frame_8161` (340 s), `frame_8401` (350 s), and `frame_8556` (356.46 s) are
  black credit frames, kept only to prove coverage of the full length; they
  score at the floor.
- The mechanical score is a comparative focus/exposure/distinctness shortlist,
  not a room-suitability rank (see
  `godot_walk/evidence/2026-11-14-issue-248/REPORT.md`).

## Contact sheets

The sheets live under the source folder because `godot_walk/evidence/**/*.jpg`
is gitignored; this keeps the operator-facing images tracked with the source.

- `godot_walk/source_library/sources/video-d857abe7a94da9d1/candidate_sheets/top-candidates.jpg`
  — the 12 top-ranked frames, labelled with rank, frame ID, time, score, focus,
  exposure, and duplicate similarity.
- `godot_walk/source_library/sources/video-d857abe7a94da9d1/candidate_sheets/coverage.jpg`
  — all 37 frames in time order for coverage of the montage.

Both sheets are scaled previews for operator review only; neither is a seed
and neither may be used as a Hunyuan input. They were produced with the shared,
source-agnostic builder `godot_walk/scripts/build_issue171_candidate_sheet.py`,
which verifies every frame SHA-256 against the ranking report before drawing.

## Operator step

**`select-seed` is PENDING.** The operator selects one direct-source
full-resolution frame from the extracted batches (or asks for a different
moment) and records it with the runner. Until then `can_start_attempt` stays
`false` and no Hunyuan stage is authorized. The operator also decides whether
this source yields a room at all or only rhythm/repetition rules for the
generative map; this report makes no claim about room identity, openings, or
connectivity.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-d857abe7a94da9d1 --run-id issue173-10s-a \
  --indices 0,240,480,720,960,1200,1440,1680,1920,2160,2400,2640
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-d857abe7a94da9d1 --run-id issue173-10s-b \
  --indices 2880,3120,3360,3600,3840,4080,4320,4560,4800,5040,5280,5520
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-d857abe7a94da9d1 --run-id issue173-10s-c \
  --indices 5760,6000,6240,6480,6720,6960,7200,7440,7680,7920,8160,8400,8555
python3 godot_walk/scripts/run_freeview_consensus.py inventory \
  --source-id video-d857abe7a94da9d1 \
  --output godot_walk/evidence/2026-11-14-issue-173/mechanical-ranking.json
python3 godot_walk/scripts/build_issue171_candidate_sheet.py \
  --ranking godot_walk/evidence/2026-11-14-issue-173/mechanical-ranking.json \
  --output-dir godot_walk/source_library/sources/video-d857abe7a94da9d1/candidate_sheets \
  --top 12
```

## Checks

- `python3 godot_walk/scripts/register_video_sources.py validate` — valid,
  13 registered sources.
- The focused runner/consensus/source-library tests
  (`test_source_ingestion_runner.py`, `test_freeview_consensus.py`,
  `test_video_source_library.py`) — 37 passed, 4 subtests passed in 0.51 s.
- Full `python3 -m pytest -q godot_walk/scripts` — **1495 passed, 5 skipped,
  67 subtests passed** (290.09 s). No test was changed for this stage.
- `ruff check` and `black --check` on the reused
  `build_issue171_candidate_sheet.py` and `run_freeview_consensus.py` — clean.
- No hash-pinned file, frozen workflow, or earlier source event was edited;
  events are append-only and remain bound to the manifest hash above.
- No Python, Godot, or hash-pinned file changed for this stage; the working
  tree adds only this report, the ranking JSON, the extracted frames, the
  contact sheets, and the three appended events.
