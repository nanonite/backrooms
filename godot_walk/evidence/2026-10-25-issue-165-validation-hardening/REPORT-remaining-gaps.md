# Issue 165: remaining validation gaps

## Result

All three findings in review comment #304 are addressed. The accepted room,
collision, materials, operator decisions, historical records, evidence, and v1/v2
freeze files were left unchanged. The changes are validation-only; no GPU,
capture, inference, or scene runtime job was run. Calibration flags remain
`registration_accepted=false` and `scale_calibrated=false`.

## Catalog isolation

Each historical v1 compatibility extension now binds the old
`godot_walk/room_catalog/catalog.json` dependency to the exact frozen
`godot_psx_room_kit@0.2.0` snapshot. Validation checks the old manifest path
and hash, the extension binding, the snapshot path/hash, and the snapshot bytes
against the original dependency hash. It does not read the live catalog for
those historical records. The v1 dependency lists and fingerprints were not
rewritten.

Full `validate_bundle()` integration tests cover both real adaptations with an
isolated live-catalog growth mapping and with a tampered snapshot mapping. Both
survive unrelated live-catalog growth; both reject the altered snapshot. The
room-large bundle also rejects missing/changed referenced module versions and
an added un-fingerprinted module dependency.

## Runtime dependencies

The bounded static resource graph follows scene/resource external references,
GDScript path-based `extends`, `preload`, direct literal `load` references,
literal string constants, explicit dynamic-load declarations, shader resources,
and quoted shader includes. It is cycle-safe. Every discovered repository file
must be hashed in the candidate dependency manifest. V1 records receive a
separately fingerprinted supplemental dependency list in the frozen v3
compatibility extension; their historic manifests and identities stay intact.

Bundle tests reproduce the missing `issue165_room_geometry.gd` preload, nested
script/material/shader-include omissions, dependency changes against accepted
approval and passed results, cycles, unresolved dynamic calls, and explicit
dynamic target coverage. A dynamic declaration is an explicit maintainer
assertion of the complete target set.

## Socket geometry

Contract v3 requires explicit floor and ceiling clearance plus an orthogonal
approach-center region for authored sockets. Static validation requires the
socket center to lie on exactly one supported perimeter edge; checks its
outward normal and complete opening width; checks floor/opening height against
the declared clearance; and checks the whole approach region is inside the
walkable polygon, has capsule-radius boundary separation, reaches the socket's
clearance band, and spans the usable doorway width. Observed openings stay
observation-only and cannot carry gameplay connector references. A rendered
AABB is not treated as a ceiling measurement.

Tests cover interior sockets, reversed normals, corner-crossing and oversized
openings, a concave-footprint approach outside the walkable region, inadequate
height clearance, observation/socket separation, and valid sockets on all four
orthogonal edge orientations.

## Versioning and limits

The v1/v2 schemas, freezes, historical adaptation records, decisions, and
fingerprints remain unchanged. Contract v3 is an explicit successor with a
predecessor hash link. It pins the active validator, extensions, and the exact
archived source bytes for every v2-pinned tool. The v1 compatibility extensions
add validation metadata only; they do not create or broaden operator approval.
New records that need dynamic resource declarations or authored socket
clearance use v3. V2 records fail closed on unresolved dynamic loads and cannot
claim the v3 authored-socket clearance contract.

This is bounded static analysis, not a full GDScript parser or runtime geometry
certificate. Multiline load expressions and non-repository/UID-only external
paths fail closed. Opaque imported/binary assets are hashed as leaves. Static
checks cannot prove dynamic branches enumerate all targets, visible geometry
matches declared bounds, collision nodes match the scene, or a player can
traverse a socket. Those still require Godot evidence.

## Verification

- Adaptation tests: **34 passed**.
- GPU/resource guard regressions: **2 passed**.
- Ruff lint, Ruff format check, and Python compile checks: passed.
- Both real adaptations passed read-only CLI validation through their v1 to v3
  compatibility path.
- Protected tracked v1 schema/freeze, records, #164/#165 operator decisions,
  and original #163/#165 evidence paths show no diff from `HEAD`.
- No commit was made; #165 remains open for review.

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

Changed paths for this hardening set: `room_catalog/contract_freeze_v3.*`,
`video_adaptation.schema.v3.json`, `video_adaptation_contract_v3.md`,
`adaptations/compatibility_v3/`, `archives/contract_v2/`, the
`video_adaptation_*.py` validator/resource-graph modules, and the
`test_video_adaptation*.py` regression tests. No room scene or asset changed.
