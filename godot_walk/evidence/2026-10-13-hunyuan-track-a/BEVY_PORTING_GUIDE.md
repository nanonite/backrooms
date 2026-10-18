# Hunyuan GLB Port To Bevy

## What The Hunyuan Export Contains

The current conversion does not rerun inference or turn the panorama into a
Gaussian splat. It reads Hunyuan's `mesh_layer0.ply` and `mesh_layer1.ply` and
packages them as named nodes in a glTF 2.0 binary. The layers keep identity
transforms and have vertex colors. Their unit scale remains unknown. In this
run they contain about 18.0 million triangles total.

The resulting `hunyuan_layers.glb` is the asset to load in Bevy. It already
contains useful visual geometry. Bevy does not need a Hunyuan-specific runtime
or a new mesh conversion for this comparison. The 344 MiB GLB is intentionally
ignored by Git, like the existing #133 fixture asset; the manifest records its
SHA-256, and the Bevy loader verifies it before capture. Reproduction requires
the matching generated GLB at the manifest path.

## Bevy Import Path

1. Load the GLB with `AssetServer` and wait for dependencies.
2. Resolve `mesh_layer0` and `mesh_layer1` from `Gltf.named_nodes`.
3. Read each node's mesh primitives and spawn them as `Mesh3d` entities.
4. Apply the node transform under the manifest's model transform.
5. Use white `StandardMaterial` with `unlit: true` and `cull_mode: None` for
   the first visual pass. This preserves vertex color and displays open,
   inconsistently wound surfaces from both sides. It does not emulate Godot's
   lighting or tone mapping.

The implementation is in
[`splat_walk/src/bin/walkability_harness/route_scene/capture.rs`](../../../splat_walk/src/bin/walkability_harness/route_scene/capture.rs)
and reuses the import approach in `splat_walk/src/main.rs`.

## Transform Contract

- Keep glTF coordinate conversion disabled for this asset. Its Hunyuan basis is
  mapped explicitly: local `-X` is registered forward, `+Y` is camera-right,
  and `+Z` is up.
- Use the #137 manifest transform: 1.5582858479 declared metres per Hunyuan
  unit, aligned to the declared #100 floor plane. This is a convention, not a
  surveyed scale or accepted registration.
- Plane alignment shifts the frame-141 camera anchor by -0.120342 m in Y.
- Keep `registration_accepted=false` and `scale_calibrated=false`. Do not apply
  either depth-corrected mesh from #142.

## Separate Visual And Collision Roles

The Hunyuan layers stay render-only. Do not create Avian colliders from them.
The authored #135 GLB owns the floor, column proxy, and edge boundaries. The
shared `splat_walk::player_controller` owns movement. This lets the visual
representation improve without making the uncalibrated geometry authoritative
for player physics.

## What The First Bevy Port Proves

The first Bevy port loads and renders the named GLB layers from the locked
frame-141 and eight loop-station poses. It confirms that this mesh export can
be imported as Bevy `Mesh3d` entities with vertex colors and the explicit
uncalibrated transform. The captures are not a claim of visual parity with
Godot. ODiff across Godot and Bevy is only a pixel diagnostic: it cannot
separate material, color-space, camera, renderer, or tone-mapping differences.

The direct Godot-Hunyuan versus Bevy-Hunyuan comparison uses the same GLB and
pose contract. It helps locate port differences, but is still cross-renderer
and cannot prove parity. Compare it alongside the unchanged #100 baseline.
Reports and captures are in `godot_walk/evidence/2026-10-13-hunyuan-track-a/`.

If the Bevy surfaces look wrong, inspect in this order:

1. Verify layer names, vertex-color attributes, and node transforms.
2. Check the Hunyuan-to-world basis and the camera forward/up axes.
3. Check back-face visibility and material color handling.
4. Only then tune exposure, tone mapping, or lighting to approach the intended
   art direction. Record any render changes as a separate comparison; do not
   change the locked geometry transform to compensate for appearance.

The first pass uses a white unlit, double-sided material to preserve vertex
colors and show open surfaces. It does not emulate Godot's lighting or tone
mapping. Further appearance matching should be a separate measured iteration.
No visual-port parity, accepted registration, or calibrated scale is claimed.
