# Issue 165: conditional resource constants

## Finding and fix

The resource scanner previously accepted the first quoted string in a
constant declaration even when the declaration was an expression, such as a
conditional. A later `load(TARGET)` could therefore hide a runtime-selected
resource from the dependency manifest.

The scanner now treats a constant as static only when its complete declaration
is one unescaped string literal. Expression-valued constants are not partially
evaluated; a resource call using one must have an explicit dynamic-resource
declaration listing its possible targets. Each target must exist and be
fingerprinted. This is deliberately conservative static analysis, not a full
GDScript evaluator.

The full-bundle regression reproduces the conditional constant, first with the
selected resource omitted and no declaration, then with a declaration that
still omits that resource, and finally with all declared targets fingerprinted.
The first two bundles fail; the complete bundle passes.

## Versioning

Validator freeze v4 is a successor to v3. It pins the updated contract and
resource-graph tools, preserves the exact v3 versions under
`room_catalog/archives/contract_v3/`, and binds the v3 manifest and sidecar by
hash. Existing v1/v2/v3 adaptation schemas, records, candidate identities,
operator decisions and runtime receipts remain unchanged. The v4 successor
does not broaden historical approval. Calibration flags remain false.

## Verification

- Adaptation suite: **36 passed**.
- GPU/resource guard regressions: **2 passed**.
- Ruff lint, Ruff format check, Python compile checks, `git diff --check`, and
  v1–v4 freeze sidecar checks passed.
- Both real adaptation bundles passed read-only validation through the
  successor validator; candidate identities remain the recorded values.
- No GPU capture, Godot runtime traversal, inference, or visual change was run.

Commands:

```bash
PYTHONPATH=godot_walk/scripts python3 -m unittest discover -s godot_walk/scripts -p 'test_video_adaptation*.py' -v
PYTHONPATH=godot_walk/scripts python3 -m unittest discover -s godot_walk/scripts -p 'test_psx_design_round_resources.py' -v
ruff check godot_walk/scripts/video_adaptation_*.py godot_walk/scripts/test_video_adaptation*.py
ruff format --check godot_walk/scripts/video_adaptation_*.py godot_walk/scripts/test_video_adaptation*.py
python3 -m compileall -q godot_walk/scripts/video_adaptation_*.py godot_walk/scripts/test_video_adaptation*.py
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle godot_walk/room_catalog/adaptations/room-large-v1.json
PYTHONPATH=godot_walk/scripts python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle godot_walk/room_catalog/adaptations/corridor-corner-v2.json
```

Changed paths for this final gap: `scripts/video_adaptation_resource_graph.py`,
`scripts/video_adaptation_contracts.py`, the runtime dependency regression
tests, the v3 source archives, `room_catalog/contract_freeze_v4.*`,
`room_catalog/video_adaptation_validator_v4.md`, and this report. No room,
source, decision, or runtime evidence artifact changed. Issue #165 remains open
for operator review.
