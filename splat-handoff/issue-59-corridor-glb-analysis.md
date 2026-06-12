# Issue #59: corridor_straight scene.glb geometry analysis

## Verdict

`godot_walk/assets/corridor_straight/scene.glb` is not a Godot
main-scene or material problem, and it is not salvageable with a simple
scale/orientation/origin tweak.

The exported GLB has the intended metric height, but its footprint is only a
thin slab. That means the upstream reconstruction/export delivered the wrong
physical space: either Meshroom produced only a partial corridor fragment, or
the Blender cleanup/export stage selected/exported only that fragment. The
available repo state does not include the source Meshroom OBJ, so the exact
upstream boundary cannot be narrowed further from the GLB alone.

## Current GLB Measurements

File: `godot_walk/assets/corridor_straight/scene.glb`

- Size: 72,232,196 bytes
- Nodes/meshes: 1 node, 1 mesh
- Materials/images/textures: 4 materials, 4 images, 4 textures
- Vertices: 1,497,641
- Triangles: 499,248
- Primitives: 4 indexed triangle primitives
- World bounds: min `[-0.5749, 0.0000, -0.2071]`, max `[0.8058, 2.0000, 0.2893]`
- World dimensions: `1.3807m x 2.0000m x 0.4964m`
- Inferred pre-export dimensions before recorded `0.682339` scale:
  `2.0234 x 2.9311 x 0.7276`

The `2.0000m` height matches `scene_transform.txt` and the Blender cleanup
script's target doorway height. The thin `0.4964m` depth is the failure. Scaling
this mesh larger would make the height wrong before it produces a usable
walkable corridor footprint.

## Topology Notes

Index topology is heavily duplicated:

- Index-connected components: 499,198
- Largest index-connected components: 10, 9, 6, 6 vertices
- Boundary edges by index: 1,497,638

That alone is not enough to call it a point cloud, because exporters can
duplicate vertices per face. A coordinate-quantized topology pass shows the
triangles do meet spatially:

- Unique quantized vertices at `1e-5`: 240,113
- Geometric components at `1e-5`: 1,119
- Largest geometric component: 234,255 quantized vertices
- Geometric boundary edges at `1e-5`: 4,701
- Geometric shared edges at `1e-5`: 746,339

So the asset is mostly a connected surface, not loose points. It is just the
wrong connected surface for a corridor: a narrow vertical slab/fragment.

## Reference Comparison

The archived Gaussian-splat pipeline assets were inspected only as reference
shape/scale checks, not as replacement assets.

`archive/splat_walk/assets/splats/corridor_straight/collision.mesh.glb`:

- Vertices: 99,615
- Triangles: 199,984
- World dimensions: `2.7161m x 2.4970m x 3.4504m`

`archive/splat_walk/assets/splats/corridor_straight/collision_proxy.mesh.glb`:

- Vertices: 2,614
- Triangles: 6,520
- World dimensions: `2.5153m x 2.2295m x 3.3945m`

Those references have a room/corridor-sized footprint. The current Godot GLB is
roughly the right height but far too shallow.

## Pipeline Diagnosis

`scripts/splat_pipeline/blender_cleanup_mesh.py` estimates scale from vertical
extent only:

- `estimate_scale()` computes `target_doorway_height / extent_z`
- `export_glb()` re-imports the GLB and verifies only the exported height
- No current check validates footprint span, floor area, or walkable corridor
  shape

This explains why the bad asset could pass export validation. A partial vertical
wall fragment can be scaled to exactly `2.0m` tall and still fail the walk test.

The #59 reference to issue #29 does not match the local tracker: local issue #29
is `C1: Offline CoACD/V-HACD decomposition script`, not a Meshroom-to-Blender
export issue. The relevant local context is the Meshroom fallback documentation
and the Blender cleanup script.

## Recommended Next Step

Treat this as a Stage-M upstream asset problem, not a Godot scene problem.

1. Locate or regenerate the Meshroom textured OBJ that fed
   `blender_cleanup_mesh.py`.
2. Measure that OBJ before Blender cleanup:
   - If it already has the same thin footprint, the Meshroom reconstruction is
     incomplete and the capture/reconstruction must be re-run with better input
     coverage/settings.
   - If it has a full corridor footprint, the Blender cleanup/export path is
     selecting, filling, decimating, or exporting the wrong geometry.
3. Add a footprint sanity check to `blender_cleanup_mesh.py` before accepting
   `scene.glb`, so a 2m-tall but sub-meter-depth fragment fails before it reaches
   Godot.

No archived collision GLB was copied into `godot_walk/`, and the current
`scene.glb` was not hand-edited.
