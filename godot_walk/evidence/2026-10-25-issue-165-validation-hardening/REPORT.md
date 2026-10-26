# Issue 165 validation hardening

## Outcome

Contract v2 adds strict checks for candidate-bound decisions, scene and spatial
metadata, receipt paths, and immutable catalog snapshots. The v1 schema, freeze,
adaptation records, decisions, and historical fingerprints remain unchanged.
Both existing adaptations pass the documented v1-to-v2 compatibility path.

Accepted decisions now require a current fingerprint/identity and a hashed
decision artifact. V2 artifacts must internally name the same adaptation,
candidate identity, and affirmative decision. The historical room-large review
uses an accepted-layout artifact without a candidate ID; its compatibility
record binds the original record and dependency fingerprint to the exact
accepted layout and tested connection. The transfer review binds its original
candidate version, dependency fingerprint, and accepted decision. Compatibility
records are derived validation bindings; they do not extend or replace operator
approval.

Validation resolves the candidate scene, controller, catalog-module scenes,
and recursive Godot external resources inside the repository, and requires
their hashes in the artifact manifest. It checks finite simple orthogonal
polygons, nondegenerate render bounds, floor inclusion, spawn capsule margin,
socket frames/clearance/approach and collision declarations. Candidate identity
includes the resolved spatial metadata, so changing footprints, render bounds,
spawn or sockets invalidates prior validation and approval.

These checks establish static consistency only. They do not prove that a scene's
rendered meshes fit its declared envelope, that declared collision nodes match
the scene, or that traversal works. Those remain Godot runtime evidence. The
validator is read-only and reports historical fingerprinted runtime receipts
without claiming a new runtime test.

Receipt IDs are restricted to stable lowercase slugs. Receipt read/write paths
are resolved and contained, symlink escapes are rejected, and creation uses
exclusive no-follow file operations. Existing stage outputs and receipts cannot
be overwritten.

Each adaptation resolves catalog modules against the frozen
`godot_psx_room_kit@0.2.0` snapshot. Unrelated additions to live `catalog.json`
do not invalidate historical records; tampering with the referenced snapshot,
module versions, scene dependencies, or decision evidence still fails.

## Migration

The original v1 freeze and the original v1 dependency fingerprints were kept
intact. Contract v2 is explicit in `video_adaptation.schema.v2.json` and
`contract_freeze_v2.json`. Two compatibility sidecars pin each original record,
decision artifact, dependency fingerprint, immutable catalog snapshot, and a
derived identity over the old decision-relevant metadata.

The transfer record's historical dependency list includes the old workflow
runner, extractor, and validator. Their exact old bytes are retained under
`adaptations/compatibility_v2/tooling_v1/`. The sidecar binds each archived hash
to the active hardened tool hash, which is itself pinned by the v2 freeze.
Candidate scene, source, texture, controller, material, evidence, and other
dependencies remain checked against their original hashes.

## Verification

- Adaptation regression suite: 21 tests passed.
- Ruff lint and format check: passed.
- Python compile check: passed.
- Both real adaptation records validated read-only; calibration flags remain
  `registration_accepted=false` and `scale_calibrated=false`.
- No GPU capture, inference, visual change, or runtime traversal was performed.

Commands:

```bash
PYTHONPATH=godot_walk/scripts python3 -m unittest discover -s godot_walk/scripts -p 'test_video_adaptation*.py' -v
ruff check godot_walk/scripts/video_adaptation_*.py godot_walk/scripts/test_video_adaptation_*.py
ruff format --check godot_walk/scripts/video_adaptation_*.py godot_walk/scripts/test_video_adaptation_*.py
python3 -m compileall -q godot_walk/scripts/video_adaptation_*.py godot_walk/scripts/test_video_adaptation_*.py
python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle godot_walk/room_catalog/adaptations/room-large-v1.json
python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle godot_walk/room_catalog/adaptations/corridor-corner-v2.json
```
