# Issue #173 — Hunyuan Panogen attempt-001 (corridor panorama produced)

Date: 2026-11-16 (UTC)
Source: `video-d857abe7a94da9d1` — `data/videos/Max Cooper - Repetition (Official Video By Kevin McGloughlin).mp4`
Source SHA-256: `d857abe7a94da9d19a4a1410a707e7632c32df6f3ded1ddd4d77317df1732bb8`
Manifest: `source_manifest-v3.json`, SHA-256 `87bc8e05cbdd34bb8cfc9a016b05dd17a552a5b0a69711215999b0453f7cd93e`
Seed: `frame_6721`, index 6720, 280.0 s, SHA-256 `5e0e9c637b1df13ded90d05789b51a9bbae78a19f387a1eb87299b5f1b314208`
(unedited direct decode, 1280x720)
Authorization: operator decision 2026-11-16 (issue #173, comment 597) — "Hunyuan attempt 1 of 3
approved for this source (local GPU, no USD ceiling). #172 proved the detached launch. Run one
attempt, then stop for operator review; operator picks winners and admits rooms."

This is the first started inference for this source. The seed is the lit corridor/tunnel at 280 s
that the 2026-11-14 ranking report called "the clearest interior" (it ranked 29 because most of the
frame is dark); the operator selected it on 2026-11-14 (event 7).

## Result

**The single authorized attempt ran to completion and produced a 512x256 equirectangular panorama.**

- Attempt id: `attempt-001`
- Run id: `run-89760dc3b39d42b7865cb3001cda2596`
- Started: `2026-11-16T17:52:56.922763Z` (event 9, `hunyuan_attempt_started`)
- Result recorded: `2026-11-16T17:56:28.804307Z` (event 10, `hunyuan_attempt_result`)
- Runtime: **211.754 s** (3 min 31.8 s) of the 2700 s budget; `return_code` 0; `status` `produced`
- Diffusers progress: fp8 quantization of 1279 modules in ~20 s, then denoising 50/50 steps in
  2:19 at ~2.40 s/it (2.79 s/it average including the first step)
- Attempts used after this run: **1 / 3**
- `status`: `awaiting_feedback` true, `can_start_attempt` false, `manual_fallback_allowed` false,
  `stopped_reason` null, `next_worker_actions` `["feedback"]`

The supervisor survived the worker turn. The launch was detached with `setsid nohup … < /dev/null &`
and a plain redirect; no receipt or ledger event was written by hand. The worker-side polling
observer (`/tmp/opencode/issue173_watch.py`, not committed) read only the ledger and the runner
status and stopped as soon as the result event appeared. The prompt file and polling script paths
avoided the preflight-blocked job name; the supervisor itself is an ancestor of the preflight
process, which the named-job scan excludes by design (as in #172).

`feedback` was **not** run, no second attempt was made, and `manual-fallback` was not run. No
winner was selected, no room was accepted, no catalog module was admitted, and no connectivity or
opening is claimed.

## Preflight and start guard (passed)

`gpu_guard.json` (SHA-256 `e1654327…4bcd9`), policy `2.2.0`:

| Check | Result |
| --- | --- |
| named-job scan (`_active_named_jobs`) | passed (no unrelated process matched) |
| GPU process scan | passed; 9 graphics-only rows ignored (`xorg`, `gnome-shell`, 6× `kitty`, `firefox`), zero compute contexts |
| `nvidia-smi --query-compute-apps` | empty |
| start limits (ARC-credited RAM, swap, VRAM) | passed |

Start snapshot `2026-11-16T17:52:56.657162Z`:

- `ram_available_bytes` = 51,310,673,576 (47.79 GiB) = `MemAvailable` 20,317,646,848 (18.92 GiB) +
  reclaimable ZFS ARC 30,993,057,984 (28.86 GiB); threshold 32 GiB
- `swap_free_bytes` = 84,834,279,424 (79.01 GiB); threshold 16 GiB
- `gpu_free_bytes` = 11,383,341,056 (10.60 GiB) of 12,878,610,432 (11.99 GiB); threshold 8 GiB

The GPU lock was acquired without waiting and `execution_guard.json` recorded `passed` at
`17:52:56.842958Z` before the child started (SHA-256 `31264da6…206ad`).

## Resources actually observed

The runner sampler ran for the whole attempt: 198 one-second samples
(`resource_samples.jsonl`, SHA-256 `4b804d4b…a8f04`).

| Metric | Observed value |
| --- | --- |
| Peak process-group RSS | 34,908,454,912 bytes (32.51 GiB) |
| Peak GPU memory used | 1,698,693,120 bytes (1.58 GiB) |
| Minimum credited RAM | 35,213,607,472 bytes (32.79 GiB); runtime floor 8 GiB |
| Minimum free swap | 72,913,043,456 bytes (67.90 GiB); runtime floor 16 GiB |
| Minimum free VRAM | 10,747,904,000 bytes (10.01 GiB); runtime floor 2 GiB |
| `stop_reason` | `null` — no stop condition tripped |

The RSS peak is higher than #172's 20.78 GiB: this attempt reached 32.51 GiB, slightly above the
32 GiB *start* threshold, which only gates the start snapshot; the runtime floor is 8 GiB, and no
stop condition tripped. Sampled fully by the supervisor; nothing was reconstructed.

## Ledger events

All bound to manifest `87bc8e05cbdd34bb8cfc9a016b05dd17a552a5b0a69711215999b0453f7cd93e`.

| Sequence | Event | Occurred (UTC) | Summary |
| --- | --- | --- | --- |
| 8 | `hunyuan_guard_passed` | `2026-11-16T17:52:56.740037` | `gpu_guard.json` receipt |
| 9 | `hunyuan_attempt_started` | `2026-11-16T17:52:56.922763` | attempt `attempt-001`, config + receipts |
| 10 | `hunyuan_attempt_result` | `2026-11-16T17:56:28.804307` | `produced`, 211.754 s, 1 output |

`events.jsonl` now has 10 events. Earlier events 1–7 are unchanged: registration, manifest v3,
review-source `proceed` (comment 557), three frame extractions, and the operator `select-seed`
(frame_6721).

## Outputs

| Path | SHA-256 |
| --- | --- |
| `…/hunyuan/attempt-001/panorama/panorama.png` (159,546 bytes, 512x256 RGB) | `01d5a7ebdb971ef24a783201d7013275db56165fe099a447c18d6d1047095693` |
| `…/attempt-001/attempt_config.json` | `956a63848b86a37cc48261c601c906560bf1d4c70cb0ab14a822150c7ddb81df` |
| `…/attempt-001/attempt_result.json` | `98c7ce7183d36459ffb5acb9cdeb7fc00c13e8176c5547b9579c5a2ef6576a49` |
| `…/attempt-001/gpu_guard.json` | `e1654327188c00a12c8afbdccf7fb62a68e313d1c23d7e1c842c4d7045eb4cd9` |
| `…/attempt-001/execution_guard.json` | `31264da614569475ccc4218f660d49b2687cffd4638a3f66d2bb4f0bb02206ad` |
| `…/attempt-001/resource_samples.jsonl` | `4b804d4b4192e47b70c9cf4f05115fd8b03c3d9b536b527bb1176e41005a8f04` |
| `…/attempt-001/stdout.log` | `022e240a8a36eccb82cb85828e1adc60d43fb25bbee2e81d7ee363361654e718` |
| `…/attempt-001/stderr.log` | `53b74b44be25d5af641b79e72b6848bf96cafc08961376d82e706fc5cd9d76c8` |

`stdout.log` contains the offload validation line only. `stderr.log` contains the diffusers
progress bars, the expected offline-cache message, the LoRA warning, the CLIP truncation notice
and no traceback. Config: 512x256, seed 42, FOV 80° (pinned upstream default; source camera FOV
unmeasured), `sequential_cpu` offload, VAE tiling, fp8 attention/gemm, true CFG 1.0, offline cache.

## Prompt

Fifty-three words, derived only from what the selected seed shows; nothing was cropped, edited or
replaced.

> A long symmetrical indoor corridor in darkness: glossy black walls with tall vertical white light
> panels, mirror-black reflective floor, dark ceiling with thin transverse strip lights. The passage
> converges on a broad glowing white far wall, brightly overexposed. Continuous unbroken wall, floor
> and ceiling lines; no people, no text, no signage, no furniture.

**CLIP length:** the CLIP tokenizer gives 74 tokens for the prompt (under the 77-token window).
The pipeline appends its own quality suffix, so the log reports
`Token indices sequence length is longer than the specified maximum sequence length for this model (88 > 77)`
and `CLIP truncated input (max_length=77): [', high - resolution, sharp, clear, 8 k']` — only the
suffix was cut, no part of the description was lost.

The seed is a dark corridor with vertical illuminated strips and a blown-out far end. It contains no
people, no text or signage and no furniture, so the prompt says so explicitly rather than inventing
them. The far end is described as a glowing wall, not as a doorway or opening; no connectivity is
implied.

## Preview render

`hunyuan_panorama_preview.gd` (scene `godot_walk/scenes/hunyuan_panorama_preview.tscn`) was run in
the repository dev shell:

```bash
nix develop --command bash -c 'cd godot_walk &&
  HUNYUAN_PANORAMA_PATH="$PWD/source_library/sources/video-d857abe7a94da9d1/hunyuan/attempt-001/panorama/panorama.png" \
  HUNYUAN_CAPTURE_DIR="$PWD/evidence/2026-11-16-issue-173-hunyuan/panorama-views" \
  timeout 180 godot4 --path . scenes/hunyuan_panorama_preview.tscn'
```

Exit 0, four yaw-bank views printed (`PANORAMA_VIEW: forward|right|back|left`) and written to
`godot_walk/evidence/2026-11-16-issue-173-hunyuan/panorama-views/`. Those PNGs are gitignored by
`.gitignore` (`godot_walk/evidence/**/*.png`) and are local review aids only.

## The panorama against the seed (honest description)

**What carried over.** The defining motif survives: a dark, symmetrical, man-made corridor whose
walls carry tall bright vertical strips, with a bright rectangle at the end of the axis. The
panorama is built as nested rectangular light frames receding to a cream-coloured centre panel, so
the "repetition" reading of this music-video source is very strong: the corridor appears to repeat
in depth. The left and right preview views show near-black wall panels with vertical light strips
and a faint horizontal panel seam, which is close to the seed's ribbed wall rhythm. There are no
people, no text, no signage and no furniture in the panorama.

**Geometry drift.** The seed is a single, fairly short corridor shot with strong glossy floor
reflections: the floor mirrors the vertical strips as long horizontal streaks, and the far end is a
broad blown-out white field that occupies much of the frame width. The panorama flattens this into
concentric outline frames. The bright centre panel is small (about 44 x 39 px of the 512 x 256
equirect, mean RGB 153/149/132) and dull cream, not the seed's white-clipped bloom, so the far end
reads as a flat lit panel closing a box tunnel rather than as a bright opening. The seed's
mirror-black floor and its reflected strip pattern are essentially absent: the lower half of the
equirect is near-black with only the ring outlines and faint diagonal surface banding. The visible
floor is therefore not glossy or reflective, and the ceiling's transverse strips are reduced to
ring edges rather than distinct fixtures.

**Invented content.** The concentric ring framing itself (a tunnel of repeated rectangular frames
is a plausible reading of the seed's receding panels, but the seed shows a handful of wall bays,
not a dozen nested frames), faint grey-brown surface mottling and small warm smudges on the dark
walls, and the near-black surface behind the camera (the back preview view is almost featureless).
No watermark, letterbox bar or video glitch was reproduced.

**Missing content.** The seed's glossy floor reflections, the bloom around the far light, the
visible depth cueing of individual wall bays, and any legible surface material on floor, walls or
ceiling. Where the seed has broad white illuminated wall strips, the panorama mostly has thin white
lines.

**Exposure and colour.** The panorama is darker overall, cooler in tint and much dimmer in its
highlights. Mean luminance 29.8 against the seed's 79.7; median 17.3 against 33.1;
95th percentile 140.1 against 220.4. Deep shadow (luminance < 16) covers 22.2 % of the panorama
against 34.5 % of the seed, but the seed spends its bright tail on large overexposed areas, while
the panorama puts only 5.3 % of pixels above 128 and 1.1 % above 240 (those are the ring lines).
Channel means are R/G/B 26/31/33 (a cool grey) against the seed's 78/81/77 (near-neutral grey).

**Seams and projection.** The 2:1 wrap is smooth: mean absolute difference between the first and
last pixel columns is 0.77 levels, far below the 6.07-level average between adjacent columns, so
there is no hard cut. The visual defect is instead a broken outline: the outermost ring is
fragmented into dashed segments at the left and right sides of the equirect, and the corner joins of
the frames show stair-stepped, uneven line thickness. Wall/ceiling and wall/floor junctions do not
meet as continuous edges; the nested frames float on black. Poles behave as usual for equirect (the
top ring fans across the top edge and the bottom ring across the bottom edge).

**Resolution.** 512x256 is soft by design; the 1152x644 preview views are visibly blurred, the ring
lines are 1–3 px wide with aliasing, and the cream centre panel shows faint vertical banding and a
dark line just above its lower edge. No fine material detail survives.

In short: an on-motif, very dark "infinite corridor" panorama that preserves the seed's vertical
light strips and bright far end as a repeated frame pattern, but not the seed's glossy reflective
floor, bloom or surface material. Whether that is usable as a room candidate — or only as
rhythm/repetition reference for the generative map, which the issue flagged as the likely value of
this abstract source — is the operator's call.

## Checks

- `python3 godot_walk/scripts/register_video_sources.py validate` → valid, 13 sources.
- `python3 -m pytest -q godot_walk/scripts` → 1527 passed, 5 skipped, 1 failed:
  `test_source_ingestion_policy.py::RecordedHistoryReplayTests::test_recorded_retry_history_records_the_started_failure`.
  That failure is **pre-existing and unrelated**: it replays the committed `video-c9115d943f6c3fe4`
  ledger, which gained `hunyuan_operator_feedback` for attempt-002 in commit `a5a6243`, so
  `awaiting_feedback` is now false where the test still expects true. The file was not modified by
  this task; fixing the stale expectation was left out of scope.
- `registration_accepted` and `scale_calibrated` remain `false` in the manifest.

## What was not done

- No `feedback` event (operator review is pending).
- No second attempt, no `manual-fallback`, no prompt or seed change. Attempts used: 1 / 3.
- No `select-winner`, no room candidate, no accepted room, no catalog admission, no generative-map
  metadata record.
- No connectivity or opening is claimed or inferred.
- Hash-pinned files (`scripts/player.gd`, `project.godot`, library room scenes, `catalog.json`,
  `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`) were not touched.

## Reproduction

```bash
python3 godot_walk/scripts/source_ingestion_runner.py status video-d857abe7a94da9d1
python3 godot_walk/scripts/register_video_sources.py validate
python3 -m pytest -q godot_walk/scripts
```

```bash
setsid nohup python3 godot_walk/scripts/run_source_hunyuan.py video-d857abe7a94da9d1 \
  --prompt "$(cat prompt.txt)" > /tmp/issue173-run.log 2>&1 < /dev/null &
# runner defaults: 512x256, seed 42, 2700 s, sequential_cpu
```
