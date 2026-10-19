# Bevy GLB Fixture: Hunyuan run-05

## Test

The isolated crate at `splat_walk/` loads the ignored run-05 `hunyuan_layers.glb`
directly from its existing directory. It does not copy or regenerate the 344 MiB
asset. The fixture uses Bevy 0.18.0, a 960 x 540 window, and the registered frame
141 camera from `source_selection.json`.

The GLB root maps local `-X` to registered forward, `+Y` to camera right, and
`+Z` to camera up. The Bevy camera has a separate look transform, with the
registered origin and 47.3988 degree vertical field of view. Both mesh nodes use
a white-base, unlit, double-sided material. This keeps the source `COLOR_0`
attribute visible and avoids relying on the source mesh winding or lighting.

Run from the crate directory:

```sh
cargo test
cargo clippy -- -D warnings
WGPU_BACKEND=vulkan ./target/debug/hunyuan_bevy_fixture
```

The fixture writes `bevy_fixture/frame_141.png` and prints node, geometry,
alignment, import-time, and wall-clock update metrics. The GLB path can be
overridden with `HUNYUAN_GLB`; the screenshot path can be overridden with
`HUNYUAN_BEVY_SCREENSHOT`.

## Results

- Import and presentation succeeded on the RTX 4070 Ti using Vulkan. Both
  expected named nodes loaded, with one triangle primitive each.
- `mesh_layer0`: 3,235,413 triangles. `mesh_layer1`: 14,783,952 triangles.
  Total: 18,019,365 triangles.
- The Bevy meshes exposed 9,706,239 and 44,351,856 positions respectively
  (54,058,095 total), with matching color and normal attribute counts. The GLB
  contains `COLOR_0` but no explicit `NORMAL`. The 3x-triangles vertex counts
  and added normal attributes are consistent with Bevy expanding the triangles
  and generating per-face normals during import.
- Time from load request to the GLB and its dependencies being available was
  20.8 seconds. The 344 MiB source grew to a measured peak process RSS of
  6,898,192 KiB (about 6.58 GiB) during this debug run.
- During 180 post-load Bevy `Update` iterations, wall time was 11.6 seconds,
  or about 64.5 ms per update (15.5 updates/s). This includes first-use render
  work. Bevy virtual-time deltas under-reported that wall time, so they are not
  used as the performance result. This is update throughput, not a claim about
  presented FPS.
- GPU sampling at 500 ms intervals showed 1,939 MiB used before launch and a
  4,229 MiB peak. At least 7,641 MiB remained free. The process exited normally;
  no inference ran and no GPU crash occurred.
- The final screenshot shows the registered forward composition: corridor,
  ceiling grid, right wall, and foreground column. Vertex colors are visible.
  See [frame_141.png](bevy_fixture/frame_141.png). An initial render with an
  incorrect camera transform was discarded; the saved image uses the corrected
  independent camera and model transforms.

## Contract And Decision

This passes the narrow #133 check: Bevy 0.18 can load and render these named
Hunyuan GLB mesh layers with vertex colors. It is a static triangle-mesh visual,
not a Gaussian splat. The existing runtime contract remains `scene.ply` for
`bevy_gaussian_splatting`, `collision.glb` for physics, and one shared
`alignment.toml` transform. No direct PLY-versus-GLB renderer benchmark was run.

This run does not calibrate model units or approve route alignment. It does not
create or validate collision, and it does not establish walkability. Keep the
GLB as an exploratory visual candidate. Continue with scale and registered-pose
evaluation in #134; assess a separate collision representation in #136.
