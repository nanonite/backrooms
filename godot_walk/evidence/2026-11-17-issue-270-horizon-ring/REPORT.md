# Chainlink issue 270 — Open-world step 2c: finite authored horizon ring (parallax)

Child of #258 (open-world umbrella), under #169, ingestion track. Operator-directed
2026-11-17 from `docs/research/issue-262-sky-horizon-parallax.md`. This is the
combined "Ready-to-file first implementation slice" named in that doc. No model
call, GPU inference, download, catalog admission, integration, socket choice,
registration, metric-scale claim or source-fidelity claim was performed. No
tracked file was edited; all artifacts are new.

## Blocker resolution (precondition)

Issue #270 declares `blocked_by=[269]` and comment 656 had stopped a prior run
while #269 was open. Verified before authoring anything in this run:

- `chainlink issue show 269 --json` → `status="closed"`,
  `closed_at="2026-11-18T08:43:33.664502417Z"`, with operator note 657 recording
  review of the #260 acceptance items. The blocking precondition is met. No
  content from #269 (or any other issue) was copied into this fixture.
- `chainlink issue show 270 --json` → `status="open"`, `blocked_by=[269]`,
  `blocking=[271]`, one prior blocker comment.

## Acceptance copied from the named research doc

From `docs/research/issue-262-sky-horizon-parallax.md`, section "Ready-to-file
first slice" (verbatim):

> **Title:** Prototype a finite, authored horizon for an open-world reference
>
> **Scope:** Create a new standalone experimental scene and evidence outside existing accepted room folders and pinned files. Use the snow-garden reference as visual context (`godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json`). Retain a static sky background and add a small fixed-world silhouette ring, labeled authored and visual-only. Do not add traversal, sockets, inferred scale or registration, change the source reference, modify the contract/catalog, or run models. Preserve `registration_accepted=false` and `scale_calibrated=false` in any experiment metadata. Do not claim source fidelity or approval based on a test pass.
>
> **Acceptance:** The standalone experiment has finite world-fixed horizon geometry, no horizon collision or implied route, a documented bounded camera path, and a baseline with the ring disabled. Record geometry placement and authorship, source references, limitations and both false flags. Provide comparable views at two separated camera positions with the same orientation, plus an in-place rotation view; the finite horizon should shift relative to the background under translation while the baseline has no finite horizon. Record any seams, clipping or occlusion failures. No accepted artifact or pinned file changes. Operator review decides whether the effect and source interpretation are acceptable; no automatic admission or acceptance follows.
>
> **Verification:** Run available scene/resource and collision checks and a deterministic headless test of fixed geometry, camera positions and disabled baseline. Under a separately authorized rendering environment, capture the paired views and a short movement sequence with recorded camera transforms and settings; inspect them and request operator judgment. If rendering is unavailable, report that limitation and leave visual acceptance pending. Compare the working-tree changes against the allowed new experiment files and verify the existing freeze and accepted references remain unchanged.

## What was done (new files only)

| File | Purpose |
|------|---------|
| `fixture/horizon_spec_v1.json` | 24 authored silhouette panels at a fixed world radius of 36.0, authored height array, static infinity sky, `collision.policy="none"`, bounded camera path `x∈[-3,3]`, parallax threshold and sampled panel, source-reference context, false flags. |
| `fixture/views_v1.json` | Two separated same-orientation views (`translate_a`, `translate_b`), an in-place rotation view (`rotated`), an off-path elevated seam diagnostic (`seam_check`), and a five-step bounded movement sequence; reused byte-for-byte by both scenes. |
| `fixture/horizon_ring_v1.tscn` / `.gd` | Variant: static sky plus finite, world-fixed, unshaded silhouette ring with no collider, no floor and no player; InspectionCamera only. |
| `fixture/baseline_sky_v1.tscn` / `.gd` | Baseline: identical static sky, an explicitly empty `AuthoredHorizonRing` group (`horizon_enabled=false`), no finite geometry and no collider. |
| `fixture/static_sky_v1.gd` | Shared static backdrop: `ProceduralSkyMaterial` → `Sky` → `Environment.BG_SKY` (`Environment.sky`), rendered at infinity so it does not parallax under translation. |
| `fixture/authored_data_v1.md`, `fixture/limitations_v1.md` | Authored placement/provenance, source reference as context only, both false flags, and pre-review limitations including seam/clipping observations. |
| `fixture/pinned_supplement_v1.json` | Hashes for supplemental pinned files, computed by the generator script (not authored by hand). |
| `fixture/capture_views.gd`, `fixture/test_fixture.gd` | Guarded paired-capture driver (views + movement, with recorded transforms/settings) and headless structural/parallax verification. |
| `scripts/generate_pinned_supplement_v1.py` | Reproducible local generator for the pinned supplement record. |
| `scripts/verify_horizon_fixture_v1.py`, `scripts/test_verify_horizon_fixture_v1.py` | Read-only integrity validator (ring, sky, collision, path, parallax, flags, pinned assets) and its 11 positive/negative tests. |
| `captures/paired_v1/{baseline,variant}/*.png`, `captures/paired_v1/capture_manifest_v1.json` | 18 generated paired captures (4 views + 5 movement steps × 2 scenes) and camera manifest; local-only under the operator `.gitignore` policy. |
| `resource/paired_capture_resource.json` | Guard receipt produced by the existing guarded capture wrapper (not written by hand). |

### Collision and route policy (explicit acceptance answers)

The ring has **no collision and no implied route**: no `StaticBody3D`, no
`CollisionShape3D`, no floor and no character controller in either scene. The
`AuthoredHorizonRing` group holds visual `MeshInstance3D` panels only, and the
headless test asserts zero collision nodes in both scenes and zero meshes in the
baseline. The camera path is a bounded **inspection** path (`x∈[-3,3]`,
`y=1.6`, `z=0`, looking `-Z`); it is not traversal. No metric scale is involved.

### Ledger

No events, receipts or hashes were written by hand. No existing runner stage
covers this isolated CPU-authored fixture slice, so no runner stage was invoked
and no `events.jsonl` was appended. The capture guard receipt was produced by the
existing guarded capture wrapper. `registration_accepted` and
`scale_calibrated` remain false in both specs, both scenes and the capture
manifest.

## Commands and results (repository root)

1. Preconditions:
   `chainlink issue show 269 --json` → closed at 08:43:33Z (note 657);
   `chainlink issue show 270 --json` → open, `blocked_by=[269]`.
2. `python3 godot_walk/evidence/2026-11-17-issue-270-horizon-ring/scripts/verify_horizon_fixture_v1.py`
   → `PASS issue-270 horizon fixture: finite world-fixed ring, static infinity sky, no collision, bounded path, disabled baseline, parallax, false flags and pinned assets verified`, `EXIT=0`.
3. `python3 -m pytest -q godot_walk/evidence/2026-11-17-issue-270-horizon-ring/scripts/test_verify_horizon_fixture_v1.py`
   → `11 passed in 0.24s`, `EXIT=0`. Covers: real fixture clean, records resolve,
   missing view, horizon collision, finite sky, invalid panel height, divergent
   camera orientation, unmet parallax threshold, true flag, edited pinned file,
   missing limitations.
4. `godot4 --headless --path godot_walk --script res://evidence/2026-11-17-issue-270-horizon-ring/fixture/test_fixture.gd`
   → `ISSUE_270_PARALLAX: panel=18 shift_deg=9.527 (sky shift=0 by construction, BG_SKY at infinity)`,
   `ISSUE_270_FIXTURE_TESTS_PASSED`, `EXIT=0`.
   An earlier draft of this script failed on two authored mistakes (using the
   Godot-3 name `background_sky` instead of `Environment.sky`, and applying the
   ground-path bounds to the elevated `seam_check` diagnostic). Both were fixed
   in the new files before any capture was taken; the result above is the final
   run. This check verifies: both scenes load; 24 panels sit on the fixed radius
   with authored heights and distinct positions; the backdrop is `BG_SKY` with a
   procedural material marked infinity; zero colliders in both scenes and zero
   meshes in the baseline; identical orientation and ≥5-unit separation for the
   translation pair; in-place rotation; path bounds; reproducible `look_at`
   camera orientation for every view; and a 9.527° finite-ring angular shift.
5. Guarded capture (no `--headless`; `DISPLAY=:1`, Vulkan 1.4.329 Forward+ on
   NVIDIA RTX 4070 Ti):
   `python3 godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/run_capture_guarded.py --output-dir godot_walk/evidence/2026-11-17-issue-270-horizon-ring/captures/paired_v1 --report godot_walk/evidence/2026-11-17-issue-270-horizon-ring/resource/paired_capture_resource.json --timeout-seconds 240 -- godot4 --path godot_walk --script res://evidence/2026-11-17-issue-270-horizon-ring/fixture/capture_views.gd -- --out=res://evidence/2026-11-17-issue-270-horizon-ring/captures/paired_v1`
   → `ISSUE_270_PAIRED_CAPTURES_READY`, `GUARD_EXIT=0`; receipt `return_code=0`,
   `timed_out=false`, `elapsed_seconds=9.258`, `compute_apps=[]`, finished
   `2026-11-18T08:48:58.622979+00:00`, preflight VRAM headroom 9.16 GB / RAM
   headroom 14.52 GB. 18 PNGs at 1152×648; manifest records exact position,
   target, forward, fov/near/far and dimensions per view, with
   `registration_accepted=false`, `scale_calibrated=false`,
   `operator_review="pending; agent does not approve appearance or source interpretation"`.
   The wrapper's static `label` field reads `snow-garden-courtyard-v2-capture`
   because it is the existing shared wrapper; its recorded command, output and
   report paths all point to this issue-270 fixture.
6. Byte-level parallax check on the generated PNGs (no visual judgment):
   `sha256` of baseline `translate_a` and `translate_b` is identical
   (`9e8622db9ffbf38f…`), as are all baseline movement frames — the baseline has
   no finite horizon, so translation changes nothing. The variant `translate_a`
   (`f6bca25cde165ebf…`) and `translate_b` (`dae8b3d7d33873bf…`) differ, as do
   its five movement frames — the finite ring shifts against the static sky.
7. `python3 godot_walk/scripts/register_video_sources.py validate`
   → `{"valid": true, "registered_count": 13}`, `VALIDATE_EXIT=0`.
8. `python3 -m ruff check .../scripts/*.py` → `All checks passed!`;
   `python3 -m ruff format --check .../scripts/*.py` → `3 files already formatted`
   (`ruff format` applied before the final check).
9. `python3 -m pytest -q godot_walk/scripts`
   → `1566 passed, 5 skipped, 94 subtests passed in 265.71s`, `PYTEST_EXIT=0`.
10. The 18 PNGs were inspected as paired contact sheets for all four views and
    both five-step movement sequences, and the variant `translate_a`,
    `translate_b` and `seam_check` views were opened at full size. Observations
    are recorded under "Honest limitations" below. No visual pass is claimed.
11. `git status --short` → one untracked directory
    (`godot_walk/evidence/2026-11-17-issue-270-horizon-ring/`);
    `git diff --stat HEAD` → empty (no tracked file modified). The validator's
    pinned checks cover the accepted record's 50 dependencies, freeze v4's 43
    files and 5 supplemental pinned paths (including `project.godot`,
    `scripts/player.gd`, `catalog.json`, `MATERIAL_LANGUAGE.md`, `PALETTES.md`).

## Comparison plan (request for operator review)

| View | Position / target (design units) | Compare |
|------|----------------------------------|---------|
| `translate_a` | `(-3, 1.6, 0)` → `(-3, 1.6, -10)` | left end of bounded path; variant silhouette vs baseline sky only |
| `translate_b` | `(3, 1.6, 0)` → `(3, 1.6, -10)` | same orientation, separated by 6 units; silhouette should shift against the unchanged sky |
| `rotated` | `(-3, 1.6, 0)` → `(7, 1.6, 0)` | in-place rotation; ring and sky rotate together |
| `seam_check` | `(0, 3.2, 0)` → `(0, 1.4, -10)` | elevated diagnostic for panel seams, clipping and occlusion |
| `move_00`–`move_04` | `x = -3 … 3`, `y=1.6`, `z=0`, forward `-Z` | short translation sequence with recorded transforms |

The operator is asked to compare each baseline/variant pair against
`docs/research/issue-262-sky-horizon-parallax.md` and the snow-garden reference
for **whether the finite ring reads as a distant horizon, whether its movement
against the sky is convincing, whether the blocky silhouette is an acceptable
authored interpretation, and whether seams/clipping disqualify the approach**.
A passing validator, clean headless test, byte-level difference or clean capture
is **not** approval. Nothing here admits or connects anything to the catalog.

## Acceptance mapping

| Acceptance item | Evidence |
|-----------------|----------|
| Finite world-fixed horizon geometry | 24 panels at radius 36 in `horizon_spec_v1.json`; headless radius/height/distinctness checks; 18 variant PNGs |
| No horizon collision or implied route | `collision.policy="none"`; no collider/floor/player in either scene; headless zero-collision and zero-mesh-baseline assertions |
| Documented bounded camera path | `camera_path` in spec; `on_path` bounds checked in verifier and headless test; five recorded movement steps |
| Baseline with ring disabled | `baseline_sky_v1.*`; empty `AuthoredHorizonRing`, zero meshes; byte-identical baseline translation/movement PNGs |
| Geometry placement/authorship, source refs, limitations, both false flags | `authored_data_v1.md`, `limitations_v1.md`, specs, manifest; snow-garden record cited as context only; flags false everywhere |
| Two same-orientation separated views + in-place rotation | `translate_a`/`translate_b`/`rotated` in `views_v1.json`; headless orientation/separation/rotation checks; manifest records transforms |
| Finite horizon shifts under translation; baseline has no finite horizon | 9.527° analytic panel shift; differing variant PNGs vs byte-identical baseline PNGs |
| Seams, clipping, occlusion recorded | `seam_check` view + "Honest limitations" below |
| No accepted artifact or pinned file change | `git diff` empty; validator checks accepted 50 deps, freeze v4 43 files, 5 supplemental pins |
| Operator review decides; no automatic acceptance | `operator_review=pending`, `candidate_pending_review` status; this report requests judgment |

## Pending the operator (not decided by this agent)

- Decide whether the effect reads as a convincing distant horizon and whether
  the blocky authored silhouette is an acceptable interpretation of the source
  reference. No source-fidelity claim is made here.
- Decide whether the visible seams and panel/ground occlusion (below) are
  acceptable or whether a different ring representation should be investigated
  in a separately authorized follow-up.
- Decide whether the static authored gradient sky is an acceptable stand-in for
  the source panorama in this experiment.
- Any admission, integration, socket, registration or scale decision remains a
  separate operator workflow.

## Honest limitations

- All geometry, colours, sky gradient, ring radius and camera transforms are
  authored in uncalibrated design units. No metric scale, registration or source
  connectivity is established; `registration_accepted=false` and
  `scale_calibrated=false` everywhere.
- The silhouette is a row of flat-topped rectangular panels. In the full-size
  `translate_a`/`translate_b` views it reads as a blocky, crenellated wall or
  fence rather than a natural tree/terrain line. This is recorded, not resolved;
  whether it is acceptable is an operator judgment.
- In the `seam_check` view, thin light gaps are visible at several panel joins
  where the sky shows between panels at different depths, and the lower parts of
  panels are clipped by the curved ground-horizon gradient of the sky. No
  z-fighting flicker was visible in stills, but the overlaps read as a flat
  stepped band. These are recorded seam/clipping/occlusion failures, not fixes.
- The sky is an authored procedural gradient rendered at infinity, not the
  source equirectangular panorama. Its horizontal colour is nearly uniform, so
  the parallax is judged mainly from the silhouette outline; the sky is the
  fixed backdrop by construction, not by measurement.
- The ring is finite and world-fixed. It has no collision, floor or route; the
  bounded camera path is authored inspection only. Agents cannot walk or judge
  feel.
- Deck-level headless checks are mechanical assertions on finite geometry,
  infinity background and threshold angular shift; they are not a human
  judgment of depth or composition.
- The 18 PNGs and the camera manifest live under `captures/` and stay local by
  the operator's `.gitignore` policy for bulky evidence outputs; only the
  report, records, scripts and guard receipt are committed. A reviewer with this
  workspace can open the PNGs directly or regenerate them with command 5.
- No ledger events were appended and no hashes, receipts or decisions were
  written by hand. A passing validator, clean headless test or clean capture is
  not approval.
