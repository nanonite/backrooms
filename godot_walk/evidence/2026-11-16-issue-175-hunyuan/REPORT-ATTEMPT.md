# Issue #175 — Hunyuan Panogen retry attempt (panorama produced)

Date: 2026-11-16 (UTC)
Source: `video-102caf53423018b7` — `data/videos/corridor_straight.mp4`
Source SHA-256: `102caf53423018b75dfd1976b5a2346b0576bdd316429f246aee87a884ba3d4b`
Manifest: `source_manifest-v3.json`, SHA-256 `6c4863b240d035cdc52b78fc6a33b79dc07b610df5d6663d19cc8f6f7364d626`
Seed: `frame_0013`, index 12, 0.5 s, SHA-256 `a836cd3e2f90deb9bbf5ad3f23fe09fba156199f315e307a02fe332bb5eb38f1` (unedited direct decode, 1920x1080).
Authorization: operator decisions 2026-11-16 (issue #175 comments 599, 607) — attempt 1 of 3 approved; after the false-positive preflight block, retry explicitly authorized. This is the single started inference for this source.

Companion report: `REPORT.md` in this folder records the **earlier blocked attempt** (event 6, no inference). This report records the attempt that actually ran.

## Result

**The single authorized attempt ran to completion and produced a 512x256 equirectangular panorama.** The named-job false positive did not recur under guard policy 2.3.0 (#254).

- Attempt id: `attempt-001-retry-001`
- Run id: `run-60dfb0225caf48e5a8d2354e8ab852e5`
- Started: `2026-11-16T19:14:21.853475Z` (event 9, `hunyuan_attempt_started`)
- Result recorded: `2026-11-16T19:17:44.050695Z` (event 10, `hunyuan_attempt_result`)
- Runtime: **202.067 s** (3 min 22 s) of the 2700 s budget; `return_code` 0; `status` `produced`
- Diffusers progress: fp8 quantization of 1279 modules in ~18 s, then denoising 50/50 steps in 2:09 at ~2.35 s/it
- Attempts used after this run: **1 / 3**
- `status`: `awaiting_feedback` true, `can_start_attempt` false, `manual_fallback_allowed` false, `stopped_reason` null, `next_worker_actions` `["feedback"]`

The launch was detached with `setsid nohup … < /dev/null &` and a plain redirect, so the supervisor survived the worker turn, reaped the child itself and wrote all receipts. No receipt or ledger event was written by hand; the only worker-side writes were the prompt file, the polling observers and this report (all outside the source ledger). Polling note: `awaiting_feedback` flips true at *attempt start*, so a first observer exited early; a second observer keyed on the result event / non-empty run log and waited the full ~3.5 min. No second attempt was launched.

`feedback` was **not** run, no further attempt was made, and `manual-fallback` was not run. No winner was selected, no room was accepted, no catalog module was admitted, and no connectivity or opening is claimed.

## Preflight and start guard (passed)

`gpu_guard.json` (SHA-256 `05fde786…58896a8`), policy `2.3.0`: named-job scan passed (no unrelated process matched), GPU process scan passed (11 graphics-only rows ignored, zero compute contexts), `nvidia-smi --query-compute-apps` empty, RAM/swap/VRAM start limits passed.

Start snapshot `2026-11-16T19:14:21.58Z`: credited RAM 51,058,136,112 bytes (47.56 GiB; threshold 32 GiB), swap free 81,961,086,976 bytes (76.33 GiB; threshold 16 GiB), GPU free 11,460,935,680 bytes (10.67 GiB of 11.99 GiB; threshold 8 GiB). The GPU lock was acquired without waiting and `execution_guard.json` recorded `passed` at `19:14:21.771Z` before the child started (SHA-256 `df83be0f…9c49ca5`).

## Resources actually observed

The runner sampler ran for the whole attempt: 189 one-second samples (`resource_samples.jsonl`, SHA-256 `95a2f094…2dad12fd`).

| Metric | Observed value |
| --- | --- |
| Peak process-group RSS | 33,174,106,112 bytes (30.89 GiB) |
| Peak GPU memory used | 1,695,547,392 bytes (1.58 GiB) |
| Minimum credited RAM | 37,997,547,768 bytes (35.39 GiB); runtime floor 8 GiB |
| Minimum free swap | 71,003,004,928 bytes (66.13 GiB); runtime floor 16 GiB |
| Minimum free VRAM | 10,750,001,152 bytes (10.01 GiB); runtime floor 2 GiB |
| `stop_reason` | `null` — no stop condition tripped |

The RAM peak occurred during pipeline load / fp8 quantization and is fully sampled. It is higher than #172's 20.78 GiB peak but stayed comfortably inside the guard's start credit.

## Ledger events

All bound to manifest `6c4863b240d035cdc52b78fc6a33b79dc07b610df5d6663d19cc8f6f7364d626`.

| Sequence | Event | Occurred (UTC) | Summary |
| --- | --- | --- | --- |
| 6 | `hunyuan_preflight_blocked` | `2026-11-16T18:26:50.173019` | earlier blocked attempt (see `REPORT.md`) |
| 7 | `hunyuan_preflight_retry_approved` | `2026-11-16T18:52:16.370486` | operator retry authorization |
| 8 | `hunyuan_guard_passed` | `2026-11-16T19:14:21.666682` | `gpu_guard.json` receipt |
| 9 | `hunyuan_attempt_started` | `2026-11-16T19:14:21.853475` | attempt `attempt-001-retry-001`, config + receipts |
| 10 | `hunyuan_attempt_result` | `2026-11-16T19:17:44.050695` | `produced`, 202.067 s, 1 output |

`events.jsonl` now has 10 events. Post-run `status`: `attempts_used` 1, `stopped_reason` null, next action `feedback`.

## Outputs

| Path | SHA-256 |
| --- | --- |
| `…/hunyuan/attempt-001-retry-001/panorama/panorama.png` (512x256 RGB) | `4c5360c16e9e2f3727c2777e958f126f5a8eeb9820806ce9c696b4b562a69002` |
| `…/attempt-001-retry-001/attempt_config.json` | `51c9ea3df48eb2975a5edc715b96bbff61f695e14761658de85fa0538f229f44` |
| `…/attempt-001-retry-001/attempt_result.json` | `42e45d8686164847bfdc03a02a265531c047dafa972368172a4a95709e592f62` |
| `…/attempt-001-retry-001/gpu_guard.json` | `05fde7869a7a65e09af6031d020ff9a0ad8fd2359667f062617c3a95a88596a8` |
| `…/attempt-001-retry-001/execution_guard.json` | `df83be0f3407aa8de40dc28ed037dca3e6845440048b3560270da4f5c8c49ca5` |
| `…/attempt-001-retry-001/resource_samples.jsonl` | `95a2f0941e5a8e5a760fd8da35487de3119b6f26f80858311cd2f5942dad12fd` |
| `…/attempt-001-retry-001/stdout.log` | `022e240a8a36eccb82cb85828e1adc60d43fb25bbee2e81d7ee363361654e718` |
| `…/attempt-001-retry-001/stderr.log` | `46061d29b87b68333c211ad2c24b61b0c0d372971f519b3e12ec231f52c3b6ce` |

`stdout.log` holds only the offload validation line (diffusers 0.34.0, accelerate 1.6.0, torch 2.5.0, transformers 4.51.0). `stderr.log` holds the checkpoint-load / fp8-quantization / 50-step denoise progress bars, the expected offline-cache message and the LoRA warning, and **no traceback**.

## Prompt

Fifty-two words, derived only from the selected seed, which was viewed but not cropped, edited or replaced. The seed shows a carpeted, wallpapered indoor corridor with a suspended lit ceiling and a large square pillar; no windows, furniture, people, text or signage. No glitches, letterbox bars or watermark were described.

> An indoor corridor with pale yellow-green chevron wallpaper partitions and a large square cream pillar with a white base. Tan carpet floor and a suspended tile ceiling with bright rectangular fluorescent panels. One continuous space with unbroken wall, floor and ceiling lines; no windows, no furniture, no people, no text or signage.

**CLIP length:** the tokenizer reported `79 > 77`; `CLIP truncated input (max_length=77): ['8 k']` — the truncated tail is only the pipeline's own quality suffix. No part of the description was lost.

Helper files (not committed): prompt `/tmp/issue175-prompt.txt`; polling observers `/tmp/opencode/issue175_poll.py` and `/tmp/opencode/issue175_poll2.py` (no restricted word in any path or contents).

## Preview render

`hunyuan_panorama_preview.gd` (scene `godot_walk/scenes/hunyuan_panorama_preview.tscn`) was run in the repository dev shell:

```bash
nix develop --command bash -c 'cd godot_walk &&
  HUNYUAN_PANORAMA_PATH="$PWD/source_library/sources/video-102caf53423018b7/hunyuan/attempt-001-retry-001/panorama/panorama.png" \
  HUNYUAN_CAPTURE_DIR="$PWD/evidence/2026-11-16-issue-175-hunyuan/panorama-views" \
  timeout 180 godot4 --path . scenes/hunyuan_panorama_preview.tscn'
```

Exit 0, four yaw-bank views printed (`PANORAMA_VIEW: forward|right|back|left`) and written to `godot_walk/evidence/2026-11-16-issue-175-hunyuan/panorama-views/`. Those PNGs are gitignored by `.gitignore` (`godot_walk/evidence/**/*.png`) and are local review aids only; they were viewed before writing this report.

## The panorama against the seed (honest description)

**What carried over.** The subject is recognisably the same place. The forward half reproduces the seed's composition closely: a tan/yellow carpet floor, pale yellow-green chevron-patterned wall partitions, a large square cream pillar slightly left of centre, and a suspended ceiling with bright rectangular fluorescent panels receding into the distance. The palette is nearly identical to the seed: mean luminance 145.0 vs 144.3, median 142.3 vs 144.6, channel means R/G/B 161.9/147.2/74.3 vs 164.0/144.9/79.5. There are no people, no text, no signage and no furniture in the panorama.

**Geometry drift.** The seed is a single straight bay with one dominant pillar and a clear view down the corridor to the right of it. The panorama wraps the wallpaper partitions and ceiling grid around the full 360°, so the corridor becomes a closed loop of repeating partitions; the far end of the seed's corridor is replaced by a blank wallpaper wall in the forward view. The single pillar is repeated as several pillars around the ring. No doorway or opening is visible; the bright gaps between partitions are lit wall surfaces, not asserted connectivity.

**Invented content.** The symmetric partition on the far side of the panorama, the additional pillars around the wrap, and the overall closed-loop layout are inventions of the panoramic projection. The `back` and `left` preview views are extreme close-ups of the wallpaper motif: at 512x256 the chevron pattern breaks into soft swirly green/cream blobs and glyph-like shapes. These are pattern artefacts, not letters or signage.

**Missing content.** The seed's fine carpet speckle, the crisp square light-panel outlines and the small wall socket near the centre-right partition are not reproduced. The seed's slight warm/lime colour cast is preserved, so nothing significant is missing chromatically.

**Seams and projection.** Unlike #171/#172, the 2:1 wrap here has a **visible seam**: the mean absolute difference between the first and last pixel columns is 15.27 levels versus 6.17 for an average adjacent-column pair (about 2.5x), so a vertical join is detectable where the equirect edges meet. The poles smear as usual: the ceiling panels fan out at the top edge and the carpet stretches at the bottom edge. The close wallpaper views are heavily blurred.

**Resolution.** 512x256 is soft by design; the 1152x644 preview views are visibly blurred, panel edges read as soft smears, and the fine wallpaper motif does not survive scaling. This is a panorama reference, not a walkable reconstruction.

This is a plausible, strongly on-genre corridor panorama and a much closer reinterpretation of the seed than the #171/#172 cases, but it is still a reinterpretation: one straight bay became a wrapped, repeating partition loop, with a wrap seam and no observed openings. Whether that is acceptable as a room candidate is the operator's call.

## What was not done

- No `feedback` event (operator review is pending).
- No further attempt, no `manual-fallback`, no prompt or seed change. Attempts used: 1 / 3.
- No `select-winner`, no room candidate, no accepted room, no catalog admission, no generative-map metadata record.
- No connectivity or opening is claimed.
- `registration_accepted` and `scale_calibrated` remain `false` in the manifest;
  `register_video_sources.py validate` reports valid (13 sources).
- Hash-pinned files (`scripts/player.gd`, `project.godot`, library room scenes, `catalog.json`,
  `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`) were not touched.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py status video-102caf53423018b7
python3 godot_walk/scripts/register_video_sources.py validate
python3 -m pytest -q godot_walk/scripts
```

```bash
setsid nohup python3 godot_walk/scripts/run_source_hunyuan.py video-102caf53423018b7 \
  --prompt "$(cat /tmp/issue175-prompt.txt)" > /tmp/issue175-run.log 2>&1 < /dev/null &
# runner defaults: 512x256, seed 42, 2700 s, sequential_cpu
```
