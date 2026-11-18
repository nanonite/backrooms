# Issue 271 — authored data and provenance (v1)

## Source reference (context only)

The accepted snow-garden-courtyard-v2 record is used as visual and geometric
context. Its 16 bench parts, statue plinth, all wall/tree/drift/post geometry and
every collider are reproduced in the shared fixture script; the accepted room and
its frozen/pinned files are only read, never edited. The reference's `room.gd`
sha256 is `2f18644b1001dbe990af4640be3bcca66064c6df83a1ecdde545dc72e89049d3`
and its accepted record sha256 is
`9d3a492b2a5e2a18d06472df7ea24252f373b6cfd7ae0a3746162a48173ec394`.

All design units are uncalibrated; `registration_accepted=false`,
`scale_calibrated=false` and `operator_approved=false` in both scenes and every
record. No metric scale, registration, catalog admission or connectivity is
implied.

## Authored vs source split

- **source_crop:stone_robe** — the existing `stone_robe.png` crop of frame 4347
  bounds `[200, 280, 380, 470]`, sha256
  `a4c0ce7f700084f6ae77577450cc4af3e8efa20b4efde4206f7894c1291dd7aa`. The
  accepted record labels it `stone_bench_surface`, but #255 identifies the pixels
  as the angel's robe, not bench stone. In the **reference** view it is still
  assigned to the 12 stone bench parts and to the statue plinth; in the
  **candidate** view it is assigned ONLY to the statue plinth. The plinth is
  deliberately not silently changed.
- **project_authored** (the fallback) — a locally authored unshaded solid
  `StandardMaterial3D`, albedo RGBA `[0.42, 0.44, 0.47, 1.0]`, roughness 1.0,
  metallic 0.0, no albedo texture, nearest texture filter. Intended role:
  `stone_like_bench_surface`. It is assigned in the candidate to exactly the 12
  bench parts that previously shared the robe crop: BenchPlinth, four BenchLeg*,
  BenchSeat, three BenchBackPost*, three BenchBackSlat*. No source pixels are
  claimed for it; it is an authored fallback, not a source reconstruction.
- **project_authored_solid:post** — the four BenchBollard* cylinders already use
  the reference's local solid post material `Color(0.27, 0.31, 0.36)` in both
  views; they are recorded as bench assignments but are unchanged because they
  never used the robe crop.

## Invariants

Geometry and collision are not branch-dependent: one shared script builds both
scenes and the only difference is the exported `bench_material_mode` property.
The statue plinth, its `StatueCollision`, `StoneBenchCollision`, floor, walls and
all 18 tree colliders are identical by construction and are compared node by node
in the headless test. The capture views are reused byte-for-byte by both scenes.
