# Issue #175 — `video-102caf53423018b7` frame extraction and mechanical seed shortlist

Status: **steps 1–3 complete (2026-11-14). Operator `select-seed` is PENDING.**
The review-source decision is already recorded as `proceed`. This run extracted a
full-resolution direct-source coverage set and computed the #169 mechanical
seed ranking. It did not run `select-seed`, `authorize-room-attempt`, Hunyuan,
Panogen, or any model/paid/API-token call. `registration_accepted` and
`scale_calibrated` remain `false`. The operator closes the issue.

## Source and gate state

| Item | Value |
|---|---|
| Source ID | `video-102caf53423018b7` |
| Source path | `data/videos/corridor_straight.mp4` |
| Source SHA-256 | `102caf53423018b75dfd1976b5a2346b0576bdd316429f246aee87a884ba3d4b` |
| Manifest | `godot_walk/source_library/sources/video-102caf53423018b7/source_manifest-v3.json` |
| Manifest SHA-256 | `6c4863b240d035cdc52b78fc6a33b79dc07b610df5d6663d19cc8f6f7364d626` |
| Review-source decision | `proceed` (event sequence 3, 2026-11-14T12:57:32Z) |
| Native video | 1920x1080, 24 fps, 96 frames, 4.0 s |
| Frame batch event | sequence 4, bound to manifest hash `6c4863b2…4d626` |
| Attempts used | 0 / 3 |
| Selected seed | `null` — operator step PENDING |

## Content observation

The registered clip is a single 4.0 s forward camera move with no cuts. The
sampled frames show a carpeted interior corridor: yellow-green patterned
wallpaper, a suspended ceiling grid holding rectangular fluorescent light
panels, beige carpet, and square structural pillars that divide the walls into
bays. The camera advances and passes a large square pillar that starts on the
left of frame at 0.00 s, drifts to the right edge by 2.25 s, and leaves the
view by 2.50 s. The last 1.5 s look down a straight run of wall bays with the
ceiling lights receding to a vanishing point. Mean luminance rises gently from
about 127 to a peak of about 134 (of 255) at 2.67 s and then falls to about 119
by the last frame, with no fade to black and no title card.

The filename suggests a straight corridor with two opposed openings, but the
name is not evidence. This stage records only what the sampled frames show: one
corridor receding in the camera's direction of travel with wall bays and
pillars on both sides. The frames do not establish doorways, thresholds, room
boundaries, or connectivity, and this stage authors no opening or socket. The
mechanical score below compares frames only and is **not** a room-suitability
assessment.

## Frame extraction

A 17-frame coverage set at 0.25 s spacing (every sixth source frame) plus the
last decodable frame spans the whole clip from 0.00 s to 3.96 s. Every frame is
a direct decode of the registered video at native 1920x1080 with no resize or
edit. The clip is a single continuous camera move, so even spacing covers the
whole observed space; the extraction does not infer room boundaries.

| Batch | Frames | Indices | Window |
|---|---:|---|---|
| `issue175-quarter-s-a` | 17 | 0–95 | 0.00–3.96 s |

Indices: `0,6,12,18,24,30,36,42,48,54,60,66,72,78,84,90,95`.

The batch appended a `direct_frame_batch_extracted` event (sequence 4) bound to
manifest hash `6c4863b240d035cdc52b78fc6a33b79dc07b610df5d6663d19cc8f6f7364d626`.
The extraction manifest is
`godot_walk/source_library/sources/video-102caf53423018b7/frames/issue175-quarter-s-a/extraction_manifest.json`
(SHA-256 `792d25587e148054cb32a875ecdf52a2286c85f6d3f79c5ab24d27ecd8165432`);
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
| 1 | `frame_0096` | 3.96 | 0.782265 | 1.000 | 0.955 | 0.987 |
| 2 | `frame_0091` | 3.75 | 0.731631 | 0.902 | 0.948 | 0.987 |
| 3 | `frame_0085` | 3.50 | 0.725413 | 0.875 | 0.942 | 0.985 |
| 4 | `frame_0013` | 0.50 | 0.670896 | 0.784 | 0.906 | 0.985 |
| 5 | `frame_0079` | 3.25 | 0.666829 | 0.764 | 0.928 | 0.981 |
| 6 | `frame_0007` | 0.25 | 0.650403 | 0.741 | 0.912 | 0.986 |
| 7 | `frame_0073` | 3.00 | 0.635044 | 0.711 | 0.907 | 0.980 |
| 8 | `frame_0067` | 2.75 | 0.631953 | 0.713 | 0.890 | 0.980 |
| 9 | `frame_0001` | 0.00 | 0.628146 | 0.694 | 0.917 | 0.986 |
| 10 | `frame_0019` | 0.75 | 0.617463 | 0.680 | 0.899 | 0.982 |
| 11 | `frame_0061` | 2.50 | 0.616290 | 0.681 | 0.890 | 0.976 |
| 12 | `frame_0049` | 2.00 | 0.599128 | 0.643 | 0.892 | 0.971 |

The complete 17-frame table with every component is in
`mechanical-ranking.json`. The report's `"issue": 210` field is a hardcoded
provenance value inside `run_freeview_consensus.py` (issue 210 owns the
consensus tooling); it is not this issue's number.

### Reading the scores for this source

- The scoring pipeline analyses every frame at 640x360 (`ANALYSIS_WIDTH`,
  `ANALYSIS_HEIGHT` in `seed_review_metrics.py`), and the focus component
  normalises the analysis-resolution Laplacian variance to the pool maximum.
  `frame_0096` is the maximum here (269.6 → `1.000`). The focus weight therefore
  ranks relative detail at analysis resolution **within this source**; it is
  not absolute sharpness. At native 1920x1080 the ordering differs:
  `frame_0013` (`559.8`) and `frame_0001` (`476.8`) are sharper than
  `frame_0096` (`461.9`), yet they rank 4th and 9th. The operator may weigh the
  native frames directly.
- The temporal-coverage component compares the nearest neighbour gap to a 0.5 s
  target (`TEMPORAL_TARGET_SECONDS`). The 0.25 s sampling makes every gap
  0.208–0.25 s, so the component is capped at 0.417–0.500 and the absolute
  scores are not comparable with sparser candidate sets from other sources.
- All 17 frames come from one continuous dolly and the 32x32 thumbnail
  similarity is 0.971–0.987 across the top 12. Ranks 1–3 are adjacent moments
  from the last half-second of the clip (3.50–3.96 s), not independent
  compositions. For the widest view of the first wall bay, the operator may
  prefer the opening frames `frame_0001` (0.00 s), `frame_0007` (0.25 s) or
  `frame_0013` (0.50 s), which show that bay before the camera moves past the
  pillar into the long straight run.
- The mechanical score is a comparative focus/exposure/distinctness shortlist,
  not a room-suitability rank (see
  `godot_walk/evidence/2026-11-14-issue-248/REPORT.md`).

## Contact sheets

The sheets live under the source folder because `godot_walk/evidence/**/*.jpg`
is gitignored; this keeps the operator-facing images tracked with the source.

- `godot_walk/source_library/sources/video-102caf53423018b7/candidate_sheets/top-candidates.jpg`
  — the 12 top-ranked frames, labelled with rank, frame ID, time, score, focus,
  exposure, and duplicate similarity
  (SHA-256 `6f6e379b252befa519dd1675dfacfce67d0522241d1e36bfc2ddf2f06c700cc8`).
- `godot_walk/source_library/sources/video-102caf53423018b7/candidate_sheets/coverage.jpg`
  — all 17 frames in time order for coverage of the clip
  (SHA-256 `3c47b481ef91b729e121b12df97a95334f7dc72ca3b6178c5db4d0a964abb0c9`).

Both sheets are scaled previews for operator review only; neither is a seed and
neither may be used as a Hunyuan input. They were produced with the shared,
source-agnostic builder `godot_walk/scripts/build_issue171_candidate_sheet.py`,
which verifies every frame SHA-256 against the ranking report before drawing.

## Operator step

**`select-seed` is PENDING.** The operator selects one direct-source
full-resolution frame from `frames/issue175-quarter-s-a/` (or asks for other
moments or a fresh batch) and records it with the runner. Until then
`can_start_attempt` stays `false` and no Hunyuan stage is authorized. The
operator also decides whether this source yields a room, a straight-corridor
archetype reference, or a reject; this report makes no claim about room
identity, openings, or connectivity.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-102caf53423018b7 --run-id issue175-quarter-s-a \
  --indices 0,6,12,18,24,30,36,42,48,54,60,66,72,78,84,90,95
python3 godot_walk/scripts/run_freeview_consensus.py inventory \
  --source-id video-102caf53423018b7 \
  --output godot_walk/evidence/2026-11-14-issue-175/mechanical-ranking.json
python3 godot_walk/scripts/build_issue171_candidate_sheet.py \
  --ranking godot_walk/evidence/2026-11-14-issue-175/mechanical-ranking.json \
  --output-dir godot_walk/source_library/sources/video-102caf53423018b7/candidate_sheets \
  --top 12
```

## Checks

- `python3 godot_walk/scripts/register_video_sources.py validate` — valid,
  13 registered sources.
- The focused runner/consensus/source-library tests
  (`test_source_ingestion_runner.py`, `test_freeview_consensus.py`,
  `test_video_source_library.py`) — 37 passed, 4 subtests passed in 0.49 s.
- Full `python3 -m pytest -q godot_walk/scripts` — **1495 passed, 5 skipped,
  67 subtests passed** (294.13 s). No test was changed for this stage.
- No hash-pinned file, frozen workflow, or earlier source event was edited;
  events are append-only and remain bound to the manifest hash above.
- No Python, Godot, or hash-pinned file changed for this stage; the working
  tree adds only this report, the ranking JSON, the extracted frames, the
  contact sheets, and one appended event.
