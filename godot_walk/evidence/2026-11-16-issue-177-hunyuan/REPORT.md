# Issue #177 — Hunyuan Panogen attempt-001 (yellow-lit partition-maze panorama produced)

Date: 2026-11-16 (UTC)
Source: `video-61b91dbeb9026dc7` — `data/videos/corridor_x.mp4`
Source SHA-256: `61b91dbeb9026dc7b404657f7ba7e081b5588a7e7a4a2abfa553be765d1a7f04`
Manifest: `source_manifest-v3.json`, SHA-256 `af41b7ed362728d9956d5cfb5eb3d0dc71b7f251febfff02f25b2be9dcf6259f`
Seed: `frame_0085`, index 84, 3.5 s, SHA-256 `6de4922c2f237eeee16013f1b86ce6f3aba945c580d0b20f2fab483989c18c1f`
(unedited direct decode, 1920x1080; no crop, resize or edit)
Authorization: operator decision 2026-11-16 (issue #177, comment 601) — "go ahead for all" /
"lets move on"; Hunyuan attempt 1 of 3 approved, local GPU, no USD ceiling, then stop for
operator review. This is the first started inference for this source.

## Result

**The single authorized attempt ran to completion and produced a 512x256 equirectangular panorama.**

- Attempt id: `attempt-001`
- Run id: `run-2e591eeb92ce4847b750725581ee44ee`
- Started: `2026-11-16T19:43:27.013777Z` (event 7, `hunyuan_attempt_started`)
- Result recorded: `2026-11-16T19:47:56.413916Z` (event 8, `hunyuan_attempt_result`)
- Runtime: **269.261 s** (4 min 29.3 s) of the 2700 s budget; `return_code` 0; `status` `produced`
- Diffusers progress: fp8 quantization of 1279 modules in ~19 s, then denoising 50/50 steps
  in 3:07 at ~2.38 s/it
- Attempts used after this run: **1 / 3**
- `status`: `awaiting_feedback` true, `can_start_attempt` false, `manual_fallback_allowed` false,
  `stopped_reason` null, `next_worker_actions` `["feedback"]`

The supervisor survived the worker turn. The launch was detached with
`setsid nohup … < /dev/null &` and a plain redirect; the runner reaped its own child and wrote
`attempt_result.json`, `resource_samples.jsonl`, `stdout.log` and `stderr.log` itself. No receipt
or ledger event was written by hand.

**Polling note.** `awaiting_feedback` is set when an attempt *starts*, not when it finishes
(`source_ingestion_policy._attempt_state`: true until a result event exists). The first read-only
observer therefore reported "done" at t=0 against a still-running supervisor. It was corrected in
the same turn by a second observer (also read-only, `/tmp/opencode/issue177_wait2.py`, not
committed) that watched for a new line in `events.jsonl` and for process exit; that observer saw
event 8 at t≈225 s after it started. The run itself was never re-launched and no second attempt
was made.

## Preflight and start guard (passed)

`gpu_guard.json` (SHA-256 `b01891a9fcbcfb6c0338feede9770acbce544c26d141dc534960ecc0abe22061`),
guard policy `2.3.0`:

| Check | Result |
| --- | --- |
| named-job scan (`_active_named_jobs`) | passed (orchestrators ignored; no unrelated python/qemu job matched) |
| GPU process scan | passed; 11 graphics-only rows ignored (`xorg`, `gnome-shell`, 8× `kitty`, `firefox`, `code`), zero compute contexts |
| `nvidia-smi --query-compute-apps` | empty |
| start limits (ARC-credited RAM, swap, VRAM) | passed |

Start snapshot `2026-11-16T19:43:26.749607Z`:

- `ram_available_bytes` = 50,992,954,128 (47.49 GiB) = `MemAvailable` 19,750,895,616 (18.39 GiB) +
  reclaimable ZFS ARC 31,242,058,512 (29.10 GiB); threshold 32 GiB
- `swap_free_bytes` = 82,778,370,048 (77.09 GiB); threshold 16 GiB
- `gpu_free_bytes` = 11,434,721,280 (10.65 GiB) of 12,878,610,432 (11.99 GiB); threshold 8 GiB

The GPU lock was acquired and `execution_guard.json` recorded `passed` before the child started
(SHA-256 `a004779222d6757f6bf58caf3b9addcc068982d4ce89dc2adc70cc5d53c55f5d`).

## Resources actually observed

The runner sampler ran for the whole attempt: 252 one-second samples (`resource_samples.jsonl`,
SHA-256 `baba40af624b2cb628b7bef4da041535e0a660b1870cfd33231baf1eddc240c2`).

| Metric | Observed value |
| --- | --- |
| Peak process-group RSS | 25,289,785,344 bytes (23.56 GiB) |
| Peak GPU memory used | 1,718,616,064 bytes (1.60 GiB) |
| Minimum credited RAM | 38,992,387,208 bytes (36.32 GiB); runtime floor 8 GiB |
| Minimum free swap | 60,425,449,472 bytes (56.27 GiB); runtime floor 16 GiB |
| Minimum free VRAM | 10,727,981,056 bytes (9.99 GiB); runtime floor 2 GiB |
| `stop_reason` | `null` — no stop condition tripped |

## Ledger events

All bound to manifest `af41b7ed362728d9956d5cfb5eb3d0dc71b7f251febfff02f25b2be9dcf6259f`.

| Sequence | Event | Occurred (UTC) | Summary |
| --- | --- | --- | --- |
| 6 | `hunyuan_guard_passed` | `2026-11-16T19:43:26.832219` | `gpu_guard.json` receipt |
| 7 | `hunyuan_attempt_started` | `2026-11-16T19:43:27.013777` | attempt `attempt-001`, config + receipts |
| 8 | `hunyuan_attempt_result` | `2026-11-16T19:47:56.413916` | `produced`, 269.261 s, 1 output |

`events.jsonl` now has 8 events; SHA-256
`2e2f5bde57f5dd83c04e5a56c5dabd78bb8dd6a05a385dcc5fabd66433017eee`.

## Outputs

| Path | SHA-256 |
| --- | --- |
| `…/hunyuan/attempt-001/panorama/panorama.png` (202,325 bytes, 512x256 RGB) | `4b5f5088bf50be56676d99a61f7646cd43863d0a745019f172f00fb1e29902da` |
| `…/attempt-001/attempt_config.json` | `300837b54f116ceca6e5fb63af98cc60a5861a9eec4608bbcc2c64de3dfaa18e` |
| `…/attempt-001/attempt_result.json` | `d36e45b873960478d550d231ecdadbe1f96f656a4547a52a219c0149003055f1` |
| `…/attempt-001/gpu_guard.json` | `b01891a9fcbcfb6c0338feede9770acbce544c26d141dc534960ecc0abe22061` |
| `…/attempt-001/execution_guard.json` | `a004779222d6757f6bf58caf3b9addcc068982d4ce89dc2adc70cc5d53c55f5d` |
| `…/attempt-001/resource_samples.jsonl` | `baba40af624b2cb628b7bef4da041535e0a660b1870cfd33231baf1eddc240c2` |
| `…/attempt-001/stdout.log` | `022e240a8a36eccb82cb85828e1adc60d43fb25bbee2e81d7ee363361654e718` |
| `…/attempt-001/stderr.log` | `85895d6db45da580ae1b7f6d88daec7cb78093d835e5e4c239f1565ec0103d68` |

All paths are relative to `godot_walk/source_library/sources/video-61b91dbeb9026dc7/`.
`stdout.log` contains the offload validation line only. `stderr.log` contains the diffusers
progress bars, the expected offline-cache and LoRA warnings, the CLIP truncation notice and
no traceback.

## Prompt

Fifty words, written only from what the selected seed shows. No video glitches, letterbox bars
or watermarks were described; nothing was cropped, edited or replaced.

> An indoor maze of floor-to-ceiling partition walls in yellow-green chevron patterned wallpaper
> with white baseboards and plain cream pillars. Tan carpet floor. A drop ceiling of square
> textured tiles with glowing rectangular fluorescent panels. One coherent interior, continuous
> wall, floor and ceiling lines; no people, text, signage or added objects.

**CLIP length:** `stderr.log` reports
`Token indices sequence length is longer than the specified maximum sequence length for this model (82 > 77)`
and `CLIP truncated input (max_length=77): [', clear, 8 k']`. The truncated tail is only the
pipeline's own quality suffix; the whole prompt description, including the coherence clause,
was seen by the text encoder. The seed genuinely shows no windows and no furniture, so none were
invented in the prompt.

## Preview render

`hunyuan_panorama_preview.gd` (scene `godot_walk/scenes/hunyuan_panorama_preview.tscn`) was run in
the repository dev shell:

```bash
nix develop --command bash -c 'cd godot_walk &&
  HUNYUAN_PANORAMA_PATH="$PWD/source_library/sources/video-61b91dbeb9026dc7/hunyuan/attempt-001/panorama/panorama.png" \
  HUNYUAN_CAPTURE_DIR="$PWD/evidence/2026-11-16-issue-177-hunyuan/panorama-views" \
  timeout 180 godot4 --path . scenes/hunyuan_panorama_preview.tscn'
```

Exit 0, four yaw-bank views printed (`PANORAMA_VIEW: forward|right|back|left`) and written to
`godot_walk/evidence/2026-11-16-issue-177-hunyuan/panorama-views/`. Those PNGs are gitignored by
`.gitignore` (`godot_walk/evidence/**/*.png`) and are local review aids only.

## The panorama against the seed (honest description)

**What carried over.** The subject is recognisably the same *kind* of place: a warm yellow-lit
indoor maze of tall partitions covered in green-yellow patterned wallpaper with white baseboards,
a tan carpet floor, and a suspended ceiling grid with bright rectangular fluorescent panels.
The golden cast, the wallpaper-on-partitions look and the carpeted open passages all survive.
There are no people, no text, no signage, no furniture and no windows in the panorama, matching
the seed and the prompt.

**Geometry drift.** The seed shows one broad room: a large patterned partition close on the
right, a smaller one behind it, open carpet to the left, a few plain cream pillars, and a coarse
ceiling grid with a conspicuously bright, slightly blown-out panel at upper left. The panorama
turns this into a **more regular, repetitive maze**: many similar narrow partitions recede in
rows, the ceiling panels become smaller and more numerous, and the partitions are thinner and
closer together. The seed's large chevron/zigzag wallpaper motif becomes a denser, busier
floral-damask motif, and the specific cream pillar at the left foreground is not reproduced as
a distinct object. No doorway or opening is visible, and no connectivity is claimed: the passages
between partitions are open in both images, but that is all.

**Invented content.** The far-field repetition of additional corridors and partitions, the exact
rhythm of ceiling lights, and small dark rectangular wall-mounted fixtures visible in the `right`
preview view (the seed's small fixtures are pale outlet plates, not clearly these). Because a
wallpapered partition sits near the camera, the equirect wraps that close pattern around most of
the `back` and `left` preview views — those two views are almost entirely wallpaper, which is a
projection/placement artifact rather than a feature of the seed.

**Missing content.** The seed's dominant right-hand panel and its specific broad chevron pattern,
the separate cream pillar, and the single large overexposed ceiling panel are not reproduced as
distinct elements. No watermark, letterbox bar, scanline or video glitch was reproduced (and none
was described to the model).

**Exposure and colour.** The panorama is slightly brighter and a touch more yellow-green than the
seed: mean luminance 148.3 vs 141.6, median 150 vs 143, 95th percentile 183 vs 175; channel means
R/G/B 170.5/151.3/74.4 vs 162.1/143.8/76.4. Both images are strongly warm with almost no deep
shadows (fraction of pixels below luminance 16: 0.024 % panorama vs 0.001 % seed).

**Seams and projection.** The 2:1 wrap is **not perfectly seamless**: the mean absolute difference
between the first and last pixel columns is 9.24 levels, slightly above the 7.63-level average
between adjacent columns, so a faint vertical tone/pattern discontinuity is possible at the wrap
rather than a clean join. The poles smear as usual for equirect: ceiling tiles fan out at the top
edge and the carpet stretches at the bottom edge. Several wall and baseboard lines are visibly
wavy in the side views.

**Resolution.** 512x256 is soft by design. At the 1152x644 preview scale the wallpaper motif
reads as blurred green-gold loops, the light panels are soft glows and the baseboards are hazy
lines; the `back` and `left` views are the softest because they are dominated by near-field
pattern. No structural holes or black voids.

This is a plausible, on-genre reinterpretation of the seed, not a reconstruction: an open-plan
office maze became a denser repeating partition maze with a different wallpaper motif. Whether
that is acceptable as a room candidate for a module is the operator's call.

## What was not done

- No `feedback` event (operator review is pending).
- No second attempt, no `manual-fallback`, no prompt or seed change. Attempts used: 1 / 3.
- No `select-winner`, no room candidate, no accepted room, no catalog admission, no generative-map
  metadata record.
- No connectivity or opening is inferred from the video; the "cross junction" suggestion in the
  source name remains unverified and no openings were observed or authored here.
- `registration_accepted` and `scale_calibrated` remain `false` in the manifest;
  `register_video_sources.py validate` reports valid (13 sources).
- Hash-pinned files (`scripts/player.gd`, `project.godot`, library room scenes, `catalog.json`,
  `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`) were not touched.

## Checks

```bash
python3 godot_walk/scripts/source_ingestion_runner.py status video-61b91dbeb9026dc7
python3 godot_walk/scripts/register_video_sources.py validate   # valid: true, 13 sources
python3 -m pytest -q godot_walk/scripts                          # 1530 passed, 5 skipped, 67 subtests passed
```

## Reproduction

```bash
setsid nohup python3 godot_walk/scripts/run_source_hunyuan.py video-61b91dbeb9026dc7 \
  --prompt "$(cat prompt.txt)" > /tmp/issue177-run.log 2>&1 < /dev/null &
# runner defaults: 512x256, seed 42, 2700 s, sequential_cpu
```
