# Issue #172 — Hunyuan Panogen attempt-001 (slot-canyon panorama produced)

Date: 2026-11-16 (UTC)
Source: `video-22909eb734e4d8e2` — `data/videos/Antelope Canyon in 4K - World's Most Iconic Slot Canyon - UHD 4K.mp4`
Source SHA-256: `22909eb734e4d8e2feede084e0305ae0aecefcc6dd5b46ca7ef884277e2a274a`
Manifest: `source_manifest-v3.json`, SHA-256 `1d3a4137c56a40949f178d8b295bb4087bc0bbb12f66aa27c6398156f1c03f83`
Seed: `frame_1363`, index 1362, 45.4454 s, SHA-256 `e500b55c57fdb74fc0186fedc5dff07ade81f9e3a84eba8a06f752ab06c6e28e`
(unedited direct decode, 1280x720)
Authorization: operator decision 2026-11-16 (issue #172, comment 596) — "Hunyuan attempt 1 of 3
approved for this source (local GPU, no USD ceiling); run one attempt, then stop for operator review".
This is the first started inference for this source.

## Result

**The single authorized attempt ran to completion and produced a 512x256 equirectangular panorama.**

- Attempt id: `attempt-001`
- Run id: `run-a4758ec5f40b4d099911aa9a0a560562`
- Started: `2026-11-16T16:00:48.518668Z` (event 7, `hunyuan_attempt_started`)
- Result recorded: `2026-11-16T16:05:11.377533Z` (event 8, `hunyuan_attempt_result`)
- Runtime: **262.738 s** (4 min 22.7 s) of the 2700 s budget; `return_code` 0; `status` `produced`
- Diffusers progress: fp8 quantization of 1279 modules in ~27 s, then denoising 50/50 steps in
  2:55 at ~2.39 s/it
- Attempts used after this run: **1 / 3**
- `status`: `awaiting_feedback` true, `can_start_attempt` false, `manual_fallback_allowed` false,
  `stopped_reason` null, `next_worker_actions` `["feedback"]`

The supervisor survived the worker turn this time. The launch was detached with
`setsid nohup … < /dev/null &` and a plain redirect, so the runner stayed alive for the whole
attempt, reaped the Panogen child itself and wrote `attempt_result.json`, `resource_samples.jsonl`,
`stdout.log` and `stderr.log` normally. No receipt or ledger event was written by hand; the only
worker-side write was the polling observer (`/tmp/opencode/issue172_watch.py`, not committed),
which stopped as soon as event 8 appeared.

`feedback` was **not** run, no second attempt was made, and `manual-fallback` was not run. No
winner was selected, no room was accepted, no catalog module was admitted, and no connectivity or
opening is claimed.

## Preflight and start guard (passed)

`gpu_guard.json` (SHA-256 `e039eb88…dd828`), policy `2.2.0`:

| Check | Result |
| --- | --- |
| named-job scan (`_active_named_jobs`) | passed (no unrelated process matched) |
| GPU process scan | passed; 9 graphics-only rows ignored (`xorg`, `gnome-shell`, 6× `kitty`, `firefox`), zero compute contexts |
| `nvidia-smi --query-compute-apps` | empty |
| start limits (ARC-credited RAM, swap, VRAM) | passed |

Start snapshot `2026-11-16T16:00:48.434748Z`:

- `ram_available_bytes` = 46,044,092,512 (42.88 GiB) = `MemAvailable` 20,245,905,408 (18.85 GiB) +
  reclaimable ZFS ARC 25,798,187,104 (24.03 GiB); threshold 32 GiB
- `swap_free_bytes` = 89,842,262,016 (83.67 GiB); threshold 16 GiB
- `gpu_free_bytes` = 11,526,995,968 (10.74 GiB) of 12,878,610,432 (11.99 GiB); threshold 8 GiB

The GPU lock was acquired without waiting and `execution_guard.json` recorded `passed` at
`16:00:48.435059Z` before the child started (SHA-256 `3ca87a01…03d2b`).

## Resources actually observed

The runner sampler ran for the whole attempt: 247 one-second samples
(`resource_samples.jsonl`, SHA-256 `cfc024a3…de7688`).

| Metric | Observed value |
| --- | --- |
| Peak process-group RSS | 22,315,532,288 bytes (20.78 GiB) |
| Peak GPU memory used | 1,678,770,176 bytes (1.56 GiB) |
| Minimum credited RAM | 41,033,299,232 bytes (38.22 GiB); runtime floor 8 GiB |
| Minimum free swap | 66,086,674,432 bytes (61.55 GiB); runtime floor 16 GiB |
| Minimum free VRAM | 10,767,826,944 bytes (10.03 GiB); runtime floor 2 GiB |
| `stop_reason` | `null` — no stop condition tripped |

The RAM peak (20.78 GiB) occurred during the pipeline load / fp8 quantization stage and is fully
sampled here; it is below the 40.13 GiB figure the previous supervisor-less run could not measure.

## Ledger events

All bound to manifest `1d3a4137c56a40949f178d8b295bb4087bc0bbb12f66aa27c6398156f1c03f83`.

| Sequence | Event | Occurred (UTC) | Summary |
| --- | --- | --- | --- |
| 6 | `hunyuan_guard_passed` | `2026-11-16T16:00:48.335116` | `gpu_guard.json` receipt |
| 7 | `hunyuan_attempt_started` | `2026-11-16T16:00:48.518668` | attempt `attempt-001`, config + receipts |
| 8 | `hunyuan_attempt_result` | `2026-11-16T16:05:11.377533` | `produced`, 262.738 s, 1 output |

`events.jsonl` now has 8 events; SHA-256
`a71efbe74b91ea6552213e7873d80d5b7882680d89a280db991fff7968e80fd4`.

Post-run `source_ingestion_runner.py status video-22909eb734e4d8e2`: `source_decision` `proceed`,
`selected_seed` `frame_1363`, `attempts_used` 1, `attempt_limit` 3, `awaiting_feedback` true,
`can_start_attempt` false, `manual_fallback_allowed` false, `stopped_reason` null,
`next_worker_actions` `["feedback"]`.

## Outputs

| Path | SHA-256 |
| --- | --- |
| `…/hunyuan/attempt-001/panorama/panorama.png` (200,955 bytes, 512x256 RGB) | `cbcecb1e3c1d20b9d59e11b44a7fbc5082796798653e8d14ab06a4ba5b27e23d` |
| `…/attempt-001/attempt_config.json` | `760193edbd5a2c581fbd24624e50eb78824bf7f882141b6f23d37c599594cb6e` |
| `…/attempt-001/attempt_result.json` | `5946c1be5d3d7ecb8e2e0a09b272834394b52328c5e70d24ad318417cdb98a96` |
| `…/attempt-001/gpu_guard.json` | `e039eb884d5607aad88cf803d0454a06abca29acbf072a5841655d6cf88dd828` |
| `…/attempt-001/execution_guard.json` | `3ca87a01cc76db77c4c909d08ec5c3eb8b61495175b3a6175ecdf5e03c203d2b` |
| `…/attempt-001/resource_samples.jsonl` | `cfc024a3acd82ead953a5190435d862bdb8817909deccc2130db1bc9d4de7688` |
| `…/attempt-001/stdout.log` | `022e240a8a36eccb82cb85828e1adc60d43fb25bbee2e81d7ee363361654e718` |
| `…/attempt-001/stderr.log` | `76e32349a059d2a59652e6cec08ca735c66c643385ecffebc4086a675f5a1642` |

`stdout.log` contains the offload validation line only. `stderr.log` contains the diffusers
progress bars, the expected offline-cache message, the LoRA warning, the CLIP truncation notice
and no traceback.

## Prompt

Fifty-five words, derived only from what the selected seed shows; the burned-in CENTERSTAR
watermark in the seed's lower-left was not described, and nothing was cropped, edited or replaced.

> A narrow slot canyon of smooth banded sandstone, flowing curved walls glowing warm orange and
> amber against deep brown shadow. A bright opening to daylight at the top; the floor below falls
> into shadow. One continuous passage with unbroken wall, floor and ceiling surfaces; no people,
> no text, no signage, no furniture or added objects.

**CLIP length:** the tokenizer reported
`Token indices sequence length is longer than the specified maximum sequence length for this model (81 > 77)`,
but the truncated tail is only the pipeline's own quality suffix
`CLIP truncated input (max_length=77): ['clear, 8 k']`. The prompt text itself fits inside the
77-token window — unlike #171, where the coherence/no-people clause was cut. No part of the
description was lost. The seed describes a natural canyon, so there are no windows or furniture to
name; the prompt says so explicitly rather than inventing them.

## Preview render

`hunyuan_panorama_preview.gd` (scene `godot_walk/scenes/hunyuan_panorama_preview.tscn`) was run in
the repository dev shell:

```bash
nix develop --command bash -c 'cd godot_walk &&
  HUNYUAN_PANORAMA_PATH="$PWD/source_library/sources/video-22909eb734e4d8e2/hunyuan/attempt-001/panorama/panorama.png" \
  HUNYUAN_CAPTURE_DIR="$PWD/evidence/2026-11-16-issue-172-hunyuan/panorama-views" \
  timeout 180 godot4 --path . scenes/hunyuan_panorama_preview.tscn'
```

Exit 0, four yaw-bank views printed (`PANORAMA_VIEW: forward|right|back|left`) and written to
`godot_walk/evidence/2026-11-16-issue-172-hunyuan/panorama-views/`. Those PNGs are gitignored by
`.gitignore` (`godot_walk/evidence/**/*.png`) and are local review aids only.

## The panorama against the seed (honest description)

**What carried over.** The subject is recognisably the same place: layered sandstone slot-canyon
walls, warm orange light on the lit faces, deep brown shadow on the near faces, and a narrow
vertical passage ahead with a bright gap above it. The palette family (ochre, rust, umber) and the
soft, water-smoothed rock read are preserved, and there are no people, no text, no signage and no
furniture in the panorama.

**Geometry drift.** The seed is a tight, dark tube shot with the camera tilted up into overhanging,
bulbous rock; its lit area is a small golden gap high in the ceiling and the visible floor is
essentially black. The panorama turns this into an **open-air slot canyon**: tall banded walls left
and right converge on a lit far wall, but the ceiling is a long strip of pale blue-white sky, and a
broad pale sand floor occupies roughly the bottom third of the equirect. The seed's rounded
overhang forms are flattened into mostly horizontal ledges, the wall profile is smoother and more
symmetric than the seed's irregular bulges, and the space is wider and taller. There is no visible
doorway: the bright area ahead is a lit rock face, not an opening, and no connectivity is claimed.

**Invented content.** The wide pink-grey sand floor with scattered dark pebbles and small rocks
(the seed's floor is not legible), the pale blue sky strip (the seed's gap glows gold/white, with no
blue), the regular horizontal stratification, and the symmetric counterpart wall behind the camera.
No watermark, letterbox bar or video glitch was reproduced.

**Missing content.** The seed's near-black shadows and heavy vignette (61.4 % of seed pixels are
below luminance 16, against 18.3 % of the panorama) and the specific overhanging arch shapes.

**Exposure and colour.** The panorama is much brighter and cooler than the seed: mean luminance
62.0 against 25.7, median 51.5 against 11.1, 95th percentile 163.8 against 101.7; channel means
R/G/B 79/55/54 against 45/19/9. The seed is a near-monochrome amber image; the panorama adds
blue-grey sky and mauve shadow rock, so the warm glow survives mainly on the lit faces.

**Seams and projection.** The 2:1 wrap is smooth: the mean absolute difference between the first and
last pixel columns is 2.51 levels, below the 3.77-level average between adjacent columns, so there
is no hard cut. The poles behave as usual for equirect: the sky strip and wall tops fan out at the
top edge and the sand stretches at the bottom edge. The left/right preview views show the close
walls heavily softened, and the whole image is low-frequency.

**Resolution.** 512x256 is soft by design; the 1152x644 preview views are visibly blurred, strata
read as broad smears at close range, and small pebbles on the floor are the only crisp detail.

This is a plausible, on-genre slot-canyon panorama and a fair reinterpretation of the seed, but it
is not a reconstruction: the seed is a dark enclosed tube and the panorama is a bright open canyon
with a large sand floor and a wide sky opening. Whether that is acceptable as a room candidate for
a non-box module is the operator's call.

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
python3 godot_walk/scripts/source_ingestion_runner.py status video-22909eb734e4d8e2
python3 godot_walk/scripts/register_video_sources.py validate
python3 -m pytest -q godot_walk/scripts
```

```bash
setsid nohup python3 godot_walk/scripts/run_source_hunyuan.py video-22909eb734e4d8e2 \
  --prompt "$(cat prompt.txt)" > /tmp/issue172-run.log 2>&1 < /dev/null &
# runner defaults: 512x256, seed 42, 2700 s, sequential_cpu
```
