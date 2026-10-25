# Chainlink #160: bounded column room and authored connection

## Status

The bounded column room, the existing early-pocket room, and their authored
Godot connection pass the mechanical checks recorded here. This is a review
candidate only. Operator visual acceptance, catalog admission, and generation
readiness remain false. Keep #160 open until the operator reviews the rooms and
assembly.

The layout is an authored game-design proposal, not a recovered floor plan.
Source footage does not establish connectivity between the later column bay
and the early pocket. `registration_accepted=false` and `scale_calibrated=false`
are preserved. No room-catalog files were changed.

## Candidate changes

- A separate bounded column scene uses the #159 proposed polygon, closed
  perimeter, floor, ceiling, and a safe spawn. The original #150 scene and
  collision assets remain unchanged.
- C01 keeps its accepted four-sided visual face, placement, dimensions, and
  texture treatment. The new collider is independently fitted to the retained
  box and checked from four sides.
- C02 is a separately authored estimated prism and collider. Its bounds are an
  estimate from visible evidence; hidden faces are not claimed as recovered.
- The Hunyuan visual is a new derivative clipped to the proposed authored
  envelope. C02's estimated footprint is removed from mesh layer 0 and filled
  by the prism. This clips triangles; it does not reconstruct the scene or
  guarantee a visually seamless source boundary.
- The early-pocket module remains independently runnable. Separate connector
  adaptations open both authored socket walls and colliders; standalone closed
  variants are retained. The paired socket is new authored geometry, not a
  video-observed opening.

## Mechanical evidence

| Scene | Spawn-connected capsule-center area estimate | Route out and back | Floor support | SafetyNet contacts | Max observed step |
|---|---:|---:|---:|---:|---:|
| Bounded column room | 31.63 m2 | 20.13 m | 100% | 0 | 0.067 m |
| Early pocket | 69.43 m2 | 53.60 m | 100% | 0 | 0.067 m |
| Assembled pair | 101.85 m2 | 80.07 m | 100% | 0 | 0.067 m |

Areas are 10 cm capsule-grid estimates of spawn-connected centers, not surveyed
architectural dimensions. All configured route segments, including travel
through the connector in both directions, were reached. Eight-direction
boundary pushes were checked per scene. Six negative controls (remove floor or
boundary, in each of the three scenes) failed with the expected support/escape
diagnostics. The Godot contract test also checks C01/C02 obstruction from four
sides, connector clearance, the level floor transition, jambs, lintel, module
flags, and both visual mesh layers.

## Rendering and resources

Fifteen Vulkan captures were produced at 960x540 after the shared GPU/RAM
headroom check passed. No compute job was active. The capture process peaked at
2,739,109,888 bytes RSS and added 575,668,224 bytes of GPU memory.

| Scene | Capped average FPS | p95 frame time | p99 frame time | Peak child RSS | GPU memory delta |
|---|---:|---:|---:|---:|---:|
| Bounded column room | 60.002 | 16.789 ms | 16.891 ms | 2,425,307,136 B | 580,911,104 B |
| Early pocket | 60.002 | 16.816 ms | 16.932 ms | 551,100,416 B | 177,209,344 B |
| Assembled pair | 59.897 | 16.806 ms | 21.636 ms | 2,425,364,480 B | 588,251,136 B |

FPS was measured at the 60 FPS cap across 14 poses per standalone module and 20
poses for the assembly. The assembly's measured average was slightly below 60;
the p99 frame time was 21.636 ms. These are hardware- and scene-specific
measurements, not a general performance guarantee.

## Provenance and review

The original #150 source visual (`hunyuan_layers.glb`) SHA-256 is
`5b3e879c0309448887cd3ceb7b29eaca49476566ac75010f7e5c5253443a23bf`; its
original collision asset SHA-256 is
`1dfdf15153194eb4b1c9f8d276bd54286168488cd693de27b1d9fa91f3b28ad9`. The
source video and frame-0152 references are also checked against the #150
manifest. Full protected-input hashes, candidate shell/collision definition
hashes, and capture hashes are in [provenance.json](provenance.json).

The bounded visual derivative SHA-256 is
`8767ebc268389197416fe1986d78553889b196fcb9ee227f46e7b81d3882c898`.
Procedural collision is defined by the hashed Godot scene/script sources in the
provenance record; it is not represented as a separately exported collision
GLB. `room_readiness.json` records separate authored sockets and the mechanically
tested connector, while keeping all acceptance/readiness flags false.

Review entry points:

- [Interactive capture index](index.html)
- [Contact sheet](contact_sheet.jpg)
- [Authored assembly layout](authored_assembly_layout.svg)
- [Readiness and test record](room_readiness.json)
- [Reproduction commands](COMMANDS.md)

Please review C02 from both approaches, the column-room perimeter and floor/
ceiling, the transition seam in both directions, and whether the new authored
connection is a useful design choice. No automatic selection or promotion has
occurred.

## Validation

- `python3 -m unittest godot_walk/scripts/test_issue160_glb.py`
- Godot `test_issue160.gd`: pass (`ISSUE160_ROOM_CONTRACT: PASS`)
- Standalone and assembled bounded-walk verifier: pass, no failures
- Six floor/boundary negative controls: expected failures observed
- Fifteen Vulkan captures: pass, no renderer errors in the final run
- Capped FPS/resource runs: completed for all three scenes

This report intentionally does not close #160 or make the candidate available
for generation/catalog use.
