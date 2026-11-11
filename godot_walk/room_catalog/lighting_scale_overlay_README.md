# T5 lighting and scale overlays

T5 keeps source manifests and module profiles immutable. A source overlay lives
beside its `source_manifest*.json` as `source_lighting_scale_v1.json`. An
authored kit module overlay lives in `module_profiles/` with the
`-lighting-scale-v1.json` suffix. Each overlay contains both lighting and scale
data and binds to its base record with a repository path and SHA-256.
Source-derived module overlays live beside `module_profile_v1.json` as
`module_profile_lighting_scale_v1.json`; repository validation discovers these
as well.

Consumers should call `lighting_scale_overlay.lighting_scale_state(overlay)`.
Pass `None` when a record has no overlay; it returns the explicit
`uncalibrated_not_reviewed` lighting and `uncalibrated` scale defaults without
rewriting the base record. `template_validate.py` validates overlays
additively. Values are only estimates until reviewed, and no consumer should
treat `estimated_pending_review` as measurement or approval.

## Review and calibration

An agent may add estimates and mark every affected field
`pending_operator_review`; it cannot mark a field reviewed. An authorized
operator may review the values, record the decision in a committed review
artifact, add that artifact's path and SHA-256 to each reviewed field's
`evidence`, update the corresponding provenance, then set its status to
`operator_reviewed`. A vision-model review may only be recorded by an authorized
vision-model process; cite its committed output in the same way and use
`vision_model_reviewed`. Neither review state is inferred from a filename or
from an agent estimate.

Calibration requires a reviewed measured anchor and a citation to a committed
measurement artifact, including its JSON pointer. The anchor must be
`operator_reviewed` or `vision_model_reviewed` and include the review evidence
required for that field. The validator checks the artifact hash and that its
cited value equals the anchor. A measured anchor may remain uncalibrated while
review is pending. A source overlay also has to agree with the source manifest
scale status, and source calibration is rejected until the manifest itself
records accepted calibration. Estimated anchors always remain uncalibrated.
This issue leaves all `scale_calibrated` and `registration_accepted`
base-record flags false.

### Claims accepted by the validator

| Field claim | Allowed claim | Required support; unsupported claims are rejected |
| --- | --- | --- |
| Anchor provenance/status | No anchor (`null`), or an `estimated` or `measured` anchor object | A measured anchor has exactly one measurement reference; an estimated anchor has none. An anchor object with status `none` is contradictory because it also carries a dimension and is rejected. |
| Measurement reference | A committed measurement | The path exists in the repository and Git `HEAD`, the SHA-256 matches both, its JSON pointer resolves to a real finite positive number (booleans excluded), and that number matches `value_m` within `tolerance_m` (default `0`, bounded to `0..0.1 m`). Any supplied reference is checked even when the anchor is estimated or another status is inconsistent. |
| Scale aggregate status | `uncalibrated` or `calibrated` | `calibrated` requires a measured anchor whose committed measurement reference passes the complete measurement check, plus `operator_reviewed` or `vision_model_reviewed` status with the required field review evidence. A valid measured anchor may remain `uncalibrated` while pending review. A source manifest must also have accepted calibration. |
| Per-field review status | `not_reviewed`, pending operator/model review, or operator/model reviewed | Reviewed claims require field evidence and a review record with reviewer kind, reviewer, timezone-aware date, what was reviewed, and committed evidence. Reviewer kind must match the claimed status. Pending and not-reviewed fields cannot claim review evidence. |
| Lighting aggregate status | Uncalibrated/not reviewed, estimated/pending review, or reviewed | Its status and review status must agree with every contributing lighting field. Mixed field review states and aggregate claims unsupported by all fields are rejected. |
| Scale review status | The anchor's review status, or not reviewed when there is no anchor | Aggregate and anchor review states must agree, with the same review evidence rules. |
| Provenance and numeric values | Nonempty provenance; finite numeric estimates | Numeric fields reject booleans and non-finite values. Provenance text does not count as review or measurement evidence. |

The state helper first validates an overlay. It returns `valid: false` and the
uncalibrated defaults with errors for any invalid overlay; invalid review or
calibration claims are never surfaced as validated state. With no overlay it
returns `valid: true` and the explicit not-reviewed defaults.

The committed source and module overlays are examples only. Their lighting and
anchor values are agent-proposed estimates, pending operator review; no
operator or vision-model review has occurred. The source example is a picture
set and does not add video ingestion behavior. This template currently covers
enclosed spaces only.
