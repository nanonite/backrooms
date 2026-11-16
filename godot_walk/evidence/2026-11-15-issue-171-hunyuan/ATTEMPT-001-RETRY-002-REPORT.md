# Issue #171 — Hunyuan Panogen attempt-001-retry-002 (started, failed on missing SageAttention)

Date: 2026-11-16 (UTC)
Source: `video-c9115d943f6c3fe4` — `data/videos/Backrooms - Found Footage #55 (Hills of Synthetic Verdure).mp4`
Source SHA-256: `c9115d943f6c3fe46fbe79b826c8c76e6378c8339736ae885e7a5a3d21ee9fae`
Manifest: `source_manifest-v3.json`, SHA-256 `ae6eee3881e287d56b2a2ba65881daff635a0e906b5c1d7eb1a701a87f4a433e`
Seed: `frame_3357`, 139.973 s, SHA-256 `b1846b7aff1252e93130d388f75e7fd3b017b8d141d70fb5936763137e96b2b8`
Authorization: operator decision 2026-11-15 (issue #171, comment 593) — preflight retry
`attempt-001-retry-002` authorized after #253 and guard policy 3; ledger sequence 11
(`hunyuan_preflight_retry_approved`).

## Result

**The attempt started and failed. No panorama was produced.**

This was the first #171 attempt to get past preflight: the #253 graphics-row change and the
ARC-credited RAM policy both behaved as designed, the GPU lock was taken, the guard receipt was
written, and `hunyuan_attempt_started` was recorded. The Panogen process then loaded the pipeline,
quantized the transformer to fp8 (1279 modules), entered the first denoising step and died with a
`NameError` in the upstream fp8 attention processor after **74.055 s**.

- Attempt id: `attempt-001-retry-002`
- Run id: `run-213ab159c4724cdb9c0b4006e39ebd55`
- Runtime seconds: 74.055 (started `2026-11-16T05:00:33Z`, finished `2026-11-16T05:01:47Z`)
- Attempts used after this run: **1 / 3** (a started inference consumes budget)
- Status: `attempts_used` 1, `awaiting_feedback` true, `can_start_attempt` false,
  `next_worker_actions` `["feedback"]`
- `feedback` was **not** run. No second attempt was made. `manual-fallback` was not run.

Command (runner defaults: 512x256, diffusion seed 42, timeout 2700 s, `sequential_cpu` offload):

```bash
python3 godot_walk/scripts/run_source_hunyuan.py video-c9115d943f6c3fe4 --prompt "<prompt below>" \
  > /tmp/issue171-run.log 2>&1
```

Plain redirect, no `tee`, no sibling wrapper, and no polling process whose command line carried
the guard's name pattern while the preflight ran.

## Exact failure

From `stderr.log` (traceback shortened to the frames that matter):

```text
Loading pipeline components...: 100%|██████████| 7/7 [00:01<00:00,  4.18it/s]
No LoRA keys associated to CLIPTextModel found with the prefix='text_encoder'. ...
Quantizing weights to fp8: 100%|██████████| 1279/1279 [00:19<00:00, 65.55it/s]
Token indices sequence length is longer than the specified maximum sequence length for this model (125 > 77).
CLIP truncated input (max_length=77): ['soft bright patches on the red carpet. keep one coherent interior
with continuous wall, floor and ceiling lines ; no people, no text, no signage, no additional objects.,
high - quality, high - resolution, sharp, clear, 8 k']
  0%|          | 0/50 [00:00<?, ?it/s]
Traceback (most recent call last):
  ...
  File ".../run_source_panogen.py", line 40, in main
    demo.run(
  File ".../HunyuanWorld-1.0/demo_panogen.py", line 214, in run
    image = self.pipe(
  File ".../HunyuanWorld-1.0/hy3dworld/models/pipelines.py", line 609, in _predict_noise
    return self.transformer(**transformer_inputs)[0]
  File ".../diffusers/models/attention_processor.py", line 605, in forward
    return self.processor(
  File ".../HunyuanWorld-1.0/hy3dworld/AngelSlim/attention_quantization_processor.py", line 94, in __call__
    hidden_states = sageattn(query, key, value, tensor_layout="HND", is_causal=False)
NameError: name 'sageattn' is not defined
```

`stdout.log` contains only the offload validation line:

```text
Validated Hunyuan offload dependencies: {'diffusers': '0.34.0', 'accelerate': '1.6.0', 'torch': '2.5.0', 'transformers': '4.51.0'}
```

No `panorama.png`, no partial image, no `panorama/` contents. `hunyuan_panorama_preview.gd` was not
run because there is nothing to preview.

## Cause

The pinned runtime has no `sageattention` package:

- `/mnt/sharedOs/backrooms-track-a-runtime/hunyuan-env/bin/python -c "import importlib.util as u; print(u.find_spec('sageattention'))"`
  prints `None`. `tools/hunyuan_runtime/pyproject.toml` and `uv.lock` do not mention it;
  `tools/hunyuan_runtime/README.md` lists `sageattention` under *deliberately not installed*.
  Upstream's own `docker/HunyuanWorld.yaml:206` pins `sageattention==1.0.6`, so the upstream image
  has it; the repo-side runtime lock is where it went missing.
- Upstream `hy3dworld/AngelSlim/attention_quantization_processor.py` lines 21-24 read
  `try: from sageattention import sageattn` / `except: pass`, so a missing package is swallowed at
  import time and only surfaces as `NameError` at the first attention call, line 94. There is no
  SDPA fallback in that processor.
- The ingestion path forces that processor on in two places:
  `source_ingestion_gpu.py:273-274` (`fp8_attention: True`, `fp8_gemm: True` in the diagnostic
  profile) and `source_ingestion_gpu.py:583-584` (always passes `--fp8-attention --fp8-gemm`).
  `run_source_panogen.py:94-95` refuses to run without both (`"The diagnostic profile requires both
  existing FP8 processors"`), so the profile cannot be narrowed from the command line.

So the #251 rebuild is complete for the four checked packages, offline cache reads and sequential
offload — the run proved all three — but its package list is missing a dependency that the
image-to-panorama path actually executes. The rebuild never ran generation, so this gap was not
observed there.

The fp8 **GEMM** path is not the problem: `FluxFp8GeMMProcessor` installed and quantized 1279
modules ("Quantizing weights to fp8"), and its linear projections ran in the first denoising step
before the attention call. Only the attention processor's `sageattn` call fails.

## What passed: GPU preflight, lock and resource guard

First #171 preflight to pass. Both #253 changes are visible in the receipts:

| Step | Check | Result |
| --- | --- | --- |
| 1 | `_active_named_jobs()` — no unrelated process matching the guard's name pattern | passed (empty) |
| 2 | `_gpu_process_scan()` — no compute context (`C`/`C+G`) outside this process group | passed; 9 graphics-only rows (`xorg`, `gnome-shell`, 6× `kitty`, `firefox`) recorded as `ignored_graphics_processes` |
| 3 | `_compute_apps()` | passed (empty) |
| 4 | `check_start_limits` — ARC-credited RAM, swap, VRAM | passed |

Policy in effect (`gpu_guard.json`): `guard_policy_version` `2.2.0`, `gpu_process_policy`
`"block compute contexts (type C or C+G); ignore graphics-only contexts"`. Resource policy
`hunyuan-sequential-offload-3`.

Start snapshot (`2026-11-16T05:00:33.049Z`):

- `ram_available_bytes` = 46,366,355,576 (43.18 GiB) = `MemAvailable` 15,077,007,360 (14.04 GiB) +
  `zfs_arc_reclaimable_bytes` 31,289,348,216 (29.14 GiB); threshold 32 GiB
- `swap_free_bytes` = 89,769,656,320 (83.60 GiB); threshold 16 GiB
- `gpu_free_bytes` = 11,640,242,176 (10.84 GiB) of 12,878,610,432 (11.99 GiB); threshold 8 GiB

The GPU lock was acquired without waiting and the execution guard recorded `status: passed` before
the child process started. No guard, lock, cap or policy was bypassed, retried or edited.

## Resources actually consumed

From `resource_samples.jsonl` (69 samples, one per second, `05:00:33.236Z` → `05:01:46.246Z`) and
`attempt_result.json`:

| Metric | Value |
| --- | --- |
| Peak process-group RSS | 27,473,936,384 bytes (25.59 GiB) — the fp8 model load |
| Peak GPU memory used | 1,455,423,488 bytes (1.36 GiB) |
| Minimum RAM available (ARC-credited) | 38,736,110,592 bytes (36.08 GiB); runtime floor 8 GiB |
| Minimum free swap | 71,414,935,552 bytes (66.51 GiB); runtime floor 16 GiB; growth 16.5 GiB of 64 GiB allowed |
| Minimum free VRAM | 10,990,125,056 bytes (10.24 GiB); runtime floor 2 GiB |
| `stop_reason` | `null` — the guard did not stop it; the process exited on its own |

The run never reached the memory-heavy part: only one denoising step was attempted and it failed
before attention returned. Sequential CPU offload was active (`DiffusionPipeline.enable_sequential_cpu_offload`,
`pipeline_cuda_move` false), and VRAM stayed at 1.36 GiB peak, so nothing suggests the 12 GiB card
would have been the limit at 512x256. This run cannot say what peak RAM a completed panorama needs.

## Ledger events

All three are bound to manifest `ae6eee3881e287d56b2a2ba65881daff635a0e906b5c1d7eb1a701a87f4a433e`.

| Sequence | Event | Occurred (UTC) | Payload summary |
| --- | --- | --- | --- |
| 12 | `hunyuan_guard_passed` | `2026-11-16T05:00:33.131318` | guard receipt SHA-256 `a3e978a9…d136` |
| 13 | `hunyuan_attempt_started` | `2026-11-16T05:00:33.322892` | config SHA-256 `c8fda7cf…b490b`, execution guard receipt `a4412ee9…e5c2` |
| 14 | `hunyuan_attempt_result` | `2026-11-16T05:01:47.510854` | `status: failed`, `return_code: 1`, `elapsed_seconds: 74.055`, `outputs: []` |

`events.jsonl` now has 14 events; event 1 (`source_registered`) still carries the predecessor
manifest hash, as recorded before this task.

## Outputs

| Path (under `godot_walk/source_library/sources/video-c9115d943f6c3fe4/hunyuan/attempt-001-retry-002/`) | SHA-256 |
| --- | --- |
| `attempt_config.json` | `c8fda7cfe68afab5d83440be89c14d09cef1942731e8fe8f9e08c5a0b41b490b` |
| `gpu_guard.json` | `a3e978a91346d27122feda21a1fadb3c5261a7dddbab7b1e48d43f7100b0d136` |
| `execution_guard.json` | `a4412ee997f7f0d53c3b9edcfac14b91374be9ddc4da929a40e9990471c7e5c2` |
| `attempt_result.json` | `8cf10ec1bcd3eb1592aabee5411230359d630bb9f85f149a795753aadd742434` |
| `resource_samples.jsonl` | `8cf964031ffa27f96ce5b17ea2859c281a8284235e6e6c0f5267720c270bf408` |
| `stdout.log` | `022e240a8a36eccb82cb85828e1adc60d43fb25bbee2e81d7ee363361654e718` |
| `stderr.log` | `b4c00869284cf54e41bc8f1303b3ff3dfd737249e616ad75e0be1c39a950f0e7` |
| `panorama/` | empty directory, no files |

`events.jsonl` SHA-256 after this attempt: `d194d17686eeb6581c86f9173329e8a7e5be14d9a1672d6ffc57a64de418ed94`.

The launcher's stdout/stderr redirect, `/tmp/issue171-run.log`, holds the JSON the runner printed and
is byte-identical to `attempt_result.json` (`8cf10ec1…742434`, 1239 bytes). It is outside the repo and
is not committed.

## Prompt

Exactly as passed to the runner (also stored verbatim in `attempt_config.json`):

> An enclosed single-level room with warm light-brown horizontal wooden-plank walls and a wooden
> plank ceiling, a dark red carpet covering the whole floor, two white sash windows set side by side
> in the far wall showing bright green grass outside, and two simple light wooden chairs with pale
> legs standing against the right-hand wall near the windows. Daylight falls through the windows in
> soft bright patches on the red carpet. Keep one coherent interior with continuous wall, floor and
> ceiling lines; no people, no text, no signage, no additional objects.

The seed was not cropped, edited or replaced. The VHS scanlines and black side bars were not
described.

**Prompt-length observation for a future attempt:** this prompt is 125 CLIP tokens and the
pipeline truncates at 77 (`CLIP truncated input (max_length=77)`). The encoder saw the room,
walls, carpet, windows, chairs and daylight clause; it did **not** see "keep one coherent interior
…, no people, no text, no signage, no additional objects" or the pipeline's own appended
"high-quality, high-resolution, sharp, clear, 8k" suffix. A shorter prompt would put the
constraints inside the window. No prompt change was made during this attempt.

## Seed frame and panorama comparison

No panorama exists, so seams, drift, duplicated geometry, lighting drift and invented objects
cannot be assessed. There is no rendered frame to compare with `frame_3357`.

For the record, the seed shows an enclosed single-level room with light warm horizontal
wooden-plank walls and a plank ceiling, a dark red carpet across the floor with bright
window-light patches, two white sash windows side by side in the far wall revealing green grass
outside, and two light wooden chairs against the right-hand wall near the windows. The frame is a
direct 1280x720 decode that also contains VHS glitch lines and black side bars, which were
deliberately not described.

## Boundary

- No `feedback`, no second attempt, no retry authorization requested, no `manual-fallback`.
- No `select-seed`/`select-winner`, no room candidate, no room accepted, no catalog module
  admitted, no generative-map metadata record.
- No connectivity, opening or room identity inferred from the video.
- Hash-pinned files (`godot_walk/scripts/player.gd`, `project.godot`, library room scenes,
  `catalog.json`, `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`) were not touched.
- `registration_accepted = false` and `scale_calibrated = false` are unchanged.
- The guard, GPU lock, attempt cap, guard policy and runtime pins were not bypassed, retried or
  edited. The pinned HunyuanWorld-1.0 checkout is untouched and still at
  `57fa9f3a79eae1079c279968cdb9d82c75fa7c86`.

## Checks

- `python3 godot_walk/scripts/register_video_sources.py validate` → valid, 13 sources.
- `python3 -m pytest -q godot_walk/scripts` → **1528 passed, 5 skipped, 67 subtests passed**.
  `test_source_ingestion_policy.RecordedHistoryReplayTests` replays this source's live ledger, so its
  assertion was updated from "0 used, stopped at the gnome-text-editor block" to "1 used, failed
  `attempt-001-retry-002`, awaiting feedback". No other test changed.
- `ruff check godot_walk/scripts/test_source_ingestion_policy.py` → clean. `black --check` on that
  file already reported pre-existing formatting drift before this change and was left alone apart
  from the edited test.
- `registration_accepted` and `scale_calibrated` are `false` in `source_manifest-v3.json`.

## What a further attempt needs from the operator

The failure is an environment dependency gap, not a policy block and not a resource problem, so the
next step is a decision about the runtime:

1. **Add `sageattention` to the pinned runtime** (`tools/hunyuan_runtime/pyproject.toml` +
   `uv.lock`; upstream's `docker/HunyuanWorld.yaml:206` pins `sageattention==1.0.6`) and rebuild the
   venv, treating it as a #251 follow-up. This keeps the fp8 profile exactly as authorized.
2. **Or authorize turning fp8 attention off** for the diagnostic profile. That is a policy change in
   `source_ingestion_gpu.py` (both the recorded settings and the CLI flags) and
   `run_source_panogen.py` (drop the "requires both processors" refusal), and it changes the memory
   profile the 512x256 diagnostic was designed around.

Either way the operator also decides whether the consumed attempt stays consumed: the ledger now
records 1 of 3 used, one attempt remains available before the cap, and no automatic retry was made.
