---
name: hunyuan-psx-room-completion
description: Organize operator-directed PSX room completion around an existing Hunyuan visual candidate, with authored geometry, collision, and reproducible review evidence.
---

# Hunyuan PSX Room Completion

Use this workflow for Godot room-completion rounds based on an existing Hunyuan result. The skill proposes bounded variants, validates mechanics, captures matched views, and summarizes evidence. The operator makes every visual decision.

## Invariants

- Treat the original source video, seed frame, Hunyuan output, and each accepted round as provenance-bearing inputs. Hash the source frame and Hunyuan asset before work.
- Keep `registration_accepted=false` and `scale_calibrated=false` unless the operator separately accepts measured evidence. Coordinate transforms and room dimensions may be design conventions only.
- Hunyuan meshes are visual-only. Walkable surfaces, boundaries, and obstacles need separate authored collision and mechanical tests.
- Distinguish source-observed, Hunyuan-generated, authored, inferred, and unknown content in every region decision. Do not infer unseen rooms or connections.
- Preserve Gaussian #100/#115 inputs and prior accepted evidence. New evidence is append-only; correct prior records through dated addenda or superseding records.
- Do not run paid services, inference, training, world generation, or SkillOpt as part of a design round.
- Never select, rank as a winner, or promote a variant. The operator may keep, reject, iterate, or reject all candidates.

## Round Loop

1. Read the prior confirmed feedback, candidate source manifest, and protected-input hashes. For a first round, record that there is no prior operator directive.
2. Propose two or three variants around one bounded design hypothesis. Give each a stable ID and parent ID. Record per-region `preserve`, `cover`, or `replace` actions, evidence, rationale, materials, authored geometry, and collision changes.
3. Keep the camera poses, viewport, FOV, route, and settle settings fixed across variants. Before each GPU capture or FPS run, use the local GPU/RAM headroom guard; stop if another GPU job is active or headroom is insufficient. Bound each invocation with a timeout.
4. Run walk, floor-support, boundary, and expected negative-control checks. Record replay drift across repeats instead of assuming deterministic physics. Test the visually fullest variant for runtime cost.
5. Compare matched captures with ODiff and record the measured control-repeat noise. A per-view delta at or below that noise is inconclusive. Metrics are diagnostics, not aesthetic scores or provenance.
6. Generate a local review page with paired images and a downloadable, schema-valid `operator_feedback.json`. Leave decisions empty until the operator submits them. Record reasons, unresolved problems, confidence, and next-round directives. To submit directly, serve the current pending round's actual bundle directory with `hunyuan_review_server.py --bundle-dir` and `--open-browser`. The server rejects confirmed rounds unless `--allow-confirmed` is supplied for historical inspection. If no pending bundle exists, do not reopen an older confirmed round.
7. Validate record shape against `design_rounds/hunyuan_round.schema.json` and `design_rounds/operator_feedback.schema.json`, then cross-check every feedback view and variant ID against that round's manifest. Stop for operator review after each bundle. Start a follow-up only from confirmed feedback; do not auto-promote its parent.
8. After confirmation, append the round to `design_rounds/hunyuan_track_record.jsonl` with `build_hunyuan_track_record.py`. Do not index pending or diagnostic-only candidates. This is data collection; it does not authorize a SkillOpt run.

For the #151 first-round runner and its fixed capture/verification contract, see `godot_walk/scripts/run_hunyuan_psx_round1.py` and the generated round `COMMANDS.md`.
