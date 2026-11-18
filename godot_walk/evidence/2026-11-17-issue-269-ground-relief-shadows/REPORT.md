# Chainlink issue 269 — Open-world step 2b: authored ground relief and static tree shadows

Child of #258 (open-world umbrella), under #169, ingestion track. Operator-directed
2026-11-17 from `docs/research/issue-260-ground-relief-shadows.md`. This is the
combined "Ready-to-file first implementation slice" named in that doc. No model
call, GPU inference, download, catalog admission, integration, socket choice,
registration or metric-scale claim was performed. No tracked file was edited;
all artifacts are new.

## Blocker resolution (precondition)

Issue #269 declares `blocked_by=[268]`. Verified before authoring anything:

- `chainlink --json issue show 268` → `status="closed"`,
  `closed_at="2026-11-18T05:57:14.674101061Z"`, with operator note 655 closing it as
  spec-complete after the tree-prototype fixture review. The blocking precondition
  is met. No content from #268 (or any other issue) was copied into this fixture.
- `chainlink --json issue show 269` → `status="open"`, `comments=[]`,
  `blocked_by=[268]`, `blocking=[270]`.

## Acceptance copied from the named research doc

From `docs/research/issue-260-ground-relief-shadows.md`, section "Ready-to-file
first implementation slice" (verbatim):

> **Title:** Prototype authored ground relief and tree shadows in an isolated open-world fixture
>
> **Scope:** Build one small, deterministic, standalone test fixture outside the accepted room and frozen catalog. Use a shallow irregular terrain surface and static tree-shadow shapes with one documented assumed direction. Use local authored data only; record provenance and the intended collision policy. Do not change existing accepted or hash-pinned files, flags, or catalog decisions. No model, GPU run, download, or external service is part of this slice.
>
> **Acceptance:**
>
> 1. The fixture visibly contains more varied relief than flattened ellipsoids and long tree shadows that originate at their corresponding trees and share the documented direction. Treat both as authored approximations.
> 2. State explicitly whether collision follows the relief or stays flat, and bound the visible-to-collision height difference so traversal implications are reviewable. Do not imply measured scale.
> 3. Provide reproducible local fixture generation or scene data and checks for deterministic bounds, shadow/tree pairing, common direction, collision policy, and absence of edits to accepted assets. Preserve `registration_accepted=false` and `scale_calibrated=false`.
> 4. Supply a comparison plan using named, repeatable viewpoints and request operator review of the visual result. A structural test alone cannot approve appearance or catalog admission.
>
> **Verification:** Run relevant CPU-only structural tests and document commands and results. If a supported rendering environment is available under its own authorization, capture matching views and report actual conditions and outcomes; otherwise explicitly leave rendering and visual review outstanding. Operator compares the reference and fixture for drift shape, shadow continuity/direction, style, and traversal plausibility. Any later lit or reconstructed approach requires its own design and authorization.

## What was done (new files only)

| File | Purpose |
|------|---------|
| `fixture/relief_spec_v1.json` | Authored drift parameters (four anisotropic humps, one swale), 0.5-unit sampling grid, `|height| <= 0.35` bound, and the **flat** collision policy with a single box collider. |
| `fixture/shadow_spec_v1.json` | Four authored trees, four tapered long polygons, one shared direction vector `[0.866, 0.5]` (azimuth 30°) with assumed light from azimuth 210°, and per-shadow tree pairing/origin/length. |
| `fixture/views_v1.json` | Five named camera viewpoints, reused byte-for-byte by both captures; all flags false. |
| `fixture/relief_shadows_v1.tscn` / `.gd` | Variant: continuous triangulated relief mesh with height baked into vertex colours, four static shadow ribbons sampled onto that surface, four simple trees with independent trunk colliders, flat floor collider and safe spawn. |
| `fixture/baseline_relief_v1.tscn` / `.gd` | Baseline: the current scheme from the issue-255 report — flattened ellipsoids above a flat floor/box collider, same trees, **no** shadows and no relief mesh. |
| `fixture/authored_data_v1.md`, `fixture/limitations_v1.md` | Explicit authored-data provenance, collision policy, bound and pre-review limitations. |
| `fixture/pinned_supplement_v1.json` | Hashes for supplemental pinned docs/catalog, computed by the generator script (not authored by hand). |
| `fixture/capture_views.gd`, `fixture/test_fixture.gd` | Paired capture driver and headless structural/traversal verification. |
| `scripts/generate_pinned_supplement_v1.py` | Reproducible local generator for the pinned supplement record. |
| `scripts/verify_relief_fixture_v1.py`, `scripts/test_verify_relief_fixture_v1.py` | Read-only integrity validator (bounds, pairing, direction, collision policy, flags, pinned assets) and its positive/negative tests. |
| `captures/paired_v1/{baseline,variant}/*.png`, `captures/paired_v1/capture_manifest_v1.json` | Ten generated paired captures and their camera manifest (local-only; see limitations). |
| `resource/paired_capture_resource.json` | Guard receipt produced by the existing guarded capture wrapper (not written by hand). |

### Collision policy (explicit answer for acceptance item 2)

Collision **stays flat**; it does not follow the relief. A single `BoxShape3D`
collider has its top at `y = 0.0`. The visible relief is bounded to
`|height| <= 0.35` design units (measured extremes from the authored spec:
`+0.314` at drift peaks, `-0.170` in the swale), so the maximum
visible-to-collision height difference is **0.35 design units**. Traversal is on
a flat plane while the visual surface undulates within that bound. These are
uncalibrated design units; no metric scale or source registration is implied.

### Ledger

No events, receipts or hashes were written by hand. No existing runner stage
covers this isolated CPU-authored fixture slice, so no runner stage was invoked
and no `events.jsonl` was appended. The capture guard receipt was produced by the
existing guarded capture wrapper. `registration_accepted` and
`scale_calibrated` remain false in all three records, both scenes and the
capture manifest.

## Commands and results (repository root)

1. Preconditions:
   `chainlink --json issue show 268` → #268 closed (operator note 655);
   `chainlink --json issue show 269` → open, no comments, blocked only by 268.
2. `python3 godot_walk/evidence/2026-11-17-issue-269-ground-relief-shadows/scripts/verify_relief_fixture_v1.py`
   → `PASS issue-269 relief fixture: deterministic relief bounds, flat collision, shadow/tree pairing, common direction, views, flags and pinned assets verified`, `EXIT=0`.
3. `python3 -m pytest -q godot_walk/evidence/2026-11-17-issue-269-ground-relief-shadows/scripts/test_verify_relief_fixture_v1.py`
   → `11 passed in 0.25s`, `EXIT=0`.
   Covers: real fixture clean, files resolve, missing view, non-flat policy,
   unknown tree, divergent direction, height-bound violation, flattened relief,
   true flag, edited pinned file, missing limitations.
4. `godot4 --headless --path godot_walk --script res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/test_fixture.gd`
   → `ISSUE_269_WALK: forward_z=2.167 side_x=2.667`,
   `ISSUE_269_FIXTURE_TESTS_PASSED`, `EXIT=0`. A benign `ObjectDB instances leaked
   at exit` warning was printed by Godot during teardown.
   This verifies: both scenes load; the player settles on the flat floor; the
   relief AABB stays inside the ±0.35 bound and varies by ≥0.15; shading is
   baked vertex colour; there is exactly one shadow per tree, each originating
   at its tree and sharing the documented direction with length ≥5; the floor
   collider is a box with top at y=0 whose ray hit has a working negative
   control; forward and side traversal stay supported on the flat plane; the
   baseline keeps flattened ellipsoids and has no shadows; all flags false.
5. Guarded capture (no `--headless`; `DISPLAY=:1`, Vulkan 1.4.329 Forward+ on
   NVIDIA RTX 4070 Ti):
   `python3 godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/run_capture_guarded.py --output-dir godot_walk/evidence/2026-11-17-issue-269-ground-relief-shadows/captures/paired_v1 --report godot_walk/evidence/2026-11-17-issue-269-ground-relief-shadows/resource/paired_capture_resource.json --timeout-seconds 240 -- godot4 --path godot_walk --script res://evidence/2026-11-17-issue-269-ground-relief-shadows/fixture/capture_views.gd -- --out=res://evidence/2026-11-17-issue-269-ground-relief-shadows/captures/paired_v1`
   → `ISSUE_269_PAIRED_CAPTURES_READY`, `CAPTURE_GUARD_EXIT=0`; receipt
   `return_code=0`, `timed_out=false`, `elapsed_seconds=4.95`, no compute apps,
   preflight VRAM headroom 9.14 GB / RAM headroom 17.29 GB.
   Ten PNGs at 1152×648; manifest lists ten views with positions/targets and
   `registration_accepted=false`, `scale_calibrated=false`,
   `operator_review=pending`.
   One earlier guarded run was discarded before review after the relief was
   strengthened for legibility (amplitudes and baked colour contrast); the
   reviewed captures are the second, successful guarded run. The wrapper's
   static `label` field reads `snow-garden-courtyard-v2-capture` because it is
   the existing shared wrapper; its recorded command, output and report paths
   all point to this issue-269 fixture.
6. `python3 godot_walk/scripts/register_video_sources.py validate`
   → `{"valid": true, "registered_count": 13}`, `VALIDATE_EXIT=0`.
7. `python3 -m ruff check godot_walk/evidence/2026-11-17-issue-269-ground-relief-shadows/scripts/*.py`
   → `All checks passed!`; `python3 -m ruff format --check ...` → all formatted
   (`ruff format` applied before the final check).
8. `python3 -m pytest -q godot_walk/scripts`
   → `1566 passed, 5 skipped, 94 subtests passed in 267.76s`, `PYTEST_EXIT=0`.
9. The ten PNGs were opened and viewed as a paired contact sheet, then the
   variant `close`, `side` and `elevated` views were opened at full size.
   Observations are recorded under "Honest limitations" below. No visual pass is
   claimed.

## Comparison plan (request for operator review)

| View | Position / target (design units) | Compare |
|------|----------------------------------|---------|
| `front` | `(0, 1.6, 10)` → `(0, 0.6, 0)` | full-plot drift silhouettes and baseline ellipsoids |
| `side` | `(10, 1.6, 0)` → `(0, 0.6, 0)` | cross-plot profile; shadow reach and foreshortening |
| `oblique` | `(7.5, 2.4, 7.5)` → `(-1, 0.3, -1)` | drift continuity and whether shadow polygons stay on the surface |
| `close` | `(-6, 1.4, -0.5)` → `(-3.6, 0.3, -1.9)` | one tree base and the shadow that originates there |
| `elevated` | `(7, 8, 7)` → `(0, 0, 0)` | whole relief pattern and common shadow direction |

The operator is asked to compare each baseline/variant pair against
`docs/research/issue-260-ground-relief-shadows.md` and the snow-garden reference
for **drift shape, shadow continuity and direction, style, and traversal
plausibility**, and to decide whether this authored approximation warrants a
successor (for example a lit or reconstructed approach, which needs its own
design and authorization). A passing validator, clean headless test or clean
capture is **not** approval. Nothing here admits or connects anything to the
catalog.

## Acceptance mapping

| Acceptance item | Evidence |
|-----------------|----------|
| 1. Varied relief + long paired shadows, one direction, authored approximations | `relief_spec_v1.json` (continuous irregular mesh vs baseline ellipsoids); `shadow_spec_v1.json` (4 trees/4 ribbons, shared `[0.866,0.5]`, length ≥6); headless checks; 10 paired PNGs; `authored_data_v1.md` |
| 2. Flat collision stated and difference bounded; no measured scale | `relief_spec_v1.json.collision`, `authored_data_v1.md`, this report "Collision policy"; headless box-collider/top-at-zero and ±0.35 AABB checks |
| 3. Reproducible data + checks for bounds, pairing, direction, policy, no accepted edits, false flags | three JSON specs + generator; validator commands 2–3; accepted-record (50 deps), contract-freeze-v4 (43 files) and supplement hash checks; flags false everywhere |
| 4. Named repeatable viewpoints + operator review requested | `views_v1.json`, manifest, "Comparison plan" above; `operator_review=pending` |

## Pending the operator (not decided by this agent)

- Compare the paired captures and decide whether the relief and shadows read
  naturally against the reference and whether the style is acceptable.
- Decide whether the flat-collision / visual-relief mismatch is acceptable for
  traversal; no feel judgement is made here.
- Decide whether any successor issue should investigate lit terrain, real
  shadow casting or reconstruction. This doc authorizes none of that.
- Any admission, integration, socket or registration decision remains a separate
  operator workflow.

## Honest limitations

- All geometry, colours, spawn, light direction and capture cameras are authored
  in uncalibrated design units. No metric scale, registration or source
  connectivity is established; `registration_accepted=false` and
  `scale_calibrated=false` everywhere.
- The relief is shallow (bounded at 0.35 units across an 18-unit plot). In the
  eye-height `front` and `side` views it reads as gentle undulation with baked
  light/dark patches rather than pronounced hills; it is more legible in the
  `oblique` and `elevated` views. Whether that is "varied enough" is an operator
  judgement, not a passing-test result.
- Shadows are static tapered polygons with one assumed direction, no softness,
  no penumbra and no dynamic light. From the `side` view a ribbon receding toward
  the camera is strongly foreshortened and can read as a vertical strip; this is
  recorded, not resolved.
- Both scenes use unshaded materials for a fair comparison (no PSX compositor);
  the background is the default clear colour, not a source panorama. This is an
  isolated fixture, not a scene-fidelity demonstration.
- The plot is finite (18 × 18 with a safety net). It makes no claim about
  unbounded open-world boundaries.
- Agents cannot hear or walk. The headless traversal checks are mechanical
  physics assertions on a flat collider; they are not a human judgement of feel.
- The ten PNGs and the capture manifest live under `captures/` and stay local by
  the operator's `.gitignore` policy for bulky evidence outputs; only the
  report, records, scripts and guard receipt are committed. A reviewer with this
  workspace can open the PNGs directly or regenerate them with command 5.
- No ledger events were appended and no hashes, receipts or decisions were
  written by hand. A passing validator, clean headless test or clean capture is
  not approval.
