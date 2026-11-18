# Chainlink issue 267 — Open-world step 1: scene category and open-scene contract variant (CPU-only)

Child of #258, ingestion track. Operator-directed 2026-11-17. This is the combined
first implementation slice named by `docs/research/issue-256-open-world-ingestion.md`
and `docs/research/issue-261-unbounded-boundary.md`. Operator comment 645 on this
issue sets the traversal policy default to **STOP** and leaves **return** as a
possible later option; runtime behaviour of the policy is deliberately not implemented.

## Acceptance copied from the named research docs

From `docs/research/issue-256-open-world-ingestion.md`, section
"Ready-to-file first implementation slice":

> **Acceptance:** Category and review state are validated and auditable; unknown or unreviewed sources cannot silently enter the outdoor path. Enclosed and legacy records retain existing validation and routing. Outdoor fixtures distinguish finite collision bounds from visual horizon, reject missing boundary or spawn declarations, and preserve uncertain scale/connectivity. A contract document specifies how exits and intentional boundaries are represented without implying unobserved destinations. No outdoor fixture is presented as an accepted real reconstruction.

From `docs/research/issue-261-unbounded-boundary.md`, section "Ready-to-file first slice":

> **Acceptance:**
>
> - A valid open-scene fixture with finite support and unknown exterior passes without a wall ring or boundary collider. It declares one of the two policies and an indication; it makes no assertion of safe ground outside coverage.
> - Missing or contradictory exterior classification, unsupported spawn, unclassified boundary geometry, and absent policy or indication fail with actionable diagnostics. Observed obstacle declarations require provenance; the coverage edge cannot be represented as an observed obstacle without separate evidence.
> - Existing room fixtures keep their current results; accepted records and frozen files remain untouched. The new variant cannot silently reinterpret the old room contract. Both calibration flags remain false in synthetic fixtures.
> - Document how an operator reviews coverage and the eventual traversal intervention; validation alone cannot approve fidelity or admission.

## What was done (new files only)

No tracked file was edited. All artifacts are new:

| File | Purpose |
|------|---------|
| `godot_walk/room_catalog/scene_category_v1.schema.json` | Versioned intake category record: `enclosed` / `open_world` / `unknown`, review state, provenance. |
| `godot_walk/room_catalog/open_scene_coverage_v1.schema.json` | Separately versioned open-scene candidate schema (`godot_open_scene_coverage` 1.0.0). |
| `godot_walk/room_catalog/open_scene_coverage_contract_v1.md` | Contract document: coverage, unknown exterior, non-physical edge, exits, obstacle provenance, operator review gate, declaration-only stop/return policy. |
| `godot_walk/scripts/scene_category_v1.py` | Category validation and safe routing. Legacy manifests (no category field) route to `enclosed` unchanged; `open_world` routes to the outdoor path only when operator-reviewed with non-unknown provenance, otherwise it is held. |
| `godot_walk/scripts/open_scene_contract_v1.py` | Read-only validator for finite orthogonal coverage, strictly-inside spawn at floor elevation, `unknown` exterior, no wall ring/boundary collider, non-observed edge, classified obstacles, required policy + coverage indication, false calibration flags, catalog exclusion, candidate-only status. |
| `godot_walk/scripts/generate_issue267_fixtures.py` | Deterministic generator for the synthetic fixtures (refuses to overwrite differing bytes). |
| `godot_walk/scripts/test_scene_category_v1.py`, `godot_walk/scripts/test_open_scene_contract_v1.py` | Positive/negative tests, legacy and review-gate tests, room-contract regression and frozen-file checks. |
| `godot_walk/evidence/2026-11-17-issue-267-open-scene-contract/fixtures/*.json` | 26 CPU-only synthetic fixture records (valid, invalid, legacy, category records, manifests). |

Design points that satisfy the operator decision and the docs:

- The contract default is `stop` (`DEFAULT_TRAVERSAL_POLICY = "stop"` and the authoring
  helper `default_traversal_policy()`); `return` is accepted as an alternative in the
  schema. v1 records must still declare the policy and a coverage indication so the
  choice is auditable — an absent policy or indication fails.
- The coverage edge is a `nonphysical_coverage_edge`, never observed wall geometry;
  `exits` may only be `coverage_limit` entries with `destination_classification:
  unknown` and `observed: false`, so no unobserved destination is implied.
- The exterior is exactly `unknown`; no assertion of safe ground outside coverage.
  `visual_horizon` is appearance-only and `is_observed_geometry: false`.
- `status` is `candidate_pending_review` or `rejected`; `registration_accepted` and
  `scale_calibrated` are `false` and `catalog_scope` is
  `not_admitted_pending_integration_design`. No fixture is an accepted reconstruction.
- The new contract has its own `contract_id`, so a frozen room-contract record is
  rejected by it (explicit diagnostic) and vice versa.

Ledger: no ledger events, receipts or hash sidecars were written by hand. No existing
runner stage covers this CPU-only category/contract slice, so no runner stage was
invoked either; nothing was appended to any `events.jsonl`.

## Commands and results (repository root)

1. Generate fixtures (idempotent):
   `python3 godot_walk/scripts/generate_issue267_fixtures.py`
   → first run: `created 25 new files; all others matched their derived bytes`;
   later re-runs after fixture amendments each reported `created 1 new files`;
   a final re-run reported `created 0 new files; all others matched their derived bytes`.

2. Open-scene validator, positive fixtures:
   `python3 godot_walk/scripts/open_scene_contract_v1.py validate <fixtures>/valid_open_scene_v1.json <fixtures>/valid_return_policy_v1.json`
   → `PASS` for both, `EXIT=0`.

3. Open-scene validator, representative negative fixture:
   `python3 godot_walk/scripts/open_scene_contract_v1.py validate <fixtures>/invalid_wall_ring_v1.json`
   → `FAIL`, `EXIT=1`, with
   `Open-scene coverage must not declare a wall ring`,
   `Open-scene coverage must not declare a boundary collider` plus schema diagnostics.
   All 14 negative fixture classes are asserted in
   `test_negative_fixtures_fail_with_actionable_diagnostics`.

4. Category validator and routing:
   - `python3 godot_walk/scripts/scene_category_v1.py validate <fixtures>/category_open_world_reviewed_v1.json`
     → `route: open_world`, `can_enter_open_world: true`.
   - `python3 godot_walk/scripts/scene_category_v1.py route <fixtures>/legacy_manifest_v1.json`
     → `route: enclosed`, `category_source: legacy_default`, `can_enter_open_world: false`.
   - `... route <fixtures>/open_world_manifest_v1.json --category <fixtures>/category_open_world_pending_v1.json`
     → `route: open_world_hold`, `can_enter_open_world: false`.
   - `... route <fixtures>/open_world_manifest_v1.json --category <fixtures>/category_unknown_v1.json`
     → `route: enclosed`, `can_enter_open_world: false`.
   - `... route <fixtures>/categorised_manifest_without_record_v1.json`
     → `ERROR: A categorised manifest requires a versioned scene_category_v1 record`, `EXIT=1`.

5. Focused tests:
   `python3 -m pytest -q godot_walk/scripts/test_scene_category_v1.py godot_walk/scripts/test_open_scene_contract_v1.py`
   → `21 passed, 20 subtests passed`.

6. Full ingestion/script suite:
   `python3 -m pytest -q godot_walk/scripts`
   → `1561 passed, 5 skipped, 92 subtests passed in 274.88s`.

7. Source-library validator:
   `python3 godot_walk/scripts/register_video_sources.py validate`
   → `{"valid": true, "registered_count": 13}`, `VALIDATE_EXIT=0`.

8. Lint on new Python files:
   `python3 -m ruff check <new python files>` → `All checks passed!`
   (and `python3 -m ruff format` was applied to those five files).

9. Working tree: `git status --short` lists only the new files above; no tracked
   file is modified, so no frozen hash, accepted room, catalog entry, manifest or
   ledger event changed.

## Acceptance mapping

| Acceptance item | Evidence |
|-----------------|----------|
| Category + review state validated/auditable; unknown/unreviewed cannot enter outdoor path | `scene_category_v1.py` routing; command 4; `test_scene_category_v1.py` |
| Enclosed and legacy records keep existing validation/routing | legacy route test; full pytest; `register_video_sources.py validate` |
| Finite collision bounds vs visual horizon; reject missing boundary/spawn | schema + `_boundary_errors`, `_visual_errors`, `_spatial_errors`; negative fixtures and command 3 |
| Preserve uncertain scale/connectivity | `provenance.scale_status: uncalibrated`, `connectivity_status: unknown` enforced; test 2 in contract tests |
| Contract document for exits/boundaries without unobserved destinations | `open_scene_coverage_contract_v1.md`; `invalid_observed_destination_v1.json` |
| No outdoor fixture as accepted real reconstruction | `status` restricted to pending/rejected; positive fixture is `synthetic_fixture: true`; test asserts flags false |
| Valid fixture passes with no wall ring/boundary collider, unknown exterior, policy + indication | positive fixtures and command 2 |
| Missing/contradictory exterior, unsupported spawn, unclassified boundary, absent policy/indication fail | 14 negative fixtures and command 3 |
| Observed obstacles need provenance; edge not an observed obstacle | `invalid_observed_edge_obstacle_v1.json`; `_obstacle_errors` |
| Existing room results unchanged; frozen files untouched; no reinterpretation | contract regression tests, `FROZEN_FILES` hash test, room-record rejection test |
| Operator review documented; validation is not approval | contract document "Operator review gate" section; Pending section below |

## Pending the operator (not decided by this agent)

- Review the `enclosed` / `open_world` / `unknown` classification of each real source and
  sign the decision record referenced by a category record. Synthetic reviewer strings in
  fixtures are test doubles and are **not** operator approvals.
- Review whether any real declared coverage footprint is faithful to its source and
  whether the unknown exterior / visual horizon are honest.
- Choose `stop` versus `return` for any real scene and approve the player-facing
  coverage-indication text. The declared default is `stop`; no runtime behaviour is implemented.
- Decide on catalog inclusion / integration in the later design; nothing here admits a
  candidate. Do not treat validation results as acceptance of a real scene.

## Honest limitations

- All fixtures are CPU-only synthetic records. No real video/picture set was ingested, no
  coverage or scale was measured, and no operator review was performed.
- The traversal policy is a machine-readable declaration only. There is no Godot runtime
  stop/return, feedback, UI indication or collision behaviour in this slice.
- No Godot scene, script, asset or project file was changed, so no Godot headless test or
  guarded capture script applies. No PNG was rendered or reviewed; appearance and feel are
  not claimed.
- Agents cannot hear or walk; any audio/feel judgement is explicitly pending the operator.
- No ledger events were appended and no hashes, receipts or decisions were written by hand.
  A passing validator or clean fixture is not approval.
