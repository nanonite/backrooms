# Chainlink issue 271 — Open-world step 2d: authored bench material fallback

Child of #258 (open-world umbrella), under #169, ingestion track. Operator-directed
2026-11-17 from the merged research doc `docs/research/issue-264-prop-materials.md`.
This is the combined "Ready-to-file first implementation slice" named in that doc.
No model call, GPU inference, download, paid call, catalog admission, integration,
socket choice, registration or scale claim was made. No tracked file was edited;
all artifacts are new. This preview was not accepted by this agent.

## Blocker resolution (precondition)

Issue #271 declares `blocked_by=[270]`. Verified before authoring anything:

- `chainlink issue show 270 --json` → `status="closed"`,
  `closed_at="2026-11-18T14:51:53.259301105Z"` (operator note recorded review of
  the #262 acceptance). The blocking precondition is met. No content from #270
  or any other issue was copied into this fixture.
- `chainlink issue show 271 --json` → `status="open"`, `blocked_by=[270]`,
  `blocking=[272]`, `comments=[]`. There are no operator comments to apply.

## Acceptance copied from the named research doc

From `docs/research/issue-264-prop-materials.md`, section "Ready-to-file first
implementation slice" (verbatim):

> **Title:** Record and preview an authored prop material fallback for the snow-garden bench
>
> **Scope:** Create a new, isolated candidate derived from the snow-garden reference, with an authored stone-like bench material and a machine-readable material decision alongside it. Record the bench's material origin as `project_authored`, its explicit color/parameters, intended role, rationale, and the fact that the available reference does not establish a faithful bench surface. Identify the original reference and its hashes; distinguish any source crop evidence from the authored fallback. Restrict the visual change to bench parts: the reference shares its stone material with the statue plinth, so give the bench a separate assignment rather than silently changing that plinth. Do not change the accepted room or frozen artifacts, catalog or ledger, and keep both calibration flags false. No model, GPU, downloads or paid calls. This is a preview for review, not acceptance or registration. [Sources: `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/room.gd`; `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json`.]
>
> **Acceptance:** A new candidate and decision record identify every bench material assignment and its parameters; no robe crop is assigned to the bench. The record makes no claim that authored pixels were observed in the source. The statue plinth, geometry and collision remain unchanged relative to the reference. Existing accepted and hash-pinned files remain byte-identical; no catalog admission or calibration is implied. Provide comparable reference and candidate views for operator review, including a close bench view and a wider scene view, or explicitly report if capture is unavailable. The operator decides visual suitability; a mechanical pass does not grant approval.
>
> **Verification:** Check material assignments and recorded parameters against the candidate, compare hashes of protected files before and after, and run the applicable candidate/contract checks without modifying their frozen inputs. Compare geometry and collision declarations against the reference. Capture the two views using the existing guarded workflow if the environment supports it, record commands and results, and request operator review. Report unavailable checks and avoid claiming a visual pass without actual captures. [Source for the existing candidate's guarded workflow: `godot_walk/evidence/2026-11-17-issue-255-room-candidate/REPORT.md` §§4–5.]

## What was done (new files only)

| File | Purpose |
|------|---------|
| `fixture/bench_material_decision_v1.json` | Machine-readable decision: `project_authored` origin, explicit RGBA/roughness/shading/texture parameters, intended role, rationale, no-observed-pixels and no-source-faithfulness statements, original reference + crop hashes, every one of the 16 bench assignments (12 stone parts change, four bollards unchanged), separate robe-crop evidence, plinth unchanged, both flags false. |
| `fixture/bench_geometry_v1.json` | Geometry and collision declarations copied from the accepted `room.gd`: 16 bench parts, statue plinth, bench/statue/floor/wall/safety colliders, 18 tree colliders; declared unchanged for both views. |
| `fixture/bench_fixture_v1.gd` | ONE derived scene script for both views. `_bench_surface_material()` selects the shared robe crop (`reference`) or the authored fallback (`candidate`). Geometry and collision construction is never branch-dependent; bench parts carry `material_origin` metadata. All other props, the panorama, dusk lights and colliders are copied from the accepted room; player and PSX compositor are omitted for a fair isolated capture. |
| `fixture/bench_reference_v1.tscn` / `bench_candidate_v1.tscn` | The two comparison scenes. They instantiate the same script and differ only in `bench_material_mode` (`reference` / `candidate`). |
| `fixture/views_v1.json` | Four camera records reused byte-for-byte: required `bench_close` and `wider_scene`, plus `bench_oblique` and `plinth_check`. |
| `fixture/textures/*.png` | Five byte-for-byte copies of the accepted room's recorded crops (including `stone_robe.png`, sha256 `a4c0ce7f…1dd7aa`); the accepted room was only read. PNGs stay local under the operator policy; the records carry the hashes for regeneration. |
| `fixture/capture_views.gd`, `fixture/test_fixture.gd` | Guarded paired-capture driver and headless load/origin/geometry/declaration/view verification. |
| `fixture/authored_data_v1.md`, `fixture/limitations_v1.md` | Explicit authored-versus-source split, provenance and pre-review limitations. |
| `fixture/pinned_supplement_v1.json` | 11 hashes of supplemental pinned files, computed by the generator script (not written by hand). |
| `scripts/generate_pinned_supplement_v1.py` | Reproducible local generator for that supplement. |
| `scripts/verify_bench_fixture_v1.py`, `scripts/test_verify_bench_fixture_v1.py` | Read-only integrity validator (decision, assignments, unchanged plinth/geometry/collision, shared non-branching script, views, flags, pinned assets) and 14 positive/negative tests. |
| `captures/paired_v1/{reference,candidate}/*.png`, `captures/paired_v1/capture_manifest_v1.json` | Eight paired captures and the camera manifest (local-only under the operator `.gitignore` policy). |
| `resource/paired_capture_resource.json` | Guard receipt produced by the existing guarded capture wrapper (not written by hand). |

### Material split (explicit acceptance answer)

The reference shares `materials.stone` — the robe crop — between the 12 stone
bench parts and the statue plinth. The candidate moves **only** the 12 bench
parts to `materials.bench_stone`, an authored unshaded solid
`Color(0.42, 0.44, 0.47, 1.0)`, roughness 1.0, metallic 0.0, no albedo texture.
The statue plinth keeps `materials.stone` in both views. The four bench bollards
keep the reference's local solid post material in both views because they never
used the robe crop; they are still recorded as bench assignments. No robe crop is
assigned to the bench in the candidate and no claim is made that the authored
pixels were observed in the source.

### Ledger

No events, receipts or hashes were written by hand. No existing runner stage
covers this isolated CPU-authored fixture slice, so no runner stage was invoked
and no `events.jsonl` was appended. The capture guard receipt was produced by
the existing guarded capture wrapper. `registration_accepted=false` and
`scale_calibrated=false` in both specs, both scenes, the manifest, the decision
and this report.

## Commands and results (repository root)

1. Preconditions: `chainlink issue show 270 --json` → closed at
   `2026-11-18T14:51:53.259301105Z`; `chainlink issue show 271 --json` → open,
   `blocked_by=[270]`, `comments=[]`.
2. `python3 godot_walk/evidence/2026-11-17-issue-271-bench-material-fallback/scripts/generate_pinned_supplement_v1.py`
   → `Wrote …/fixture/pinned_supplement_v1.json with 11 computed hashes`.
3. `python3 -m ruff check godot_walk/evidence/2026-11-17-issue-271-bench-material-fallback/scripts/*.py`
   → `All checks passed!`; `python3 -m ruff format --check …/scripts/*.py` →
   `3 files already formatted` (`ruff format` applied before the final check).
4. `python3 godot_walk/evidence/2026-11-17-issue-271-bench-material-fallback/scripts/verify_bench_fixture_v1.py`
   → `PASS issue-271 bench fixture: authored fallback parameters, zero robe-crop bench assignments, unchanged plinth/geometry/collision, shared non-branching script, close/wider views, false flags and pinned assets verified`, `EXIT=0`.
   An earlier draft failed on two validator bugs (a function-body regex that did
   not match `-> void:` signatures and a nested-`if` lint finding); both were
   fixed in the new files before the final run.
5. `python3 -m pytest -q godot_walk/evidence/2026-11-17-issue-271-bench-material-fallback/scripts/test_verify_bench_fixture_v1.py`
   → `14 passed in 0.32s`, `EXIT=0`. Covers: real fixture clean, records resolve,
   source origin, robe crop on bench, observed-pixel claim, plinth switch,
   unknown bench material key, changed bench collision, divergent scene mode,
   branch-dependent bench geometry, script colour mismatch, missing required
   view, true flag, edited pinned file.
6. `godot4 --headless --path godot_walk --script res://evidence/2026-11-17-issue-271-bench-material-fallback/fixture/test_fixture.gd`
   → `ISSUE_271_FIXTURE_TESTS_PASSED`, `EXIT=0`. Two early GDScript parse errors
   in the new files (an undeclared camera variable and an untyped `mesh`
   inference) were fixed before this final run. This verifies: both scenes load;
   flags false and modes correct; every node, transform, mesh and collision shape
   is identical between scenes; exactly 12 bench parts change origin while the
   plinth and bollards do not; the authored material matches the recorded
   parameters and has no texture; the plinth keeps a texture; declared geometry
   and colliders match the instantiated scenes; and all four camera views are
   reproducible from their recorded transforms.
7. Guarded capture (no `--headless`; `DISPLAY=:1`, Vulkan 1.4.329 Forward+ on
   NVIDIA RTX 4070 Ti):
   `python3 godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/run_capture_guarded.py --output-dir godot_walk/evidence/2026-11-17-issue-271-bench-material-fallback/captures/paired_v1 --report godot_walk/evidence/2026-11-17-issue-271-bench-material-fallback/resource/paired_capture_resource.json --timeout-seconds 240 -- godot4 --path godot_walk --script res://evidence/2026-11-17-issue-271-bench-material-fallback/fixture/capture_views.gd -- --out=res://evidence/2026-11-17-issue-271-bench-material-fallback/captures/paired_v1`
   → `ISSUE_271_PAIRED_CAPTURES_READY`, `GUARD_EXIT=0`; receipt `return_code=0`,
   `timed_out=false`, `error=null`, `elapsed_seconds=4.306`, `compute_apps=[]`,
   finished `2026-11-18T15:02:00.549470+00:00`, preflight VRAM headroom 9.03 GB /
   RAM headroom 14.64 GB. Eight 1152×648 PNGs; manifest records exact position,
   target, forward, fov/near/far and dimensions per view, with flags false and
   `operator_review="pending; agent does not approve appearance or source interpretation"`.
   The wrapper's static `label` field reads `snow-garden-courtyard-v2-capture`
   because it is the existing shared wrapper; its recorded command, output and
   report paths all point to this issue-271 fixture.
8. Byte-level paired-image difference (no visual judgment): differing-pixel
   bounding boxes are `bench_close (221,172)-(931,517)`,
   `bench_oblique (446,237)-(760,484)`, `wider_scene (446,302)-(706,454)` and
   `plinth_check (943,36)-(1152,387)`. In the wider view the statue plinth
   (left of frame) is untouched; in `plinth_check` the plinth region is identical
   and only the bench at the right edge differs.
9. `python3 godot_walk/scripts/register_video_sources.py validate`
   → `{"valid": true, "registered_count": 13}`, `EXIT=0`.
10. `python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/adaptation_standalone_accepted_v1.json`
    → `"status": "valid"`, `static_consistency=passed`,
    `validation_is_read_only=true`, fingerprint
    `3ab070183f63c27b538af23a99196106338ec818252b8d3f6766a247af676cb9`, `EXIT=0`.
    This contract check ran against the frozen input without modifying it.
11. `python3 -m pytest -q godot_walk/scripts`
    → `1566 passed, 5 skipped, 94 subtests passed in 268.62s`, `EXIT=0`.
12. The eight PNGs were read as paired views; `bench_close`, `wider_scene` and
    `plinth_check` pairs were opened at full size. Observations are recorded
    under "Honest limitations" below. No visual pass is claimed.
13. `git status --short` → one untracked directory
    (`godot_walk/evidence/2026-11-17-issue-271-bench-material-fallback/`);
    `git diff --stat HEAD` → empty (no tracked file modified). The validator's
    pinned checks cover the accepted record's dependencies, freeze v4 and 11
    supplemental paths (including `project.godot`, `scripts/player.gd`,
    `catalog.json`, `MATERIAL_LANGUAGE.md`, `PALETTES.md`, the accepted
    `room.gd`, accepted record, crop plan/manifest and both stone crops).

## Comparison plan (request for operator review)

| View | Position / target (design units) | Compare |
|------|----------------------------------|---------|
| `bench_close` | `(0, 1.45, 3.2)` → `(0, 0.8, 0)` | **Required close bench view.** Reference robe-crop surface vs authored solid fallback on seat, plinth, legs and back. |
| `wider_scene` | `(0, 3.6, 7.2)` → `(0, 1.0, -2)` | **Required wider scene view.** Same bench change in context; statue plinth, trees, floor, bollards and sky unchanged. |
| `bench_oblique` | `(4.6, 1.8, 3.0)` → `(0, 0.85, 0)` | Second bench angle for legs, back slats and bollards. |
| `plinth_check` | `(-4.6, 1.5, 3.2)` → `(-4.6, 0.4, 0.8)` | Confirms the statue plinth keeps the reference crop in both views. |

The operator is asked to compare each pair against the research doc and the
snow-garden reference for **whether the authored grey reads as plausible stone
in this scene, whether it fits the dusk palette, and whether the split from the
plinth is visually coherent**. A passing validator, clean headless test,
localised pixel diff or clean capture is **not** approval. Nothing here admits
or connects anything to the catalog.

## Acceptance mapping

| Acceptance item | Evidence |
|-----------------|----------|
| New candidate and decision identify every bench assignment and its parameters | `bench_material_decision_v1.json` lists all 16 bench assignments with reference/candidate material keys, origins and changed flags; authored parameters explicit; validator command 4 and headless command 6 |
| No robe crop assigned to the bench | All 12 stone bench parts use `bench_stone` in candidate; `robe_crop_bench_assignments_in_candidate=0`; headless origin assertions; differing bench pixels only |
| No claim authored pixels observed in source | `source_pixels_observed_for_this_surface=false`, `no_claim_authored_pixels_observed_in_source=true`, `source_faithfulness_claimed=false`; limitations record |
| Plinth, geometry and collision unchanged | Shared non-branching script; plinth keeps `materials.stone` in both; node-by-node geometry/collision equality; declared colliders match; plinth_check pixel region identical |
| Accepted and hash-pinned files byte-identical | `git diff` empty; validator checks accepted dependencies, freeze v4 and 11 supplemental pins; `register_video_sources.py validate` and read-only bundle validation pass |
| No catalog admission or calibration implied | flags false everywhere; `catalog_admission=false`; no runner stage, ledger event or manifest edit |
| Comparable close and wider views, camera records | `bench_close`, `wider_scene` (+ two extra views) in `views_v1.json`; eight paired PNGs and manifest; guarded receipt |
| Source reference, hashes, crop evidence separated from fallback | `source_reference`, `source_crop_evidence`, `authored_material` blocks in the decision; generator-computed supplement |
| Operator decides suitability; mechanical pass is not approval | `candidate_pending_review`, `operator_review=pending`; this report requests the judgment |

## Pending the operator (not decided by this agent)

- Decide whether the authored solid grey reads as plausible stone and fits the
  dusk scene; no appearance pass is claimed.
- Decide whether the plinth should keep the robe crop or whether a later,
  separately authorised slice should give the statue its own material too.
- Decide whether a direct-source bench crop exists and is suitable; no frame
  survey was performed and no crop was extracted here.
- Any acceptance, catalog admission, integration, socket, registration or scale
  decision remains a separate operator workflow.

## Honest limitations

- All geometry, colours, materials and camera transforms are authored in
  uncalibrated design units. No metric scale, registration or source
  connectivity is established; `registration_accepted=false` and
  `scale_calibrated=false` everywhere.
- The fallback is a flat unshaded solid colour with no texture detail. In the
  viewed `bench_close` and `wider_scene` pairs it reads as a uniform grey slab
  rather than stone; whether that is acceptable is an operator judgment. It is
  deliberately not described as a source reconstruction.
- The plinth still carries the angel's robe crop in both views, so the
  reference's underlying mislabelling is preserved on the statue rather than
  fixed. This is intentional: this slice only separates the bench assignment.
- Geometry, props, panorama sky and dusk lights are copied from the accepted
  room, but the isolated fixture omits the player controller and PSX
  compositor/preset so a plain InspectionCamera can capture fair paired views.
  The absence of PSX post-processing is a capture-only difference, not a scene
  change, and the fixture is not a scene-fidelity demonstration.
- Agents cannot judge appearance. The headless checks are mechanical assertions
  on material origins, geometry and transforms; a passing validator, clean
  headless test, localised pixel diff or clean capture is not approval.
- The eight PNGs and the camera manifest live under `captures/` and stay local
  by the operator's `.gitignore` policy for bulky evidence outputs (`captures/`
  and all `*.png`, including the copied crops); only the report, records,
  scripts and guard receipt are committed. A reviewer with this workspace can
  open the PNGs directly, regenerate the captures with command 7, and recreate
  the crops by copying the five named accepted-room files (hashes are recorded).
- No ledger events were appended and no hashes, receipts or decisions were
  written by hand. The five texture crops are byte-for-byte copies of already
  recorded accepted-room crops; no new source region was claimed.
