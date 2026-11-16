# Issue #174 — Hunyuan Panogen attempt: panorama produced (`attempt-001-retry-001`)

Date: 2026-11-16 (UTC)
Source: `video-d92fc1fa764aa3a2` — `data/videos/Angel (Joseph Cornell, 1957).mp4`
Source SHA-256: `d92fc1fa764aa3a25a40910f01858def4b72dd3b51ca4af8d5d012d788567428`
Manifest: `source_manifest-v3.json`, SHA-256 `28c01ed69ccbe6acc9854b659cbfb3a8b902903a6257542bb289f9a042b8f77f`
Seed: `frame_4347`, index 4346, 145.0115 s, SHA-256 `ae59a84fb9aa07612b5b100c2ee5b5ab5645836dd5bccc665b862acd51ab500f`
(unedited direct decode, 636x480). The seed was viewed and not cropped, edited or replaced.
Authorization: operator decision 2026-11-16 (issue #174, comment 598: "go ahead for all" / "lets
move on") — attempt 1 of 3 approved, local GPU, no USD ceiling; run one attempt, then stop for
operator review. Comment 606 authorized a preflight retry after the earlier false-positive block,
so the runner reserved the id `attempt-001-retry-001`. The original `attempt-001` never started
inference; this is still the **single authorized attempt**.

This report is `REPORT-ATTEMPT.md` because `REPORT.md` in this folder already records the earlier
preflight block and is kept unchanged.

## Result

**The single authorized attempt ran to completion and produced a 512x256 equirectangular panorama.**

- Attempt id: `attempt-001-retry-001`
- Run id: `run-02b4153b90364d0eb29d9a34a246a08e`
- Started: `2026-11-16T18:55:37.219470Z` (event 12, `hunyuan_attempt_started`)
- Result recorded: `2026-11-16T18:58:56.151836Z` (event 13, `hunyuan_attempt_result`)
- Runtime: **198.845 s** (3 min 18.8 s) of the 2700 s budget; `return_code` 0; `status` `produced`
- Diffusers progress: fp8 quantization of 1279 modules in ~19 s, then denoising 50/50 steps in
  2:10 at ~2.5 s/it
- Attempts used after this run: **1 / 3**
- Post-run status: `awaiting_feedback` true, `can_start_attempt` false,
  `manual_fallback_allowed` false, `stopped_reason` null, `next_worker_actions` `["feedback"]`

The launch was detached with `setsid nohup … < /dev/null &` and a plain redirect. The supervisor
survived the worker turn, reaped the Panogen child itself, and wrote `attempt_result.json`,
`resource_samples.jsonl`, `stdout.log` and `stderr.log` normally. No receipt or ledger event was
written by hand; the only worker-side write was the polling observer (`/tmp/opencode/issue174_watch.py`,
not committed).

State-machine note: in this revision `awaiting_feedback` flips true as soon as `attempt_started` is
recorded, before inference finishes. The observer therefore waited for the terminal
`hunyuan_attempt_result` event rather than stopping at that early flag. No stage was advanced by the
observer; it only polled `status` every 25 s.

`feedback` was **not** run, no second attempt was made, and `manual-fallback` was not run. No winner
was selected, no room was accepted, no catalog module was admitted, and no connectivity or opening
is claimed.

## Preflight and start guard (passed)

`gpu_guard.json` (SHA-256 `22ea7fcb37c23677594610376462578e69cafb25f3d390a60f6f97c86c07d223`),
ingestion guard policy `2.3.0`:

| Check | Result |
| --- | --- |
| named-job scan | passed — policy 2.3.0 ignores non-python orchestrators (the #254 fix); no unrelated job matched |
| GPU process scan | passed; 11 graphics-only rows ignored (`xorg`, `gnome-shell`, 8× `kitty`, `firefox`, `code`), zero compute contexts |
| `compute_apps` | empty |
| start limits (ARC-credited RAM, swap, VRAM) | passed |

Start snapshot `2026-11-16T18:55:36.958465Z`:

- `ram_available_bytes` = 48,378,351,896 (45.07 GiB) = `MemAvailable` 31,144,329,216 (29.02 GiB) +
  reclaimable ZFS ARC 17,234,022,680 (16.05 GiB); threshold 32 GiB
- `swap_free_bytes` = 85,334,511,616 (79.49 GiB); threshold 16 GiB
- `gpu_free_bytes` = 11,480,858,624 (10.69 GiB) of 12,878,610,432 (11.99 GiB); threshold 8 GiB

The GPU lock was acquired without waiting and `execution_guard.json` recorded `passed` at
`18:55:37.137938Z` before the child started (SHA-256
`fcaba197c8ae3ab243f1cb3c29f54f9a8b2e811ff68f2e0f63d5e4e6cc7b718c`).

## Resources actually observed

The runner sampler ran for the whole attempt: 185 one-second samples
(`resource_samples.jsonl`, SHA-256 `9169fbc4466fc3147833e25085ef395c069be69916ccc162211a51fa901db359`).

| Metric | Observed value |
| --- | --- |
| Peak process-group RSS | 40,304,025,600 bytes (37.54 GiB) |
| Peak GPU memory used | 1,675,624,448 bytes (1.56 GiB) |
| Minimum credited RAM | 35,718,544,080 bytes (33.27 GiB); runtime floor 8 GiB |
| Minimum free swap | 75,088,146,432 bytes (69.93 GiB); runtime floor 16 GiB |
| Minimum free VRAM | 10,770,972,672 bytes (10.03 GiB); runtime floor 2 GiB |
| `stop_reason` | `null` — no stop condition tripped |

## Ledger events

All bound to manifest `28c01ed69ccbe6acc9854b659cbfb3a8b902903a6257542bb289f9a042b8f77f`.
Events 9–10 (earlier block and its operator-authorized retry) are unchanged and remain in the log.

| Sequence | Event | Occurred (UTC) | Summary |
| --- | --- | --- | --- |
| 11 | `hunyuan_guard_passed` | `2026-11-16T18:55:37.036405` | `gpu_guard.json` receipt |
| 12 | `hunyuan_attempt_started` | `2026-11-16T18:55:37.219470` | `attempt-001-retry-001`, config + receipts |
| 13 | `hunyuan_attempt_result` | `2026-11-16T18:58:56.151836` | `produced`, 198.845 s, 1 output |

`events.jsonl` now has 13 events (3 added by the runner this run); SHA-256
`0946a77b3d0b9862d7e2f7b394637efb66165fd7ce1bc27666906b5dc7bda1b5`. The log is append-only and
was written only by the runner.

## Outputs

Under `godot_walk/source_library/sources/video-d92fc1fa764aa3a2/hunyuan/attempt-001-retry-001/`:

| Path | SHA-256 |
| --- | --- |
| `attempt_config.json` (3,182 bytes) | `bc239cda9c64effcaa286c97eb146ccd05f66c689bfe0f78b1cd74d3a16047aa` |
| `attempt_result.json` (1,467 bytes) | `98bb6deff7f89cef7c93ef8f73eea044e272a7aa8b8d756cbeceb4954e92fbd1` |
| `gpu_guard.json` (3,003 bytes) | `22ea7fcb37c23677594610376462578e69cafb25f3d390a60f6f97c86c07d223` |
| `execution_guard.json` (1,007 bytes) | `fcaba197c8ae3ab243f1cb3c29f54f9a8b2e811ff68f2e0f63d5e4e6cc7b718c` |
| `panorama/panorama.png` (240,806 bytes, 512x256 RGB) | `f9c95477644ed77038775ec23a99c3573db78c0d06e991ace76796b5a57b283b` |
| `resource_samples.jsonl` (74,225 bytes) | `9169fbc4466fc3147833e25085ef395c069be69916ccc162211a51fa901db359` |
| `stdout.log` (131 bytes) | `022e240a8a36eccb82cb85828e1adc60d43fb25bbee2e81d7ee363361654e718` |
| `stderr.log` (13,984 bytes) | `930219bfaf3d7dd8454f000bea2d46239700abc5b14c0e751fbde68e85c4fdae` |

`stdout.log` contains the offload validation line only. `stderr.log` contains the diffusers
progress bars, the expected offline-cache message, the LoRA warning, the CLIP truncation notice and
no traceback.

## Prompt

Fifty-one words, derived only from what the selected seed shows. The burned-in blue-violet film tint
was read as the scene's colour; no glitch, letterbox bar or watermark was described, and nothing was
cropped, edited or replaced.

> A blue-toned outdoor garden at dusk, seen looking upward: a weathered stone angel statue, draped
> and winged, among dark evergreen trees and bare branching limbs against a pale overcast sky in
> soft cool light. One continuous outdoor scene with unbroken natural forms; no people, no text,
> no signage, no added objects.

**CLIP length:** the tokenizer reported
`Token indices sequence length is longer than the specified maximum sequence length for this model (81 > 77)`,
but the truncated tail is only the pipeline's own quality suffix
`CLIP truncated input (max_length=77): ['clear, 8 k']`. The entire 51-word description, including
the coherence and no-people/no-text clause, is inside the 77-token window and reached the text
encoder.

## Preview render

`hunyuan_panorama_preview.gd` (scene `godot_walk/scenes/hunyuan_panorama_preview.tscn`) was run in
the repository dev shell:

```bash
nix develop --command bash -c 'cd godot_walk &&
  HUNYUAN_PANORAMA_PATH="$PWD/source_library/sources/video-d92fc1fa764aa3a2/hunyuan/attempt-001-retry-001/panorama/panorama.png" \
  HUNYUAN_CAPTURE_DIR="$PWD/evidence/2026-11-16-issue-174-hunyuan/panorama-views" \
  timeout 180 godot4 --path . scenes/hunyuan_panorama_preview.tscn'
```

Exit 0; four yaw-bank views printed (`PANORAMA_VIEW: forward|right|back|left`) and written to
`godot_walk/evidence/2026-11-16-issue-174-hunyuan/panorama-views/`. The PNGs are gitignored by
`.gitignore` (`godot_walk/evidence/**/*.png`) and are local review aids only. The forward/right/
left views are close, heavily blurred crops of the tree canopy; the equirect source itself is the
clearer overview.

## The panorama against the seed (honest description)

**What carried over.** The setting is still an outdoor, tree-filled scene under cool blue light.
The seed's leafless, sprawling branches and blue-violet cast are recognisable, and there are no
people, no text, no signage and no interior furniture in the panorama.

**Geometry drift.** The seed is a tight, low-angle upward shot: a weathered grey stone angel with a
bowed hooded head and folded wings fills the lower-left foreground, one dark evergreen mass sits to
the left, and bare limbs cross a pale sky. The panorama is a level, wide winter park: flat
snow-covered ground, a roughly regular grid of bare trunks, a dark wooden bench near the centre,
an open pale-blue sky and a low warm sun at the far left. The angel statue is **absent entirely**;
the low upward framing, the evergreen mass and the specific branch shapes are gone. There is no
doorway or opening of any kind.

**Invented content.** The snow ground, the bench, the low sun, the distant treeline/hills at the
wrap, the repeated tree grid and the flat horizon are all additions not present in the seed. No
watermark, letterbox bar or video glitch was reproduced.

**Missing content.** The defining stone angel, the dark evergreen and the tight upward composition.
The seed shows no legible floor or ceiling; the panorama supplies a full snow floor and a wide sky.

**Exposure and colour.** Seed: mean luminance 104.3, median 82.0, 95th percentile 209.7, channel
means R/G/B 95.8/104.0/132.8, 0.0 % of pixels below luminance 16. Panorama: mean luminance 110.8,
median 132.9, 95th percentile 175.3, channel means 82.2/113.6/167.4, 1.0 % below 16. The panorama
is bluer and more saturated in blue, with a brighter median but a compressed highlight range (the
seed's pale sky is brighter than anything in the panorama).

**Seams and projection.** The 2:1 wrap is not perfectly smooth: the mean absolute difference
between the first and last pixel columns is 12.38 levels, slightly above the 10.64-level average
between adjacent columns. That is a mild seam at the wrap, not a hard cut. As usual for equirect,
the poles smear branches into radial streaks at the top and bottom edges, and the close canopy in
the right/back/left preview views shows wavy trunks and softened, sometimes doubled branch edges.

**Resolution.** 512x256 is soft by design; the 1152x644 preview views are visibly blurred and the
bench and trunks read only as coarse shapes. This is a plausible on-genre winter-park panorama and a
loose reinterpretation of the seed's trees and blue tone, but it is not a reconstruction: its
defining statue was lost and snow, a bench and a low sun were invented. The seed is an outdoor
statue shot, not a bounded interior, so no room candidate, doorway or connectivity is implied.
Whether this is useful as atmosphere reference is the operator's call.

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

## Checks and reproduction

- `python3 godot_walk/scripts/register_video_sources.py validate` → `{"valid": true, "registered_count": 13}`
- `python3 -m pytest -q godot_walk/scripts` → 1530 passed, 5 skipped, 67 subtests passed

```bash
python3 godot_walk/scripts/source_ingestion_runner.py status video-d92fc1fa764aa3a2
python3 godot_walk/scripts/register_video_sources.py validate
python3 -m pytest -q godot_walk/scripts
```

```bash
setsid nohup python3 godot_walk/scripts/run_source_hunyuan.py video-d92fc1fa764aa3a2 \
  --prompt "$(cat /tmp/opencode/issue174-seed-prompt.txt)" > /tmp/issue174-run.log 2>&1 < /dev/null &
# runner defaults: 512x256, seed 42, 2700 s, sequential_cpu
```
