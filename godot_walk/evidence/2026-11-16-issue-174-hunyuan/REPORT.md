# Issue #174 — guarded Hunyuan attempt-001: BLOCKED AT PREFLIGHT (no inference ran)

Date: 2026-11-16 (UTC)
Source: `video-d92fc1fa764aa3a2` — `data/videos/Angel (Joseph Cornell, 1957).mp4`
Source SHA-256: `d92fc1fa764aa3a25a40910f01858def4b72dd3b51ca4af8d5d012d788567428`
Manifest: `source_manifest-v3.json`, SHA-256 `28c01ed69ccbe6acc9854b659cbfb3a8b902903a6257542bb289f9a042b8f77f`
Seed: `frame_4347`, index 4346, 145.0115 s, SHA-256 `ae59a84fb9aa07612b5b100c2ee5b5ab5645836dd5bccc665b862acd51ab500f`
(unedited direct decode, 636x480)
Authorization: operator decision 2026-11-16 (issue #174, comment 598) — attempt 1 of 3 approved
(local GPU, no USD ceiling); run one attempt, then stop for operator review.

## Result

**The single authorized attempt did not start.** The runner's GPU preflight refused to launch the
Panogen child because its named-job scan matched two processes belonging to the harness that is
running this worker. No model inference, no panorama and no resource sampling occurred.

- Attempt id (reserved): `attempt-001`
- Launch: exactly one detached invocation with runner defaults
  (`512x256`, seed `42`, `2700 s`, `sequential_cpu`), as directed:
  `setsid nohup python3 godot_walk/scripts/run_source_hunyuan.py video-d92fc1fa764aa3a2 --prompt "$(cat <prompt-file>)" > /tmp/issue174-run.log 2>&1 < /dev/null &`
- Runner stdout (`/tmp/issue174-run.log`): `{"status": "blocked", "attempt_id": "attempt-001", ...}`
- `checked_at_utc`: `2026-11-16T18:11:15.178175+00:00`
- `attempts_used` after the block: **0 / 3** (a preflight block does not consume the cap)
- Post-run `status`: `awaiting_feedback` false, `can_start_attempt` false,
  `manual_fallback_allowed` true, `stopped_reason` set, `next_worker_actions` `["manual-fallback"]`

## Exact error

`GPU preflight blocked by active job(s):` two process rows were matched by
`psx_design_round_resources._active_named_jobs()` (regex `hunyuan|hunyuanworld|qemu-system|qemu`
over each process's `name` + `args`, excluding only the runner's own ancestors and
`hunyuan_review_server.py`):

1. pid `2453891` — the `chainlink-loop` plugin process (bun), invoked with `--task 174,175,176,177,178 …`
   and the full task prompt passed via `--prompt`.
2. pid `2456132` — the `opencode` worker process for this task, whose command line embeds the
   same task prompt / operator direction.

Both command lines contain the restricted word **only because the task prompt itself contains it**
(the direction repeatedly names the launcher and the runtime). They are the worker's own controller
processes, not concurrent GPU jobs. The guard cannot distinguish that and blocks unconditionally.

This is a genuine environment/guard conflict, not a mistake in the launch. Per the operator
direction the guard may not be bypassed, edited or retried, so the worker stopped here.

## Prompt (written, never sent to a model)

51 words, derived only from the selected seed frame (`frame_4347`), which shows a weathered grey
stone angel statue with folded wings and a bowed hooded head seen from a low angle outdoors, bare
branching trees and a dark evergreen against a pale blue sky under a soft blue-violet tint. The
burned-in video tint was described as the scene's colour; no glitch, letterbox bar or watermark was
described; nothing was cropped, edited or replaced.

> Weathered grey stone angel statue with folded wings and bowed hooded head, seen from a low angle
> outdoors. Bare branching trees and a dark evergreen stand against a pale blue sky, all under a
> soft blue-violet tint. One continuous outdoor garden scene; no people, no text, no signage,
> no added objects.

## Ledger event (written by the runner, not by hand)

All bound to manifest `28c01ed69ccbe6acc9854b659cbfb3a8b902903a6257542bb289f9a042b8f77f`.

| Sequence | Event | Occurred (UTC) |
| --- | --- | --- |
| 9 | `hunyuan_preflight_blocked` | `2026-11-16T18:11:15.261414+00:00` |

Event 9 carries a `gpu_guard.json` receipt (`hunyuan/attempt-001/gpu_guard.json`, SHA-256
`d64b6c168606a0dfe6054e56cc684c718f1c36851f845ea8554adf6911af537d`). `events.jsonl` remains
append-only; no receipt or event was authored by the worker.

## Outputs that exist

| Path | Notes |
| --- | --- |
| `…/hunyuan/attempt-001/attempt_config.json` | reserved config, 512x256 / seed 42 / 2700 s / sequential_cpu |
| `…/hunyuan/attempt-001/gpu_guard.json` | preflight guard receipt (blocked run) |

No `panorama/`, `attempt_result.json`, `execution_guard.json`, `resource_samples.jsonl`,
`stdout.log` or `stderr.log` was produced — the Panogen child was never started. There is no
panorama to preview, so no seam / drift / invented-object / resolution assessment is possible.

## What was not done

- No Panogen inference, no panorama, no `awaiting_feedback` result.
- No second attempt, no `manual-fallback`, no guard bypass or edit, no manual receipts.
- No `feedback`, no winner selection, no room candidate, no accepted room, no catalog admission,
  no generative-map metadata record.
- No connectivity or opening claimed; the seed is an outdoor statue shot, not a bounded interior.
- `registration_accepted` and `scale_calibrated` remain `false`.
- Hash-pinned files (`scripts/player.gd`, `project.godot`, library room scenes, `catalog.json`,
  `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`) were not touched.

## Blocker / decision needed

The guard's named-job scan must not treat the worker's own controller processes — whose command
lines necessarily embed the task prompt — as blocking jobs. A human decision is needed on how to
run the next (still first) attempt: e.g. supply the worker its direction by a mechanism that does
not place the restricted word in a process command line, or whitelist the loop plugin and its
`opencode` worker in `_active_named_jobs`. The attempt cap is untouched (0 / 3), so no inference
budget was spent.
