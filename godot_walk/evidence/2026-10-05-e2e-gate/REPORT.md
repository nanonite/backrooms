# End-to-end acceptance gate (#91) — report

**Task:** #91 Verify end-to-end video walkthroughs on representative local fixtures
**Parent:** #78 · **Supersedes:** #44, #76
**Date:** 2026-10-05 · **Worker:** Chainlink agent, workflow `chainlink_7q9dq`, attempt 1/8
**Verdict:** **BLOCKED — #91 remains OPEN.** The one-command pipeline does not
complete on this host for any fixture, and no real capture exists to satisfy the
primary acceptance. Precise missing evidence below.

## Summary

| Question | Answer |
|---|---|
| Real textured single-room capture with measured reference? | **No** — none exists locally. |
| Difficult low-texture real capture? | **No** — none exists locally. |
| Synthetic corridor/column-orbit input? | **Yes** — 7 clips; only 3 pass the current capture gate. |
| One-command pipeline completes on a synthetic fixture? | **No** — blocked at Stage B for all 3 eligible clips. |
| Calibrated alignment (#83/#74) verified? | Yes, on the historical synthetic asset. |
| Generated collision (#84) passes? | No — 9/10 checks pass; camera-path coverage is 20.3 % (< 90 %). |
| Production-controller physics (#85) verified? | Yes, fresh run, exit 0. |
| Real-GPU visual + fps? | Yes — 4 non-blank PNGs; 58.94 fps @1280x720. |
| Fresh/resumed equivalence? | Yes, via the pipeline integration test (4 passed). |

## The blocking findings

1. **No real capture.** All local video is AI-generated (`scripts/generate_videos.py`,
   Veo 3.1-lite) at 1080p. The only real-looking asset is a downloaded PlayCanvas
   demo splat with no capture, poses or contract. The task explicitly says
   "synthetic success is not evidence of general real-video reconstruction", so
   the primary acceptance is unscorable here.

2. **Stage B default path blocked.** `glomap` is not installed, and the documented
   install (`nix develop` + `setup-pipeline-tools.sh install-glomap`) fails at
   `cmake` configuration (`FindDependencies.cmake`, `CMakeLists.txt:23`).

3. **Stage B VGGT fallback has a pipeline bug.** `sample_frames.py` writes
   `images/frames.json`; VGGT's `load_and_preprocess_images_square` globs `*` and
   crashes with `PIL.UnidentifiedImageError` on that manifest. (Reproducible:
   `logs/pipeline_room_large_fresh.log`.)

4. **VGGT fallback OOMs on 12 GiB once the glob is worked around.** 50 frames →
   11 757 MiB; 31 frames → 11 805 MiB; both `torch.cuda.OutOfMemoryError` in the
   global-attention block.

5. **The pipeline's gate rejects its own historical input.** The 8 s column-orbit
   clip that trained the shipped `corridor_splat` asset scores 0.17 frame widths
   of travel and is rejected (`camera_path_too_short`). The shipped asset is not
   reproducible through the current one-command pipeline.

## What does work (on the historical synthetic asset)

- Alignment contract (#83) reproduces exactly; rendered AABB matches to 4
  decimals (real-GPU).
- Production controller (#85): full walk battery passes fresh, zero SafetyNet
  contacts, wall/column blocking and openings verified.
- Real-GPU render: 58.94 fps at 1280x720 with 182 569 splats (0.28 GiB stage
  VRAM).
- Collision mesh is watertight and self-consistent, **but fails
  `walkway_covers_camera_path`** (20.3 % of camera positions navigable, need
  90 %) — carried forward honestly from #84.

## Precise missing evidence (why #91 stays open)

1. A **real camera capture** of a textured single room, with a tape-measured
   reference distance, plus a low-texture difficult capture, recorded with
   provenance and permitted use.
2. A working **Stage B** on this host: either GLOMAP installed (fix the
   `FindDependencies.cmake` failure) or the VGGT fallback fixed (filter
   `frames.json`) and made to fit 12 GiB (frame chunking or lower resolution).
3. A **complete fresh one-command run** on the real fixture producing
   `scene.ply`, `alignment_manifest.json`, `collision.collision.glb`,
   `traversal_manifest.json`, with alignment/collision/walk/render scored against
   the tolerances in `RESULTS.md`.
4. A **real-GPU walkthrough verdict** (human or scripted) on that real scene, plus
   a fresh-vs-resumed comparison within the documented Stage C tolerance.

## Artifacts

| File | Contents |
|---|---|
| `ENVIRONMENT.md` | host, GPU, engine, tool versions, gsplat workaround |
| `FIXTURES.md` | fixture inventory, provenance, gate verdicts, fidelity classes |
| `RESULTS.md` | pre-registered tolerances, linked results table, peaks |
| `COMMANDS.md` | exact reproducible commands |
| `logs/` | capture-gate logs (7), pipeline logs (3), traversal, render, tests, GLOMAP install, hashes, tool versions, 1 Hz resource samples |
| `screenshots/` | 4 fresh real-GPU PNGs of `corridor.tscn` |
| `../2026-10-05-gdgs-alignment/` | #74 real-GPU alignment evidence (retained) |
| `../../assets/corridor_splat/{README,TRAVERSAL}.md` | #83/#84/#85 contracts (retained) |

## Honest limitations

- The walk and render results are for the **synthetic** column-orbit asset, not a
  real capture; they show the downstream physics/visual path, not general
  real-video reconstruction.
- The rendered fps (58.94) is against a 60 Hz vsync cap; headroom is not
  established.
- The scale (5.128384 m/unit) is a **choice** for synthetic footage, not a
  measurement.
- Collision is validated only on the region the generated mesh leaves navigable;
  `walls_measured: false` means the room footprint is observation bounds, not
  measured wall planes.
