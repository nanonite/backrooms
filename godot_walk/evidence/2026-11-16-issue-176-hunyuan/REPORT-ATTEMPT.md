# Issue #176 — Hunyuan Panogen attempt-001-retry-001 (panorama produced)

Date: 2026-11-16 (UTC)
Source: `video-2671b32f256a4ee7` — `data/videos/corridor_t.mp4`
Source SHA-256: `2671b32f256a4ee7f326fae67290bcec2143efabb4f1000fc4bcfa9507260409`
Manifest: `source_manifest-v3.json`, SHA-256 `101159bf8200611ef994a1f5b8ba5f4eaa86ff839972128150eb15e1a16245ae`
Seed: `frame_0096`, index 95, 3.9583 s, SHA-256 `39442f1ae81cea1cd0eef682a99ca7c8030a6e72824be7626e34188be7cb3d75`
(unedited direct-source decode, 1920x1080). Not cropped, edited or replaced; no other seed was picked.
Authorization: operator decision 2026-11-16 (issue #176, comments 600, 608) — one guarded attempt,
local GPU, no USD ceiling; the earlier preflight block was a false positive (fixed in #254, policy
2.3.0) and a single retry was authorized, with `attempts_used` still 0/3. This report is for that
one authorized retry. The earlier block report remains in `REPORT.md` in this folder.

## Result

**The single authorized attempt ran to completion and produced a 512x256 equirectangular panorama.**

- Attempt id: `attempt-001-retry-001`
- Run id: `run-4c2501b2c3c145509720ae5c2943fd24`
- Guard passed: `2026-11-16T19:33:58.151127Z` (event 8, `hunyuan_guard_passed`)
- Attempt started: `2026-11-16T19:33:58.324569Z` (event 9, `hunyuan_attempt_started`)
- Result recorded: `2026-11-16T19:38:12.681951Z` (event 10, `hunyuan_attempt_result`)
- Runtime: **254.229 s** (4 min 14.2 s) of the 2700 s budget; `return_code` 0; `status` `produced`
- `stop_reason`: `null` — no RAM/swap/VRAM/compute/timeout stop condition tripped
- Attempts used after this run: **1 / 3**
- Post-run `status`: `awaiting_feedback` true, `can_start_attempt` false,
  `manual_fallback_allowed` false, `stopped_reason` null, `next_worker_actions` `["feedback"]`

The supervisor survived the worker turn. The launch used the exact operator-prescribed detached
command (`setsid nohup … < /dev/null &`) with a plain redirect, no pipe or tee, and a prompt/log file
name without the restricted word; the runner defaults were kept (512x256, diffusion seed 42,
2700 s timeout, `sequential_cpu` offload, offline cache, fp8 attention/GEMM, VAE tiling). The detached
runner reaped its Panogen child and wrote all receipts itself; **no receipt or event was written by
hand**. The only worker-side writes were two polling observers under `/tmp/opencode/` (not committed)
and this report. One observer stopped early because this runner flips `awaiting_feedback` true at
attempt start; a second waited for the detached runner PID to exit before the result was recorded.

## Preflight and start guard (passed)

`gpu_guard.json` SHA-256 `97a2bf0ba24c049e4daf46d0827c07bd53c951cac7f95754f132e7beb6281a2c`,
policy `2.3.0` (the #254 fix):

| Check | Result |
| --- | --- |
| named-job scan (`source_ingestion_preflight._active_named_jobs`) | passed — only `python*`/`qemu*` job processes are matched; the harness's `bun` chainlink loop and `opencode` worker are ignored, so the earlier false positive did not recur |
| GPU process scan | passed; 11 graphics-only rows ignored (`xorg`, `gnome-shell`, 8× `kitty`, `firefox`, `code`), zero compute contexts |
| `nvidia-smi --query-compute-apps` | empty |
| start limits (ARC-credited RAM, swap, VRAM) | passed |

Start snapshot `2026-11-16T19:33:58.074123Z`:

- `ram_available_bytes` = 51,954,708,016 (48.40 GiB) = `MemAvailable` 26,976,759,808 (25.14 GiB) +
  reclaimable ZFS ARC 24,977,948,208 (23.27 GiB); threshold 32 GiB
- `swap_free_bytes` = 82,952,470,528 (77.26 GiB); threshold 16 GiB
- `gpu_free_bytes` = 11,534,336,000 (10.74 GiB) of 12,878,610,432 (11.99 GiB); threshold 8 GiB

The GPU lock was acquired without waiting and `execution_guard.json` (SHA-256
`5db719c2d43a4f3120323a5970126c49377ead8620370c10a7551abb17723670`) recorded `passed` at
`19:33:58.246762Z` before the child started.

## Resources actually observed

The runner sampler ran for the whole attempt: 238 one-second samples (`resource_samples.jsonl`,
SHA-256 `4ee29e06006ec3f52deaa5169ad9e9b66dc5c92e80e46620a3406570a5bea79c`).

| Metric | Observed value |
| --- | --- |
| Peak process-group RSS | 26,453,692,416 bytes (24.64 GiB) |
| Peak GPU memory used | 1,710,227,456 bytes (1.59 GiB) |
| Minimum credited RAM | 40,114,997,208 bytes (37.36 GiB); runtime floor 8 GiB |
| Minimum free swap | 61,147,656,192 bytes (56.96 GiB); runtime floor 16 GiB |
| Minimum free VRAM | 10,736,369,664 bytes (10.00 GiB); runtime floor 2 GiB |
| `stop_reason` | `null` |

Diffusers progress: fp8 quantization of 1279 modules in ~17 s, then denoising 50/50 steps in 3:00
at ~2.4 s/it. `stderr.log` contains the pipeline progress bars, the expected offline-cache message,
a benign LoRA/CLIP warning and the CLIP truncation notice, and no traceback. `stdout.log` contains
only the offload validation line.

**CLIP length:** the tokenizer reported 85 > 77 tokens and the truncated tail was
`resolution, sharp, clear, 8 k` — the pipeline's own quality suffix. The 51-word prompt itself fits
inside the 77-token window; no part of the scene description was lost.

## Ledger events

All bound to manifest `101159bf8200611ef994a1f5b8ba5f4eaa86ff839972128150eb15e1a16245ae`.

| Sequence | Event | Occurred (UTC) | Summary |
| --- | --- | --- | --- |
| 6 | `hunyuan_preflight_blocked` | `2026-11-16T18:45:42.094720` | earlier false-positive block (kept for history) |
| 7 | `hunyuan_preflight_retry_approved` | `2026-11-16T18:52:17.269186` | operator retry, `attempt-001-retry-001` |
| 8 | `hunyuan_guard_passed` | `2026-11-16T19:33:58.151127` | `gpu_guard.json` receipt |
| 9 | `hunyuan_attempt_started` | `2026-11-16T19:33:58.324569` | config + guard receipts |
| 10 | `hunyuan_attempt_result` | `2026-11-16T19:38:12.681951` | `produced`, 254.229 s, 1 output |

`events.jsonl` now has 10 events; SHA-256 `0bfa449d8f9b4ff554eb24f0f8e293bc46c97c9b85ec3617b1558390ab3ed28b`.

## Prompt

Fifty-one words, derived only from what the selected seed shows (materials, floor, ceiling, setting
and partitions). No watermark, letterbox bar or video glitch was described, and nothing was invented
in the text.

> A single indoor corridor with a golden-yellow carpet floor and a white suspended grid ceiling holding bright rectangular fluorescent panels. Tall freestanding partitions are covered in yellow-green chevron-patterned wallpaper with pale trim, receding into the distance. One coherent interior with continuous lines; no windows, people, text, signage, furniture or added objects.

## Outputs

| Path | SHA-256 |
| --- | --- |
| `…/attempt-001-retry-001/panorama/panorama.png` (213,243 bytes, 512x256 RGB) | `bb5a53f2141243013f17aa0a40a20d9fee4c37ca1168c7c75379daedda29157d` |
| `…/attempt-001-retry-001/attempt_config.json` | `973e91b5af352c06f38aea91d45f57a6cdd7b47de4aff6c0679f47d23d01aa75` |
| `…/attempt-001-retry-001/attempt_result.json` | `405ea60a85fdff6bdf5d9f0983efcd4f28d143cc81704965e53f8a2a022c5ea3` |
| `…/attempt-001-retry-001/gpu_guard.json` | `97a2bf0ba24c049e4daf46d0827c07bd53c951cac7f95754f132e7beb6281a2c` |
| `…/attempt-001-retry-001/execution_guard.json` | `5db719c2d43a4f3120323a5970126c49377ead8620370c10a7551abb17723670` |
| `…/attempt-001-retry-001/resource_samples.jsonl` | `4ee29e06006ec3f52deaa5169ad9e9b66dc5c92e80e46620a3406570a5bea79c` |
| `…/attempt-001-retry-001/stdout.log` | `022e240a8a36eccb82cb85828e1adc60d43fb25bbee2e81d7ee363361654e718` |
| `…/attempt-001-retry-001/stderr.log` | `6d7a5e60d3849cc77f1d3cb4990f0b37e2746b0fbb8473ed8e7f8b2240b847d9` |

All paths are relative to `godot_walk/source_library/sources/video-2671b32f256a4ee7/`.

## Preview render

`hunyuan_panorama_preview.gd` (scene `godot_walk/scenes/hunyuan_panorama_preview.tscn`) was run in the
repository dev shell:

```bash
nix develop --command bash -c 'cd godot_walk &&
  HUNYUAN_PANORAMA_PATH="$PWD/source_library/sources/video-2671b32f256a4ee7/hunyuan/attempt-001-retry-001/panorama/panorama.png" \
  HUNYUAN_CAPTURE_DIR="$PWD/evidence/2026-11-16-issue-176-hunyuan/panorama-views" \
  timeout 180 godot4 --path . scenes/hunyuan_panorama_preview.tscn'
```

Exit 0, four yaw-bank views printed (`PANORAMA_VIEW: forward|right|back|left`) and written to
`godot_walk/evidence/2026-11-16-issue-176-hunyuan/panorama-views/`. Those PNGs are gitignored by
`.gitignore` (`godot_walk/evidence/**/*.png`) and are local review aids only.

## The panorama against the seed (honest description)

**What carried over.** The palette and subject are recognisably the seed's: a golden-yellow carpet
floor, a pale cream ceiling, and tall yellow-green wallpapered partitions standing as freestanding
walls in an interior corridor. The forward preview reads as a continuous carpeted passage between
two patterned panels with a far wall, and there are no people, no text and no signage. The overall
warm yellow/olive cast matches the seed's lighting family.

**Geometry drift.** The seed's pattern is a regular fine chevron/zigzag motif repeated on many
square partitions receding down a long, open path, with a large foreground pillar/panel on the right
and bright white fluorescent ceiling panels. The panorama replaces the chevron with a much larger
looping floral/arabesque motif, reduces the partitions to two broad panels flanking a short corridor,
closes the far end with a plain wall, and loses the visible fluorescent panels — the ceiling reads
as plain cream with only faint structure. The seed's large foreground partition becomes one of two
near-symmetric side panels. The `right` preview view also shows a tall plain wall with a pale
rectangular recessed frame; this is invented surface detail, **not** an authored opening, and no
connectivity is claimed. The filename's suggested T-junction remains unverified and unobserved.

**Invented content.** The floral/arabesque wallpaper motif (vs the seed's chevron), the far end wall,
the recessed pale wall panel in the side view, and the smooth, unbroken pale ceiling. No watermark,
letterbox bar or video glitch was reproduced.

**Missing content.** The seed's crisp repeating chevron pattern, its bright rectangular fluorescent
panels, the large foreground pillar, and the long vista of repeated partitions.

**Seams and projection.** The 2:1 wrap has a visible vertical discontinuity: the mean absolute
difference between the first and last pixel columns is 21.11 levels, about double the 11.30-level
average between adjacent columns, so the panel/car boundary does not close cleanly at the seam. The
equirect poles smear as usual: the ceiling fans out at the top edge and the carpet stretches at the
bottom edge. The `right` preview shows the close patterned panel heavily softened, and a slight wavy
bend on the far wall.

**Exposure and colour.** The panorama is brighter and slightly cooler-yellow than the seed: mean
luminance 169.1 against 146.2, median 175.0 against 147.5, 95th percentile 209.9 against 180.4.
Channel means R/G/B are 185/172/99 against 165/147/82, so the yellow-olive family survives while the
olive wallpaper reads lighter and greener.

**Resolution.** 512x256 is soft by design; the 1152x644 preview views are visibly blurred, and the
fine wallpaper detail that is crisp in the 1920x1080 seed becomes broad smears in the panorama.

This is a plausible, on-genre reinterpretation of the seed, but it is not a reconstruction: the fine
chevron corridor became a short corridor with large floral panels and a blank end wall, and the wrap
seam is noticeable. Whether that is acceptable as a room candidate is the operator's call.

## What was not done

- No `feedback` event (operator review is pending).
- No second attempt, no `manual-fallback`, no prompt or seed change. Attempts used: 1 / 3.
- No `select-winner`, no room candidate, no accepted room, no catalog module admitted, no generative
  map metadata record, no room candidate built.
- No connectivity or opening is claimed or inferred; the T-junction reading of the filename is
  unverified.
- `registration_accepted` and `scale_calibrated` remain `false` in the manifest;
  `register_video_sources.py validate` reports valid (13 sources).
- Hash-pinned files (`scripts/player.gd`, `project.godot`, library room scenes, `catalog.json`,
  `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`) were not touched.
- The earlier block report (`REPORT.md`) was not deleted or edited.

## Checks after the run

- `python3 godot_walk/scripts/source_ingestion_runner.py status video-2671b32f256a4ee7` — result above.
- `python3 godot_walk/scripts/register_video_sources.py validate` → `{"valid": true, "registered_count": 13}`.
- `python3 -m pytest -q godot_walk/scripts/test_source_ingestion_preflight.py godot_walk/scripts/test_psx_design_round_resources.py` → `13 passed`.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py status video-2671b32f256a4ee7
python3 godot_walk/scripts/register_video_sources.py validate
```

```bash
setsid nohup python3 godot_walk/scripts/run_source_hunyuan.py video-2671b32f256a4ee7 \
  --prompt "$(cat prompt.txt)" > /tmp/issue176-run.log 2>&1 < /dev/null &
# runner defaults: 512x256, seed 42, 2700 s, sequential_cpu
```
