# Issue #169: Free vision model smoke check

This check verified that the configured OpenCode Go provider accepts a local
image attachment and returns a bounded visual description. It used the
already accepted direct-source frame from #168; it did not select a seed from
multiple candidates, run Hunyuan, or change any room asset.

- Input: `frame_4560.png`, direct video decode at index 4559 / PTS 151.966667 s.
- Input SHA-256: `7a2b3dd1b43478fa491447731c06b0f36fce71e2b80cbb089d3744cb02abcd0f`.
- Model: `opencode/nemotron-3.5-super-vl-free`; OpenCode v2.0.22.
- Result: success, image was accepted; response is in `seed_review.json`.
- Cost: selected model is listed as free. OpenCode's response did not expose
  token-usage metadata, so usage accounting still needs a fail-closed design
  before a paid model can be used.

The response identifies visible surfaces and explicitly lists unknown areas,
which is a useful output shape for a room brief. Its object-level claims (for
example, the objects on the floor and wall feature) were not independently
verified and are not treated as source facts. This single-image smoke check is
not seed ranking, candidate acceptance, or evidence of general model accuracy.

A second bounded call attempted to rank the 11 labeled adjacent frames in the
existing #168 contact sheet. It exceeded the 120-second process timeout; the
OpenCode transport closed without returning a ranking. This is recorded in
`seed_rank_attempt.json`. No automatic retry ran. The free model therefore
passes the single-image attachment smoke check, while that contact-sheet
format remains unproven.

A separately issued three-image comparison of frames 4558–4560 completed. The
model ranked the already operator-selected frame 4560 first, but assigned
confidence 2/5 and said the frames were nearly indistinguishable. That is a
useful bounded seed-selection signal, not evidence that the model can resolve
meaningful differences across an entire video. The exact result and image
hashes are in `seed_rank_3frames.json`.

## Runner integration check

The CPU seed-review runner now has a live OpenCode adapter and extracts model
text from OpenCode's JSON event stream. A dry run validates the request and
prints the invocation without calling a model. A recorded-response replay
produced an append-only receipt under `replay-receipts/` and correctly stopped
at low confidence.

One live call through the runner used the same three frames and the free,
image-tested `opencode/nemotron-3.5-super-vl-free` model. It completed in
29.602 seconds, chose frame 4560 again, and returned confidence 4/5; the earlier
independent call returned 2/5. This confidence variation is a reason to retain
operator review of seed decisions. Neither result changed the source library's
selected-seed event or authorized Hunyuan. The append-only receipt is
`live-adapter-receipts/video-ccf9722164a0bdc8/20261102T03551442860-bba8480e9d56.json`.
The model response did not report token usage; the selected model is listed as
free and the receipt records a $0 listed price.

A separate attempt to replay the accepted #167 seed with adjacent direct-source
frames 1096–1098 reached OpenCode's free-usage quota and returned HTTP 429.
Its failed receipt is preserved under `live-adapter-receipts-167/`; it did not
retry or change the accepted frame-1097 source event. The raw provider event in
that receipt identifies `provider.quota` and `Free usage limit reached`. Future
receipts now surface the structured provider error instead of only a generic
nonzero exit; the historical receipt is not rewritten.

The seed-review suite has 52 passing tests; the full Python suite has 211
passing tests. Ruff lint, formatting, Python compilation, source-library
validation, dry-run, and recorded-response replay pass. No Hunyuan inference,
GPU capture, room authoring, or paid model call ran in this integration check.
The free DeepSeek Flash Chainlink reviewer timed out at its 180-second limit
before returning a verdict, so it did not dispatch a worker follow-up. The
subsequent #167 comparison stopped at the provider's free quota; no alternate
or paid endpoint was tried.

Reproduction:

```bash
timeout 120s opencode run --standalone \
  --model opencode/nemotron-3.5-super-vl-free \
  --file godot_walk/source_library/sources/video-ccf9722164a0bdc8/frames/issue168-seed-152s/frame_4560.png \
  --format json \
  "Inspect this one image as a direct video frame. Return JSON with fields visible_evidence, uncertain_or_occluded, and seed_quality. Cite only visual details actually visible; do not infer adjacent rooms, connectivity, or hidden geometry."
```

Reproduce the runner checks with the three-frame request and recorded response:

```bash
python3 godot_walk/scripts/run_seed_review.py \
  --source-id video-ccf9722164a0bdc8 \
  --request godot_walk/evidence/2026-11-02-issue-169-model-smoke/REQUEST_168_THREE_FRAMES.json \
  --dry-run

python3 godot_walk/scripts/run_seed_review.py \
  --source-id video-ccf9722164a0bdc8 \
  --request godot_walk/evidence/2026-11-02-issue-169-model-smoke/REQUEST_168_THREE_FRAMES.json \
  --replay-response godot_walk/evidence/2026-11-02-issue-169-model-smoke/seed_rank_3frames.json \
  --receipts-dir godot_walk/evidence/2026-11-02-issue-169-model-smoke/replay-receipts
```

The live invocation used the same request and the model options described in
its append-only receipt. Use a new receipts directory for a new call; identical
inputs are refused rather than overwritten.
