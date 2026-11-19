# Issue #283 variant-pair evidence — commands

Run all commands from the workspace root. No map is generated, no catalog entry
is changed, and no integration or tested-status decision is made by these
commands.

## Headless walk test

```bash
godot4 --headless --path godot_walk \
  --script res://evidence/2026-11-19-issue-283-variant-pairs/test_variant_pairs.gd
```

Passes with `ISSUE283_VARIANT_PAIR_TESTS_PASSED`. Per-pair nominal assertions
plus both negative controls run for each of the four chains. The machine-readable
receipt is `mechanics/traversal.json` (create-only; delete it before a rerun).

## Paired captures (guarded, DISPLAY=:1 only)

`--headless` is not usable for captures. Rendering goes through the guarded
wrapper, which takes the shared GPU lock, checks headroom and refuses to
overwrite existing output.

```bash
DISPLAY=:1 python3 godot_walk/evidence/2026-11-19-issue-283-variant-pairs/run_capture_guarded.py \
  --output-dir godot_walk/evidence/2026-11-19-issue-283-variant-pairs/captures \
  --report godot_walk/evidence/2026-11-19-issue-283-variant-pairs/capture_resource_run.json \
  -- godot4 --path godot_walk \
  --script res://evidence/2026-11-19-issue-283-variant-pairs/capture_variant_pairs.gd \
  -- --out=res://evidence/2026-11-19-issue-283-variant-pairs/captures
```

Repeatable run: remove `captures/` and `capture_resource_run.json` first; the
wrapper deliberately refuses to overwrite them.

## Repository checks

```bash
python3 -m pytest -q godot_walk/scripts
python3 godot_walk/scripts/register_video_sources.py validate
python3 -m ruff check godot_walk/evidence/2026-11-19-issue-283-variant-pairs/run_capture_guarded.py
```

## Files touched

Only new files under `godot_walk/evidence/2026-11-19-issue-283-variant-pairs/`.
Neither room, the catalog, nor any hash-pinned file was edited.
