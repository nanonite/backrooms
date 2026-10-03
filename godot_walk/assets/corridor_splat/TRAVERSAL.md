# Walking the generated collision — task #85

`corridor.tscn` no longer carries hand-fitted boxes. Its collision is the mesh
`#84` generated, placed by the `#83` contract, and this directory records how the
player was made to walk it.

Everything here is headless physics. It proves the controller moves, is stopped,
and keeps its footing on the geometry that exists. It cannot show that the splat
renders, that the visual and the collision agree, or that the frame rate holds —
`#74` owns real-GPU visual evidence and `#91` the end-to-end gate. Nothing in this
file should be read as either.

## The files

| file | what it is |
|---|---|
| `collision/corridor_splat.collision.glb` | the mesh `#84` generated, md5 `c8f7a46effade8002a9bc51f74e3b11e`, 10 178 triangles |
| `traversal_manifest.json` | route, probes, spawn and tolerances, derived by `scripts/splat_pipeline/traversal_plan.py` |
| `traversal_run.log` | the committed run of `res://scripts/verify_traversal.gd` |
| `../scripts/generated_collision.gd` | builds the `ConcavePolygonShape3D` from the imported GLB at load |
| `../scripts/traversal_plan.gd` | reads the manifest inside Godot |
| `../scripts/verify_traversal.gd` | the walk battery |

## Reproducing

```bash
# 1. regenerate the collision (needs the pinned tool; see COLLISION.md)
cd scripts/splat_pipeline
npm install @playcanvas/splat-transform@3.9.0
SPLAT_TRANSFORM_NODE_MODULES=$PWD/node_modules python3 generate_collision.py \
    --manifest ../../godot_walk/assets/corridor_splat/alignment_manifest.json \
    --ply ../../exports/corridor_travel_v1/splat.ply \
    --out ../../godot_walk/assets/corridor_splat/collision/corridor_splat \
    --report collision_benchmark.json

# 2. derive the traversal plan (a few seconds, no GPU)
python3 traversal_plan.py \
    --manifest ../../godot_walk/assets/corridor_splat/alignment_manifest.json \
    --report collision_benchmark.json \
    --glb ../../godot_walk/assets/corridor_splat/collision/corridor_splat.collision.glb \
    --out ../../godot_walk/assets/corridor_splat/traversal_manifest.json

# 3. import, then walk
godot4 --headless --path godot_walk --import
godot4 --headless --path godot_walk --script res://scripts/verify_traversal.gd
```

Step 3 rewrites `traversal_run.log` and exits non-zero if anything fails. About
two minutes: 5 scenes, ~2 400 physics ticks each.

## Settings, and where each number comes from

Nothing in the walk test is a constant of its own. Every tolerance is read from
`traversal_manifest.json`, which `traversal_plan.py` derives from the mesh and
the contract — a verifier carrying its own copy of a tolerance is a second source
of truth that drifts, and a drifted *stop* tolerance quietly turns "was stopped
by the wall" into "ended up somewhere plausible".

| setting | value | source |
|---|---|---|
| player capsule | radius 0.30 m, height 1.20 m | `scenes/player.tscn`, read by `verify_scene.gd` and asserted to match |
| controller speed | 4.0 m/s | `player.gd:SPEED` |
| required clearance | 1.25 m | capsule height + 0.05 m margin |
| floor plan | 0.25 m cells, origin (−10.069, −4.306) m | `#84` `expected_geometry` |
| column test height | 1.00 m above the contract floor | `#84` `OBSTRUCTION_TEST_HEIGHT_M` |
| position tolerance | 0.18 m | wider than a 0.067 m tick, narrower than a 0.25 m cell |
| step tolerance | 0.20 m | 3× a tick; a step longer is tunnelling or depenetration |
| block-stop tolerance | 0.12 m | mesh is a smoothed 5 cm voxel surface |
| floor support | ≥ 95 % of ticks | short gaps while snapping down are expected |
| floor-surface tolerance | 0.05 m | one voxel; both readings are of the same triangles |
| spawn drop limit | 1.00 m | contract's marker is 0.5 m above its own floor plane |
| physics | 60 ticks/s, 60 to settle, 150 probe push | the project's default |

Two derived quantities are worth spelling out because they were wrong before.

**The collision node's transform is a pure rotation.** `#84`'s first record gave
it a basis carrying `metres_per_unit` (5.128×), which places the generated floor
metres away from the room. The tool is handed a splat the contract has already
scaled into metres, so its engine frame is metric and no second scale belongs in
the node transform. Found here because `collision_params.py` held two mappings
that disagreed — `collision_node_transform` scaled and `engine_frame_to_world`
did not — and only the point mapping had ever been checked against the other.
`collision_benchmark.json` has been re-emitted with the corrected basis and a
`correction` note; every other field, every check and the verdict are unchanged,
and the GLB is byte-identical.

**The spawn is the capsule's centre, not the marker.** The contract places
`PlayerSpawn` 0.5 m above its own *floor plane*, which is a drop-in reference,
not a standable height: a 1.2 m capsule put 0.5 m above a floor has its lower
hemisphere 0.1 m inside it. The marker keeps the contract's position — `#83`'s
evidence depends on it — and `Player` is placed on the generated collision's own
floor surface under the marker (−1.1430 m, measured) plus half the capsule. The
same rule `#84` used to place its carve seed.

## What the walk proves

`verify_traversal.gd` presses the real input actions and lets real physics ticks
run; nothing writes velocity or teleports the player. Every assertion is about
observed motion or an observed physics query, so a scene whose collision node
exists but holds no shape fails rather than passing.

Measured on the shipped scene (`traversal_run.log`):

```
spawn           floor −1.1430 m, capsule bottom −1.1430 m, headroom 2.150 m
route_outbound  15 legs, 6.60 m, floor support 100.0 %, max step 0.067 m
boundary_out    15 legs, 6.99 m, floor support 100.0 %, max step 0.072 m
low_clearance   cell (28, 27), 1.900 m headroom, floor support 100.0 % over 60 ticks
boundary_back   15 legs, 6.88 m, floor support 100.0 %, max step 0.073 m
route_inbound   15 legs, 6.44 m, floor support 100.0 %, max step 0.067 m
probe column    ran 1.09 m, stopped 0.067 m from the planned face
probe wall      ran 1.40 m, stopped 0.119 m from the planned face
```

- **Floor support, both directions.** The whole route is walked out and back, with
  no teleport at the turn-around. Every leg reports `is_on_floor()` per tick.
- **The opening.** The route's tightest passage — measured as *width*, not
  headroom, since headroom here is 2.0 m in open floor — is on the route and is
  threaded in both directions. The `blocked_opening` case fills those cells and
  the route fails, so the passage is load-bearing.
- **Wall and column blocking.** Two probes drive into solid from a measured
  approach run and must come to rest within 0.12 m of where the plan predicts,
  having covered at least the plan's minimum displacement. A probe that never
  moved cannot pass.
- **No tunnelling, floating or fall-through.** Per-tick displacement, the body's
  y envelope, and a floor ray under the capsule.
- **Capsule clearance.** 2.150 m of headroom at the spawn and 1.900 m at the
  least-headroom walkable cell, both above the 1.25 m the capsule plus margin
  needs.
- **SafetyNet.** Any contact is a failure, and so is *standing* on it. Those are
  separate checks: a scene whose collision is removed leaves the net as the only
  floor, and an overlap-only check would watch the player walk 6.6 m across it
  and call it a route.

## What the walk does not prove

**`#84`'s benchmark for this capture is a FAIL, and that is recorded, not
papered over.** `collision_benchmark.json` carries
`walkway_covers_camera_path: 153 of 192 camera positions are inside solid
collision at 1.00 m above the floor (20.3 % traversable, need 90 %)`: the
generated walls block the route that was actually walked. The manifest already
records why — `walls_measured: false`, no wall plane was ever resolved from this
capture, so no collision stage can recover one.

What that means for the two artefacts:

- The walk test measures the region the generated collision *does* leave
  navigable, and measures it directly. A pass is a statement about the collision
  that exists, not a claim that it reconstructs the corridor somebody filmed.
- The plan's route is inside a region covering 412 of 1 368 tested cells, and
  probing with the real capsule leaves several disconnected pockets — the 1.0 m
  gap the voxel grid resolves leads to a pocket the player cannot walk into. Every
  route and boundary target is restricted to the spawn's own component, so the
  test never has to teleport to reach one.
- There is no through-opening in this collision to report. `#74`'s real-GPU
  screenshots and `#91`'s end-to-end gate are where a visual or coverage claim
  belongs.

## The negatives

A battery that cannot fail proves nothing, so the same assertions run against
four deliberately broken scenes, and each has to fail *for its own stated reason*.

| case | mutation | rejected for | also caught |
|---|---|---|---|
| `missing_collision` | the mesh is removed | `GeneratedCollision` | wrong floor, no ceiling, **stood on the net** on all five walks, net contact on both probes |
| `wrong_transform` | the node is scaled by `metres_per_unit` | wrong floor | the same set: the collision exists but the room is not under the spawn |
| `blocked_opening` | a box fills the route's tightest passage | `did not reach` | both directions, and both probes lose their approach |
| `safety_net_landing` | the net is raised into the capsule | `SafetyNet` | contact and support on every walk |

Two of these detectors were dead on the first run and are worth naming. The net
detector queried the *net's own box* and then looked for a collider named
`SafetyNet`: the net either intersects its own query shape every tick, or is
excluded and never reported. It now queries the **player's capsule** against the
space and asks which bodies it overlaps. And `missing_collision` initially passed
its route walks — the net was the floor, so the player walked 6.6 m and arrived.
That is why support and contact are checked separately.

## Out of scope here

Real-GPU rendering, the splat-versus-collision visual alignment, frame rate, and
the end-to-end video walkthrough: `#74`, `#91`, and `#88`.
