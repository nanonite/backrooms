# Video adaptation contract v2

Contract v2 is the current validation contract for new video-to-room adaptations.
It keeps observation, reusable requirements, and resolved room design separate.
The candidate identity hashes the source observations, reusable requirements,
resolved geometry/render/collision metadata, calibration flags, adaptation ID,
contract version, and immutable catalog snapshot reference. Validation results and
the decision itself are excluded to avoid a hash cycle.

An accepted record must carry that current identity in
`operator_decision.candidate_fingerprint`, a decision artifact path and hash, and
an artifact whose internal adaptation ID, candidate identity, and decision agree.
Pending records may omit approval, but cannot carry or validate as accepted.

The validator checks static consistency: repository-contained files, dependency
coverage and hashes, simple finite orthogonal polygons, nondegenerate bounds,
footprint containment, spawn geometry, and socket declarations. These checks do
not establish that rendered meshes fit the declared envelope or that a player can
traverse the room. Those claims require separately fingerprinted Godot runtime
evidence, such as the historical bounded-route, containment, boundary, and
negative-control receipts.

## Contract v1 migration

The v1 schema, freeze, records, fingerprints, decisions, and receipts remain
unchanged. The v2 compatibility manifest pins each historical source record and
its original decision artifact, then records a derived v2 candidate identity
over the old decision-relevant metadata. The `room-large` approval uses the
original accepted-layout decision format, which names the exact seed-164 layout
and connection rather than a candidate ID. It is accepted only because the v1
freeze pins the exact source record and the v2 compatibility entry binds that
record, dependency fingerprint, tested connection reference, and affirmative
layout decision together. The transfer example's decision contains a candidate
version, dependency fingerprint, and affirmative decision, all of which are
checked directly.

The transfer record also listed the original workflow runner, extractor, and
validator as candidate dependencies. Their exact v1 sources are retained under
`adaptations/compatibility_v2/tooling_v1/`. The compatibility entry binds each
old dependency hash to that archived source and to the corresponding active v2
tool, whose current hash is frozen by `contract_freeze_v2.json`. Only these
three explicitly identified workflow tools use this migration rule; scene,
texture, source, controller, evidence, and other candidate dependencies still
must match the historical record directly.

Both v1 examples resolve catalog references against the byte-identical v0.2.0
catalog snapshot frozen by v2. The live catalog may grow without changing these
historical adaptations. Changes to the snapshot, referenced module version,
scene dependencies, decision artifact, source record, or derived metadata fail
validation. Historical Godot measurements are reported as runtime evidence;
static schema and metadata checks are not presented as runtime validation.
