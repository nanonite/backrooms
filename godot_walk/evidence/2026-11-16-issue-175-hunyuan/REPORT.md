# Issue #175 — Hunyuan Panogen attempt-001: BLOCKED AT PREFLIGHT (no inference ran)

Date: 2026-11-16 (UTC)
Source: `video-102caf53423018b7` — `data/videos/corridor_straight.mp4`
Source SHA-256: `102caf53423018b75dfd1976b5a2346b0576bdd316429f246aee87a884ba3d4b`
Manifest: `source_manifest-v3.json`, SHA-256 `6c4863b240d035cdc52b78fc6a33b79dc07b610df5d6663d19cc8f6f7364d626`
Seed: `frame_0013`, index 12, 0.5 s, SHA-256 `a836cd3e2f90deb9bbf5ad3f23fe09fba156199f315e307a02fe332bb5eb38f1` (unedited direct decode, 1920x1080)
Authorization: operator decision 2026-11-16 (issue #175, comment 599) — "Hunyuan attempt 1 of 3 approved ... Run one attempt, then stop for operator review".

## Result: the single authorized attempt never started

The launch was performed exactly as directed: detached with `setsid nohup … < /dev/null &`, plain redirect, no tee/pipes, log and prompt-file names without the restricted word, runner defaults (512x256, seed 42, 2700 s, `sequential_cpu`). The supervisor was alive, ran the preflight, and **refused to start** the Panogen child at the named-job guard.

- Attempt id assigned but not consumed: `attempt-001`
- Launched: `2026-11-16T18:26:49Z`; preflight blocked: `2026-11-16T18:26:50.091094Z` (~1 s later)
- `status`: `blocked`; attempt never started; **no panorama, no runtime, no resource samples**
- `attempts_used` after this run: **0 / 3** — the cap was not consumed and no second attempt was made
- Post-run `status`: `awaiting_feedback` false, `can_start_attempt` false, `stopped_reason` set (preflight block), `manual_fallback_allowed` true, `next_worker_actions` `["manual-fallback"]`

`feedback`, a second attempt, and `manual-fallback` were **not** run. No winner was selected, no room accepted, no catalog module admitted, no connectivity inferred.

## Exact error

```
GPU preflight blocked by active job(s): 2453891 ... chainlink-loop --task 174,175,176,177,178 ... --prompt <the operator direction verbatim>, 2533912 ... opencode run --standalone ... --title "Chainlink 175 worker" <the operator direction verbatim>
```

Full text: `/tmp/issue175-run.log`, and the runner-written receipts `…/hunyuan/attempt-001/gpu_guard.json` and event 6 below.

## Root cause (environmental, not a code/model failure)

`psx_design_round_resources._active_named_jobs()` scans `ps -eo …args` and matches any non-ancestor process whose command line contains the restricted token (with a single carve-out for one review-server script). `_ancestor_pids()` excludes only the runner's own parent chain.

The mandated `setsid` launch reparents the runner into a new session, so the harness's own long-lived processes are **not** ancestors and are therefore scanned as "active jobs":

- the `chainlink-loop --task 174,175,176,177,178` plugin process, whose `--prompt` argument is the operator direction verbatim (which contains the restricted token several times), and
- this worker's own `opencode run …` process, whose arguments carry the same operator direction.

Both therefore match the named-job regex and block the guard. The worker process command line is harness-owned and cannot be changed by this task, so with a detached launch the preflight cannot pass in this environment. Resolving it requires a human decision (e.g. re-launching the loop with a prompt that does not carry the restricted token, or adjusting the ancestor/exemption logic in the guard) — neither of which this worker may do: the direction forbids bypassing, retrying or editing the guard, and forbids `manual-fallback`.

Note: in issue #172 the same detached launch passed because no non-ancestor process there carried the restricted token in its command line. The difference here is the verbatim operator direction in the loop/worker command lines.

## Ledger and outputs (all written by the runner, none by hand)

Event 6, bound to the current manifest hash:

| Sequence | Event | Occurred (UTC) | Summary |
| --- | --- | --- | --- |
| 6 | `hunyuan_preflight_blocked` | `2026-11-16T18:26:50.173019` | named-job guard blocked launch; `gpu_guard.json` receipt |

`events.jsonl` now has 6 events. Files written under the source folder:

| Path | Note |
| --- | --- |
| `godot_walk/source_library/sources/video-102caf53423018b7/hunyuan/attempt-001/attempt_config.json` | runner-written attempt config |
| `godot_walk/source_library/sources/video-102caf53423018b7/hunyuan/attempt-001/gpu_guard.json` | runner-written guard receipt, status `blocked` |

No `panorama/`, `attempt_result.json`, `execution_guard.json`, `resource_samples.jsonl`, `stdout.log` or `stderr.log` exists — the child was never started.

## Prompt (prepared, not consumed by an inference)

55 words, derived only from the selected seed, which was viewed but not cropped, edited or replaced. The seed shows a carpeted, wallpapered indoor corridor with a suspended lit ceiling and a large square pillar; no windows, people, text or signage. No glitches, letterbox bars or watermark were described.

> An indoor carpeted corridor with a yellow speckled carpet floor, pale green chevron wallpaper on dividing walls, and a suspended ceiling grid with glowing rectangular light panels. A large square beige pillar stands on the left. The walls and ceiling lines run continuously into the distance. No windows. No people, text, signage or added objects.

Helper files (not committed): prompt `/tmp/issue175-prompt.txt`; polling observer `/tmp/opencode/issue175_watch.py` (neither path nor contents contain the restricted word).

## Panorama vs seed

No panorama was produced, so there is nothing to compare: no seams, drift, invented objects or resolution to report. The seed itself (viewed for the prompt) is a single straight carpeted corridor receding ahead with a large square pillar the camera passes at 0–2.25 s; no doorways, room boundaries, openings or connectivity are observed or claimed.

## Checks

- `python3 godot_walk/scripts/register_video_sources.py validate` → `valid: true`, 13 sources.
- `python3 godot_walk/scripts/source_ingestion_runner.py status video-102caf53423018b7` → `attempts_used` 0, `stopped_reason` set, next `manual-fallback` (not run).
- `registration_accepted` and `scale_calibrated` remain `false` in the manifest.
- Hash-pinned files (`scripts/player.gd`, `project.godot`, library room scenes, `catalog.json`, `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`) untouched.

## Escalation

Blocked, awaiting operator decision. See the `ESCALATION:` comment on issue #175. The task is **not** complete; no inference result exists for the operator to review.
