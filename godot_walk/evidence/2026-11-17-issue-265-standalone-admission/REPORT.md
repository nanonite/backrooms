# Issue 265 — Standalone catalog admission of the six accepted video rooms

Date: 2026-11-17
Issue: #265 (child of #169), operator decision comment 646
Status: **PARTIAL — blocked at `register_source_room.py`; operator decision required**

## Operator authorisation and scope

Comment 646 authorises, for this issue only, the admission edits used by the
earlier Bill Viola admission: bump `catalog.json` 0.5.0 → 0.6.0 by *adding* six
module entries (never changing an existing entry), write the immutable
`godot_psx_room_kit-0.6.0.json` snapshot, add the new library index version,
write one `catalog_admission_decision.json` per room (scope `standalone_only`,
`layout_eligible: false`), run `register_source_room.py` per source, then
`derive-module-metadata` per room. It withholds `accept-module-metadata`,
`decide-integration` and every socket decision. The standing rules keep
`registration_accepted`/`scale_calibrated` false and forbid editing hash-pinned
files, accepted rooms and frozen contracts.

No research doc under `docs/research/` is named by issue 265; the applicable
design documents are `docs/MODULE_METADATA_CONSOLIDATION_PROPOSAL.md`,
`docs/GENERATIVE_MAP_METADATA_PROPOSAL.md` and
`docs/MAZE_DYNAMICS_PROPOSAL.md`, plus the source-library README and the Bill
Viola admission (`git show 4a21bee`).

## Written plan (per-room disposition)

All six rooms are operator-accepted standalone candidates with no sockets and
no source-inferred connectivity. Per comment 646 the operator admitted all six
as STANDALONE modules: `layout_eligible: false`, `sockets: []`,
`tested_connector_pairs: []`. No room receives authored sockets in this issue.
The slot canyon (#172) and snow garden (#174) are open-world stand-ins and stay
standalone until the open-world contract (#267) lands.

| Room | Source | Module id | Admitted | Metadata | Sockets | Standalone reason |
|---|---|---|---|---|---|---|
| slot-canyon-courtyard-v1 (#172) | video-22909eb734e4d8e2 | `video_22909eb734e4d8e2_slot_canyon_courtyard_v1` | catalog entry + decision written (manifest link blocked) | v1 draft derived | none | Operator decision 646; open-world stand-in, blocked on #267 |
| nested-light-corridor-v1 (#173) | video-d857abe7a94da9d1 | `video_d857abe7a94da9d1_nested_light_corridor_v1` | catalog entry + decision written (manifest link blocked) | v1 draft derived | none | Operator decision 646; no operator socket authorisation |
| snow-garden-courtyard-v2 (#174) | video-d92fc1fa764aa3a2 | `video_d92fc1fa764aa3a2_snow_garden_courtyard_v2` | catalog entry + decision written (manifest link blocked) | v1 draft derived | none | Operator decision 646; open-world stand-in, blocked on #267 |
| chevron-corridor-v1 (#175) | video-102caf53423018b7 | `video_102caf53423018b7_chevron_corridor_v1` | catalog entry + decision written (manifest link blocked) | v1 draft derived | none | Operator decision 646; no operator socket authorisation |
| chevron-corridor-v1 (#176) | video-2671b32f256a4ee7 | `video_2671b32f256a4ee7_chevron_corridor_v1` | catalog entry + decision written (manifest link blocked) | v1 draft derived | none | Operator decision 646; distinct source video, no socket authorisation |
| chevron-cross-corridor-v1 (#177) | video-61b91dbeb9026dc7 | `video_61b91dbeb9026dc7_chevron_cross_corridor_v1` | catalog entry + decision written (manifest link blocked) | v1 draft derived | none | Operator decision 646; no operator socket authorisation |

`operator_review.json` and `adaptation_standalone_accepted_v1.json` were used
unchanged as the operator's accepted records for every room. No existing
catalog entry, snapshot, map, module poetics record, or any other frozen
artifact was edited.

## Work completed and exact commands

All commands run from the repository root.

1. Baseline validation:
   - `python3 godot_walk/scripts/register_video_sources.py validate`
     → `{"valid": true, "registered_count": 13}`
2. Catalog bump and new immutable artifacts (generator recorded under
   `GENERATION.md` in this folder):
   - Bumped `godot_walk/room_catalog/catalog.json` `catalog_version` 0.5.0 → 0.6.0
     and appended exactly six `modules` entries; verified with a JSON comparison
     that all 8 pre-existing module entries and all other top-level fields are
     byte-for-byte unchanged. Module ids follow
     `video_<source hex>_<room name>_v1`; each entry has `layout_eligible: false`,
     `sockets: []`, `registration_accepted: false`, `scale_calibrated: false`,
     the room's `candidate_identity`, and real footprint/provenance data copied
     from that room's accepted adaptation record.
   - Wrote `godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.6.0.json`
     as an exact byte copy of the new catalog.
     SHA-256 `2095b4e67742f8de17f83da3f0900397f1603f1d10cb4367ae74ca4e1dad1cce`.
   - Wrote one `catalog_admission_decision.json` per room
     (`decision: accepted_standalone_module_admission`, `issue: 265`,
     `scope: standalone_only`, `layout_eligible: false`,
     `tested_connector_pairs: []`, both accepted records named by
     comment 646 and bound by their real SHA-256, and the new snapshot bound by
     its SHA-256). The decisions additionally cite the hash-verified
     `operator_review.json` so the ledger can inherit its original timestamp.
3. New library index version:
   - `python3 godot_walk/scripts/library_index.py build --snapshot godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.6.0.json`
     → `{"index": "godot_walk/room_catalog/library_index/godot_psx_room_kit-0.6.0.json", "module_count": 17, "pair_count": 2, "status": "created"}`
     Index SHA-256 `846159f7572c776b39c348b733f51d722692494318769681b281f9bf0e124a43`.
4. Ledger events for the new decision files, using only the existing runner
   stage (`source_ingestion_runner.py reconcile-historical <source_id>`), once
   per source → appended sequences 12/14/17/14/14/12 respectively. Each is a
   `historical_decision_reconciled` event citing the exact decision path/hash
   (verified for video-22909eb734e4d8e2, sequence 12).
5. Mechanical metadata drafts, using only the existing runner stage:
   - `python3 godot_walk/scripts/source_ingestion_runner.py derive-module-metadata <source_id> --room-id <room_id>`
     once per room → appended `module_metadata_derived` sequences 13/15/18/15/15/13.
   - Each room now has `module_poetics_v1.json` (`metadata_status:
     draft_mechanical`, poetics fields null/empty, `layout_eligible_derived:
     false`). A direct `module_poetics.validate_drafts()` check against the new
     0.6.0 index reports **0 errors for the six new drafts**. The 22 reported
     errors all belong to the 11 pre-existing drafts, which still bind the
     frozen 0.5.0 index; those were deliberately not edited.
6. Verification:
   - `python3 godot_walk/scripts/register_video_sources.py validate`
     → `{"valid": true, "registered_count": 13}` (still clean; frozen evidence
     hashes still validate).
   - `python3 -m pytest -q godot_walk/scripts`
     → `1530 passed, 5 skipped, 67 subtests passed in 274.94s` (exit 0).
   - Focused pre-flight after correcting the module `visual_assets`/`dependencies`
     to repository-relative paths:
     `python3 -m pytest -q godot_walk/scripts/test_issue149_layout.py godot_walk/scripts/test_issue164_layout.py`
     → `13 passed, 2 subtests passed` (the first full-suite attempt had 13 setup
     errors from `res://` strings in those two arrays; corrected with new files,
     no frozen record edited).
   - No Godot headless capture was rendered: this issue's authorised work is
     catalog/metadata bookkeeping, and no visual judgement is being claimed.

## Blocker — exact missing precondition (escalated)

`register_source_room.py` cannot admit any of the six rooms, and therefore no
new source-manifest version or source-index entry was written:

```
python3 godot_walk/scripts/register_source_room.py video-22909eb734e4d8e2 \
  --adaptation godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/adaptation_standalone_accepted_v1.json \
  --decision   godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms/slot-canyon-courtyard-v1/catalog_admission_decision.json
# register_source_room.py: error: Original visual decision does not match this room
# SourceLibraryError at register_source_room.py:208, via _verify_visual_decision
```

Cause: `_verify_visual_decision` (`godot_walk/scripts/register_source_room.py`,
lines ~200–210) requires the visual decision to contain
`accepted_record_path == adaptation_path`. That visual decision is read from
`adaptation_standalone_accepted_v1.json → operator_decision.decision_record_path`,
which for all six rooms is `operator_review.json`. Those six
`operator_review.json` files do **not** contain an `accepted_record_path` field.
The only prior standalone admission (Bill Viola,
`video-b9161c467ed2d30a/rooms/bill-viola-single-room-v1/operator_decision_001.json`)
does contain it, which is why the template path worked there.

I did not add the field: `operator_review.json` is a frozen accepted-room
record whose SHA-256 is cited both by the accepted adaptation's
`operator_decision.decision_sha256` and by pre-existing
`historical_decision_reconciled` events; changing it would invalidate those
frozen bindings, and comment 646 does not authorise editing accepted rooms.
Adding a fabricated v2 acceptance record or changing the validator would be
improvising a worker-side operator decision.

Operator decision needed (one of): (a) authorise the field addition to the six
`operator_review.json` files together with regeneration of every dependent
decision/manifest hash and reconciled event; (b) supply an admission runner that
accepts this `operator_review.json` shape; or (c) explicitly direct that the six
rooms remain cataloged standalone without manifest linking.

## Pending operator decisions (not attempted)

- `accept-module-metadata` for each room (operator-only); the six v1 drafts are
  mechanical and still have empty poetics.
- `propose-integrations` / `decide-integration` against committed maps, and any
  socket design (operator-only decisions; no connectivity is inferred from the
  videos).
- A committed seeded map that *places* at least two of the new rooms. All six
  rooms are standalone with no sockets, so the generator excludes them from
  automatic layout; placing them would require an operator-approved socket and
  integration decision. No map was generated or edited in this issue.
- Audio/feel judgements — pending the operator (the agent cannot hear or walk).

## Honest limitations

- The catalog now advertises six admitted modules, but their source manifests
  are not linked to those admissions because `register_source_room.py` is
  blocked as described above. The catalog admission itself and the mechanical
  metadata are in place and validated.
- The derived drafts validate only against the new 0.6.0 index; the 11 existing
  drafts still bind 0.5.0. This is expected after a catalog version bump and was
  left untouched rather than rewriting frozen drafts.
- A passing validator or a clean test run is not operator approval. Operator
  approval of this issue is pending.

## Files changed

- Modified: `godot_walk/room_catalog/catalog.json`; six source `events.jsonl`
  ledgers (reconcile + derive events appended only, never rewritten).
- Added: `godot_walk/room_catalog/catalog_snapshots/godot_psx_room_kit-0.6.0.json`,
  `godot_walk/room_catalog/library_index/godot_psx_room_kit-0.6.0.json`, six
  `catalog_admission_decision.json` files, six `module_poetics_v1.json` drafts,
  this report and `GENERATION.md`.
