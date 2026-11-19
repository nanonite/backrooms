# Issue 277 — nested-light-corridor-v1 two-socket through variant (north/south), untested

Date: 2026-11-19
Issue: #277 (child of #265). Pattern: issue #275, `godot_walk/evidence/2026-11-18-issue-275-socket-variant/REPORT.md`
and its variant room `video-102caf53423018b7/rooms/chevron-corridor-v2-north-south-socket/`.
Status: **IMPLEMENTED — pending operator review of socket placement and captures. No blocker.**

## Operator authorisation and scope

Task data authorises ONE new two-socket THROUGH variant of the operator-accepted #173 room
(`video-d857abe7a94da9d1/rooms/nested-light-corridor-v1`), built without editing the accepted
room or any hash-pinned file. Sockets: `level_doorway_2m_v1`, clear `2.0 x 2.1`, floor `0.0`,
approach clearance `1.2`, `circulation_role through`, status `untested`. The openings are
authored proposals, not observed in the source video. `tested_connector_pairs` is empty,
`layout_eligible` is `false`, `registration_accepted` and `scale_calibrated` stay `false`.
No map, connector-pair test, `module_profile_v1.json` sidecar, `accept-module-metadata` or
`decide-integration` was produced. No Hunyuan or other model call was made. The previous
socket-variant issue (#275) is committed; the catalog bump is sequential (`0.7.0` → `0.8.0`).

## Socket placement — exact openings and why

The accepted room is an authored rectangle x ∈ [-5, 5], z ∈ [-12, 12], height 4.8, spawn
`(0, 0.6, 10)`. Both openings are centred on the short end walls at x = 0:

| Socket | Opening | Outward normal | Clear volume | Why this spot |
|---|---|---|---|---|
| `north` | x = 0, z = **-12** | (0, 0, -1) | x ∈ [-1, 1], y ∈ [0, 2.1] | The far short end of the corridor; the only interior element there is the inherited far-light-wall visual (see below). Plinths at (±4.2, 0, -6) and portal/wall-panel frames at x ≈ ±4.9 are far to the sides of x = 0. |
| `south` | x = 0, z = **+12** | (0, 0, +1) | x ∈ [-1, 1], y ∈ [0, 2.1] | The near short end, 2 m behind the unchanged safe spawn; the nearest portal frame is at z = +8 and x ≈ ±4.92, so the 1.2 m approach sector is unobstructed. |

Each wall is built as two side returns (x = -5.15…-1.0 and x = 1.0…5.15) plus a header from
y = 2.1 to y = 4.8, each with a matching `StaticBody3D`/`BoxShape3D` collider. West and east
walls stay fully closed with matching colliders. Floor, materials, textures and the PSX profile
are inherited unchanged.

**Far-light-wall note (operator review required).** The accepted room's `_add_far_light_wall()`
places a visual panel at x ∈ [-4.3, 4.3], y ∈ [0.6, 4.2], z ≈ -11.98, spanning the whole north
end. Left in place it would cover the proposed north doorway exactly as the #275 far light
panel did. The variant therefore does **not** call that inherited method, so the doorway is
visually clear. This removes a source-observed terminal surface from the variant only; the
accepted room and its textures are untouched. Whether that is acceptable appearance is an
operator judgement — agents cannot judge appearance.

The plinths at (±4.2, 0, -6), portal frames (`PORTAL_Z = [-8, -4, 0, 4, 8]`, x ≈ ±4.92),
wall panels (`PANEL_Z = [-9, -5, -1, 3, 7]`, x ≈ ±4.97), ceiling strips (y ≈ 4.78) and floor
strips (y ≈ 0.014, visual only) do **not** block either x = 0 doorway below the 2.1 m header.
No proposed socket was left blocked by interior geometry; nothing was improvised beyond the
#275 pattern.

## What was done — new files and new versions only

New room folder
`godot_walk/source_library/sources/video-d857abe7a94da9d1/rooms/nested-light-corridor-v2-north-south-socket/`:

- `room.gd` extends the accepted room's script (accepted file untouched). It overrides
  `_set_candidate_metadata()` and `_build_boundaries()`, opens the two doorways with collider
  returns/headers, omits the far-light-wall call, and declares both sockets `untested`.
- `room.tscn`, `*.gd.uid` files, `test_room.gd`, `capture_room.gd`, `run_capture_guarded.py`.
- `test_room.gd` checks floor support, floor ray, both open doorways below the header, both
  header colliders, both side-wall colliders, closed west/east boundaries, the two plinth
  obstacles, real player traversal through both doorways, missing-floor/open-boundary negative
  controls and R reset.
- `adaptation_catalog_v1.json` (v3 contract), derived from the operator-accepted base record:
  identity `53b89178df9a05fff2c617d6c744d5820987dd479b270ddc598f5c2d8c97cacf`, bound to the new
  decision by path and SHA-256, snapshot reference `0.7.0` as in the #275 pattern.
- `catalog_admission_decision.json`: `scope: sockets_declared`, `tested_connector_pairs: []`,
  `layout_eligible: false`, both flags false.
- `module_poetics_v1.json` **draft only** (`draft_mechanical`, poetics empty,
  `untested_sockets: ["north","south"]`, `layout_eligible_derived: false`). No v2 record.
- Guarded captures and their manifest/receipt (four 1152x648 PNGs).

Catalog, ledger and library index:

- `catalog.json`: `catalog_version` `0.7.0` → `0.8.0`, exactly ONE appended module entry
  `video_d857abe7a94da9d1_nested_light_corridor_v2_north_south_socket_v1` (two sockets declared,
  `tested_connectors: []`, `layout_eligible: false`, both flags false). A JSON comparison
  confirmed all 15 pre-existing entries and every other top-level field are byte-equivalent.
- New immutable snapshot `catalog_snapshots/godot_psx_room_kit-0.8.0.json`, byte copy of the
  live catalog. SHA-256 `d1ebeeb3ea1901a75d79bfd01ef6427e2dba41e9fa29f3f3c2801c1673d0f920`.
- New library index `library_index/godot_psx_room_kit-0.8.0.json`, built with the existing
  `library_index.py build` stage → module_count 19, pair_count 2, status created.
- Registered through the existing path:
  `register_source_room.py video-d857abe7a94da9d1 --adaptation <new adaptation> --decision <new decision>`
  → `source_manifest-v5.json`, `1e49f0b641cdea5c0246b73d69bc0b937dba0b1f36202a2e313724e5e1af2c73`.
- Ledger events through existing runner stages only: `source_ingestion_runner.py
  reconcile-historical video-d857abe7a94da9d1` → sequence 17 (`historical_decision_reconciled`);
  `source_ingestion_runner.py derive-module-metadata video-d857abe7a94da9d1 --room-id
  nested-light-corridor-v2-north-south-socket` → sequence 18. No event, receipt or hash was
  written by hand.

## Verification commands and exact results

All commands from `/mnt/sharedOs/backrooms-workspace`.

| Command | Result |
|---|---|
| `godot4 --headless --path godot_walk --script res://…/nested-light-corridor-v2-north-south-socket/test_room.gd` | exit 0, `NESTED_LIGHT_THROUGH_VARIANT_TESTS_PASSED` |
| `python3 -m ruff check …/run_capture_guarded.py` | `All checks passed!` |
| `python3 godot_walk/scripts/register_video_sources.py validate` | `{"valid": true, "registered_count": 13}` |
| `python3 godot_walk/scripts/template_validate.py` | `{"valid": true, "source_manifests": 44, "module_profiles": 22, "generative_maps": 68, "errors": []}` |
| `python3 godot_walk/scripts/module_poetics.py validate --index …/godot_psx_room_kit-0.8.0.json` | `draft_count: 19`, overall `valid: false`; **0 errors** for the new variant draft. The 36 errors all belong to pre-existing drafts bound to older indices (not edited). |
| `python3 -m pytest -q godot_walk/scripts` | **1574 passed, 5 skipped, 94 subtests passed in 285.08 s (exit 0)** |

Guarded capture command (through `run_capture_guarded.py` only):

```
python3 godot_walk/source_library/sources/video-d857abe7a94da9d1/rooms/nested-light-corridor-v2-north-south-socket/run_capture_guarded.py \
  --output-dir godot_walk/source_library/sources/video-d857abe7a94da9d1/rooms/nested-light-corridor-v2-north-south-socket/captures \
  --report godot_walk/source_library/sources/video-d857abe7a94da9d1/rooms/nested-light-corridor-v2-north-south-socket/capture_resource_run.json \
  -- godot4 --path godot_walk \
  --script res://source_library/sources/video-d857abe7a94da9d1/rooms/nested-light-corridor-v2-north-south-socket/capture_room.gd \
  -- --out=res://source_library/sources/video-d857abe7a94da9d1/rooms/nested-light-corridor-v2-north-south-socket/captures
```

Receipt: `return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=3.199`, guard
policy 2.1.0, VRAM preflight 0 % utilization. `captures/capture_manifest.json`: four
1152x648 PNGs — `spawn_toward_north_opening`, `north_doorway`, `south_doorway`,
`east_wall_panels`; mean 4.17 ms / p95 4.22 ms / p99 4.26 ms over 300 samples. Files exist
and are non-empty. **Appearance and feel judgements are the operator's; agents cannot judge
appearance.** No capture image was interpreted for acceptance.

## Pending operator-only steps (not attempted)

- Approval of the exact north/south socket placement, including the omitted far-light-wall
  visual noted above.
- Connector-pair test and approval; no partner or rotation is claimed here.
- `accept-module-metadata` (would write `module_poetics_v2.json`), `decide-integration`, and any
  seeded-map placement. No map was generated or committed.

## Honest limitations

- Passing validators, a green headless room test and a clean guarded capture are not approval.
  The sockets remain declared-but-untested and layout-ineligible by design.
- The variant reuses the accepted room's textures by reference; no texture was copied or edited.
- No hash-pinned file was touched: `git diff --name-only -- godot_walk/scripts/player.gd
  godot_walk/project.godot godot_walk/room_catalog/MATERIAL_LANGUAGE.md
  godot_walk/room_catalog/PALETTES.md
  godot_walk/source_library/sources/video-d857abe7a94da9d1/rooms/nested-light-corridor-v1
  godot_walk/source_library/sources/video-102caf53423018b7/rooms` is empty.

## Files changed

Modified: `godot_walk/room_catalog/catalog.json`, `godot_walk/source_library/index.json`,
`godot_walk/source_library/sources/video-d857abe7a94da9d1/events.jsonl`.
Added: `godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.8.0.json`,
`godot_walk/room_catalog/library_index/godot_psx_room_kit-0.8.0.json`,
`godot_walk/source_library/sources/video-d857abe7a94da9d1/source_manifest-v5.json`,
the new `nested-light-corridor-v2-north-south-socket/` room folder (scene, scripts, test,
captures, decision, adaptation, poetics draft), and this report.
