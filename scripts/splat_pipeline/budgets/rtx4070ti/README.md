# Verification artifacts for `budgets/rtx4070ti/`

Evidence behind the numbers in `HARDWARE_BUDGET.md`, so a reviewer can check a
claim instead of taking it on trust. Every file is raw command output; the header
of each records the exact commit, command, interpreter and date it came from.

## Test results

| File | Commit under test | Command | Result |
|---|---|---|---|
| `pytest_new_tests.txt` | `HEAD` (this task) | `pytest` over the 7 new test files | **134 passed, 1 skipped** |
| `pytest_full_suite.txt` | `HEAD` (this task) | `pytest scripts/splat_pipeline/tests/ -q` | **18 failed, 315 passed, 1 skipped** |
| `pytest_baseline_before_task.txt` | `HEAD~1` (before this task) | `pytest scripts/splat_pipeline/tests/ -q` | **18 failed, 181 passed** |

**The 18 failures are pre-existing.** They are byte-identical in both runs:
`test_train_brush` 12, `test_cull_blurry` 4, `test_stage_assets` 2. This task
introduced none and fixed none.

**This task adds 135 tests and changes no existing test's outcome.** The
arithmetic is exact: 181 passing before + 134 new = 315 passing after, with the
single skip belonging to the new set.

The one skip is `test_a_real_splat_asset_reports_a_plausible_count`, which
checks a 45 MB `.ply` asset that is not tracked in git. It skips rather than
fails when the asset is absent, because a benchmark's reader must not depend on
an asset a fresh checkout does not have.

### A number in the first report of this task was wrong

An earlier worker report claimed "403 passed" for the full suite. That number came
from the shared working tree, which also contains task #83's untracked
`test_splat_frame.py` — 403 − 315 = 88 tests that are **not** part of this commit.

**315 passed is the number that describes this commit.** The raw output above is
what the claim should have been checked against, and should have been committed
from the start rather than reported from a terminal.

### Reproducing

```bash
mkdir /tmp/verify && git archive HEAD | tar -x -C /tmp/verify
cd /tmp/verify && python3 -m pytest scripts/splat_pipeline/tests/ -q

mkdir /tmp/verify_base && git archive HEAD~1 | tar -x -C /tmp/verify_base
cd /tmp/verify_base && python3 -m pytest scripts/splat_pipeline/tests/ -q
```

`git archive` is used rather than a working-tree copy so the run sees exactly
what is committed and nothing another task has left uncommitted. Durations and the
skip count may differ on re-run; the pass and fail counts should not.

## Measurement artifacts

| File | Contents |
|---|---|
| `measurements.json` | every stage attempted: exact argv, interpreter, exit code, peak VRAM/RAM, elapsed, splat count, fps, and for failures the log tail |
| `preflight.json` | hardware snapshot, three capability probes, four stage verdicts, budgets |
| `splatfacto_failed.log` | the full Splatfacto failure (gsplat CUDA build) |