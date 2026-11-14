# Issue #176 — `video-2671b32f256a4ee7` frame extraction and mechanical seed shortlist

Status: **steps 1–3 complete (2026-11-14). Operator `select-seed` is PENDING.**
The review-source decision is already recorded as `proceed`. This run extracted a
full-resolution direct-source coverage set and computed the #169 mechanical
seed ranking. It did not run `select-seed`, `authorize-room-attempt`, Hunyuan,
Panogen, or any model/paid/API-token call. `registration_accepted` and
`scale_calibrated` remain `false`. The operator closes the issue.

## Source and gate state

| Item | Value |
|---|---|
| Source ID | `video-2671b32f256a4ee7` |
| Source path | `data/videos/corridor_t.mp4` |
| Source SHA-256 | `2671b32f256a4ee7f326fae67290bcec2143efabb4f1000fc4bcfa9507260409` |
| Manifest | `godot_walk/source_library/sources/video-2671b32f256a4ee7/source_manifest-v3.json` |
| Manifest SHA-256 | `101159bf8200611ef994a1f5b8ba5f4eaa86ff839972128150eb15e1a16245ae` |
| Review-source decision | `proceed` (event sequence 3, 2026-11-14T12:57:32Z) |
| Native video | 1920x1080, 24 fps, 96 frames, 4.0 s |
| Frame batch event | sequence 4, bound to manifest hash `101159bf…16245ae` |
| Attempts used | 0 / 3 |
| Selected seed | `null` — operator step PENDING |

## Content observation

The registered clip is a single 4.0 s forward camera move with no cuts. Between
the 17 sampled frames the mean absolute gray-level difference stays in the
narrow 8.7–11.8 band and mean luminance stays between 141 and 146 of 255, with
no fade to black and no title card.

The sampled frames show a carpeted interior in the same synthetic vocabulary as
the other corridor captures: yellow-green patterned wallpaper, a suspended
ceiling grid holding rectangular fluorescent light panels, beige carpet, and
square structural pillars or freestanding wall blocks that divide the space into
bays. The camera starts beside a large square pillar slightly left of centre,
advances past it, and leaves it behind by about 2.50 s. The rest of the move
looks down a long open sightline between wall sections, with a wall corner at
the right edge in the closing frames.

The filename suggests a T-junction with three openings, but the filename is not
evidence and the clip was not verified as such. This stage records only what the
sampled frames show: one forward camera move through a carpeted, wallpapered
space past pillars and wall sections. The frames do not establish doorways,
thresholds, room boundaries, or connectivity, and this stage authors no opening
or socket. The mechanical score below compares frames only and is **not** a
room-suitability assessment.

## Frame extraction

A 17-frame coverage set at 0.25 s spacing (every sixth source frame) plus the
last decodable frame spans the whole clip from 0.00 s to 3.96 s. Every frame is
a direct decode of the registered video at native 1920x1080 with no resize or
edit. The clip is a single continuous camera move, so even spacing covers the
whole observed space; the extraction does not infer room boundaries.

| Batch | Frames | Indices | Window |
|---|---:|---|---|
| `issue176-quarter-s-a` | 17 | 0–95 | 0.00–3.96 s |

Indices: `0,6,12,18,24,30,36,42,48,54,60,66,72,78,84,90,95`.

The batch appended a `direct_frame_batch_extracted` event (sequence 4) bound to
manifest hash `101159bf8200611ef994a1f5b8ba5f4eaa86ff839972128150eb15e1a16245ae`.
The extraction manifest is
`godot_walk/source_library/sources/video-2671b32f256a4ee7/frames/issue176-quarter-s-a/extraction_manifest.json`
(SHA-256 `912ecb50d00d9bed47e2552da2f570647a2b327e238fbcfcbb249f3f6a0f26bd`);
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
| 1 | `frame_0096` | 3.96 | 0.768150 | 1.000 | 0.900 | 0.989 |
| 2 | `frame_0085` | 3.50 | 0.750388 | 0.948 | 0.893 | 0.980 |
| 3 | `frame_0091` | 3.75 | 0.733176 | 0.935 | 0.890 | 0.989 |
| 4 | `frame_0079` | 3.25 | 0.720513 | 0.887 | 0.896 | 0.980 |
| 5 | `frame_0073` | 3.00 | 0.707786 | 0.862 | 0.895 | 0.980 |
| 6 | `frame_0013` | 0.50 | 0.706810 | 0.856 | 0.910 | 0.989 |
| 7 | `frame_0067` | 2.75 | 0.689479 | 0.829 | 0.889 | 0.980 |
| 8 | `frame_0061` | 2.50 | 0.685482 | 0.820 | 0.890 | 0.981 |
| 9 | `frame_0007` | 0.25 | 0.672721 | 0.786 | 0.913 | 0.989 |
| 10 | `frame_0019` | 0.75 | 0.667765 | 0.780 | 0.904 | 0.989 |
| 11 | `frame_0037` | 1.50 | 0.666309 | 0.781 | 0.894 | 0.986 |
| 12 | `frame_0025` | 1.00 | 0.654886 | 0.756 | 0.900 | 0.988 |

The complete 17-frame table with every component is in
`mechanical-ranking.json`. The report's `"issue": 210` field is a hardcoded
provenance value inside `run_freeview_consensus.py` (issue 210 owns the
consensus tooling); it is not this issue's number.

### Reading the scores for this source

- The scoring pipeline analyses every frame at 640x360 (`ANALYSIS_WIDTH`,
  `ANALYSIS_HEIGHT` in `seed_review_metrics.py`), and the focus component
  normalises the analysis-resolution Laplacian variance to the pool maximum.
  `frame_0096` is the maximum here (analysis variance 365.8 → `1.000`). The
  focus weight therefore ranks relative detail at analysis resolution **within
  this source**; it is not absolute sharpness. At native 1920x1080 the ordering
  differs: `frame_0013` (604.3), `frame_0007` (472.9), `frame_0037` (467.8) and
  `frame_0001` (459.6) are sharper than `frame_0096` (365.8), yet they rank 6th,
  9th, 11th and 14th. The operator may weigh the native frames directly.
- The temporal-coverage component compares the nearest-neighbour gap to a 0.5 s
  target (`TEMPORAL_TARGET_SECONDS`). The 0.25 s sampling makes every gap
  0.208–0.25 s, so the component is capped at 0.417–0.500 and the absolute
  scores are not comparable with sparser candidate sets from other sources.
- All 17 frames come from one continuous dolly and the 32x32 thumbnail
  similarity is 0.980–0.989 across the top 12. Ranks 1–5 are adjacent moments
  from the last second of the clip (3.00–3.96 s), not independent compositions,
  and rank 6 (`frame_0013`, 0.50 s) is nearly tied with them. For a view that
  still includes the large foreground pillar the operator may prefer
  `frame_0007` (0.25 s), `frame_0013` (0.50 s) or `frame_0019` (0.75 s); for
  the clear sightline past the pillar, the closing frames `frame_0085`
  (3.50 s) or `frame_0096` (3.96 s) are the candidate set's widest views.
- The mechanical score is a comparative focus/exposure/distinctness shortlist,
  not a room-suitability rank (see
  `godot_walk/evidence/2026-11-14-issue-248/REPORT.md`).

## Contact sheets

The sheets live under the source folder because `godot_walk/evidence/**/*.jpg`
is gitignored; this keeps the operator-facing images tracked with the source.

- `godot_walk/source_library/sources/video-2671b32f256a4ee7/candidate_sheets/top-candidates.jpg`
  — the 12 top-ranked frames, labelled with rank, frame ID, time, score, focus,
  exposure, and duplicate similarity
  (SHA-256 `5f9e50e989bbc75ab5daa35d3079accfb8dcf552066af01bd25d8db857ac4ac7`).
- `godot_walk/source_library/sources/video-2671b32f256a4ee7/candidate_sheets/coverage.jpg`
  — all 17 frames in time order for coverage of the clip
  (SHA-256 `e133aa7410b8b14bf4f94d350c12fcbb7411198a8a943c1d4b440fa6cd1e5da1`).

Both sheets are scaled previews for operator review only; neither is a seed and
neither may be used as a Hunyuan input. They were produced with the shared,
source-agnostic builder `godot_walk/scripts/build_issue171_candidate_sheet.py`,
which verifies every frame SHA-256 against the ranking report before drawing.

## Operator step

**`select-seed` is PENDING.** The operator selects one direct-source
full-resolution frame from `frames/issue176-quarter-s-a/` (or asks for other
moments or a fresh batch) and records it with the runner. Until then
`can_start_attempt` stays `false` and no Hunyuan stage is authorized. The
operator also decides whether this source yields a room, a T-junction or other
topology archetype reference, or a reject; this report makes no claim about
room identity, openings, or connectivity.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames \
  video-2671b32f256a4ee7 --run-id issue176-quarter-s-a \
  --indices 0,6,12,18,24,30,36,42,48,54,60,66,72,78,84,90,95
python3 godot_walk/scripts/run_freeview_consensus.py inventory \
  --source-id video-2671b32f256a4ee7 \
  --output godot_walk/evidence/2026-11-14-issue-176/mechanical-ranking.json
python3 godot_walk/scripts/build_issue171_candidate_sheet.py \
  --ranking godot_walk/evidence/2026-11-14-issue-176/mechanical-ranking.json \
  --output-dir godot_walk/source_library/sources/video-2671b32f256a4ee7/candidate_sheets \
  --top 12
```

## Checks

- `python3 godot_walk/scripts/register_video_sources.py validate` — valid,
  13 registered sources.
- The focused runner/consensus/source-library tests
  (`test_source_ingestion_runner.py`, `test_freeview_consensus.py`,
  `test_video_source_library.py`) — 37 passed, 4 subtests passed in 0.49 s.
- Full `python3 -m pytest -q godot_walk/scripts` — **1495 passed, 5 skipped,
  67 subtests passed** (266.95 s). No test was changed for this stage.
- No hash-pinned file, frozen workflow, or earlier source event was edited;
  events are append-only and remain bound to the manifest hash above.
- No Python, Godot, or hash-pinned file changed for this stage; the working
  tree adds only this report, the ranking JSON, the extracted frames, the
  contact sheets, and one appended event.
