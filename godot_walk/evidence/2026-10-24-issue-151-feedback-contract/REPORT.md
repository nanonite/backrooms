# Issue #151 — manifest-driven feedback contract

## Change

Operator feedback now supports the view IDs and variant IDs declared by each
round manifest. The JSON Schema validates record shape; the runtime validator
checks that confirmed feedback covers each manifest view and variant exactly
once, and that each view choice names a variant, `tie`, or `none`.

The local review server validates the manifest before accepting a submission.
It accepts submissions only for pending rounds and refuses to replace a
confirmed feedback record. Round 2's preflight validates both the prior
manifest and its feedback against each other before starting another round.
The room-completion skill now states these rules. Confirmed Rounds 1 and 2
are indexed in `godot_walk/design_rounds/hunyuan_track_record.jsonl`; the index
preserves variant hypotheses and authored changes, per-view ODiff measurements,
mechanical gates, operator reasons, and stable directive IDs. The
diagnostic-only Round 3 is excluded.

## Verification

- Current #151 Round 1 and Round 2 manifests and confirmed feedback validate
  against their actual manifest IDs.
- A synthetic review with two views and three variants submits successfully;
  this covers an ID set different from the original nine-view/two-variant
  form.
- Confirmed feedback cannot be replaced, even if the manifest is stale and
  still says pending.
- No capture or GPU job ran.

Commands:

```bash
python3 godot_walk/scripts/test_hunyuan_round_schema.py
python3 godot_walk/scripts/test_hunyuan_review_server.py
python3 godot_walk/scripts/test_hunyuan_track_record.py
# Validate future source bundles without appending duplicate IDs.
python3 godot_walk/scripts/build_hunyuan_track_record.py --validate-only --bundle-dir godot_walk/evidence/2026-10-21-issue-151-round-1 --bundle-dir godot_walk/evidence/2026-10-21-issue-151-round-2
ruff check godot_walk/scripts/hunyuan_round1_records.py godot_walk/scripts/hunyuan_review_server.py godot_walk/scripts/run_hunyuan_psx_round2.py godot_walk/scripts/test_hunyuan_round_schema.py godot_walk/scripts/test_hunyuan_review_server.py
ruff check godot_walk/scripts/build_hunyuan_track_record.py godot_walk/scripts/test_hunyuan_track_record.py
```

Results: 10 schema tests, 9 review-server tests, and 4 track-record tests
passed. Ruff passed. The index is append-only; future confirmed rounds use
`--append`. SkillOpt remains deferred. These changes make future workflow
rounds easier to record; they do not select or promote room designs.

To build the initial index in a fresh checkout, run the same command without
`--validate-only`. Do not rerun that write command over an existing index.

