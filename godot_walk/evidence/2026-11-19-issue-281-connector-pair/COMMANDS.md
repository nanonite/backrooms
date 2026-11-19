# Issue #281 connector-pair test — commands

Run all commands from the workspace root. No map is generated, no catalog entry
is changed, and no integration decision is made by these commands.

## Headless walk test

```bash
godot4 --headless --path godot_walk \
  --script res://evidence/2026-11-19-issue-281-connector-pair/test_connector_pair.gd
```

Passes with `ISSUE281_CONNECTOR_PAIR_TESTS_PASSED`. The machine-readable receipt
is `mechanics/traversal.json` (create-only; delete it before a rerun).

## Paired captures (guarded, DISPLAY=:1 only)

`--headless` is not usable for captures. Rendering goes through the guarded
wrapper, which takes the shared GPU lock, checks headroom and refuses to
overwrite existing output.

```bash
DISPLAY=:1 python3 godot_walk/evidence/2026-11-19-issue-281-connector-pair/run_capture_guarded.py \
  --output-dir godot_walk/evidence/2026-11-19-issue-281-connector-pair/captures \
  --report godot_walk/evidence/2026-11-19-issue-281-connector-pair/capture_resource_run.json \
  -- godot4 --path godot_walk \
  --script res://evidence/2026-11-19-issue-281-connector-pair/capture_connector_pair.gd \
  -- --out=res://evidence/2026-11-19-issue-281-connector-pair/captures
```

Repeatable run: remove `captures/` and `capture_resource_run.json` first; the
wrapper deliberately refuses to overwrite them.

## Repository checks

```bash
python3 -m pytest -q godot_walk/scripts
python3 godot_walk/scripts/register_video_sources.py validate
python3 -m ruff check godot_walk/evidence/2026-11-19-issue-281-connector-pair/run_capture_guarded.py
```

## Files touched

Only new files under `godot_walk/evidence/2026-11-19-issue-281-connector-pair/`.
Neither room, the catalog, nor any hash-pinned file was edited.
