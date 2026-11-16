# Issue #178 — Hunyuan Panogen attempt-001 (panorama produced)

Date: 2026-11-16 (UTC)
Source: `video-f657e9bc27813df8` — `data/videos/dead_end.mp4`
Source SHA-256: `f657e9bc27813df8759acf720d7dd57060320d18270acf80c15c42c7cc7f3770`
Manifest: `source_manifest-v3.json`, SHA-256 `ce413b916cca14a1c00bc898275e23e97a20c26be70890a9b2de0e3039fd7c7d`
Seed: `frame_0079`, index 78, 3.25 s, SHA-256 `df1c00ec7d6c4060815d8f252d2b5f5a4b51f444b59877d6fc87e24d0227b28b`
(unedited direct decode, 1920x1080)
Authorization: operator decision 2026-11-16 (issue #178, comment 602) — "Hunyuan attempt 1 of 3
approved for this source (local GPU, no USD ceiling) ... Run one attempt, then stop for operator
review; operator picks winners and admits rooms." This is the first started inference for this source.

## Result

**The single authorized attempt ran to completion and produced a 512x256 equirectangular panorama.**

- Attempt id: `attempt-001`
- Run id: `run-8be34062b4d84f75a9dce94dc4b72bad`
- Started: `2026-11-16T19:58:27.059215Z` (event 7, `hunyuan_attempt_started`)
- Result recorded: `2026-11-16T20:02:50.837717Z` (event 8, `hunyuan_attempt_result`)
- Runtime: **263.655 s** (4 min 23.7 s) of the 2700 s budget; `return_code` 0; `status` `produced`
- Diffusers progress: fp8 quantization of 1279 modules in ~19 s, then denoising 50/50 steps in
  3:05 at ~2.44 s/it
- Attempts used after this run: **1 / 3**
- `status`: `awaiting_feedback` true, `can_start_attempt` false, `manual_fallback_allowed` false,
  `stopped_reason` null, `next_worker_actions` `["feedback"]`

The supervisor survived the worker turn. The launch was detached with
`setsid nohup … < /dev/null &` and a plain redirect, so the runner stayed alive for the whole
attempt, reaped the Panogen child itself and wrote `attempt_result.json`, `resource_samples.jsonl`,
`stdout.log` and `stderr.log` normally. No receipt or ledger event was written by hand; the only
worker-side write was the polling observer (`/tmp/opencode/issue178_watch.py`, not committed),
which stopped as soon as the runner printed its result. Note that `awaiting_feedback` flips true at
attempt *start* (before any result), so the observer keyed completion on the runner's printed
result line, not on that flag.

`feedback` was **not** run, no second attempt was made, and `manual-fallback` was not run. No
winner was selected, no room was accepted, no catalog module was admitted, and no connectivity or
opening is claimed.

## Preflight and start guard (passed)

`gpu_guard.json` (SHA-256 `78569c0f…459c9`), policy `2.3.0`:

| Check | Result |
| --- | --- |
| named-job scan (`_active_named_jobs`) | passed — enforced as the first preflight check; not separately stored in the receipt, and the run proceeded |
| GPU process scan | passed; 9 graphics-only rows ignored (`xorg`, `gnome-shell`, 6× `kitty`, `firefox`, `code`), zero compute contexts |
| `nvidia-smi --query-compute-apps` | empty |
| start limits (ARC-credited RAM, swap, VRAM) | passed |

Start snapshot `2026-11-16T19:58:26.978487Z`:

- `ram_available_bytes` = 51,751,432,272 (48.21 GiB) = `MemAvailable` 21,293,846,528 (19.83 GiB) +
  reclaimable ZFS ARC 30,457,585,744 (28.36 GiB); threshold 32 GiB
- `swap_free_bytes` = 81,939,206,144 (76.32 GiB); threshold 16 GiB
- `gpu_free_bytes` = 11,443,109,888 (10.66 GiB) of 12,878,610,432 (11.99 GiB); threshold 8 GiB

The GPU lock was acquired without waiting and `execution_guard.json` recorded `passed` at
`19:58:26.978793Z` before the child started (SHA-256 `2ce26d54…94b5`).

## Resources actually observed

The runner sampler ran for the whole attempt: 246 one-second samples
(`resource_samples.jsonl`, SHA-256 `aed9884f…de7a`).

| Metric | Observed value |
| --- | --- |
| Peak process-group RSS | 23,793,762,304 bytes (22.16 GiB) |
| Peak GPU memory used | 1,714,421,760 bytes (1.60 GiB) |
| Minimum credited RAM | 38,407,134,688 bytes (35.77 GiB); runtime floor 8 GiB |
| Minimum free swap | 60,050,010,112 bytes (55.92 GiB); runtime floor 16 GiB |
| Minimum free VRAM | 10,732,175,360 bytes (9.99 GiB); runtime floor 2 GiB |
| `stop_reason` | `null` — no stop condition tripped |

The RAM peak occurred during the pipeline load / fp8 quantization stage. Nothing was bypassed or
retried; the GPU lock, RAM/VRAM/swap guard and 3-attempt cap were left intact.

## Ledger events

All bound to manifest `ce413b916cca14a1c00bc898275e23e97a20c26be70890a9b2de0e3039fd7c7d`.

| Sequence | Event | Occurred (UTC) | Summary |
| --- | --- | --- | --- |
| 6 | `hunyuan_guard_passed` | `2026-11-16T19:58:26.873311` | `gpu_guard.json` receipt |
| 7 | `hunyuan_attempt_started` | `2026-11-16T19:58:27.059215` | attempt `attempt-001`, config + receipts |
| 8 | `hunyuan_attempt_result` | `2026-11-16T20:02:50.837717` | `produced`, 263.655 s, 1 output |

`events.jsonl` now has 8 events; SHA-256
`d1e4f3253828014f9cef99e5a67424ea738ba300d7a5328870b538846c488ee4`.

Post-run `source_ingestion_runner.py status video-f657e9bc27813df8`: `source_decision` `proceed`,
`selected_seed` `frame_0079`, `attempts_used` 1, `attempt_limit` 3, `awaiting_feedback` true,
`can_start_attempt` false, `manual_fallback_allowed` false, `stopped_reason` null,
`next_worker_actions` `["feedback"]`.

## Outputs

| Path | SHA-256 |
| --- | --- |
| `…/hunyuan/attempt-001/panorama/panorama.png` (212,046 bytes, 512x256 RGB) | `40560a66494d5352505faf84169a7c23db8d0e21056ee1c29351a6ef524dab1d` |
| `…/attempt-001/attempt_config.json` | `3f7a03989f1502bedd455f1f853c59700cbf15d10c08b5059e12cbdec4c154f1` |
| `…/attempt-001/attempt_result.json` | `531ba8c3c82af7debb466967d0eb91579666f3200193816d0cb869143f7f900c` |
| `…/attempt-001/gpu_guard.json` | `78569c0fcc7f3527d7552ab8a3f1c86dfc22f6cfb2f766b456fd54cf903459c9` |
| `…/attempt-001/execution_guard.json` | `2ce26d54cf0cb38bc653cc34d6fb175efa670e163d77ca19f73be2bf978094b5` |
| `…/attempt-001/resource_samples.jsonl` | `aed9884fc15d949bc5b8eb728f7723409d355b1d4ed5f89d8b848d0f343ede7a` |
| `…/attempt-001/stdout.log` | `022e240a8a36eccb82cb85828e1adc60d43fb25bbee2e81d7ee363361654e718` |
| `…/attempt-001/stderr.log` | `46127a6c7cf6fdb6c27fbc87641f75b94a2a0c138e20cf6c25c9c6f848af7c3d` |

`stdout.log` contains the offload validation line only. `stderr.log` contains the diffusers
progress bars, the expected offline-cache message, the LoRA warning, the CLIP truncation notice
and no traceback.

## Prompt

Forty-seven words, derived only from what the selected seed shows. The seed was not cropped,
edited or replaced, and no glitch, letterbox bar or watermark was described (none are present in
the selected frame). SHA-256 of the prompt string:
`8eae7ffb45eb02b290f3b78a92ed8e893c1e50b0462326a9d04f57cbe40e5b78`.

> An empty indoor room with pale yellow-green chevron-patterned wallpaper, an amber-brown
> wooden-plank floor with a white baseboard, and a cream suspended ceiling of square acoustic
> tiles with thin dark grid lines. Warm yellow light. Continuous wall, floor and ceiling; no
> windows, no furniture, no people, no text.

**CLIP length:** the tokenizer reported
`Token indices sequence length is longer than the specified maximum sequence length for this model (82 > 77)`,
but the truncated tail is only the pipeline's own quality suffix
`CLIP truncated input (max_length=77): [', clear, 8 k']`. The prompt text itself fits inside the
77-token window — no part of the description was lost. The seed shows no windows or furniture, so
the prompt says so explicitly rather than inventing them.

## Preview render

`hunyuan_panorama_preview.gd` (scene `godot_walk/scenes/hunyuan_panorama_preview.tscn`) was run in
the repository dev shell:

```bash
nix develop --command bash -c 'cd godot_walk &&
  HUNYUAN_PANORAMA_PATH="$PWD/source_library/sources/video-f657e9bc27813df8/hunyuan/attempt-001/panorama/panorama.png" \
  HUNYUAN_CAPTURE_DIR="$PWD/evidence/2026-11-16-issue-178-hunyuan/panorama-views" \
  timeout 180 godot4 --path . scenes/hunyuan_panorama_preview.tscn'
```

Exit 0, four yaw-bank views printed (`PANORAMA_VIEW: forward|right|back|left`) and written to
`godot_walk/evidence/2026-11-16-issue-178-hunyuan/panorama-views/`. Those PNGs are gitignored by
`.gitignore` (`godot_walk/evidence/**/*.png`) and are local review aids only.

## The panorama against the seed (honest description)

**What carried over.** The palette is recognisably the seed's: pale yellow-green walls, an
amber-brown wooden floor, warm yellow light, and an empty interior with no people, no text, no
signage and no furniture. The forward preview reads as a plausible corner of the same kind of room:
a striated yellow-green wall above a thin white baseboard and a brown plank floor, with a warm
ceiling band across the top.

**Geometry drift.** The seed's wallpaper is a regular *vertical zigzag/chevron* repeat. The
panorama converts it into broad **concentric rings/contours radiating around a central dark oval**
— the equirect wraps the pattern into a target-like vortex, most obvious in the right/left views
and in the plan view of the raw panorama. The dark oval with a thin bright white rim is an invented
feature with no counterpart in the seed. It is a generation artifact, **not** an observed opening
or authored doorway; no connectivity is claimed. The seed's suspended ceiling grid (thin dark tile
lines) is gone — the ceiling becomes a smooth amber band — and the small wall outlet plate is lost.

**Invented content.** The oval void and its glowing rim, the concentric contour rings, and soft
vertical striations in place of the crisp chevrons. No watermark, letterbox bar or video glitch was
reproduced.

**Seams and projection.** Unlike #171/#172, the 2:1 wrap is *not* clean: the mean absolute
difference between the first and last pixel columns is 7.74 levels, above the 4.51-level average
between adjacent columns. The dark oval straddles the wrap, so the right and left preview views each
show half of its bright rim and there is a visible discontinuity at the seam. The equirect poles
smear as usual (rings fan out at the top edge and stretch at the bottom). Some ring edges are wavy.

**Exposure and colour.** The panorama is brighter and more washed-out than the seed: mean luminance
168.4 against 127.4, median 171.1 against 134.0, 95th percentile 184.8 against 153.2; channel means
R/G/B 184/173/82 against 148/129/48. The seed has more mid-tone contrast and a greener wall; the
panorama pushes everything toward a flat pale yellow.

**Resolution.** 512x256 is soft by design; the 1152x644 preview views are visibly blurred and the
concentric contours read as broad smears at close range.

This is an on-genre, palette-faithful reinterpretation, but it is not a reconstruction: the seed's
flat chevron wall became a ring vortex with an invented oval void, and the ceiling grid was lost.
The wrap seam is worse than the earlier attempts. Whether this is acceptable as a room candidate
for a non-box module is the operator's call.

## What was not done

- No `feedback` event (operator review is pending).
- No second attempt, no `manual-fallback`, no prompt or seed change. Attempts used: 1 / 3.
- No `select-winner`, no room candidate, no accepted room, no catalog admission, no generative-map
  metadata record.
- No connectivity or opening is claimed or inferred.
- `registration_accepted` and `scale_calibrated` remain `false` in the manifest;
  `register_video_sources.py validate` reports valid (13 sources).
- Hash-pinned files (`scripts/player.gd`, `project.godot`, library room scenes, `catalog.json`,
  `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`) were not touched.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py status video-f657e9bc27813df8
python3 godot_walk/scripts/register_video_sources.py validate
python3 -m pytest -q godot_walk/scripts
```

```bash
setsid nohup python3 godot_walk/scripts/run_source_hunyuan.py video-f657e9bc27813df8 \
  --prompt "$(cat /tmp/issue178-prompt.txt)" > /tmp/issue178-run.log 2>&1 < /dev/null &
# runner defaults: 512x256, seed 42, 2700 s, sequential_cpu
```
