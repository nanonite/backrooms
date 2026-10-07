# #107 — coverage-complete source clip for both reconstruction tracks

Date: 2026-10-07 · Base commit: `a0d1dbf` · Issue: **#107** (parent #106; blocks #104 and #108)

## 1. Outcome

A new, single, 1080p continuous Backrooms clip was generated and is delivered as
the shared source for both tracks:

| | |
|---|---|
| Clip | `data/scenes/backrooms_coverage_v1/video.mp4` |
| Size | 1920x1080, 24 fps, 8.000 s, 192 frames, h264/yuv420p, 16,463,899 bytes |
| sha256 | `d50f6770cb5767109202e1bcae41e4e412035ff4852c8a6b86d9e28aeae55f06` |
| Model | `google/veo-3.1-lite` (image-to-video, seeded from `Backrooms_model.jpg`) |
| generation id | `gen-vid-1791408274-CRIWF6kH2IpI3DWS4e7Y` |
| Prompt / settings | `generation.json` (this directory); seed sha256 `e5c1ead9…82a18` |

The clip is git-ignored under `data/` like every other source capture in this
repo; this directory is the tracked record (prompt, settings, gate output, pose
evidence, sampled contact sheet, key frames, hashes).

**Verdict up front.** The clip passes the pipeline's *current* Stage A capture
gate (`capture_gate.py`) as `ACCEPTED_WITH_WARNINGS`, and it shows the wall and
the wall/floor and wall/ceiling joins deliberately. It does **not** pass the
older `preflight_parallax.py` gate (median triangulation angle 4.57° vs the 6°
minimum), and COLMAP registers it as two overlapping components rather than one.
Both facts are documented below; they are the honest limit of what a synthetic
generator produced here. See §8 for what that means for #104/#108.

## 2. Why no existing clip was reused

#104 has no outputs: it is `open` and `blocked_by` #107 itself, so there is no
#104 capture to inherit. The pre-existing synthetic captures were re-gated this
run (JSON in `existing/`):

| Existing clip | Gate verdict | Blocking / warning |
|---|---|---|
| `data/videos/room_large.mp4` | accepted_with_warnings | `single_direction_walk` — 1 direction over 0.57 frame widths |
| `data/videos/corridor_x.mp4` | accepted_with_warnings | `rotation_dominant` — 24% explained |
| `data/videos/dead_end.mp4` | accepted_with_warnings | `rotation_dominant` — 2% explained |
| `corridor_straight` / `corridor_corner` / `corridor_t` / `corridor_travel` | **rejected** (#91) | `camera_path_too_short`, `too_few_frames` |

None is coverage-complete: the three that pass are either a single-direction
walk or rotation-dominant (pan-only, which #107 explicitly rejects), and none
was prompted for, or checked against, the missing-wall and floor/ceiling-join
requirement. So a new clip was produced.

## 3. The delivered clip (candidate A)

Prompt (exact text also in `generation.json`):

> Continuous single-take first-person walk through one bounded backrooms room,
> eight seconds, one unbroken shot, no cuts, no teleports. The camera body
> physically walks forward at a steady pace across the open carpet floor, then
> turns smoothly and keeps walking sideways across the room to the opposite
> side, so the camera travels in two different directions. While walking it
> deliberately faces the far wall of the room and holds it in frame, showing the
> whole wall surface including the clean horizontal join where the wall meets
> the carpeted floor and the join where the wall meets the drop ceiling. The
> camera passes within arm's reach of the side walls and a structural column, so
> nearby textured surfaces fill the frame and shift with parallax. Yellow
> patterned wallpaper, moist carpet tiles, drop ceiling with recessed fluorescent
> light panels. One rigid consistent room, fixed geometry, stable lighting, sharp
> focus, no motion blur, no flicker, no people, no windows, fixed camera lens,
> photorealistic, liminal backrooms.

Settings: `duration=8s`, `resolution=1080p`, `aspect_ratio=16:9`,
`generate_audio=false`, one `first_frame` seed image. Reproduce with
`python3 scripts/generate_coverage_clip.py`.

## 4. Current Stage A capture gate — ACCEPTED_WITH_WARNINGS

`scripts/splat_pipeline/capture_gate.py data/scenes/backrooms_coverage_v1/video.mp4
--target-frames 150 --json capture_gate.json` (exit 0; full output in
`gate_stdout.txt`, machine JSON in `capture_gate.json`):

| Measurement | Value | Requirement | Result |
|---|---|---|---|
| camera travel | **0.942** frame widths | ≥ 0.25 | pass |
| travel directions | **4** | ≥ 2 | pass |
| selected frames | **111** of 192 | ≥ 30 | pass |
| temporal consistency | `temporal_geometry_consistent` (4.7% pixels changed, 0.0% blocks) | one rigid scene | pass |
| cuts | none detected | reject cuts | pass |
| `rotation_dominant` | 25% explained | ≥ 25% | **warning (borderline)** |

The single warning is that the median global translation explains exactly 25% of
the frame change (the threshold). It is a warning, not a block: the clip still
travelled ~0.94 frame widths in four directions, so it is not pan-only.

## 5. Pose evidence (COLMAP, selected frames)

`colmap feature_extractor` → `sequential_matcher --SequentialMatching.overlap 20`
→ `colmap mapper` on the 111 gate-selected frames (log `colmap_pose.log`):

| Model | Cameras | Points | Mean track | Mean reprojection error |
|---|---|---|---|---|
| `sparse_seq/1` | 86 | 6,638 | 7.79 | **0.755 px** |
| `sparse_seq/2` | 45 | — | — | — |
| `sparse_seq/0` | 5 | — | — | — |

All 111 frames register, but the mapper consistently splits them into two main
components (86 and 45) **that overlap on 20 frames** (`frame_0026`–`frame_0045`
appear in both). So the views do overlap — this is a mapper outcome, not a
coverage gap — but the clip does not fuse into a single model. Exhaustive
matching reproduces the same 86 + 45 split; GLOMAP, the supported global-SfM
path, aborts on this database (`Reconstruction::Load` → `std::invalid_argument`).
A denser run over all 192 frames (sequential overlap 30) reaches 113 + 99
cameras, 10,683 points, and lifts the angle only to 5.01°.

## 6. Legacy parallax gate — FAIL (documented, not hidden)

`scripts/splat_pipeline/preflight_parallax.py sparse_seq/1` (`preflight_parallax.txt`):

| Measurement | Value | Need | Result |
|---|---|---|---|
| lateral/forward ratio | 14.7% | ≥ 10% | pass |
| near-field coverage | 51.7% | ≥ 25% | pass |
| median triangulation angle | **4.57°** | ≥ 6° | **fail** |

This is the repo's own gate conflict, not a hidden failure: the historically
shipped asset (`corridor_travel`, a column orbit) **passes** `preflight_parallax`
at 6.20° but **fails** the current Stage A gate (`camera_path_too_short`, 0.17
widths). The new clip is the mirror image — it passes Stage A and fails
preflight. #107's acceptance names the capture gate, not the old parallax gate,
so the clip is delivered against that; the preflight result is reported so #104
can weigh it.

## 7. Coverage check the gates cannot make (human/visual)

The gate measures motion, not surfaces, so the missing-wall and join
requirement was checked against the sampled frames (`contact_sheet.jpg` = all
111 selected frames; `key_frames/` = start, mid, end at full resolution). The
frames show one bounded Backrooms room — wallpaper walls, structural columns,
carpet tiles, drop ceiling with fluorescent panels — with the camera translating
across it. Full wall surfaces and both joins are visible and held: the wall/floor
join (baseboard) and the wall/ceiling join are in frame in the wide wall-facing
frames (`frame_0075_wall_joins.jpg`, `frame_0111_end.jpg`). No cuts.

Honest caveat visible in the frames: the floor "stain" morphs across the clip
(small at the start, large by the end). Geometry is stable — the gate scores the
scene consistent — but AI-generated texture is not perfectly static, which is
also the likely cause of the two-component COLMAP split.

## 8. Rejected candidate and what that shows

A second clip (candidate B, `candidate_b.generation.json`) was generated with a
stronger near-field prompt ("small enclosed alcove … within one metre …"). It
was worse on every axis and was **not** delivered:

| | candidate A (delivered) | candidate B (rejected) |
|---|---|---|
| Stage A travel / directions | 0.94 widths / 4 | 0.89 widths / 4 |
| Stage A `rotation_dominant` | 25% | **2%** (pan-dominant) |
| COLMAP best model | 86 cameras | 54 cameras |
| near-field coverage | 51.7% | **12.6%** (far-field) |
| median triangulation angle | 4.57° | **2.44°** |

Candidate A is the better synthetic result and is the one shared clip; B is kept
only as provenance. This bounds the claim: the generator did not respond to a
near-field instruction, so a synthetic clip that clears *both* gates is not
something this pipeline produced.

## 9. Limitations

1. **Fails the legacy parallax gate** (§6). A reconstruction from this clip is
   expected to be softer than the historical column-orbit asset.
2. **Two-component COLMAP registration** (§5). The two components overlap, so
   views are shared, but #104 may need `model_merger`/GLOMAP, or may see a seam.
3. **AI texture drift** (§7). Geometry is consistent; floor detail is not.
4. **Not real footage.** Like every prior clip in this repo it is AI-generated;
   success here is not evidence about real captures.
5. **Pose evidence is COLMAP-only.** GLOMAP aborts on this database.

## 10. Handoff

* The one shared clip is `data/scenes/backrooms_coverage_v1/video.mp4`. #108 must
  consume this same file; do not generate a second capture for the mesh branch.
* #104 may train from it, but should read §6/§9 first: the parallax gate is
  below its historical bar. If a higher-parallax source is required, that is a
  real capture or an operator-chosen generator run, not something this worker
  could extract from the synthetic generator.
* Nothing here closes or changes #103/#104, and no historical asset was
  overwritten (the previous column-orbit clip and all `data/videos/*.mp4` are
  untouched).

## 11. Verification (this tree)

| Check | Result |
|---|---|
| `validate_input.py` on the clip | Hard checks passed (exit 0) |
| `capture_gate.py` on the clip | exit 0, `ACCEPTED_WITH_WARNINGS` |
| `sample_frames.py` | 111/111 selected frames written at 1920x1080 |
| COLMAP (feature → match → map) | 111 frames register; 86 + 45 overlapping components |
| `preflight_parallax.py` | exit 1 (4.57° < 6°) — reported, not hidden |
| `pytest scripts/splat_pipeline/tests/test_coverage_clip.py` | 8 passed |
| Full `pytest scripts/splat_pipeline/tests/` | see COMMANDS.md (same 6 pre-existing failures as #88/#99/#103) |

### Files added by this run

* `scripts/splat_pipeline/coverage_clip.py` — pure prompt/settings/payload spec.
* `scripts/generate_coverage_clip.py` — the OpenRouter generator CLI (overwrite-guarded).
* `scripts/splat_pipeline/tests/test_coverage_clip.py` — 8 tests.
* `godot_walk/evidence/2026-10-07-coverage-source-clip/` — this evidence.
* On disk (git-ignored): `data/scenes/backrooms_coverage_v1/` (video, generation.json,
  capture_gate.json, frames/, sparse_seq/, candidates/).
