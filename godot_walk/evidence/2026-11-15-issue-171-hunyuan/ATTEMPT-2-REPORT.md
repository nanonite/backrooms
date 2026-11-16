# Issue #171 — Hunyuan Panogen attempt-002 (panorama produced)

Date: 2026-11-16 (UTC)
Source: `video-c9115d943f6c3fe4` — `data/videos/Backrooms - Found Footage #55 (Hills of Synthetic Verdure).mp4`
Source SHA-256: `c9115d943f6c3fe46fbe79b826c8c76e6378c8339736ae885e7a5a3d21ee9fae`
Manifest: `source_manifest-v3.json`, SHA-256 `ae6eee3881e287d56b2a2ba65881daff635a0e906b5c1d7eb1a701a87f4a433e`
Seed: `frame_3357`, 139.973 s, SHA-256 `b1846b7aff1252e93130d388f75e7fd3b017b8d141d70fb5936763137e96b2b8` (unedited direct decode)
Authorization: operator decision 2026-11-16 (issue #171, comment 595) — "Attempts used 1 of 3;
launching attempt 2 (run once, stop for operator review)". This is the second started inference.

## Result

**The attempt ran to completion and produced a 512x256 equirectangular panorama.** It is the first
#171 attempt to get past the first denoising step; the `sageattention==1.0.6` install (commit
`61ddbba`, #251 follow-up) fixed the `NameError` that killed `attempt-001-retry-002`.

- Attempt id: `attempt-002`
- Run id: `run-887116851f3140c88a62a6eac5c9c9e8`
- Started: `2026-11-16T05:57:50.257330Z` (event 17, `hunyuan_attempt_started`)
- Finished: `2026-11-16T06:02:25.137208Z` (observed process exit)
- Runtime: **274.88 s** (4 min 34.9 s) of the 2700 s budget
- Diffusers progress: fp8 quantization of 1279 modules, then denoising 50/50 steps in 3:18
  (2.58 s/it); `panorama.png` written at `06:02:12.836Z`
- `status`: `produced`; `return_code`: 0 (see the caveat below — inferred, not reaped by the runner)
- Attempts used after this run: **2 / 3**
- `awaiting_feedback`: true; `can_start_attempt`: false; `next_worker_actions`: `["feedback"]`

`feedback` was **not** run, no third attempt was made, and `manual-fallback` was not run. No winner
was selected, no room was accepted, no catalog module was admitted, and no connectivity was
inferred.

## Incident: the runner supervisor was killed when the worker turn ended

This is a process-anomaly account, not a model result, and it is reported in full because it
affects how the receipts were written.

- The attempt was launched from a background shell of the worker session with a plain redirect
  (`python3 godot_walk/scripts/run_source_hunyuan.py video-c9115d943f6c3fe4 --prompt "<prompt>" >
  /tmp/issue171-run2.log 2>&1`), no `tee`, no sibling wrapper. The preflight passed and the run
  started (`hunyuan_guard_passed`, `hunyuan_attempt_started`).
- The worker turn ended immediately after the launch. The agent harness killed the background
  shell and with it the `run_source_hunyuan.py` supervisor. Because
  `source_ingestion_process.run_guarded_process` starts the Panogen child with
  `start_new_session=True`, the child **survived as an orphan** (reparented to the user systemd,
  pid 906383) and kept running.
- Consequence: after ~05:58 UTC the runner's execution guard was gone. No runtime resource
  sampling, no 2700 s timeout enforcement and no automatic result receipt. The GPU start lock and
  start limits had already passed and were recorded; nothing was bypassed by choice.
- A manual observer (not committed; `/tmp/opencode/attempt2_watch.py`) held read handles on the
  child's unlinked stdout/stderr temp files, sampled the same metrics at 1 Hz, and mirrored the
  guard's runtime stop conditions (RAM/swap/VRAM floors, swap growth, external compute, 2700 s).
  None tripped. It captured the process output after exit.
- The `hunyuan_attempt_result` event (sequence 18), `attempt_result.json`, `stdout.log`,
  `stderr.log` and `resource_samples.manual.jsonl` were written by the worker from that captured
  data and the panorama hashes. Every reconstructed field is labelled:
  `payload.recording.supervisor = "lost"`, `return_code_source`, `elapsed_source`,
  `sampling_caveat`.

Operator note for the next run: launching the runner from a background shell is not survivable
across a worker turn boundary in this harness. The attempt itself was healthy; the infrastructure
around it was not.

## Preflight and start guard (passed)

`gpu_guard.json` (SHA-256 `c3f65862…131809`), policy `2.2.0`:

| Check | Result |
| --- | --- |
| named-job scan (`_active_named_jobs`) | passed (no unrelated process matched) |
| GPU process scan | passed; 9 graphics-only rows ignored (`xorg`, `gnome-shell`, 6× `kitty`, `firefox`), zero compute contexts |
| `nvidia-smi --query-compute-apps` | empty |
| start limits (ARC-credited RAM, swap, VRAM) | passed |

Start snapshot `2026-11-16T05:57:49.996Z`:

- `ram_available_bytes` = 48,097,174,576 (44.79 GiB) = `MemAvailable` 25,306,763,264 (23.57 GiB) +
  reclaimable ZFS ARC 22,790,411,312 (21.23 GiB); threshold 32 GiB
- `swap_free_bytes` = 85,084,995,584 (79.24 GiB); threshold 16 GiB
- `gpu_free_bytes` = 11,429,478,400 (10.64 GiB) of 12,878,610,432 (11.99 GiB); threshold 8 GiB

The GPU lock was acquired without waiting and `execution_guard.json` recorded `passed` at
`05:57:50.177Z` before the child started (SHA-256 `c4d5c6b2…3ccf9a`).

## Resources actually observed

The runner sampler was lost with the supervisor, so only the final 32 seconds
(`06:01:50.005Z` → `06:02:23.097Z`, 32 one-second samples) were observed:

| Metric | Observed value |
| --- | --- |
| Peak process-group RSS | 14,093,885,440 bytes (13.13 GiB) |
| Peak GPU memory used | 1,625,292,800 bytes (1.51 GiB) |
| Minimum credited RAM | 43,112,296,848 bytes (40.15 GiB); runtime floor 8 GiB |
| Minimum free swap | 58,924,163,072 bytes (54.88 GiB); runtime floor 16 GiB |
| Minimum free VRAM | 10,821,304,320 bytes (10.08 GiB); runtime floor 2 GiB |
| `stop_reason` | `null` — no stop condition tripped |

**Caveat:** the peaks cover the last 32 s only. The pipeline load / fp8 quantization peak (the
failed attempt reached 27.5 GB RSS at that stage in 74 s) was not sampled and is unknown here.
`resource_samples.manual.jsonl` is therefore named accordingly; it is not a runner guard file.

## Ledger events

All bound to manifest `ae6eee3881e287d56b2a2ba65881daff635a0e906b5c1d7eb1a701a87f4a433e`.

| Sequence | Event | Occurred (UTC) | Summary |
| --- | --- | --- | --- |
| 16 | `hunyuan_guard_passed` | `2026-11-16T05:57:50.075839` | `gpu_guard.json` receipt |
| 17 | `hunyuan_attempt_started` | `2026-11-16T05:57:50.257330` | attempt `attempt-002`, config + receipts |
| 18 | `hunyuan_attempt_result` | `2026-11-16T06:04:51.214307` | `produced`, 274.88 s, 1 output, supervisor-loss note |

`events.jsonl` now has 18 events; SHA-256
`49d7b12ef89ba60ac2dc79c5f5d84ab79bb6e71188d70302478e89dfeb32bb4c`.
Event 18 was written after the run from captured output (see the incident section); it is
append-only and bound to the current manifest hash like every other event.

Post-run `source_ingestion_runner.py status video-c9115d943f6c3fe4`: `source_decision` `proceed`,
`selected_seed` `frame_3357`, `attempts_used` 2, `attempt_limit` 3, `awaiting_feedback` true,
`can_start_attempt` false, `manual_fallback_allowed` false, `stopped_reason` null,
`next_worker_actions` `["feedback"]`.

## Outputs

| Path | SHA-256 |
| --- | --- |
| `…/hunyuan/attempt-002/panorama/panorama.png` (188,596 bytes, 512x256 RGB) | `52a7d84330caac26a89fd1cba81ae4c7687a33a579a07e4e56b1e8cfc578bcad` |
| `…/attempt-002/attempt_config.json` | `8775ecff5c5756066aef6660f2fdb389d8b5e4e016771b0949567f815bb374cb` |
| `…/attempt-002/gpu_guard.json` | `c3f6586252db91ba53aca9332e8bb30f2965e7c31cff0e0918f30a1077131809` |
| `…/attempt-002/execution_guard.json` | `c4d5c6b203ee5570f330737c2a444d2c7287b5d6530c7abb7da6c3c0ee3ccf9a` |
| `…/attempt-002/attempt_result.json` | `645b079e86202dad2482d43d50d14be7e4f541fb21d49f59e6489546c7af17e4` |
| `…/attempt-002/stdout.log` | `022e240a8a36eccb82cb85828e1adc60d43fb25bbee2e81d7ee363361654e718` |
| `…/attempt-002/stderr.log` | `a9aca4e29c64abfdebd5e057d33803b87c5eda7b2142b300816363ea270ae46e` |
| `…/attempt-002/resource_samples.manual.jsonl` | `c07a71d4eddf2f0bc9e492909dbde0cb4cb70f356a9c73e3a396f265d32dfbe2` |

`stdout.log` contains the offload validation line only. `stderr.log` contains the diffusers
progress bars, the LoRA warning, the CLIP truncation notice and no traceback. The pipeline
completed all 50 denoising steps and then wrote the PNG.

## Preview render

`hunyuan_panorama_preview.gd` (scene `godot_walk/scenes/hunyuan_panorama_preview.tscn`) was run in
the repository dev shell (the bare nix-store `godot` binary crashes on this host: Vulkan
`VK_KHR_surface` missing, GL fallback segfaults):

```bash
nix develop --command bash -c 'cd godot_walk &&
  HUNYUAN_PANORAMA_PATH="$PWD/source_library/sources/video-c9115d943f6c3fe4/hunyuan/attempt-002/panorama/panorama.png" \
  HUNYUAN_CAPTURE_DIR="$PWD/evidence/2026-11-15-issue-171-hunyuan/panorama-views" \
  timeout 180 godot4 --path . scenes/hunyuan_panorama_preview.tscn'
```

Exit 0, four yaw-bank views printed (`PANORAMA_VIEW: forward|right|back|left`) and written to
`godot_walk/evidence/2026-11-15-issue-171-hunyuan/panorama-views/`. Those PNGs are gitignored by
`.gitignore` (`godot_walk/evidence/**/*.png`) and are local review aids only.

## The panorama against the seed (honest description)

**What carried over.** The forward half of the equirect reproduces the prompt's composition: warm
light-brown plank walls, a dark red carpet, and two tall windows in the far wall with bright green
grass/foliage outside. The ceiling is panelled wood, the room is one continuous interior, and
there are no people, no text and no signage.

**Geometry drift.** The seed is a small enclosed room with two sash windows on one wall and two
chairs against the right-hand wall. The panorama turns it into a long, wide hall/gallery: window
bands run along both long walls and the rear wall (about a dozen window openings instead of two),
separated by pale wooden pilasters. The two far windows from the prompt end up small and narrow,
centred at the back, rather than filling the frame as they do in the seed. There is no visible
doorway; the space is closed by window walls.

**Invented content.** The side window walls and their greenery, the pilasters, the dark repeating
floral/medallion motif on the carpet (the seed carpet is plain red with only soft light patches),
and the taller, higher-contrast plank ceiling. The exterior is an invented continuation of the
green field seen through the seed's windows.

**Missing content.** The seed's two light wooden chairs are absent, as are the white sash bars:
the panorama's windows are plain dark-framed panes. The seed's VHS scanlines, black side bars and
heavy vignette are gone — expected, since the prompt did not describe them.

**Seams and projection.** The 2:1 wrap is smooth: the mean absolute difference between the first
and last pixel columns is 2.9 levels, below the 4.6-level average between adjacent columns, so
there is no hard cut. A window frame that crosses the wrap does show a slightly doubled mullion
if inspected closely. The equirect poles smear as usual: the ceiling planks fan out into a radial
starburst at the top edge and the carpet stretches at the bottom edge. Several window frames are
slightly wavy, and the 512x256 resolution leaves the result soft (the preview views are visibly
blurred when scaled to 1152x644).

**Exposure and colour.** The panorama is brighter and cleaner than the seed (mean luminance 46.7
against 33.6 over the seed's content area; 95th percentile 159 against 131), with saturated
greens outside and a red carpet that reads lighter than the seed's dark crimson. There is a
small grey dash floating in the sky near the right-hand trees (visible in the `back` view), and
the vegetation outside has soft, bulbous shapes. No structural holes or black voids.

This is a plausible, on-genre room, but it is a **reinterpretation** of the seed, not a
reconstruction: one two-window room became a multi-window hall, and the two chairs were lost.
Whether that is acceptable as a room candidate is the operator's call.

## Prompt (unchanged from attempt-001-retry-002)

The exact prompt from
`hunyuan/attempt-001-retry-002/attempt_config.json` was reused verbatim (SHA-256 of the prompt
string `fe2ff1a4f9f106808bff94e99baf384a97bcc01ad8f5d8eed844a40f0269b144`):

> An enclosed single-level room with warm light-brown horizontal wooden-plank walls and a wooden
> plank ceiling, a dark red carpet covering the whole floor, two white sash windows set side by
> side in the far wall showing bright green grass outside, and two simple light wooden chairs with
> pale legs standing against the right-hand wall near the windows. Daylight falls through the
> windows in soft bright patches on the red carpet. Keep one coherent interior with continuous
> wall, floor and ceiling lines; no people, no text, no signage, no additional objects.

**CLIP truncation (unchanged, as instructed):** the prompt is 125 CLIP tokens and the pipeline
truncates at 77; `stderr.log` again shows
`Token indices sequence length is longer than the specified maximum sequence length for this model (125 > 77)`
and `CLIP truncated input (max_length=77): ['soft bright patches … no additional objects., high - quality, …']`.
The text encoder therefore did not see the coherence/no-people/no-signage clause or the pipeline's
quality suffix. This matches the previous attempt and was not changed.

The seed was not cropped, edited or replaced; the VHS scanlines and black side bars were not
described to the model.

## What was not done

- No `feedback` event (operator review is pending).
- No third attempt, no `manual-fallback`, no prompt or seed change.
- No `select-winner`, no room candidate, no accepted room, no catalog admission.
- No connectivity or opening is claimed.
- `registration_accepted` and `scale_calibrated` remain `false` in every manifest.
- Hash-pinned files (`scripts/player.gd`, `project.godot`, library room scenes, `catalog.json`,
  `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`) were not touched.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py status video-c9115d943f6c3fe4
python3 godot_walk/scripts/register_video_sources.py validate
python3 -m pytest -q godot_walk/scripts
```

```bash
python3 godot_walk/scripts/run_source_hunyuan.py video-c9115d943f6c3fe4 --prompt "$(cat prompt.txt)" \
  > /tmp/issue171-run2.log 2>&1   # runner defaults: 512x256, seed 42, 2700 s, sequential_cpu
```
