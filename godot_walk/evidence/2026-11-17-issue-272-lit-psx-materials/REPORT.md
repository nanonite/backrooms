# Chainlink issue 272 — Open-world step 3: opt-in lit PSX materials (after the static-shadow baseline)

Child of #258 (open-world umbrella), under #169, ingestion track. Operator-directed
2026-11-17 from the merged research doc `docs/research/issue-263-psx-lighting.md`.
This is the combined "Ready-to-file first slice" named in that doc. No model call,
GPU inference, download, paid call, catalog admission, integration, socket choice,
registration or scale claim was made. No tracked file was edited; all artifacts are
new. This preview was not accepted by this agent.

## Blocker resolution (precondition)

Issue #272 declares `blocked_by=[271]`. An earlier attempt recorded a blocker because
#271 was open at 15:16 UTC. Verified fresh before authoring anything:

- `chainlink issue show 271 --json` → `status="closed"`,
  `closed_at="2026-11-18T16:34:25.653759294Z"` (operator review note recorded). The
  blocking precondition is met. Commit `d7eebaa` merged its slice.
- `chainlink issue show 272 --json` → `status="open"`, `blocked_by=[271]`,
  `blocking=[273]`; its only comment is the now-superseded 15:16 blocker. No other
  operator comment applies. No content from #271 or any other issue was copied.

## Acceptance copied from the named research doc

From `docs/research/issue-263-psx-lighting.md`, section "Ready-to-file first slice"
(verbatim):

> **Title:** Prototype opt-in lit PSX materials in an isolated open-world fixture
>
> **Scope:** Add separate experimental solid-color and textured PSX material variants and a small standalone fixture with representative surfaces and a controllable light. Preserve the current fog setting for the initial comparison. Include a baseline using the current unshaded materials and document exact camera, light and material settings. Do not modify the accepted room, existing shader dependencies, frozen contracts, catalog or source records; do not change calibration or registration flags. This slice does not implement a day/night cycle, source relighting, catalog admission or a production migration.
>
> **Acceptance:** Both material paths can be selected independently in the fixture; the baseline remains available. The fixture exposes a repeatable light-on/light-off comparison and records whether geometry visibly responds, without claiming success in advance. Document shader choices, limitations, and any material or rendering regressions. Verify existing pinned files remain byte-identical. Keep operator visual approval separate from technical checks; no inference of scale, registration or scene connectivity.
>
> **Verification:** Run relevant project import and validation tests available without a GPU, record commands and results, and compare hashes of affected frozen and accepted dependencies before and after. On operator-approved hardware, capture matched baseline and variant views with identical camera and settings, then compare light-on/light-off behavior, solid and textured surfaces, transparency, double-sided geometry, shadows, PSX character and performance. Record renderer, settings, observations and operator decision; failures remain open findings. GPU capture requires the existing guard and exclusive lock (`godot_walk/source_library/README.md`), plus operator authorization for this work.

The guarded capture was made through the existing wrapper under the shared lock, as
the operator direction for this run explicitly authorises ("render captures where
visual, through the existing guarded capture scripts, then view the PNGs").

## What was done (new files only)

| File | Purpose |
|------|---------|
| `fixture/psx_solid_baseline_v1.gdshader`, `fixture/psx_textured_baseline_v1.gdshader` | Two **new** baseline variants mirroring the accepted library shaders' defines (`UNSHADED`, `FOG_DISABLED`, `CULL_MODE cull_disabled`, plus `TEXTURE_DISABLED`/`TEXTURE_REPEAT`). Unshaded control. |
| `fixture/psx_solid_lit_v1.gdshader`, `fixture/psx_textured_lit_v1.gdshader` | Two **new** lit variants. The only define changed is removal of `UNSHADED`, so `common.gdshaderinc` selects `diffuse_lambert_wrap` + `vertex_lighting`. `FOG_DISABLED`, texture path, cull mode and the whole PSX include are retained. |
| `fixture/psx_lighting_fixture_v1.gd` | ONE shared script for all four scenes. Builds identical floor/cuboid/sphere/cylinder/back wall, key light, ambient environment and inspection camera in every scene. `_shader_path()` selects solid/textured and baseline/lit independently; `set_light_on(bool)` toggles key visibility and ambient energy together, repeatably. Fog is recorded unchanged. |
| `fixture/psx_baseline_solid_v1.tscn`, `psx_lit_solid_v1.tscn`, `psx_baseline_textured_v1.tscn`, `psx_lit_textured_v1.tscn` | Four comparison scenes, differing only in the `surface_kind`, `lighting_mode` and initial `light_on=false` properties. |
| `fixture/shader_decision_v1.json` | Machine-readable record of every shader define, material parameter, light/camera setting, fog state, preserved artifacts and false flags. |
| `fixture/views_v1.json` | Two identical camera records reused byte-for-byte by all 16 captures. |
| `fixture/capture_views.gd`, `fixture/test_fixture.gd` | Guarded paired-capture driver and headless load/geometry/shader/toggle/view verification. |
| `fixture/authored_data_v1.md`, `fixture/limitations_v1.md` | Explicit authored-versus-source split, settings, and pre-review limitations/regressions. |
| `fixture/pinned_supplement_v1.json`, `scripts/generate_pinned_supplement_v1.py` | 14 hashes computed from the working tree by the reproducible generator (not written by hand), covering the accepted room, both library shaders, the shared include, and hash-pinned project files. |
| `scripts/verify_psx_lighting_fixture_v1.py`, `scripts/test_verify_psx_lighting_fixture_v1.py` | Read-only integrity validator and 17 positive/negative tests. |
| `scripts/compute_light_response_v1.py` | Computes decoded-pixel differences between matched captures; writes the observation record under `captures/` (no visual judgment). |
| `resource/paired_capture_resource.json` | Guard receipt produced by the existing guarded capture wrapper (not written by hand). |
| `captures/paired_v1/**/*.png`, `capture_manifest_v1.json`, `light_response_v1.json` | 16 paired PNGs, camera manifest and mechanical response record; local-only under the operator `.gitignore` policy. |

### Shader choice and settings (explicit acceptance answer)

Both material paths are independently selectable via `surface_kind= solid|textured`,
and `lighting_mode= baseline|lit` independently, giving four scenes; the baseline
shaders remain available unchanged in define terms. The baseline sets `UNSHADED`
and `FOG_DISABLED` exactly like the accepted library shaders. The lit variants
remove only `UNSHADED`; the shared URSC include then uses `diffuse_lambert_wrap`
with `vertex_lighting`, `specular_disabled` and `shadows_disabled`. Fog stays
`FOG_DISABLED` with environment fog disabled in all four variants and both light
states. Exact values: solid albedo (0.62, 0.66, 0.71); authored 64 px / 8-cell
checker (0.86, 0.83, 0.75) / (0.27, 0.32, 0.39) with UV scale 3; directional key
energy 1.7, colour (1.0, 0.93, 0.82), rotation (-38, 28, 0); ambient colour
(0.5, 0.55, 0.62) energy 0.4 on / 0.0 off; camera fov 62, near 0.05, far 200 with
per-view transforms recorded in `views_v1.json`.

### Ledger

No events, receipts or hashes were written by hand. No existing runner stage covers
this isolated CPU-authored fixture slice, so no runner stage was invoked and no
`events.jsonl` was appended. The capture guard receipt and the pinned-supplement
hashes were produced by the existing scripts. `registration_accepted=false` and
`scale_calibrated=false` in every record, scene, manifest and this report.

## Commands and results (repository root)

1. Preconditions: `chainlink issue show 271 --json` → closed at
   `2026-11-18T16:34:25.653759294Z`; `chainlink issue show 272 --json` → open,
   `blocked_by=[271]`, one stale blocker comment.
2. `python3 godot_walk/evidence/2026-11-17-issue-272-lit-psx-materials/scripts/generate_pinned_supplement_v1.py`
   → `Wrote .../fixture/pinned_supplement_v1.json with 14 computed hashes`.
3. `python3 -m ruff format godot_walk/evidence/2026-11-17-issue-272-lit-psx-materials/scripts/*.py`
   → `2 files reformatted, 2 files left unchanged`;
   `python3 -m ruff check .../scripts/*.py` → `All checks passed!`;
   `python3 -m ruff format --check .../scripts/*.py` → `4 files already formatted`.
4. `python3 godot_walk/evidence/2026-11-17-issue-272-lit-psx-materials/scripts/verify_psx_lighting_fixture_v1.py`
   → `PASS issue-272 lit PSX fixture: four isolated new shader variants, fog unchanged, baseline + solid/textured independently selectable, shared non-branching geometry, repeatable light toggle, required views, false flags and pinned assets verified`, `EXIT=0`.
   An earlier draft failed on a multi-line-GDScript function-body regex and on shader
   copies not resolving from a mutated fixture dir; both were fixed in the new files
   before the final run.
5. `python3 -m pytest -q godot_walk/evidence/2026-11-17-issue-272-lit-psx-materials/scripts/test_verify_psx_lighting_fixture_v1.py`
   → `17 passed in 3.51s`, `EXIT=0`. Covers: real fixture clean; wrong/edited
   `UNSHADED` and `FOG_DISABLED` defines; fog change; missing material path;
   unavailable baseline; preclaimed response; shadows enabled; divergent scene mode;
   light-on scene start; branch-dependent geometry; script colour mismatch; missing
   required view; true flag; edited pinned file.
6. `godot4 --headless --path godot_walk --script res://evidence/2026-11-17-issue-272-lit-psx-materials/fixture/test_fixture.gd`
   → `ISSUE_272_FIXTURE_TESTS_PASSED`, `EXIT=0` (only benign exit-time `ObjectDB`
   / resource-cleanup warnings). This verifies: all four scenes load with correct
   modes, flags false and light-off start; shader defines including fog unchanged;
   node/mesh/transform/camera/light equality across all four scenes; correct shader
   assignment and texture presence per path; repeatable light toggle; reproducible
   views. An initial run emitted `look_at` errors from orienting the camera before
   it entered the tree; this was fixed in the new script before the final run.
7. Guarded capture (no `--headless`; `DISPLAY=:1`, Vulkan 1.4.329 Forward+ on
   NVIDIA RTX 4070 Ti):
   `python3 godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/run_capture_guarded.py --output-dir godot_walk/evidence/2026-11-17-issue-272-lit-psx-materials/captures/paired_v1 --report godot_walk/evidence/2026-11-17-issue-272-lit-psx-materials/resource/paired_capture_resource.json --timeout-seconds 240 -- godot4 --path godot_walk --script res://evidence/2026-11-17-issue-272-lit-psx-materials/fixture/capture_views.gd -- --out=res://evidence/2026-11-17-issue-272-lit-psx-materials/captures/paired_v1`
   → `ISSUE_272_PAIRED_CAPTURES_READY`, `GUARD_EXIT=0`; receipt `return_code=0`,
   `timed_out=false`, `error=null`, `elapsed_seconds=3.292`, `compute_apps=[]`,
   finished `2026-11-18T16:42:15.634153+00:00`, preflight VRAM headroom 8.95 GB /
   RAM headroom 11.77 GB. Sixteen 1152×648 PNGs (four variants × light off/on ×
   two views). The wrapper's static `label` field reads
   `snow-garden-courtyard-v2-capture` because it is the existing shared wrapper;
   its recorded command, output and report paths all point to this fixture. Godot
   emitted warnings that global parameters `cull_distance`,
   `vertex_snap_intensity`, `texture_filtering` and `texture_lod_halve_distance`
   "were removed at some point"; see Honest limitations.
8. `python3 godot_walk/evidence/2026-11-17-issue-272-lit-psx-materials/scripts/compute_light_response_v1.py`
   → wrote `captures/paired_v1/light_response_v1.json`; mechanical decoded-pixel
   results: baseline solid and baseline textured changed **0** pixels on light
   on/off in both views (no response); lit solid and lit textured changed
   `160072/746496` (21.4%) in `surface_survey` and `543224/746496` (72.8%) in
   `sphere_close` (visible response). Baseline-vs-lit at light-on differed by the
   same pixel counts (solid max channel delta 61, textured 64). These are
   observations, not appearance judgments.
9. `python3 godot_walk/scripts/register_video_sources.py validate`
   → `{"valid": true, "registered_count": 13}`, `EXIT=0`.
10. `python3 -m pytest -q godot_walk/scripts`
    → `1566 passed, 5 skipped, 94 subtests passed in 279.52s`, `EXIT=0`.
11. The PNGs were read as paired views; `lit_solid/light_on|light_off/surface_survey`,
    `baseline_solid/light_on/surface_survey`, `lit_textured/light_on/surface_survey`
    and `lit_solid/light_on/sphere_close` were opened at full size. Observations:
    the lit solid on-view shows a normal-dependent shading gradient on the sphere
    and cylinder and flat-lit planes, while the off-view is a near-black silhouette;
    the unshaded baseline is a uniform flat tone in both light states; the lit
    textured on-view shows the authored checker with lighting applied. No visual
    pass is claimed.
12. `git status --short` → one untracked directory
    (`godot_walk/evidence/2026-11-17-issue-272-lit-psx-materials/`);
    `git diff --stat HEAD` → empty (no tracked file modified). The validator's pinned
    checks cover every freeze-v4 file plus 14 supplemental hashes including
    `project.godot`, `scripts/player.gd`, `catalog.json`, `MATERIAL_LANGUAGE.md`,
    `PALETTES.md`, both library shaders, the shared include and the accepted room
    and its dependencies.

## Comparison plan (request for operator review)

| View | Position / target (design units) | Compare |
|------|----------------------------------|---------|
| `surface_survey` | `(0, 3.4, 9.0)` → `(0, 1.1, -0.5)` | Required wide view: baseline vs lit, solid vs textured, light off vs on across floor, cuboid, sphere, cylinder and wall. |
| `sphere_close` | `(1.6, 1.7, 3.4)` → `(0.4, 0.95, 0.0)` | Close view resolving normal-dependent lighting response and PSX/texture character. |

For each of the four variants, compare `light_off` against `light_on` with identical
camera and settings; then compare baseline against lit at `light_on` for each
material path. Ask whether the lit variants' response is acceptable, whether the
textured path behaves like the solid path, and whether any shading/PSX character is
a regression. A passing validator, clean headless test, pixel-difference count or
clean capture is **not** approval. Nothing here admits or connects anything to the
catalog, infers scale, or establishes scene connectivity.

## Acceptance mapping

| Acceptance item | Evidence |
|-----------------|----------|
| Both material paths selectable independently; baseline available | `surface_kind` and `lighting_mode` exported independently; four scenes; `_shader_path()` selection; headless command 6; validator command 4 |
| Repeatable light-on/light-off comparison | `set_light_on(bool)` toggles key + ambient together; headless toggle assertions; 16 paired captures; on/off response record (command 8) |
| Records whether geometry visibly responds, no success preclaimed | `light_response_v1.json`: 0 changed pixels for both baselines, >0 for both lit paths; `response_preclaimed=false`; operator review pending |
| Shader choices, limitations and regressions documented | `shader_decision_v1.json`, `authored_data_v1.md`, `limitations_v1.md`, this report |
| Pinned files byte-identical | Freeze-v4 + 14 supplemental hash checks in validator; `git diff` empty; `register_video_sources.py validate` |
| Operator visual approval kept separate | `operator_review=pending`, `operator_approved=false` everywhere; no appearance pass claimed |
| No scale/registration/connectivity inference | flags false in all records and manifest; no ledger events; no catalog or manifest edit |
| No production migration / day-night / relighting / admission | scope stated in decision and report; no changes outside the new evidence folder |

## Pending the operator (not decided by this agent)

- Compare the paired views on suitable hardware and decide whether the lit
  response, textured-path behaviour and PSX character are acceptable. No appearance
  pass is claimed.
- Decide whether shadows must be added (the shared PSX path disables them) and
  whether `vertex_lighting` faceting is acceptable; both are open findings, not fixes.
- Decide whether fog should ever be enabled with lit materials — deliberately held
  constant here.
- Decide whether transparency, double-sided geometry and performance need a later,
  separately authorised slice; none was exercised or measured here.
- Any acceptance, catalog admission, integration, socket, registration or scale
  decision remains a separate operator workflow.

## Honest limitations

- All geometry, colours, materials, light and camera values are authored in
  uncalibrated design units. No metric scale, registration or source connectivity
  is established; `registration_accepted=false` and `scale_calibrated=false`
  everywhere.
- **Shader global-uniform warnings are an open finding, not introduced by this
  slice.** The shared URSC include references `cull_distance`,
  `vertex_snap_intensity`, `texture_filtering` and `texture_lod_halve_distance`,
  but this project currently registers only `affine_texture_mapping` in
  `project.godot`. Godot 4.6 warns that these globals "were removed at some point"
  and that the material "will not display correctly"; they therefore default to
  benign values (no culling, no vertex snapping, no texture-LOD halving, nearest
  filtering). This affects the accepted library shaders identically and is
  unchanged between baseline and lit. `project.godot` is hash-pinned and was not
  edited; resolving this needs a separate operator decision.
- **Shadows are disabled.** `common.gdshaderinc` declares `shadows_disabled` and the
  key light has shadow maps off. Lit variants respond to light direction but cast
  no real shadows; whether real shadows are required is unverified.
- **Lighting is per-vertex** (`vertex_lighting`). The lit response on the low-poly
  primitives can look faceted; this is a property of the chosen PSX path, not a
  regression that this slice fixes.
- **Double lighting / baked albedo.** Existing accepted palettes bake dusk into
  albedo. These neutral authored colours deliberately avoid double lighting; no
  source palette was relit and none was claimed faithful.
- **Transparency and double-sided surfaces are not exercised.** The five meshes are
  opaque. `CULL_MODE cull_disabled` is retained, but no alpha or two-sided case was
  captured; this remains an open finding.
- **Performance was not measured.** Any runtime cost of the lit path is unverified.
- The lit variants become near-black with all scene lighting off by design; a lit
  variant used without a light would be a visible regression. The unshaded baseline
  is unaffected by light state, which is the intended control.
- The PSX compositor/preset and player controller from the accepted room are omitted
  so a plain InspectionCamera can capture fair comparisons; their absence is a
  capture-only condition, not a scene change, so PSX post-processing character is
  not evaluated here.
- Agents cannot judge appearance. The headless checks are mechanical assertions and
  the pixel differences are arithmetic; none is approval.
- The 16 PNGs, camera manifest and response record live under `captures/` and stay
  local by the operator's `.gitignore` policy for bulky outputs; only reports,
  records, scripts and the guard receipt are committed. A reviewer with this
  workspace can open the PNGs directly, regenerate them with command 7, and
  recompute the response with command 8.
- No ledger events were appended and no hashes, receipts or decisions were written
  by hand. The pinned hashes were computed by the generator script; the guard
  receipt was produced by the existing wrapper.
