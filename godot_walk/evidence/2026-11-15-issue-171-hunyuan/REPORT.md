# Issue #171 — Hunyuan Panogen attempt 1 (blocked at preflight)

Date: 2026-11-15 (UTC)
Source: `video-c9115d943f6c3fe4` — `data/videos/Backrooms - Found Footage #55 (Hills of Synthetic Verdure).mp4`
Source SHA-256: `c9115d943f6c3fe46fbe79b826c8c76e6378c8339736ae885e7a5a3d21ee9fae`
Manifest: `source_manifest-v3.json`, SHA-256 `ae6eee3881e287d56b2a2ba65881daff635a0e906b5c1d7eb1a701a87f4a433e`
Seed: `frame_3357`, 139.973 s, SHA-256 `b1846b7aff1252e93130d388f75e7fd3b017b8d141d70fb5936763137e96b2b8`
Authorization: operator decision comment 2026-11-15 (issue #171), one attempt on the local GPU.

## Result

**Blocked at GPU preflight. No panorama was produced.** The model was never loaded and no
diffusion process was started.

- Attempt id: `attempt-001`
- Run id: `run-640d4c9f201c41f29d0974abfae71fe3`
- Runtime seconds: 0 (the runner refused before `run_source_panogen.py` was invoked)
- Ledger event: sequence 8, `hunyuan_preflight_blocked`, occurred `2026-11-15T23:18:49.117115+00:00`
- Attempts used after the block: 0 / 3
- `can_start_attempt`: false; `next_worker_actions`: `["manual-fallback"]`
- `manual-fallback` was **not** run. No feedback was run. No second attempt was made.

Command (runner defaults: 512x256, seed 42, timeout 2700 s, `sequential_cpu` offload):

```bash
python3 godot_walk/scripts/run_source_hunyuan.py video-c9115d943f6c3fe4 --prompt "<prompt below>"
```

## Exact error

From `godot_walk/source_library/sources/video-c9115d943f6c3fe4/hunyuan/attempt-001/gpu_guard.json`:

```text
GPU preflight blocked by active job(s): 4096426   11324 bash            /bin/bash -c source /home/goya/.claude/shell-snapshots/snapshot-bash-1794385857562-3tkk2w.sh 2>/dev/null || true && shopt -u extglob 2>/dev/null || true && { \builtin unalias -- 'which'; \builtin unset -f -- 'which'; } >/dev/null 2>&1 || true && { \builtin unalias -- 'unsetenv'; \builtin unset -f -- 'unsetenv'; } >/dev/null 2>&1 || true && eval 'L=/home/goya/.local/share/opencode-loop-plugin/chainlink-runs/run_mwig5rij_jfc2m5az.log; for i in $(seq 1 58); do if grep -q "status: " $L; then break; fi; sleep 10; done; tail -n 4 $L | cut -c1-300; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader; ls /mnt/sharedOs/backrooms-workspace/godot_walk/source_library/sources/video-c9115d943f6c3fe4/hunyuan 2>&1 | head' < /dev/null && pwd -P >| /tmp/claude-5989-cwd, 4117176 4117174 tee             tee /tmp/opencode/issue171-hunyuan-run.log
```

## What the preflight matched

`psx_design_round_resources._active_named_jobs()` rejects any process whose command line
matches `hunyuan|hunyuanworld|qemu-system|qemu`, excluding only that process's own ancestors.
Two processes matched:

| PID | Process | Why it matched | GPU job? |
| --- | --- | --- | --- |
| 4096426 | Chainlink runner monitor shell | its `ls .../video-c9115d943f6c3fe4/hunyuan` argument contains the word `hunyuan` | no |
| 4117176 | `tee /tmp/opencode/issue171-hunyuan-run.log` | the log filename contains `hunyuan` | no |

Both are text/logging processes from this run's own harness. Neither was using the GPU:
`nvidia-smi` reported 869–974 MiB used of 12,282 MiB at the time. This is a process-name
false positive, not a real concurrent inference job.

## Independent memory condition

The block above happened before the RAM check, but the host also does not currently meet the
guard's start threshold:

- `MemAvailable`: 21.4–23.2 GiB sampled around the run and at report time
- guard `min_start_ram_bytes`: 32 GiB (`source_ingestion_resource_guard.py`)
- `SwapFree`: ~85.8 GiB (minimum 16 GiB) — fine
- GPU free: ~10.6–10.9 GiB (minimum 8 GiB) — fine

So even with the process-name false positive removed, `check_start_limits` would refuse this
attempt on host RAM. `/proc/spl/kstat/zfs/arcstats` reports a 26.2 GiB ZFS ARC, which the
`MemAvailable` figure does not credit as reclaimable headroom. That may explain part of the
gap; it was observed, not altered, and the guard was not bypassed or edited.

## Outputs

| Path | SHA-256 |
| --- | --- |
| `godot_walk/source_library/sources/video-c9115d943f6c3fe4/hunyuan/attempt-001/attempt_config.json` | `5b3e7d2b2465289e34094bfff3bc8e0a8984dc3914d8e8517d758b2b76790e66` |
| `godot_walk/source_library/sources/video-c9115d943f6c3fe4/hunyuan/attempt-001/gpu_guard.json` | `996dab859fc1b847e3e61ed90349242622fc847f0461b20abe1b1834010fd3cb` |

There is no `hunyuan/attempt-001/panorama/` directory, no panorama PNG, and no preview
render. The `hunyuan_panorama_preview.gd` script was not run because there is nothing to
preview.

## Prompt

Exactly as passed to the runner:

> An enclosed single-level room with warm wooden plank walls and a matching plank ceiling, dark red carpet covering the floor, two white sash windows in the far wall showing green grass outside, two simple light wooden chairs against the wall, daylight falling through the windows. Keep a coherent single-level interior with continuous wall, floor and ceiling; no people, text, signage, or additional objects.

Settings recorded in `attempt_config.json`: 512x256, diffusion seed 42, `sequential_cpu`,
timeout 2700 s, `true_cfg_scale` 1.0, `fov_degrees` 80.0, VAE tiling on, fp8 attention and
GEMM on.

## Seed frame and panorama comparison

No panorama exists, so seams, drift, duplicated geometry and invented objects cannot be
assessed. For the record, the seed is a direct 1280x720 decode (no crop, no edit) of an
enclosed room with wooden plank walls and ceiling, dark red carpet, two white sash windows
showing green grass, and two light wooden chairs. The VHS scanlines and black side bars in
the frame were deliberately not described in the prompt.

## Boundary

- No `feedback`, no second attempt, no `select-seed`/`select-winner`, no room candidate.
- No room accepted, no catalog module admitted, no connectivity inferred.
- Hash-pinned files were not touched.
- `registration_accepted = false` and `scale_calibrated = false` remain unchanged.
- `register_video_sources.py validate` still reports valid (13 sources).

## Retry mechanics for the operator

`attempt-001/` now exists with a blocked receipt. A later Hunyuan run needs an operator
`hunyuan_preflight_retry_approved` event naming a fresh attempt id (as was done for
`video-ccf9722164a0bdc8/attempt-004-retry-001`); otherwise the runner would try to create
`attempt-001/` again and fail. The source's three-attempt budget is untouched.
