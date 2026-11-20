# Issue #287 — formalize operator acceptance of wooden-verdure-hall-v1 (#171)

Source `video-c9115d943f6c3fe4`; candidate `wooden-verdure-hall-v1`;
candidate identity `3262fc81646c8433f8743fd324dbdc16c3be7db03c136db5d3e52d5c4e794e4a`.
Mirrors commit `5c2b215` (six prior standalone-room formalizations); no catalog admission.

## Identity check before recording

Recomputed all 48 dependency hashes from `adaptation_candidate.json` and the
`candidate_identity_v2` digest: 0 missing, 0 hash mismatches, identity matches.
`room.gd` (`3d6c2b45…d566`) and `room.tscn` (`ccff1b36…d48a6`) are unchanged since the
candidate was built, so the accepted record binds to the exact reviewed candidate.

## What was recorded

- `…/rooms/wooden-verdure-hall-v1/operator_review.json` — decision `accepted`,
  `reviewed_at_utc` `2026-11-20T02:28:08.414669+00:00`, `registration_accepted=false`,
  `scale_calibrated=false`.
- `…/rooms/wooden-verdure-hall-v1/adaptation_standalone_accepted_v1.json` — built from the
  unchanged candidate plus the operator review binding; status `accepted_reference`,
  `operator_decision.status=accepted`, same candidate identity. No other field changed.
- `events.jsonl` — two `historical_decision_reconciled` events (sequences 20, 21) appended
  by `source_ingestion_runner.py reconcile-historical video-c9115d943f6c3fe4`. Events carry
  reconciliation-time `occurred_at_utc` (never backdated), cite the exact artifact hashes,
  and leave both calibration flags false. No event or receipt was written by hand.

## Operator words (quoted from #287)

> "this room looks good, i cant jump in it and dont hear anything but that is fine if that was the intent"

> "audio nor jumping was not working or implemented in any of those simulation runs"

> "we can close 275 and 171 formulation"

Recorded scope: the operator accepted this exact candidate identity as a bounded standalone
room for authored appearance and traversal only, as reviewed in the live walk on 2026-11-19
(`DISPLAY=:1 godot4 --path godot_walk --rendering-driver vulkan res://source_library/sources/video-c9115d943f6c3fe4/rooms/wooden-verdure-hall-v1/room.tscn`).

Scope limits: no audio or jumping coverage — neither was implemented in the reviewed run.
No catalog admission, sockets, integration, maps, source-video connectivity, registration or
metric scale; `registration_accepted=false` and `scale_calibrated=false` unchanged. No room,
hash-pinned file, catalog, metadata, snapshot or library index was edited.

## Checks (exact result lines)

`python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle …/adaptation_standalone_accepted_v1.json`

```
  "status": "valid",
  "adaptation_id": "wooden-verdure-hall-v1",
  "candidate_fingerprint": "3262fc81646c8433f8743fd324dbdc16c3be7db03c136db5d3e52d5c4e794e4a",
  "candidate_identity": "3262fc81646c8433f8743fd324dbdc16c3be7db03c136db5d3e52d5c4e794e4a",
  "static_consistency": "passed",
  "validation_is_read_only": true
```

`python3 godot_walk/scripts/register_video_sources.py validate`

```
  "valid": true,
  "registered_count": 13
```

`python3 -m pytest -q godot_walk/scripts`

```
1582 passed, 5 skipped, 94 subtests passed in 466.48s (0:07:46)
```

No push, no issue close, no new hash-pinned dependency.
