# SkillOpt data readiness audit

Audit date: 2026-10-23. This checks the evidence gate in Chainlink #152 only;
it does not install or run SkillOpt.

## Counted evidence

The two schema-valid, `confirmed` records under the #151 round bundles are:

| Round | View decisions | Variant decisions | Total labeled decisions |
| --- | ---: | ---: | ---: |
| `hunyuan-psx-r1` | 9 | 2 | 11 |
| `hunyuan-psx-r2` | 9 | 2 | 11 |
| **Total** | **18** | **4** | **22** |

The #152 minimum is five confirmed rounds and 30 labeled decision items. The
current record is short by **three rounds** and **eight decisions**. Splits by
round and a held-out latest round cannot be defined yet.

## Excluded candidate

`godot_walk/evidence/2026-10-21-issue-151-round-3/` contains a two-view
source-face extrusion candidate. The operator commented that the patch looked
good while also describing the column as a four-sided box. There is no
`operator_feedback.json` for this bundle. Its manifest uses two view IDs and
`column_face_extrusion`; the current feedback schema requires nine fixed view
IDs and does not allow that variant ID. Therefore this candidate is not counted
as a schema-valid confirmed round. Preserve the existing bundle and feedback
text; do not infer missing per-view choices from the screenshots.

## Next readiness work

1. Version the feedback schema so a round declares its actual matched view IDs
   and candidate IDs, with explicit source/provenance for any chat-backed
   record.
2. If the operator's existing round-3 statement is normalized, retain only
   choices stated directly and leave unspecified views as `none` or unlabelled
   according to the new schema.
3. Collect at least two further confirmed rounds after the round-3 record, and
   continue until the five-round/30-decision floor is met. Split by whole round;
   hold the latest confirmed round out for test.
4. Only after that gate, build the seed workflow skill, calibrate scorers, and
   request approval for backend/model and a hard budget before any SkillOpt run.

## Constraints retained

No room design is scored as ground truth, auto-selected, or promoted. ODiff is
evidence only. No SkillOpt backend, optimizer model, training run, or paid
service was selected or used. Calibration remains
`registration_accepted=false` and `scale_calibrated=false`.
