# Open-scene finite-coverage candidate contract v1

Contract id `godot_open_scene_coverage`, version `1.0.0`, schema
`open_scene_coverage_v1.schema.json`. This is a **separately versioned** variant.
It does not amend, replace or reinterpret the frozen enclosed-room contract
(`godot_video_room_completion` 3.0.0 and its v1–v4 freeze lineage). A record that
names the room contract is rejected by this variant, and vice versa.

## Purpose and limits

This contract describes a *finite supported area* extracted from an open source,
not a reconstruction and not an infinite world. It is a candidate-only record:
`status` is `candidate_pending_review` or `rejected`, `registration_accepted` and
`scale_calibrated` are always `false`, and `catalog_scope` is always
`not_admitted_pending_integration_design`. Nothing here admits an outdoor
candidate to `catalog.json` or to room assembly. No model, GPU, download,
capture, streaming, terrain reconstruction or runtime traversal behaviour is
part of this contract.

## Required declarations

- `scene_category` is `open_world`. Enclosed and legacy records do not use this
  contract; they keep the existing enclosed workflow.
- `coverage` is a finite simple orthogonal XZ polygon with a `floor_elevation`.
  It is the area for which support is declared, not a measured world boundary.
  `basis` and `evidence_ref` keep its provenance explicit (`authored`,
  `estimated` or `observed`). A larger polygon is not evidence of real terrain.
- `safe_spawn_xyz` must lie strictly inside the coverage polygon at the declared
  floor elevation. Missing, unsupported or boundary spawn points are rejected.
- `exterior_classification` is exactly `unknown`. The exterior is *unknown
  continuation of the source*, not safe ground, not a void and not a measured
  extent. Missing or contradictory classification is rejected.
- `visual_horizon` declares `open_sky: true`, `visual_only: true` and
  `is_observed_geometry: false`. Distant scenery is appearance only.
- `boundary` declares no wall ring, no boundary collider and
  `edge_is_observed_geometry: false`. The coverage edge is a **coverage limit**,
  not observed wall geometry. `coverage_limit_representation` names how the
  limit is represented. `exits` may contain only `coverage_limit` entries whose
  `destination_classification` is `unknown` and `observed` is `false`; an exit
  that names or implies an observed destination is rejected.
- `obstacles` are separately declared with `provenance` (`observed` or
  `authored`) and a non-empty `evidence_ref`. An observed obstacle needs
  provenance; the coverage edge cannot be listed as an observed obstacle
  without separate evidence. Synthetic fixtures use `source_kind:
  synthetic_fixture` and never claim a real source.
- `provenance` records `scale_status: uncalibrated` and
  `connectivity_status: unknown`. Nothing in this contract asserts a calibrated
  scale or a connection to another region.

## Traversal policy (declaration only)

`traversal_policy.policy` is machine-readable and must be present. The contract
default is **`stop`**: at the end of the covered area movement stops with a
coverage-limit indication. `return` remains a possible later option. The field
is required in v1 records so the choice is auditable; authoring helpers default
it to `stop`. A `coverage_indication` with a machine `kind` and a
`player_facing_text` is also required — a policy without an indication is
rejected. Runtime behaviour, feedback, the stop/return choice and its
presentation are explicitly **not implemented or selected here**; they belong
to a later operator-reviewed slice.

## Operator review gate

Validation is mechanical and cannot approve fidelity, boundary experience or
admission. An operator must separately review: the reviewed scene category and
its decision record; whether the declared coverage is faithful to the source;
whether the unknown exterior and horizon are honest; and later, whether the
chosen traversal intervention and coverage indication are acceptable. Only the
operator may choose `stop` versus `return` for a real scene and accept any
candidate. A passing validator or a clean synthetic fixture is not acceptance
of a real scene.
