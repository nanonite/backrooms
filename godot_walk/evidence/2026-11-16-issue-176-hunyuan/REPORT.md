# Issue #176 — Hunyuan attempt-001 blocked at GPU preflight (no panorama produced)

Date: 2026-11-16 (UTC)
Source: `video-2671b32f256a4ee7` — `data/videos/corridor_t.mp4`
Source SHA-256: `2671b32f256a4ee7f326fae67290bcec2143efabb4f1000fc4bcfa9507260409`
Manifest: `source_manifest-v3.json`, SHA-256 `101159bf8200611ef994a1f5b8ba5f4eaa86ff839972128150eb15e1a16245ae`
Authorization: operator decision 2026-11-16 (issue #176, comment 600) — one guarded attempt, local GPU, no USD ceiling.
Seed: `frame_0096`, index 95, 3.9583 s, SHA-256 `39442f1ae81cea1cd0eef682a99ca7c8030a6e72824be7626e34188be7cb3d75`
(unedited direct-source decode, 1920x1080). Not cropped, edited or replaced.

## Result

**The single authorized launch did not start inference. The runner's GPU preflight blocked the attempt before any model call. No panorama was produced.**

- Attempt id (allocated by the runner, never started): `attempt-001`
- Preflight checked at: `2026-11-16T18:45:42.017613+00:00`
- Event: sequence 6, `hunyuan_preflight_blocked`, at `2026-11-16T18:45:42.094720+00:00`
- `attempts_used` after this run: **0 / 3** — no attempt was consumed
- Post-run `status`: `stopped_reason` = "GPU resource preflight blocked: …" (verbatim below),
  `can_start_attempt` false, `awaiting_feedback` false, `manual_fallback_allowed` true,
  `next_worker_actions` `["manual-fallback"]`
- Runtime / peak RAM / peak VRAM: **not applicable** — no inference ran, no guard sampler started.
  There is no `attempt_result.json`, `stdout.log`, `stderr.log` or `resource_samples.jsonl`.

Per the operator rule "If it fails, record the exact error and stop; no second attempt", no relaunch
was made. `manual-fallback`, `feedback`, a second attempt, winner selection, room acceptance and
catalog admission were all deliberately not run, even though `status` now offers `manual-fallback`.

## Exact error

Verbatim `reason` field (shared by `/tmp/issue176-run.log`, event 6 in `events.jsonl` and
`gpu_guard.json`). The two matched `ps` lines are quoted in full up to the point where each
process's command line becomes this task's own prompt text; that prompt text (which is what trips
the guard's name scan) is stored unabridged in those three artifacts:

```
GPU preflight blocked by active job(s):
2453891  3098  bun  /home/goya/.bun/bin/bun /home/goya/storage/opencode-chainlink-loop-plugin/bin/chainlink-loop --task 174,175,176,177,178 ... --prompt The current task issue (take its number N from the task you were given), ONE guarded Hunyuan Panogen attempt for its source ...
2573738  2453891  opencode  opencode run --standalone --auto --format json --agent build --model opencode/hy4-flash-free --title Chainlink 176 worker You are the worker agent for Chainlink task 176, workflow chainlink_e3kmz, attempt 1/2. ...
```

First line of the runner's own stdout: `{"status": "blocked", "source_id": "video-2671b32f256a4ee7", "attempt_id": "attempt-001", ...}`.

## Why the preflight blocked (infrastructure, not resource exhaustion)

- The launch used the exact operator-prescribed detached command, with runner defaults
  (512x256, seed 42, 2700 s, `sequential_cpu` offload, offline cache), a plain redirect, no pipe or
  tee, and a prompt/log file name without the restricted word:
  `setsid nohup python3 godot_walk/scripts/run_source_hunyuan.py video-2671b32f256a4ee7 --prompt "$(cat /tmp/opencode/issue176-prompt.txt)" > /tmp/issue176-run.log 2>&1 < /dev/null &`
- `_active_named_jobs()` in `godot_walk/scripts/psx_design_round_resources.py` scans
  `ps -eo pid=,ppid=,comm=,args=` and skips only PIDs in `_ancestor_pids()` of the guard process.
  The launching shell exits as soon as the background `&` job is spawned, so the detached runner is
  reparented away from the harness. PIDs 2453891 (chainlink-loop) and 2573738 (this worker's
  `opencode run`) then no longer appear as ancestors; their command lines carry this task's prompt,
  which contains the restricted word, so they matched the guard regex and were classified as
  unrelated active jobs. This is a shared-harness classification issue, not a model, GPU or budget
  failure: `nvidia-smi --query-compute-apps` was empty before launch, no GPU lock was acquired, no
  start snapshot or execution guard was written, and no model call was made.

## Prompt (written from the seed only; never sent to a model)

51 words; derived only from the seed frame's materials, floor, ceiling, setting and partitions.
No watermark, letterbox bar or video glitch was described; no object was invented.

> An indoor corridor with golden-yellow carpet floor and a white suspended grid ceiling with bright rectangular fluorescent panels. Large freestanding partitions are covered in yellow-green wallpaper with chevron stripes and light trim, receding into the distance. One continuous interior with unbroken lines; no windows, people, text, signage, furniture or added objects.

## Outputs and receipts (all written by the runner, none by hand)

| Path | SHA-256 | Note |
| --- | --- | --- |
| `…/hunyuan/attempt-001/attempt_config.json` | `9107d2610195a934a4e1cb554f1381eda81e793cefa25e70e121c5537ff85d16` | config recorded before preflight |
| `…/hunyuan/attempt-001/gpu_guard.json` | `f897ed90ee4d7f3baba7650fe3e6b458f0d9f6e26fb7188aefb0ed4de5e4ec62` | `status: blocked` receipt |
| `…/events.jsonl` (event 6) | `a78c3cc55ec06ffd7df2de28da382d1ac8cf64d8e834e04a259fe2165d1a0a23` | append-only, bound to the current manifest hash |

Worker-side, not in the repo: `/tmp/issue176-run.log` (`f897ed90…4ec62`),
`/tmp/opencode/issue176-prompt.txt` (`ed3daccc…62a41`), `/tmp/opencode/issue176_watch.py`
(polling observer, never reached a running attempt). No panorama directory was created.

## Checks after the block

- `python3 godot_walk/scripts/source_ingestion_runner.py status video-2671b32f256a4ee7` — see result above.
- `python3 godot_walk/scripts/register_video_sources.py validate` → `{"valid": true, "registered_count": 13}`.
- `python3 -m pytest -q godot_walk/scripts/test_source_ingestion_preflight.py godot_walk/scripts/test_psx_design_round_resources.py` → `11 passed`.
- `registration_accepted=false` and `scale_calibrated=false` unchanged in `source_manifest-v3.json`.
- No hash-pinned file was touched (`scripts/player.gd`, `project.godot`, library room scenes,
  `catalog.json`, `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`).

## Escalation

This needs a human decision: the approved attempt was blocked by the preflight's ancestor-based
named-job scan in this multi-agent harness, with `attempts_used` still 0. The operator must decide
how to run the one authorized attempt so that the guard does not classify the harness/plugin
processes as unrelated jobs (or otherwise authorize the next step). No second attempt was made.
