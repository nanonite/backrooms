# Lighting and scale overlay review contract

T5 overlays are append-only sidecars for enclosed spaces. The source manifest or
module profile remains the authority for its own fields; an overlay binds to
that record by relative path and SHA-256. A missing overlay means lighting is
`uncalibrated_not_reviewed` and scale is `uncalibrated` with review status
`not_reviewed`. Consumers should use `lighting_scale_state` to obtain this
default without rewriting legacy records.

## Status and provenance claims

| Field | Claim it can make | Required support / rejected combinations |
|---|---|---|
| Lighting aggregate `status` | `uncalibrated_not_reviewed`, `estimated_pending_review`, or `reviewed` | All lighting contributors (colour temperature, illuminance, every fixture) must have the same review status. Aggregate review status must equal theirs. `reviewed` requires all contributors and aggregate to be `operator_reviewed` or all to be `vision_model_reviewed`, with review evidence for each. |
| Lighting and scale aggregate `review_status` | not reviewed, pending operator/model review, or operator/model reviewed | Must match the status of every contributing field. A mixture is invalid. Reviewed aggregates require evidence stating reviewer, date, scope, and cited record(s). |
| Value and fixture `review_status` | not reviewed, pending, operator reviewed, or vision-model reviewed | Reviewed fields require cited value evidence plus review evidence. The reviewer kind in the review evidence must match the status. Pending and not-reviewed fields cannot claim review evidence. |
| Scale `status` | `uncalibrated` or `calibrated` | It must agree with the base record's scale status. `calibrated` requires a reviewed measured anchor, a committed measurement reference, a matching measured value, and (for sources) base-manifest `scale_calibrated: true`. |
| Anchor `status` | `estimated` or `measured` | A measured anchor requires a cited committed measurement; its value must match the referenced JSON pointer. A source overlay must agree with the manifest anchor. Estimated anchors cannot calibrate scale. |
| `provenance` | Human-readable origin and basis for the estimate or observation | This is descriptive context, not review evidence and cannot change a review/calibration status. Agent-proposed estimates must say they are estimates and identify their basis. |
| `evidence` / `review_evidence` | Content binding and review record | Content references require path and SHA-256. Review evidence additionally records `reviewer_kind`, reviewer identity, ISO date-time, what was reviewed, and at least one cited record. No operator or model review may be inferred from an estimate. |

All file references are checked for readability, root containment, and digest
agreement. Review records are only valid when their evidence references also
validate. `lighting_scale_state` returns the conservative uncalibrated default
if an overlay fails validation, so invalid aggregate claims are never exposed
as state.

## Review path

An operator may change a field to `operator_reviewed` after inspecting the
cited source or authored module evidence. The record must add a review-evidence
entry with the operator identity, review date, specific fields and decisions
reviewed, and committed evidence references. A vision-model review may be
recorded only after such a review actually occurs; it uses
`vision_model_reviewed`, names the model/reviewer, states the reviewed scope,
and cites the committed input and output records. The corresponding aggregate
status changes only when every contributing field has the same review status
and its own review evidence. The worked source and module overlays currently
contain agent-proposed estimates and remain pending operator review.
