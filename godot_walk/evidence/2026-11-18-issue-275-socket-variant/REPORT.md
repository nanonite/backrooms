# Issue 275 — chevron-corridor-v1 two-socket through variant (north/south), untested

Date: 2026-11-18
Issue: #275 (child of #265). Operator design: comment 653 on #265, 2026-11-18.
Status: **IMPLEMENTED BUT BLOCKED — full Python suite is red on two pinned
invariants. Operator decision required. Task is NOT complete.**

## Operator authorisation and scope

Comment 653 authorises a NEW two-socket THROUGH variant of the accepted #175 room
(`video-102caf53423018b7/rooms/chevron-corridor-v1`), built without editing the
accepted room or any hash-pinned file. Sockets: north `(x=0, z=-10, floor 0.0,
normal 0,0,-1)` and south `(x=0, z=+10, floor 0.0, normal 0,0,+1)`, each
`level_doorway_2m_v1`, clear `2.0 x 2.1`, approach clearance `1.2`,
`circulation_role through`. The openings are authored, not observed in the source
frames. Sockets start UNTESTED; the variant stays out of automatic layout.
Connector-pair testing against `godot_source_textured_large_room_v1` hall_end
(90-degree rotation, floor 0.0), `accept-module-metadata`, `decide-integration`
and any map generation remain operator-only. `registration_accepted` and
`scale_calibrated` stay false everywhere.

The issue names no research doc under `docs/research/`; the applicable design
documents are the source-library README, `docs/MODULE_METADATA_CONSOLIDATION_PROPOSAL.md`,
`docs/GENERATIVE_MAP_METADATA_PROPOSAL.md` and `docs/MAZE_DYNAMICS_PROPOSAL.md`.
No docs/research file was read for design input.

## What was done

### New room (new files only)

Folder: `godot_walk/source_library/sources/video-102caf53423018b7/rooms/chevron-corridor-v2-north-south-socket/`

- `room.gd` extends the accepted room's script (the accepted file is untouched).
  It overrides `_build_boundaries()` to open two 2.0 x 2.1 doorways (side-wall
  returns plus headers with matching colliders) at north and south, keeps west
  and east fully closed, splits the baseboards around the openings and omits the
  old far light panel so the north doorway is clear. Materials, floor, pillars,
  ceiling and PSX profile are inherited unchanged. `_set_candidate_metadata()`
  declares both sockets as `untested` and `circulation_role through`.
- `room.tscn`, `.gd.uid` files, `test_room.gd`, `capture_room.gd`,
  `run_capture_guarded.py` — all new.
- `test_room.gd` checks floor support, floor ray, open north/south doorways below
  the header, both header colliders, both side-wall colliders, closed west/east
  boundaries, pillar obstacles, real player traversal through each doorway,
  missing-floor/open-boundary negative controls and R reset.

### Catalog, admission and ledger (new versions only)

- `catalog.json`: `catalog_version` 0.6.0 → 0.7.0 and exactly ONE appended module
  entry `video_102caf53423018b7_chevron_corridor_v2_north_south_socket_v1`
  (two sockets declared, `tested_connectors: []`, `layout_eligible: false`,
  both flags false). A JSON comparison asserted all 14 pre-existing entries and
  all other top-level fields unchanged.
- New immutable snapshot `catalog_snapshots/godot_psx_room_kit-0.7.0.json`,
  byte copy of the live catalog. SHA-256
  `b1d60a876e52d1e98dc8afe6b2391d00deeba42e8f8a4347057fe584c7127b82`.
- New library index `library_index/godot_psx_room_kit-0.7.0.json`, built with the
  existing `library_index.py build` stage → module_count 18, pair_count 2,
  status created.
- New `catalog_admission_decision.json`: `scope: sockets_declared`,
  `tested_connector_pairs: []`, `layout_eligible: false`, both flags false, real
  hashes for the accepted base adaptation, the operator review, the 0.7.0
  snapshot and the new adaptation.
- New `adaptation_catalog_v1.json` (v3 contract, copied from the accepted base
  record and updated for the variant): candidate identity
  `4367485987d2fded92732e6c1801a47b64a22048c1933749e2d200b4bf9aedf3`, bound to
  the decision by path and SHA-256.
- Registered through the existing path:
  `python3 godot_walk/scripts/register_source_room.py video-102caf53423018b7 --adaptation <new adaptation> --decision <new decision>`
  → `{"manifest_path": "…/source_manifest-v5.json", "manifest_sha256": "a6f5201c…"}`.
- Ledger events through existing runner stages only:
  `source_ingestion_runner.py reconcile-historical video-102caf53423018b7` →
  sequence 17 (`historical_decision_reconciled` citing the new decision);
  `source_ingestion_runner.py derive-module-metadata video-102caf53423018b7 --room-id chevron-corridor-v2-north-south-socket`
  → sequence 18. No event, receipt or hash was written by hand.
- New `module_poetics_v1.json` draft (metadata_status `draft_mechanical`,
  poetics empty, `untested_sockets: ["north","south"]`,
  `layout_eligible_derived: false`). No `module_poetics_v2.json` was created:
  `accept-module-metadata` is operator-only.
- New `module_profile_v1.json` sidecar (mechanical projection described below).
- No map was generated or committed. No accepted room, frozen contract,
  `scripts/player.gd`, `project.godot`, `MATERIAL_LANGUAGE.md` or `PALETTES.md`
  was edited. `git diff --name-only` for those paths is empty.

### Captures

Rendered through the guarded wrapper in the new room folder:

```
python3 godot_walk/source_library/sources/video-102caf53423018b7/rooms/chevron-corridor-v2-north-south-socket/run_capture_guarded.py \
  --output-dir godot_walk/source_library/sources/video-102caf53423018b7/rooms/chevron-corridor-v2-north-south-socket/captures \
  --report godot_walk/source_library/sources/video-102caf53423018b7/rooms/chevron-corridor-v2-north-south-socket/capture_resource_run.json \
  -- godot4 --path godot_walk \
  --script res://source_library/sources/video-102caf53423018b7/rooms/chevron-corridor-v2-north-south-socket/capture_room.gd \
  -- --out=res://source_library/sources/video-102caf53423018b7/rooms/chevron-corridor-v2-north-south-socket/captures
```

Receipt: `return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=9.732`.
`captures/capture_manifest.json`: four 1152x648 PNGs, mean 16.67 ms / p95 16.73 ms
/ p99 16.81 ms over 300 samples. All four PNGs were viewed:
`spawn_toward_north_opening.png`, `north_doorway.png`, `south_doorway.png`,
`wallpaper_wall.png`. They show the inherited carpet/chevron/pillar/ceiling
treatment with visible north and south openings and headers. **Appearance and
feel judgements are pending the operator — agents cannot judge appearance.**

## Verification commands and exact results

All commands run from `/mnt/sharedOs/backrooms-workspace` (repo root).

| Command | Result |
|---|---|
| `godot4 --headless --path godot_walk --script res://…/chevron-corridor-v2-north-south-socket/test_room.gd` | exit 0, `CHEVRON_THROUGH_VARIANT_TESTS_PASSED` (after two test-harness fixes: the player's own collider had to be moved off the south doorway ray path) |
| `python3 -m ruff check …/run_capture_guarded.py` | `All checks passed!` |
| `python3 godot_walk/scripts/register_video_sources.py validate` | `{"valid": true, "registered_count": 13}` |
| `python3 godot_walk/scripts/template_validate.py` | `{"valid": true, "source_manifests": 43, "module_profiles": 23, "generative_maps": 68, "errors": []}` |
| `python3 godot_walk/scripts/module_poetics.py validate --index godot_walk/room_catalog/library_index/godot_psx_room_kit-0.7.0.json` | `draft_count: 18`, 0 errors for the new variant draft; 34 errors all belong to pre-existing drafts still bound to older indices (not edited) |
| `python3 -m pytest -q godot_walk/scripts` | **6 failed, 1542 passed, 5 skipped, 13 errors, 90 subtests passed in 272.42s** (exit 1) — see blockers below |

Before the new artifacts, the same full suite baseline was green in prior
issues (1530 passed, 5 skipped). The regressions are entirely caused by the two
blocker conditions below; neither was "fixed" by editing a test or a validator.

## Blockers — exact missing preconditions (escalated)

### Blocker 1 — layout validator forbids declared sockets on a non-layout module

`godot_walk/scripts/issue149_layout_core.py:117-127`, called by
`load_catalog_snapshot()` on the LIVE `catalog.json`, enforces:

```
if not layout_eligible and socket_ids:
    raise ValueError(f"Non-layout module {id} must not declare sockets")
```

The operator-approved design requires the variant to declare two sockets AND
stay `layout_eligible: false` until a tested connector pair is approved. These
requirements are mutually exclusive under this validator. Result: 13 setup
errors (9 in `test_issue149_layout.py`, 4 in `test_issue164_layout.py`), all with:

```
ValueError: Non-layout module video_102caf53423018b7_chevron_corridor_v2_north_south_socket_v1 must not declare sockets
```

Choices needed from the operator (a human decision; I did not improvise):
(a) authorise a change to `issue149_layout_core._validate_module` to permit
declared-but-untested sockets on `layout_eligible: false` modules (and update
its pinned tests), or (b) authorise a separate catalog representation for
untested socket declarations (e.g. a `socket_declarations` field) that layout
code ignores, or (c) direct that the variant not be added to the live catalog
until that validator changes. Setting `layout_eligible: true`, removing the
sockets, or editing the validator/tests without authorisation would each be a
worker-side operator decision.

### Blocker 2 — pinned module-profile inventory and missing acoustics record

The issue asks for a "module profile". Adding the new
`module_profile_v1.json` sidecar breaks 6 tests:

- `test_module_profiles.py::test_committed_profile_paths_are_exactly_the_expected_sidecars`
  and `::test_backfill_check_is_clean`,
  `test_module_profile_t6.py::test_overlays_are_additive_and_do_not_change_maps_or_v1_profiles`:
  the committed profile set is pinned to exactly 11 sidecars from the frozen
  0.5.0 index (`backfill_module_profiles.ADMITTED_MODULE_COUNT == 11`). The new
  sidecar is reported as `unexpected module profile` (12 vs 11).
- `test_module_surface_palette.py` (3 tests): `ValueError: no module acoustics
  record for video_102caf53423018b7_chevron_corridor_v2_north_south_socket_v1@1`.
  Every committed profile must have a record in the frozen module-acoustics file.

The profile was built from the operator-accepted base poetics
(`chevron-corridor-v1/module_poetics_v2.json`, commit b00db72), which shares the
variant's materials and PSX profile, after overriding identity, geometry,
translation chain and the 0.7.0 snapshot hash. Its two exits are `kind:
untested` with empty `tested_pair_ids` and `layout_eligible_derived: false`.
The exit `circulation_role` is the schema-required placeholder `connector`; the
operator's `through` role is recorded in the catalog socket entries and room
metadata. This projection still leaves the variant's own poetics acceptance
operator-only.

Choices needed from the operator: (a) authorise updating the pinned profile
inventory and adding a module-acoustics record/surface-palette mapping for the
new module (new versions, without editing frozen records), or (b) direct that
"module profile" means only the derived `module_poetics_v1.json` draft, in which
case the new profile sidecar should be removed.

## Pending operator-only steps (not attempted)

- `accept-module-metadata` for the variant (would write `module_poetics_v2.json`).
- Connector-pair test against `godot_source_textured_large_room_v1` hall_end
  (90-degree rotation, floor 0.0) and approval of any tested pair.
- `decide-integration` and any seeded-map placement; no map generated.
- Appearance/feel judgement of the four captures (agents cannot judge appearance).
- Resolution of blockers 1 and 2 above.

## Honest limitations

- The headless room test, guarded captures, registries and template validator
  pass, and registration plus metadata derivation are real ledger events.
  However, `python3 -m pytest -q godot_walk/scripts` is red because of the two
  pinned invariants above. A passing validator or clean capture is not approval.
- The catalog entry and admission decision deliberately say sockets are
  untested and layout-ineligible; if the operator chooses Blocker 1 option (c),
  the 0.7.0 catalog/index/snapshot and the registration would need to be
  reverted or re-versioned — I did not do that unprompted.
- The variant reuses textures from the accepted room by reference; no texture
  file was copied or edited.

## Files changed

Modified: `godot_walk/room_catalog/catalog.json`,
`godot_walk/source_library/index.json`,
`godot_walk/source_library/sources/video-102caf53423018b7/events.jsonl`.
Added: `godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.7.0.json`,
`godot_walk/room_catalog/library_index/godot_psx_room_kit-0.7.0.json`,
`godot_walk/source_library/sources/video-102caf53423018b7/source_manifest-v5.json`,
the new `chevron-corridor-v2-north-south-socket/` room folder (scene, scripts,
test, captures, decision, adaptation, poetics draft, module profile), and this
report.
