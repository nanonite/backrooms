# Issue #171 — Hunyuan Panogen attempt-001-retry-001 (blocked at GPU preflight)

Date: 2026-11-16 (UTC)
Source: `video-c9115d943f6c3fe4` — `data/videos/Backrooms - Found Footage #55 (Hills of Synthetic Verdure).mp4`
Source SHA-256: `c9115d943f6c3fe46fbe79b826c8c76e6378c8339736ae885e7a5a3d21ee9fae`
Manifest: `source_manifest-v3.json`, SHA-256 `ae6eee3881e287d56b2a2ba65881daff635a0e906b5c1d7eb1a701a87f4a433e`
Seed: `frame_3357`, 139.973 s, SHA-256 `b1846b7aff1252e93130d388f75e7fd3b017b8d141d70fb5936763137e96b2b8`
Authorization: operator decision 2026-11-15 (issue #171) — one attempt on the local GPU; preflight retry
authorized for `attempt-001-retry-001` (issue #171 decision, 2026-11-16 02:14 UTC; ledger sequence 9).

## Result

**Blocked at GPU preflight again. No panorama was produced.** The model was never loaded, the Panogen
script never started, and no diffusion process ran.

- Attempt id: `attempt-001-retry-001`
- Run id: `run-ec9878f027f14878b58c9b2f279a6289`
- Runtime seconds: 0 (the runner refused before `run_source_panogen.py` was invoked; total wall clock
  from launch to refusal was about 1 s)
- Ledger event: sequence 10, `hunyuan_preflight_blocked`, occurred `2026-11-16T02:20:08.373665+00:00`,
  bound to the manifest hash above
- Attempts used after the block: 0 / 3 (a preflight block does not consume the budget)
- `can_start_attempt`: false; `next_worker_actions`: `["manual-fallback"]`
- `manual-fallback` was **not** run. No feedback was run. No second attempt was made.

Command (runner defaults: 512x256, seed 42, timeout 2700 s, `sequential_cpu` offload):

```bash
python3 godot_walk/scripts/run_source_hunyuan.py video-c9115d943f6c3fe4 --prompt "<prompt below>" \
  > /tmp/issue171-run.log 2>&1
```

The launcher waited for a moment when no unrelated process command line contained the guard's name
pattern, then started the runner directly (no `tee`, no sibling wrapper, no polling process). The log
file name contains no matched word.

## Exact error

From `godot_walk/source_library/sources/video-c9115d943f6c3fe4/hunyuan/attempt-001-retry-001/gpu_guard.json`:

```text
GPU preflight blocked by active GPU process(es): pid=28826 type=G command=gnome-text-editor
```

`preflight_details.snapshot` and `preflight_details.resource_policy` are `null`: the block came from
`psx_design_round_resources.check_capture_headroom()` before the resource snapshot was taken.

## What passed and what failed

`check_capture_headroom()` runs its checks in order; the failure is the second one.

| Step | Check | Result |
| --- | --- | --- |
| 1 | `_active_named_jobs()` — no unrelated process name/command line matching `hunyuan`/`qemu` | **passed** (empty; the attempt-001 false positives were absent) |
| 2 | `_active_gpu_jobs()` — every `nvidia-smi pmon` row must be `type=G` and on the desktop allowlist | **failed** on `pid=28826 gnome-text-editor` |
| 3 | `_compute_apps()` — no other compute process | would pass (empty) |
| 4 | RAM / VRAM headroom | would pass (see below) |

Read-only re-check at `2026-11-16T02:21:41Z`, after the block:

```
active_named_jobs: []
active_gpu_jobs: ['pid=28826 type=G command=gnome-text-editor']
compute_apps: []
check_start_limits: PASS
```

The re-check called the guard's own functions; it did not start, retry or authorize an attempt.

## Why this is a false positive, again

`nvidia-smi pmon` at the same moment:

```text
# gpu         pid   type     sm    mem    enc    dec    jpg    ofa    command
    0       5672     G      -      -      -      -      -      -    Xorg
    0       5848     G      0      7      -      -      -      -    gnome-shell
    0       6821     G      -      -      -      -      -      -    kitty
    0       8347     G      -      -      -      -      -      -    kitty
    0      10246     G      -      -      -      -      -      -    kitty
    0      28826     G      -      -      -      -      -      -    gnome-text-edit
    0     528794     G      -      -      -      -      -      -    kitty
    0    1817747     G      -      -      -      -      -      -    firefox
    0    2751161     G      -      -      -      -      -      -    kitty
    0    4123114     G      -      -      -      -      -      -    kitty
```

- PID 28826 is `/usr/bin/gnome-text-editor /home/goya/Desktop/opencode-chainlink-loop-prompt.txt`, an
  open desktop text editor. It holds a **graphics** context (`type=G`), `sm` is `-` (0 %), and
  `nvidia-smi --query-compute-apps` is empty: it is not a compute job.
- `GPU_DESKTOP_PROCESS_ALLOWLIST` in `psx_design_round_resources.py` lists `xorg`, `gnome-shell`,
  `kitty`, `firefox`, `code`, `discord`, `nautilus`, `obsidian`, `kicad`, … but not
  `gnome-text-editor`, so `_active_gpu_jobs()` flags it. Any desktop application that keeps a
  graphics context and is missing from that list blocks the preflight.
- Unlike attempt-001, the process-name check did **not** fire: the runner's own ancestors are excluded
  and no unrelated process carried the matched word during the preflight.

## Resource state (the ARC change worked)

Measured at the re-check, the first preflight where reclaimable ZFS ARC counted:

- `ram_available_bytes` = 51,206,931,984 (47.7 GiB) = `MemAvailable` 23,924,633,600 (22.3 GiB) +
  `zfs_arc_reclaimable_bytes` 27,282,298,384 (25.4 GiB)
- `swap_free_bytes` = 92,640,808,960 (86.3 GiB), minimum 16 GiB
- `gpu_free_bytes` = 11,463,032,832 (10.7 GiB), minimum 8 GiB; `gpu_used_bytes` = 982,515,712 (0.9 GiB)
  of 12,878,610,432 (12.0 GiB)
- `check_start_limits` → **PASS** (policy `hunyuan-sequential-offload-3`, 32 GiB start threshold)

So the ARC credit fixed the RAM condition; this run was stopped by the separate GPU-process allowlist.

## Outputs

| Path | SHA-256 |
| --- | --- |
| `godot_walk/source_library/sources/video-c9115d943f6c3fe4/hunyuan/attempt-001-retry-001/attempt_config.json` | `90435fe8d97fc426fca77ef0cffecdce51a4a1cc5fb40d8f08da5927aa985013` |
| `godot_walk/source_library/sources/video-c9115d943f6c3fe4/hunyuan/attempt-001-retry-001/gpu_guard.json` | `7c11b570b224b66d1d87c54f2d7f8ebcf19f96986506c2b238bf3015b6aeed04` |
| `godot_walk/source_library/sources/video-c9115d943f6c3fe4/events.jsonl` (10 events, newest is sequence 10) | `98736ac70985398e48b6b76aeb0bed6a2e16493bb9c9d805ed7582b40a78f240` |

There is no `panorama/` directory, no `panorama.png`, no `resource_samples.jsonl` and no execution
guard receipt. `hunyuan_panorama_preview.gd` was not run because there is nothing to preview.

Recorded settings in `attempt_config.json`: 512x256, diffusion seed 42, `sequential_cpu` offload,
timeout 2700 s, `true_cfg_scale` 1.0, `fov_degrees` 80.0, VAE tiling on, fp8 attention and GEMM on,
cache disabled.

## Prompt

Exactly as passed to the runner (also stored verbatim in `attempt_config.json`):

> An enclosed single-level room with warm horizontal wooden-plank walls and a matching plank ceiling,
> a dark red carpet covering the floor, two white sash windows in the far wall showing green grass
> outside, two simple light wooden chairs standing against the right wall, daylight falling through
> the windows onto the carpet. Keep a coherent single-level interior with continuous wall, floor and
> ceiling lines; no people, no text, no signage, no additional objects.

The seed frame was not cropped, edited or replaced; it stayed `frame_3357` from the `issue171-16s-a`
direct-source set. The VHS scanlines and the black side bars in the frame were deliberately not
described.

## Seed frame and panorama comparison

No panorama exists, so seams, drift, duplicated geometry, lighting drift and invented objects cannot
be assessed. For the record, the seed is an enclosed room with horizontal warm wooden-plank walls and
a plank ceiling, a dark red carpet, two white sash windows in the far wall showing green grass, and
two light wooden chairs against the right-hand wall, with daylight patches on the carpet.

## Boundary

- No `feedback`, no second attempt, no further retry, no `manual-fallback`.
- No `select-seed`/`select-winner`, no room candidate, no room accepted, no catalog module admitted.
- No connectivity or opening inferred.
- Hash-pinned files (`godot_walk/scripts/player.gd`, `project.godot`, library room scenes,
  `catalog.json`, `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`) were not touched.
- `registration_accepted = false` and `scale_calibrated = false` remain unchanged.
- The guard, GPU lock, attempt cap and guard policy were not bypassed, retried or edited.

## What a further attempt would need from the operator

1. **The GPU-process allowlist.** `gnome-text-editor` (or desktop apps in general) needs either to be
   added to `GPU_DESKTOP_PROCESS_ALLOWLIST`, or the rule needs to ignore `type=G` rows that have
   `sm`/`mem` at `-` and no compute context. Either change is a policy edit, so it belongs to the
   operator and was not made here.
2. **A second retry authorization.** `_preflight_retry_authorization()` in
   `godot_walk/scripts/source_ingestion_policy.py` accepts exactly one
   `hunyuan_preflight_retry_approved` event per source and raises `WorkflowGateError` on a second one,
   so the current policy does not allow `attempt-001-retry-002` at all.
3. **A fresh attempt id.** `hunyuan/attempt-001-retry-001/` now exists with a blocked receipt and
   `_create_attempt_dir()` uses `mkdir()` without `exist_ok`, so rerunning under the same id fails.
   The retry id is also not consumed by a start event (`hunyuan_attempt_started` was never recorded),
   so `_next_attempt_id()` would hand back the same id.

The three-attempt budget is untouched at 0 / 3.
