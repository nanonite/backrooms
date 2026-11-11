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

Calibration requires a measured anchor and a citation to a committed
measurement artifact, including its JSON pointer. The validator checks the
artifact hash and that its cited value equals the anchor. A source overlay also
has to agree with the source manifest scale status, and source calibration is
rejected until the manifest itself records accepted calibration. Estimated
anchors always remain uncalibrated. This issue leaves all `scale_calibrated`
and `registration_accepted` base-record flags false.

The committed source and module overlays are examples only. Their lighting and
anchor values are agent-proposed estimates, pending operator review; no
operator or vision-model review has occurred. The source example is a picture
set and does not add video ingestion behavior. This template currently covers
enclosed spaces only.
