# Chainlink issue 268 — Open-world step 2a: tree prototype (source-backed trunk, layered canopy)

Child of #258 (open-world umbrella), under #169, ingestion track. Operator-directed
2026-11-17 from `docs/research/issue-259-trees-foliage.md`. This is the combined
"Ready-to-file first implementation slice" named in that doc. No model, GPU model
call, download, catalog admission, integration, socket choice or registration was
performed. No tracked file was edited; all artifacts are new.

## Blocker resolution (precondition)

Issue #268 declares `blocked_by=[267]`. A previous run recorded blocker comment 650
because #267 was open. Before authoring anything this run verified the current state:

- `chainlink issue show 267 --json`
  → `status="closed"`, `closed_at="2026-11-18T03:17:57.904481572Z"`, with operator
  review comment 652 ("Closing as spec-complete; runtime stop behaviour and real-scene
  review remain separate"). The blocking precondition is met, so work proceeded.
  Traversal-policy decisions and other content from #267 were not applied here.

## Acceptance copied from the named research doc

From `docs/research/issue-259-trees-foliage.md`, section "Ready-to-file first
implementation slice" (verbatim):

> **Title:** Prototype source-backed trunk and layered canopy for one open-world tree
>
> **Scope:** In a new, versioned isolated fixture, build one tree using a source-backed bark crop if a suitable crop can be identified, plus several spatially separated canopy cards with varied orientations using traceable existing or newly extracted source crops. Record source paths, crop coordinates and hashes, and label authored placement and geometry. If no appropriate bark crop exists, document that finding and retain an explicitly authored trunk appearance rather than claiming a source-backed texture. Preserve separate trunk collision and a traversable inspection path. Do not change the accepted snow-garden room, frozen contracts, shared pinned files, registration or scale flags. No model, GPU, download, catalog admission or implied connectivity is part of this slice.
>
> **Acceptance:** The fixture includes the tree, crop provenance and authored-versus-source notes; its trunk collision is independently defined; canopy cards have multiple orientations and depth offsets. Provide matched front, side, oblique, close and elevated views with camera positions recorded, alongside a baseline view of the current representation. Record any remaining silhouette, crop-edge, repetition and collision limitations. Do not describe a visual pass or source fidelity as operator approval. Keep `registration_accepted=false` and `scale_calibrated=false` wherever those flags are recorded.
>
> **Verification:** Agent checks the fixture loads, source/crop hashes and references resolve, card transforms differ, and the player cannot pass through the trunk while the inspection route remains usable. Run the relevant existing automated checks and record exact commands and results. Capture the matched views only in an authorized environment with the required rendering access; report unavailable checks rather than substituting synthetic results. The operator compares the views with the source and decides whether visual quality warrants a successor issue; any acceptance or catalog admission follows its separate workflow.

## What was done (new files only)

| File | Purpose |
|------|---------|
| `fixture/tree_trunk_canopy_v1.tscn` / `.gd` | Variant: one tree with an explicitly authored tapered trunk, five authored branches, and seven source-backed layered canopy cards; independent cylinder trunk collision; finite inspection floor; safe spawn. |
| `fixture/baseline_tree_v1.tscn` / `.gd` | Baseline: current scheme for one tree — solid six-sided cylinder trunk, four small branch cylinders, two thin textured canopy boxes, separate box collision. |
| `fixture/card_specs_v1.json` | Authored canopy card placement: crop, azimuth, radial offset, centre height, tilt and size for seven cards. All azimuths, radial offsets and heights are distinct. |
| `fixture/crop_provenance_v1.json` | Source video + frame manifest + frame hashes, three crops with exact `[x0,y0,x1,y1]` bounds and origin/copied SHA-256, bark-crop assessment, authored-vs-source notes and false flags. |
| `fixture/views_v1.json` | Recorded camera positions/targets for the five matched views, reused byte-for-byte by both captures. |
| `fixture/authored_vs_source_v1.md`, `fixture/limitations_v1.md` | Explicit authored/source split and pre-review limitation record. |
| `fixture/textures/*.png` | Byte-for-byte copies of three already-recorded source crops from the accepted snow-garden room; that room and its pinned inputs were only read. |
| `fixture/capture_views.gd`, `fixture/test_fixture.gd` | Paired capture driver and headless load/transform/collision/traversal verification. |
| `scripts/verify_tree_fixture_v1.py`, `scripts/test_verify_tree_fixture_v1.py` | Read-only integrity validator and its positive/negative tests. |
| `captures/paired_v1/{baseline,variant}/*.png`, `captures/paired_v1/capture_manifest_v1.json` | Ten generated paired captures and their camera-position manifest (local-only; see below). |
| `resource/paired_capture_resource.json` | Guard receipt generated by the existing guarded capture wrapper (not written by hand). |

### Bark-crop finding

Seven decoded frames (`frame_3597`, `frame_3747`, `frame_3897`, `frame_4047`,
`frame_4197`, `frame_4347`, `frame_4497`) were inspected. Trunks appear as near-black
silhouettes or water reflections against blue sky; no unobstructed, well-lit bark
region with resolvable texture detail exists in the available source imagery. Per the
doc, the trunk retains an explicitly authored tapered appearance and makes **no**
source-backed texture claim. The three canopy crops are reused from the existing
traceable crop manifest and are not re-cropped, resized or colour-edited.

### Ledger

No events, receipts or hashes were written by hand. No existing runner stage covers
this isolated CPU-authored fixture slice, so no runner stage was invoked and no
`events.jsonl` was appended. The capture guard receipt was produced by the existing
guarded capture wrapper.

## Commands and results (repository root)

1. Precondition: `chainlink issue show 267 --json` → #267 closed (operator review 652).
2. `python3 godot_walk/evidence/2026-11-17-issue-268-tree-prototype/scripts/verify_tree_fixture_v1.py`
   → `PASS issue-268 tree fixture: source/crop hashes, card transforms, views and flags verified`, `EXIT=0`.
3. `python3 -m pytest -q godot_walk/evidence/2026-11-17-issue-268-tree-prototype/scripts/test_verify_tree_fixture_v1.py`
   → `8 passed`.
4. `godot4 --headless --path godot_walk --script res://evidence/2026-11-17-issue-268-tree-prototype/fixture/test_fixture.gd`
   → `ISSUE_268_WALK: approach_stopped_z=0.567 side_x=2.667`,
   `ISSUE_268_FIXTURE_TESTS_PASSED`, `EXIT=0`. (A prior run failed on a wrong
   node path for the trunk visual; the test was corrected and re-run clean.)
   This verifies: both scenes load; player settles on the floor; independently
   defined trunk cylinder collides and its negative control does not; seven cards
   have distinct yaw, radial and height transforms and three distinct source
   textures; the player stops at the trunk (`z=0.567`, capsule + authored radius)
   and can walk the side inspection route (`x=2.667`) while staying on the floor.
5. Guarded capture (no `--headless`, matching the existing capture recipe; `DISPLAY=:1`,
   Vulkan 1.4 Forward+ on NVIDIA RTX 4070 Ti):
   `python3 godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/run_capture_guarded.py --output-dir godot_walk/evidence/2026-11-17-issue-268-tree-prototype/captures/paired_v1 --report godot_walk/evidence/2026-11-17-issue-268-tree-prototype/resource/paired_capture_resource.json --timeout-seconds 240 -- godot4 --path godot_walk --script res://evidence/2026-11-17-issue-268-tree-prototype/fixture/capture_views.gd -- --out=res://evidence/2026-11-17-issue-268-tree-prototype/captures/paired_v1`
   → `ISSUE_268_PAIRED_CAPTURES_READY`, `CAPTURE_GUARD_EXIT=0`;
   guard receipt `return_code=0`, `timed_out=false`;
   10 PNGs at 1152×648; manifest lists 10 views with positions/targets and
   `registration_accepted=false`, `scale_calibrated=false`.
   (Two earlier attempts were discarded before review: a headless run produced no
   viewport texture, and an un-awaited coroutine produced an empty manifest. Both
   were corrected; the reviewed captures are the successful guarded run.)
   The wrapper's static `label` field reads `snow-garden-courtyard-v2-capture`
   because it is the existing wrapper copied from that room; the recorded command,
   output and report paths all point to this issue-268 fixture.
6. `python3 godot_walk/scripts/register_video_sources.py validate`
   → `{"valid": true, "registered_count": 13}`, `VALIDATE_EXIT=0`.
7. `python3 -m ruff check godot_walk/evidence/2026-11-17-issue-268-tree-prototype/scripts/*.py`
   → `All checks passed!` (`--fix` and `ruff format` applied to the two new Python files).
8. `python3 -m pytest -q godot_walk/scripts`
   → `1561 passed, 5 skipped, 92 subtests passed in 270.65s`, `EXIT=0`.
9. The ten PNGs were opened and viewed as a paired contact sheet; observations are
   recorded under "Honest limitations" below. No visual pass is claimed.

## Acceptance mapping

| Acceptance item | Evidence |
|-----------------|----------|
| New versioned isolated fixture; one tree | `fixture/tree_trunk_canopy_v1.*`; all new files |
| Source-backed bark crop if suitable; else authored trunk, documented | `bark_crop_assessment` in `crop_provenance_v1.json`; `authored_vs_source_v1.md`; `AuthoredTrunk` meta `bark_source_crop=none` |
| Several spatially separated canopy cards, varied orientations, traceable crops | `card_specs_v1.json` (7 cards, distinct azimuth/radial/height); `crop_provenance_v1.json` (3 crops, bounds + hashes); headless distinct-transform assertions |
| Source paths, crop coordinates and hashes recorded | `crop_provenance_v1.json`; validator command 2 |
| Authored placement/geometry labelled | meta on trunk/branches/cards; `authored_vs_source_v1.md` |
| Independently defined trunk collision | `TreeCollision/TrunkCollision` cylinder, `independent_of_visual=true`; headless ray + negative control |
| Traversable inspection path | headless walk test: forward stops at trunk, side route usable, floor support retained |
| Matched front/side/oblique/close/elevated + baseline, camera positions recorded | `views_v1.json`; 10 PNGs + `capture_manifest_v1.json`; commands 3–5 |
| Silhouette, crop-edge, repetition, collision limitations recorded | `limitations_v1.md`; observations below |
| Visual pass / source fidelity not described as operator approval | manifest `operator_review=pending`; Pending section; report language |
| Flags false wherever recorded | both scenes, both JSON records, capture manifest, report |

## Pending the operator (not decided by this agent)

- Compare each baseline/variant pair against the source frames and decide whether
  the layered-card hypothesis warrants a successor issue. No appearance or source
  fidelity pass is claimed.
- Decide whether any future tree representation should be accepted, catalog-admitted
  or integrated. Nothing here admits or connects anything.
- Decide whether a later slice should investigate a reconstructed or modelled trunk
  if the authored trunk remains unacceptable.

## Honest limitations

- All geometry, placement, spawn, lights and capture cameras are authored in
  uncalibrated design units. No metric scale, registration or source connectivity is
  established; `registration_accepted=false` and `scale_calibrated=false` everywhere.
- The trunk is explicitly authored because no usable bark crop was found; the three
  canopy crops are reused, not newly extracted, and no new source region was claimed.
- Viewed captures show the expected issues: rectangular crop edges and near-black
  crop regions remain visible, silhouette gaps are apparent from the elevated and
  oblique views, the same crop motifs repeat across cards, and the authored trunk is
  a flat dark surface. These are recorded, not resolved.
- Captures use plain unshaded nearest-filtered materials in both scenes (no PSX
  compositor), chosen for a fair baseline/variant comparison and double-sided cards.
  The background is the default clear colour rather than a source panorama; this is
  an isolated fixture, not a scene-fidelity demonstration.
- Agents cannot hear or walk. The headless traversal checks are mechanical physics
  assertions; they are not a human judgement of feel, and any feel judgement is
  pending the operator.
- The ten PNGs and the capture manifest live under `captures/` and stay local by the
  operator's `.gitignore` policy for bulky evidence outputs; only the report, records,
  scripts and guard receipt are committed. A reviewer with this workspace can open
  the PNGs directly or regenerate them with command 5.
- No ledger events were appended and no hashes, receipts or decisions were written
  by hand. A passing validator, clean headless test or clean capture is not approval.
