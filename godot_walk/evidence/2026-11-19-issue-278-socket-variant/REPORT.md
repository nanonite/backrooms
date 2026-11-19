# Issue 278 — chevron-corridor-v1 (corridor_t) two-socket through variant (north/south), untested

Date: 2026-11-19
Issue: #278 (child of #265). Pattern: issue #275,
`godot_walk/evidence/2026-11-18-issue-275-socket-variant/REPORT.md`, its addendum, and its variant room
`video-102caf53423018b7/rooms/chevron-corridor-v2-north-south-socket/`.
Status: **IMPLEMENTED — pending operator review of socket placement and captures. No blocker.**

## Operator authorisation and scope

Task data authorises ONE new two-socket THROUGH variant of the operator-accepted #176 room
(`video-2671b32f256a4ee7/rooms/chevron-corridor-v1`), built without editing the accepted room or any
hash-pinned file. Sockets: `level_doorway_2m_v1`, clear `2.0 x 2.1`, floor `0.0`, approach clearance
`1.2`, `circulation_role through`, status `untested`. The openings are authored proposals, not
observed in the source video. `tested_connector_pairs` is empty, `layout_eligible` is `false`,
`registration_accepted` and `scale_calibrated` stay `false`. No map, connector-pair test,
`module_profile_v1.json` sidecar, `module_poetics_v2.json`, `accept-module-metadata` or
`decide-integration` was produced. No Hunyuan or other model call was made. The previous
socket-variant issue (#277) is committed; the catalog bump is sequential (`0.8.0` → `0.9.0`).

## Socket placement — exact openings and why

The accepted room is an authored rectangle x ∈ [-8, 8], z ∈ [-10, 10], height 4.2, spawn
`(0, 0.6, 8.4)`. Its four interior PARTITIONS (read from `chevron-corridor-v1/room.gd`) are thin
walls at x = ±4.5, each 4 m long in z:

| Partition | x range | z range |
|---|---|---|
| `PartitionCollision_00` | [-4.65, -4.35] | [3, 7] |
| `PartitionCollision_01` | [4.35, 4.65] | [0, 4] |
| `PartitionCollision_02` | [-4.65, -4.35] | [-4, 0] |
| `PartitionCollision_03` | [4.35, 4.65] | [-8, -4] |

They leave the central lane x ∈ [-4.35, 4.35] (8.7 m wide) open along the full z range. That lane
is the only axis whose **two wall ends** both give a 2.0 × 2.1 doorway with a clear 1.2 m approach,
and it is the through-axis used by the #275/#277 pattern. The two sockets are therefore the two ends
of that lane, centred on x = 0:

| Socket | Opening | Outward normal | Clear volume | 1.2 m approach sector | Why this spot |
|---|---|---|---|---|---|
| `north` | x = 0, z = **-10** | (0, 0, -1) | x ∈ [-1, 1], y ∈ [0, 2.1] | x ∈ [-1, 1], z ∈ [-10, -8.8] | Far end of the clear central lane. Nearest partition (`_03`) is at x = 4.5, z ≥ -8: 3.35 m to the side and 0.8 m beyond the approach sector. |
| `south` | x = 0, z = **+10** | (0, 0, +1) | x ∈ [-1, 1], y ∈ [0, 2.1] | x ∈ [-1, 1], z ∈ [8.8, 10] | Near end of the lane, 0.4 m behind the unchanged safe spawn. Nearest partition (`_00`) is at x = -4.5, z ≤ 7: 3.35 m to the side and 1.8 m before the approach sector. |

Each end wall is rebuilt as two side returns (x ∈ [-8.15, -1.0] and x ∈ [1.0, 8.15]) plus a header
from y = 2.1 to y = 4.2, each with a matching `StaticBody3D`/`BoxShape3D` collider. West and east
walls stay fully closed with matching colliders. Floor, materials, textures, the four partitions,
ceiling, lights and PSX profile are inherited unchanged. A headless ray test confirms the central
lane is unobstructed and real player traversal crosses both openings.

**Far-light-panel note (operator review required).** The accepted room's `_build_boundaries()`
emits a visual-only `FarLightPanel` at x ∈ [-0.8, 0.8], y ∈ [1.4, 3.4], z ≈ -9.99, which would
cover the centred north doorway. The variant overrides `_build_boundaries()` and deliberately does
not emit that box, so the north opening is visually clear. It has no collider, so traversal was
never blocked. This removes one source-observed terminal surface from the variant only; the
accepted room and its textures are untouched. Appearance is an operator judgement — agents cannot
judge appearance.

### Clear and blocked candidate positions (as requested)

- **Clear — chosen:** north (x = 0, z = -10) and south (x = 0, z = +10), both on the open central
  lane; measured above.
- **Clear — not chosen:** the west wall (x = -8) and east wall (x = +8). Every partition lies at
  x ∈ [±4.35, ±4.65], so no partition enters a side-wall approach sector (x ∈ [-8, -6.8] or
  [6.8, 8]); the side strips are reachable through partition gaps at least 2 m wide (west gaps
  z ∈ [7,10], [0,3], [-10,-4]; east gaps z ∈ [4,10], [-4,0], [-10,-8]). These are the literal
  "arm ends" if the unverified filename T-junction is read as a crossbar. They were not selected
  because they do not form the straight through-corridor of the #275 pattern, and their inward
  approach opens into a side strip rather than the main lane. **Operator review of this choice is
  required.**
- **Blocked candidates:** none of the wall positions is blocked by an interior partition. Every
  partition z-range stops at least 0.8 m short of the north approach sector's inner edge (z = -8.8)
  and 1.8 m short of the south approach sector's inner edge (z = 8.8), and sits 3.35 m away from
  either side wall. The only obstruction found at a proposed spot is the visual-only FarLightPanel
  at the north end, handled as described above. No partition was added or moved, and no socket was
  left blocked by geometry; there was no geometry blocker to stop and report.
- The filename "T-junction" was already recorded as unverified in #176 ("No branching topology
  authored; no connectivity claimed"). The parenthetical "arm ends of the T" is therefore treated
  as a placement hint, resolved to the two clear ends of the main through-lane and documented here
  in full for the operator.

## What was done — new files and new versions only

New room folder
`godot_walk/source_library/sources/video-2671b32f256a4ee7/rooms/chevron-corridor-v2-north-south-socket/`:

- `room.gd` extends the accepted room's script (accepted file untouched). It overrides
  `_set_candidate_metadata()` and `_build_boundaries()`, opens the two doorways with collider
  returns/headers, omits the visual far-light panel, and declares both sockets `untested`.
- `room.tscn`, `*.gd.uid`, `test_room.gd`, `capture_room.gd`, `run_capture_guarded.py` — all new.
- `test_room.gd` checks floor support, floor ray, both open doorways below the header, both header
  colliders, both side-wall colliders, the unobstructed central lane, closed west/east boundaries,
  the four inherited partition obstacles, real player traversal through both openings,
  missing-floor/open-boundary negative controls and R reset. One harness adjustment was needed:
  perimeter boundary rays are cast at z = 8.5, outside every partition z-range, so the
  open-boundary negative control measures the wall rather than an inherited partition; the
  player's own collider is parked at x = 3 during the doorway ray checks.
- `adaptation_catalog_v1.json` (v3 contract), derived from the operator-accepted base record:
  identity `68ad5e8d36cb108f696278f0e38342d00202ed743e0ad1a33ff1ca926c19bbde`, bound to the new
  decision by path and SHA-256 `65b516d4a3844d86f92b6b5eea7862e972d099fa0cde84940c44f79309e1520e`.
  Its `catalog_snapshot` binding remains the pre-bump `0.8.0` snapshot, as in the #275/#277 pattern.
- `catalog_admission_decision.json`: `scope: sockets_declared`, `tested_connector_pairs: []`,
  `layout_eligible: false`, both flags false.
- `module_poetics_v1.json` **draft only** (`draft_mechanical`, poetics empty,
  `untested_sockets: ["north","south"]`, `layout_eligible_derived: false`), written by the
  `derive-module-metadata` runner stage. No v2 record and no `module_profile_v1.json` sidecar.
- Guarded captures and their manifest/receipt (four 1152×648 PNGs).

Catalog, ledger and library index:

- `catalog.json`: `catalog_version` `0.8.0` → `0.9.0`, exactly ONE appended module entry
  `video_2671b32f256a4ee7_chevron_corridor_v2_north_south_socket_v1` (two sockets declared,
  `tested_connectors: []`, `layout_eligible: false`, both flags false). A JSON comparison
  confirmed all 16 pre-existing entries and every other top-level field are unchanged.
- New immutable snapshot `catalog_snapshots/godot_psx_room_kit-0.9.0.json`, byte copy of the live
  catalog. SHA-256 `0b394553f528517326e3eafa19f81502b320713b0183d80528760fad57453be3`.
- New library index `library_index/godot_psx_room_kit-0.9.0.json`, built with the existing
  `library_index.py build` stage → module_count 20, pair_count 2, status created.
- Registered through the existing path:
  `register_source_room.py video-2671b32f256a4ee7 --adaptation <new adaptation> --decision <new decision>`
  → `source_manifest-v5.json`, `82d532227a64ba74b222c255f323020bbfb4c6e90723304ebd7c67c5ea9a6ba4`.
- Ledger events through existing runner stages only: `source_ingestion_runner.py
  reconcile-historical video-2671b32f256a4ee7` → sequence 17 (`historical_decision_reconciled`);
  `source_ingestion_runner.py derive-module-metadata video-2671b32f256a4ee7 --room-id
  chevron-corridor-v2-north-south-socket` → sequence 18. No event, receipt or hash was written by
  hand. `module_poetics.py derive-all` was attempted first but correctly refused to overwrite
  frozen drafts; it was not used.

## Verification commands and exact results

All commands from `/mnt/sharedOs/backrooms-workspace`.

| Command | Result |
|---|---|
| `godot4 --headless --path godot_walk --script res://…/chevron-corridor-v2-north-south-socket/test_room.gd` | exit 0, `CHEVRON_T_THROUGH_VARIANT_TESTS_PASSED` |
| `python3 -m ruff check …/run_capture_guarded.py` | `All checks passed!`, exit 0 |
| `python3 godot_walk/scripts/register_video_sources.py validate` | `{"valid": true, "registered_count": 13}`, exit 0 |
| `python3 godot_walk/scripts/template_validate.py` | `{"valid": true, "source_manifests": 45, "module_profiles": 22, "generative_maps": 68, "errors": []}`, exit 0 |
| `python3 godot_walk/scripts/module_poetics.py validate --index …/godot_psx_room_kit-0.9.0.json` | `draft_count: 20`, overall `valid: false` with 40 errors; **0 errors** for the new variant draft (all errors belong to pre-existing drafts bound to older indices, not edited) |
| `python3 -m pytest -q godot_walk/scripts` | **1574 passed, 5 skipped, 94 subtests passed in 287.92 s (exit 0)** |

Guarded capture command (through `run_capture_guarded.py` only):

```
python3 godot_walk/source_library/sources/video-2671b32f256a4ee7/rooms/chevron-corridor-v2-north-south-socket/run_capture_guarded.py \
  --output-dir godot_walk/source_library/sources/video-2671b32f256a4ee7/rooms/chevron-corridor-v2-north-south-socket/captures \
  --report godot_walk/source_library/sources/video-2671b32f256a4ee7/rooms/chevron-corridor-v2-north-south-socket/capture_resource_run.json \
  -- godot4 --path godot_walk \
  --script res://source_library/sources/video-2671b32f256a4ee7/rooms/chevron-corridor-v2-north-south-socket/capture_room.gd \
  -- --out=res://source_library/sources/video-2671b32f256a4ee7/rooms/chevron-corridor-v2-north-south-socket/captures
```

Receipt: `return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=5.303`. The Godot
X11 `NO GRAB` mouse warning is non-fatal. `captures/capture_manifest.json`: four 1152×648 PNGs —
`spawn_toward_north_opening`, `north_doorway`, `south_doorway`, `partition_lane`; mean 8.84 ms /
p95 16.71 ms / p99 66.98 ms over 300 samples. All four files exist and are non-empty. **Appearance
and feel judgements are the operator's; agents cannot judge appearance.** No capture image was
interpreted for acceptance.

`video_adaptation_runner.py validate --bundle` on the new adaptation record is not part of the
task's verification set and, like the #275/#277 pattern records, reports a schema difference in
the hand-authored record (`catalog_module_refs`/`sockets` shape); it is noted here as an honest
limitation, not claimed as passing.

## Pending operator-only steps (not attempted)

- Approval of the exact north/south socket placement, including the interpretation of "arm ends
  of the T" and the omitted far-light-panel visual noted above.
- Connector-pair test and approval; no partner or rotation is claimed here.
- `accept-module-metadata` (would write `module_poetics_v2.json`), `decide-integration`, and any
  seeded-map placement. No map was generated or committed.

## Honest limitations

- Passing validators, a green headless room test and a clean guarded capture are not approval. The
  sockets remain declared-but-untested and layout-ineligible by design.
- The variant reuses the accepted room's textures by reference; no texture was copied or edited.
- The catalog entry and admission decision deliberately say sockets are untested and
  layout-ineligible. Reverting the 0.9.0 catalog/index/snapshot and registration would be needed if
  the operator rejects the placement; that was not done unprompted.
- No hash-pinned file was touched. `git diff --name-only` for `godot_walk/scripts/player.gd`,
  `godot_walk/project.godot`, `godot_walk/room_catalog/MATERIAL_LANGUAGE.md`,
  `godot_walk/room_catalog/PALETTES.md`, the accepted `chevron-corridor-v1` room and the #275/#277
  variant rooms is empty.

## Files changed

Modified: `godot_walk/room_catalog/catalog.json`, `godot_walk/source_library/index.json`,
`godot_walk/source_library/sources/video-2671b32f256a4ee7/events.jsonl`.
Added: `godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.9.0.json`,
`godot_walk/room_catalog/library_index/godot_psx_room_kit-0.9.0.json`,
`godot_walk/source_library/sources/video-2671b32f256a4ee7/source_manifest-v5.json`,
the new `chevron-corridor-v2-north-south-socket/` room folder (scene, scripts, test, captures,
decision, adaptation, poetics draft) and this report.
