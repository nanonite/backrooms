# Issue #169 seed-review stage, first CPU-only slice

Date: 2026-11-04
Status: implemented and verified; operator decision still pending.

This bundle is the reproducible evidence for the first slice of issue #169: a
bounded, receipt-backed review of **at most three individual direct-source
frames**. It does not call a model, does not run OpenCode against a provider,
does not touch Hunyuan, does not capture a GPU frame, does not author a room,
and does not close the issue.

## What this slice enforces

- One request holds at most three candidates. Each candidate must be a direct,
  native-resolution decode of the registered source video, bound by frame ID,
  zero-based index, PTS, repository-relative path, SHA-256, and width/height.
- A fourth candidate fails closed with `candidate_count_exceeds_limit` and a
  mechanically ranked three-frame shortlist. The deterministic shortlist is used
  only when `--mechanical-shortlist` is passed explicitly.
- Mechanical scoring is advisory: native and 640x360 Laplacian focus, exposure
  and clipping, 32x32 duplicate similarity, and nearest-neighbour PTS coverage.
  It cannot select the model's answer or override a validation failure.
- A response must be one JSON object with a selected frame from the set or
  `null`, alternatives, evidence, uncertainty, confidence 1-5, and
  `use_original_frame_not_a_composite=true`.
- Confidence below threshold, abstention, timeout, provider error, and invalid
  output all require operator review. Nothing here authorizes the next stage.
- Receipts are append-only (`O_EXCL` file plus one `receipts.jsonl` line). An
  identical input fingerprint is refused, not overwritten. `registration_accepted`
  and `scale_calibrated` stay `false`.

## Frozen contract

- `godot_walk/seed_review/workflow.v1.json` — spec version, three-frame limit,
  120 s timeout, confidence threshold, model policy, schema paths.
- `godot_walk/seed_review/WORKFLOW_V1.md` — human-readable invariants.
- `godot_walk/seed_review/schemas/seed_review_{request,response,receipt}.schema.json`.

## Result 1: replay of the recorded #168 three-frame response

Input: [`REQUEST_168_THREE_FRAMES.json`](REQUEST_168_THREE_FRAMES.json), the three
direct-source frames `frame_4558`, `frame_4559`, `frame_4560` at 151.900–151.967 s,
1280x720, source video SHA-256
`ccf9722164a0bdc8aa0497e8f4ca16b30fcdc6b752192859fd8fef537ba5a0bb`.

Fixture: [`RECORDED_RESPONSE_168.json`](RECORDED_RESPONSE_168.json), the response
recorded in the earlier model smoke test (`2026-11-02-issue-169-model-smoke`),
shipped with the prompt, inputs, and limitations of that run. It is replayed, not
regenerated.

Command output: [`REPLAY_RESULT_168.json`](REPLAY_RESULT_168.json).
Receipt: [`receipts/video-ccf9722164a0bdc8/`](receipts/video-ccf9722164a0bdc8/).

- status: `completed_low_confidence`
- exit code: `2` (operator review)
- selected frame: `frame_4560`
- ranked alternatives: `frame_4559`, `frame_4558`
- confidence: `2/5` against threshold `3`
- invocation mode: `replayed_recorded_response`
- `guards.model_invoked = false`, `guards.paid_call_allowed = false`
- `requires_operator_review = true`, `next_stage_authorized = false`
- usage: `reported = false`; token and cost fields null, listed price 0.0
- `registration_accepted = false`, `scale_calibrated = false`

The mechanical order for this set is `frame_4560` (rank 1), `frame_4558`
(rank 2), `frame_4559` (rank 3). The model's pick agrees with the mechanical
rank, but the model's stated reason is its own and the confidence stays below
threshold, so the stage pauses for the operator instead of promoting a seed.

## Result 2: eleven-frame #167 set fails closed

Input: [`REQUEST_167_ELEVEN_FRAMES.json`](REQUEST_167_ELEVEN_FRAMES.json), the
eleven adjacent native frames `frame_1090`–`frame_1100` from the #167 GoPro
pilot (the historical set that timed out as a contact sheet).

Command output: [`FAIL_CLOSED_167.json`](FAIL_CLOSED_167.json).

- code: `candidate_count_exceeds_limit`
- provided: 11, limit: 3
- no model, no receipt, exit code `1`
- mechanical shortlist: `frame_1100`, `frame_1097`, `frame_1099`
- message requests a three-frame shortlist or an explicit
  `--mechanical-shortlist` opt-in

The explicit opt-in path is recorded in
[`SHORTLIST_167_DRY_RUN.json`](SHORTLIST_167_DRY_RUN.json): the same eleven
candidates resolve to reviewed `frame_1100` (rank 1, score 0.749914),
`frame_1097` (rank 2, 0.719725), `frame_1099` (rank 3, 0.704914) and eight
excluded frames, with `mechanical_shortlist_applied = true`. That run is a dry
run: it plans the command and writes no receipt, because no response exists for
this set.

`frame_1097` (index 1096, PTS 36.533333 s) is the frame the earlier #167 review
selected; it survives the shortlist, which is the regression this test protects.

## Result 3: dry run of the #168 request

[`DRY_RUN_168.json`](DRY_RUN_168.json) validates source identity, the source
manifest hash, every frame hash, the request schema, the prompt, the model
policy, and the OpenCode command, then stops. `invocation_mode = dry_run`,
`model_invoked = false`, no receipt.

## Verification

```
python3 -m pytest godot_walk/scripts/test_seed_review_*.py -q
60 passed

ruff check godot_walk/scripts/seed_review_*.py \
  godot_walk/scripts/run_seed_review.py \
  godot_walk/scripts/test_seed_review_*.py \
  godot_walk/scripts/build_seed_review_request.py
All checks passed!
```

The tests are fully mocked or replay-only: no provider call, no OpenCode
subprocess, no GPU, no image generation.

## Out of scope, unchanged by this bundle

- Hunyuan image-to-panorama and GPU capture.
- Room briefs, geometry, collision, materials, and catalog admission.
- Reviewer/worker loops, SkillOpt, model training.
- Issue closure, seed acceptance, registration, and scale calibration.

## Known limits

- Mechanical metrics are relative within a candidate set, not absolute quality
  thresholds.
- The replayed response is a recorded model opinion; its visual claims were not
  independently measured.
- The recorded run reported no token usage, so per-call cost accounting for a
  paid model is still unproven.
- The eleven-frame path is verified only for validation and shortlisting; no
  model has reviewed those three shortlisted frames.
