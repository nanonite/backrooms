# Seed-review workflow, version 1.0.0

Status: frozen first CPU-only slice of issue #169. This stage reviews at most
three individual direct-source frames with a vision model and records an
append-only receipt. It does not run Hunyuan, start a GPU job, author a room,
invoke the reviewer/worker loop, admit a catalog module, or close an issue.

Machine-readable contract: [`workflow.v1.json`](workflow.v1.json). It names the
stage, the three-frame limit, the timeout and confidence defaults, the model
policy, and the three JSON schemas under [`schemas/`](schemas/).

## Why this slice is bounded

The #169 smoke evidence showed two different behaviours from the same free
vision model:

- one native-resolution direct-source frame was accepted and described;
- an eleven-tile labeled contact sheet timed out after 120 s without a result;
- three separate image attachments completed, ranking the already accepted
  #168 frame first at confidence 2/5.

The workflow therefore sends individual native-resolution frames, never a
contact sheet or composite. Three images is the review limit. A larger
candidate set fails closed with a request for a mechanically ranked shortlist;
the operator may explicitly opt into the deterministic shortlist.

## Invariants

1. Every candidate is a direct decode of the registered source video, recorded
   with frame ID, zero-based index, PTS, repository-relative path, SHA-256, and
   native width/height.
2. The source video SHA-256, source manifest SHA-256, and each candidate frame
   SHA-256 are checked before the model is called and recorded in the receipt.
3. A panorama, contact sheet, composite, resized frame, rendered-room capture,
   or foreign source is rejected before model invocation.
4. At most three candidates reach the model. More than three is a contract
   failure unless `--mechanical-shortlist` is explicitly passed.
5. A model response must be a single JSON object with a selected frame ID from
   the candidate set or `null` for abstention, alternatives, evidence,
   uncertainty, confidence 1-5, and
   `use_original_frame_not_a_composite=true`.
6. Confidence below the configured threshold, abstention, timeout, provider
   error, and invalid output all require operator review. None authorizes the
   next stage.
7. Receipts are append-only. An identical input fingerprint is refused rather
   than overwritten; the prior receipt path is reported.
8. `registration_accepted` and `scale_calibrated` stay false. Visual acceptance,
   catalog admission, and issue closure remain operator actions.

## Mechanical scoring

Before any model call the stage computes, per candidate:

- focus: variance of a four-neighbour Laplacian at native resolution and at a
  640x360 analysis size (relative within the candidate set, not an absolute
  blur threshold);
- exposure: mean luminance plus clipped-highlight and clipped-shadow fractions;
- duplicate similarity: maximum 32x32 greyscale mean-absolute-difference
  similarity to another candidate in the set;
- temporal coverage: nearest-neighbour PTS gap normalized to 0.5 s.

The weighted mechanical score is advisory. It supplies a deterministic order
only for shortlisting and for a diagnostic comparison with prior accepted
seeds. It never selects the model's answer and never overrides a mechanical
validation failure.

## Receipts

Receipts live under the source-scoped directory chosen by the caller, by default
`godot_walk/seed_review/receipts/<source_id>/`. Each run writes one JSON receipt
with `O_EXCL` and appends one index line to `receipts.jsonl`. The receipt binds:

- workflow spec path and SHA-256;
- request schema, response schema, and receipt schema paths and SHA-256 values;
- source video path, SHA-256, metadata, manifest path, and manifest SHA-256;
- every reviewed and excluded frame's identity and hash;
- provider/model reference, image-input-support basis, and OpenCode version when
  known;
- the exact prompt text and SHA-256;
- timeout, timestamps, elapsed seconds, command, and invocation mode;
- selected frame, alternatives, evidence, uncertainty, confidence, and raw
  response hash;
- usage metadata when the provider reports it, or explicit `reported=false`
  with null token/cost fields when it does not;
- paid-call guard state, timeout-limit check, and calibration flags.

## Model and cost policy

The preferred free reference is `opencode/nemotron-3.5-super-vl-free`, matching
the recorded #169 image-attachment evidence. Image support must be asserted
before a live frame-review call. Free calls still have one request, one timeout,
and no automatic retry. A model treated as paid or unknown-price is refused
before invocation unless both a positive per-run USD ceiling and a
provider-enforced spend limit or accounting basis are recorded. No API key or
secret is read, written, or logged.

## Commands

Dry run (validates source, candidates, hashes, schema, prompt, and command; calls
no model and writes no receipt):

```bash
python3 godot_walk/scripts/run_seed_review.py \
  --source-id video-ccf9722164a0bdc8 \
  --request godot_walk/evidence/2026-11-02-issue-169-seed-review-stage/REQUEST_168_THREE_FRAMES.json \
  --dry-run --json
```

Replay a recorded response (CPU only, no model call):

```bash
python3 godot_walk/scripts/run_seed_review.py \
  --source-id video-ccf9722164a0bdc8 \
  --request godot_walk/evidence/2026-11-02-issue-169-seed-review-stage/REQUEST_168_THREE_FRAMES.json \
  --replay-response godot_walk/evidence/2026-11-02-issue-169-seed-review-stage/RECORDED_RESPONSE_168.json \
  --receipts-dir godot_walk/evidence/2026-11-02-issue-169-seed-review-stage/receipts \
  --json
```

A live model call requires the explicit enable flag, a verified image-input
assertion, and free/paid policy values:

```bash
python3 godot_walk/scripts/run_seed_review.py \
  --source-id video-ccf9722164a0bdc8 \
  --request godot_walk/evidence/2026-11-02-issue-169-seed-review-stage/REQUEST_168_THREE_FRAMES.json \
  --provider opencode --model nemotron-3.5-super-vl-free \
  --model-is-free --image-input-supported --enable-model --json
```

## Explicitly out of scope for version 1.0.0

- Hunyuan image-to-panorama, GPU locks, RAM/VRAM/swap guards.
- Room briefs, authored geometry, collision, PSX material decisions.
- Godot captures, reviewer findings, and worker feedback cycles.
- Catalog admission, source-event edits, accepted-asset edits, and issue closure.
- SkillOpt runs or model training.

Those stages require separate versioned slices and operator authorization.
