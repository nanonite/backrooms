# Godot video-adaptation contract v3.0.0

Contract v3 is a validation successor to the immutable v1 and v2 contracts. It
does not alter accepted room assets or historical decisions. The v3 freeze pins
the current validator and preserves exact v2 validator source bytes in
`room_catalog/archives/contract_v2/`.

## Runtime resource coverage

The bounded static graph follows:

- `.tscn` and `.tres` external resource paths;
- GDScript quoted `extends`, `preload`, and `load` paths, including direct
  string constants;
- GDScript dynamic or unresolved load callsites through explicit declarations
  naming every possible repository resource path;
- quoted shader `#include` paths in `.gdshader`, `.gdshaderinc`, and `.glsl`
  files, including repository-contained relative includes.

Every discovered resource must exist in the repository and appear in the
candidate dependency manifest with its hash. Dynamic declaration keys bind to
the source script path, line, call index, and normalized call expression. The
declaration is a maintainer assertion that its resource list is exhaustive;
validation cannot evaluate arbitrary runtime values. A missing literal target
is rejected unless that callsite explicitly declares it as an optional missing
path with a reason; if that path later appears, it must be added to the
fingerprinted manifest. Resource cycles terminate through a visited-path set.

This is not a full GDScript parser. Multiline load expressions are rejected.
Binary/imported resources are hashed as leaves; the scanner does not decode
their private container formats. A future asset that has external resources
inside an opaque container needs an explicit declaration or a Godot resource
dependency export before it can claim complete coverage. Static checks do not
prove runtime branches exercise every declared dynamic target.
External resource IDs that do not expose a repository `res://` path fail
closed; resolve them to a repository path before the candidate can claim
validation. Engine-provided angle-bracket shader includes are treated as
engine resources and are not hashed as repository files.

V2 records without dynamic-resource declarations can validate only when their
reachable resources contain no unresolved dynamic load callsites. New records
that need dynamic declarations use v3. Authored sockets in a v2 record cannot
claim the v3 clearance contract; migrate them to v3 with a declared
floor/ceiling and full approach region. This leaves the v2 freeze and schema
unchanged while refusing underspecified new declarations.

## Socket geometry

New authored sockets declare the room floor/ceiling clearance and an orthogonal
approach-center region. The validator checks a socket center against exactly
one supported footprint edge, verifies the normal points outward, checks the
entire opening width stays strictly inside that edge, confirms floor and
opening height fit the declared room clearance, and checks the whole approach
region remains inside the walkable polygon with capsule-radius boundary
separation, reaches the capsule-clearance band at the socket, and spans the
usable opening width. A rendered AABB is not a ceiling measurement. Observed
source openings remain observation-only and cannot carry a gameplay connector
reference.

These are static declaration checks. Runtime collision obstacles, actual
openings, capsule traversal and connector seams still need Godot evidence.

## Historical adaptation compatibility

V1 adaptation records retain their exact source hashes, dependency fingerprints,
decisions and runtime evidence. A v3 compatibility extension supplements each
record with dynamic-resource callsite declarations, a separately fingerprinted
set of transitive dependencies omitted from the original manifest, and an
explicit binding from its old `catalog.json` dependency to the byte-identical
frozen snapshot. The legacy dependency list and candidate fingerprint are not
rewritten. The live catalog is not read to validate those historical catalog
dependencies. Snapshot/module tampering, dependency omissions and source-record
changes still fail. The extension adds validation coverage only and does not
broaden the historical operator approval.

V2 freeze and schema bytes remain immutable. The v3 verifier checks every v2
frozen artifact against its original path or a v3-pinned archive containing the
exact original bytes. Current v3 validator files are separately pinned by the
v3 freeze.
