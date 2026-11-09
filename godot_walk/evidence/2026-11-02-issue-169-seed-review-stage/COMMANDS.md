# Commands run for the issue #169 seed-review slice

All commands run from the repository root. CPU only; no model call, no OpenCode
invocation, no GPU, no Hunyuan.

## Tests and lint

```bash
python3 -m pytest godot_walk/scripts/test_seed_review_*.py -q

ruff check godot_walk/scripts/seed_review_*.py \
  godot_walk/scripts/run_seed_review.py \
  godot_walk/scripts/test_seed_review_*.py \
  godot_walk/scripts/build_seed_review_request.py
```

Observed: `60 passed`; `All checks passed!`.

Run a single test file, for example the historical replay:

```bash
python3 -m pytest godot_walk/scripts/test_seed_review_history.py -q
```

## Build the two requests in this bundle

The three-frame #168 request was derived from the recorded direct-frame
manifest `godot_walk/evidence/2026-11-01-issue-168-source-zone-survey/seed-review-152s/seed_candidate_manifest.json`,
keeping `frame_4558`, `frame_4559`, `frame_4560`.

The eleven-frame #167 request was derived from
`godot_walk/evidence/2026-10-26-issue-167-gopro-pilot/adjacent_seed_frames.json`.

The reusable builder covers the ≤3 case:

```bash
python3 godot_walk/scripts/build_seed_review_request.py \
  --source-id video-ccf9722164a0bdc8 \
  --extraction-manifest godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/seed-check-36s/extraction_manifest.json \
  --output godot_walk/evidence/2026-11-02-issue-169-seed-review-stage/REQUEST_167_THREE_FRAMES.json
```

That command is shown for reference and was not run for this bundle; the
eleven-frame request must stay eleven frames so the fail-closed path is
exercised.

## Dry run of the three-frame request (no model, no receipt)

```bash
E=godot_walk/evidence/2026-11-02-issue-169-seed-review-stage
python3 godot_walk/scripts/run_seed_review.py \
  --source-id video-ccf9722164a0bdc8 \
  --request "$E/REQUEST_168_THREE_FRAMES.json" \
  --dry-run --json > "$E/DRY_RUN_168.json"
```

Exit: `0`.

## Replay the recorded three-frame response (no model, writes a receipt)

```bash
E=godot_walk/evidence/2026-11-02-issue-169-seed-review-stage
python3 godot_walk/scripts/run_seed_review.py \
  --source-id video-ccf9722164a0bdc8 \
  --request "$E/REQUEST_168_THREE_FRAMES.json" \
  --replay-response "$E/RECORDED_RESPONSE_168.json" \
  --receipts-dir "$E/receipts" \
  --opencode-version 2.0.22 \
  --model-is-free \
  --json > "$E/REPLAY_RESULT_168.json"
```

Exit: `2` (`completed_low_confidence` → operator review). Writes
`$E/receipts/video-ccf9722164a0bdc8/<timestamp>-<receipt_id>.json` and appends
one line to `$E/receipts/video-ccf9722164a0bdc8/receipts.jsonl`.

Re-running the identical command is refused with `stage_already_completed`; the
existing receipt is never overwritten.

## Eleven-frame set fails closed

```bash
E=godot_walk/evidence/2026-11-02-issue-169-seed-review-stage
python3 godot_walk/scripts/run_seed_review.py \
  --source-id video-ccf9722164a0bdc8 \
  --request "$E/REQUEST_167_ELEVEN_FRAMES.json" \
  --dry-run --json > "$E/FAIL_CLOSED_167.json" 2>&1
```

Exit: `1`, code `candidate_count_exceeds_limit`, no receipt. The error payload
carries the mechanically ranked shortlist.

## Explicit mechanical shortlist (dry run, no receipt)

```bash
E=godot_walk/evidence/2026-11-02-issue-169-seed-review-stage
python3 godot_walk/scripts/run_seed_review.py \
  --source-id video-ccf9722164a0bdc8 \
  --request "$E/REQUEST_167_ELEVEN_FRAMES.json" \
  --mechanical-shortlist --dry-run --json > "$E/SHORTLIST_167_DRY_RUN.json"
```

Exit: `0`. Reviewed `frame_1100`, `frame_1097`, `frame_1099`; excluded eight.

## Guard check

```bash
grep -o '"registration_accepted": [a-z]*\|"scale_calibrated": [a-z]*' \
  "$E"/receipts/video-ccf9722164a0bdc8/*.json
```

Both read `false`.
