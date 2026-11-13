# Blender 5.3 native Gaussian splats and the Godot/Hunyuan workflow

Date: 2026-11-12
Issue: #230
Status: research note only. This file changes no pipeline, code, schema, dependency, or frozen asset.

Question: does Blender 5.3's native 3D Gaussian splat support give the current
Godot + Hunyuan workflow a useful inspection, cleanup or cropping stage?

Short answer: **no material gain**. Blender 5.3 can import and render our
standard 3DGS PLYs, and a human can inspect or crop one in the viewport. It
cannot currently write a usable 3DGS PLY back out: direct PLY export produced an
empty file, and the mesh-conversion workaround dropped the colour/opacity
attribute. The Hunyuan seed path does not consume splats at all, and the
existing Godot/GDGS cleanup is deterministic, measured, and already better
aligned with the file format. Recommendation: **ignore as a pipeline stage**;
optional manual inspection only, with no follow-up implementation issue.

## 1. What the article states

Source: Mark van de Ruit and Sergey Sharybin, "Splatting the Gaussians into
Blender", code.blender.org, 2026-10-30,
<https://code.blender.org/2026/10/splatting-the-gaussians-into-blender/>. The
page was fetched and read for this note.

- Blender 5.3 adds **initial** native 3D Gaussian splat support: import, editing
  and rendering. The authors call it a first step and say refinement is planned.
- **Import:** `.PLY` and `.SPZ`, plus loading from USD. The post describes **no
  export path**.
- **Representation:** splats are a point-cloud type, exposed through a
  `Pointcloud Type` geometry node. The attributes are position, scaling (a 3D
  vector, not a point radius), rotation (a quaternion), and radiance (spherical
  harmonics, split into `radiance:base` and `radiance:sh` for Geometry Nodes).
  The default material is emissive from radiance.
- **EEVEE/Workbench:** EEVEE uses dithered transparency, described as noisy, so
  the sample count should be raised. Splats are camera-oriented billboards.
  Workbench needs Viewport Shading > Lighting > Flat.
- **Cycles:** rays intersect splats and opacity is treated as a probability
  (stochastic, ray-oriented). Most splat data was fitted for the EEVEE-style
  approach, so Cycles can differ visibly.
- **Limitations named in the post:** EEVEE overdraw and culling still need work;
  editing tools are the ordinary point-cloud tools and feel clunky; relighting
  is early and uses view-dependent radiance, with albedo extraction a possible
  future step.
- **Not in the post:** a capture/training-to-engine workflow, an export format,
  batch/headless automation, or any Godot, Unity or Bevy integration. Treating
  the post as an end-to-end workflow would be an inference, not a reading.

## 2. Q1: what the old Blender-to-Bevy route lost

The repository contains two different historical routes, and neither is a
Blender-to-Bevy **splat** export.

1. **Textured mesh route (the old Blender authoring path).**
   `scripts/apply_textures_headless.py` is still tracked. It opens
   `backrooms_infinite/assets/scenes/source/corridor_corner_box.blend`, assigns
   source textures to named box faces and exports a GLB with
   `export_yup=True`. The referenced `.blend` and the `backrooms_infinite/` tree
   are not tracked. This route carries positions, UVs, normals and materials;
   it has no Gaussians.
2. **Archived Bevy splat route.** `archive/splat_walk` loads `scene.ply`
   directly through `bevy_gaussian_splatting` v7 with the `io_ply`, `sh3`,
   `planar` and sort features enabled (`archive/splat_walk/Cargo.toml`;
   `archive/splat_walk/src/splat.rs` uses `PlanarGaussian3dHandle`). Blender
   appears only for mesh work: `decimate_to_glb.py` decimates the SuGaR
   collision mesh and `blender_cleanup_mesh.py` cleans the Stage M
   photogrammetry mesh. Both are triangle-mesh tools.

There is therefore **no tracked Blender-to-Bevy splat exporter to audit** for
attribute, SH or sorting loss. The question's categories need to be separated:

| Category | What the repo supports | What is unknown |
|---|---|---|
| Per-splat attributes | A GLB mesh round-trip cannot carry Gaussian scale, quaternion rotation, opacity or SH. It carries positions/UVs/materials. If the old route exported a mesh, the Gaussian primitive was not translated lossily; it was absent. | Whether the pre-repo Blender route exported meshes or PLY. No pre-repo files are tracked. |
| SH handling | Blender 5.3's importer maps the 45 `f_rest` floats into `radiance:sh_0..14` RGB vectors correctly for the tested channel-major layout (Section 3). No native importer existed for the old route. | Whether any custom SH conversion was used before this repo. |
| Sorting/alpha | Sorting is a renderer behaviour, not a file attribute; opacity is the data. A Blender render bakes one view and cannot carry a runtime sort order. | Whether the old route used a renderer that sorted differently. |
| Scale conventions | The old mesh route exports Y-up (`export_yup=True`). The splat handoff default converts Z-up to Y-up; the archived `corridor_straight/alignment.toml` instead used identity rotation because the Brush PLY header says Y-up. A double conversion is possible if those are mixed. That file also kept `scale = 1.0` and zero translation; scale was never recovered (`archive/PLAN_splat_collider_fix.md`). | Whether any axis mismatch actually caused the observed failure. |

What the repo **does** record as concrete handoff failures is not SH loss:

- On the Bevy side: scale never recovered, so the character controller and floor
  did not agree with the reconstruction
  (`archive/PLAN_splat_collider_fix.md`); a single monolithic concave trimesh
  collider tunneled and panicked; `bevy_gaussian_splatting`'s glTF loader
  collided with the separate collision GLB loading path (commit `82bc6dd`); the
  mesh-first path was abandoned after dense reconstruction collapsed under a
  two-view consistency check (commit `155c865`).
- On the Godot/GDGS side: a single NaN splat poisoned the merged AABB and
  blanked the camera framing (commit `8a1f91f`); far-flung floaters then
  inflated the AABB (commit `0a56442`). Those are not Blender-export losses, but
  they show the same PLY family needed cleanup before either engine could frame
  it.

So the honest answer to "what did the old Blender-to-Bevy route lose?" is: the
repo cannot show a Gaussian attribute/SH/sorting loss because the tracked
Blender route was mesh authoring and the tracked splat route bypassed Blender.
The recorded losses are scale/axis and collider handoff. If the operator's
earlier project did export Blender splats, those files are not in this repo and
cannot be audited here.

## 3. Q2: can Blender inspect, crop or clean our PLYs?

Environment: `/snap/bin/blender`, Blender 5.3.0, build date 2026-11-10. All
tests ran headless with `--background --factory-startup` and the Python API.
The core calls were:

```python
bpy.ops.wm.ply_import(filepath=path, up_axis="Y")  # Y only for the Brush file
bpy.ops.wm.ply_export(filepath=out, export_attributes=True)
bpy.ops.object.convert(target="MESH")  # export workaround, lossy
```

Assets tested:

| Asset | Splats | Format |
|---|---:|---|
| `data/scenes/backrooms_coverage_v1_gaussian_splatfacto/scene.ply` | 111,812 | Splatfacto, 62 float properties, z-up |
| `data/scenes/corridor_straight/scene.ply` | 746,100 | Brush, 59 float properties, y-up, one NaN |
| `godot_walk/assets/corridor_splat/corridor.ply` | 182,569 | Splatfacto, z-up |
| `godot_walk/assets/gdgs_demo/demo.compressed.ply` | 271,123 | GDGS compressed/chunked PLY |

### Import

- A standard 3DGS PLY imports as a `POINTCLOUD` object whose data type is
  `GAUSSIAN_SPLAT`.
- The attributes are: `position` (FLOAT_VECTOR), `radiance:base` (FLOAT4),
  `scale` (FLOAT_VECTOR), `rotation` (QUATERNION), and
  `radiance:sh_0..14` (FLOAT_VECTOR).
- The conversion is semantically correct on the first vertex of both Brush and
  Splatfacto files: `scale` is `exp(raw log-scale)`, `rotation` is normalised,
  and `radiance:base` is `(f_dc_0, f_dc_1, f_dc_2, sigmoid(opacity))`. The 45
  SH floats are reorganised from channel-major `f_rest` into 15 per-coefficient
  RGB vectors; they are not merely renamed.
- Import times were about 43-55 ms for 111k splats, about 300 ms for 746k, and
  about 76 ms for 182k.
- The headless import created **no material slots**. EEVEE and Cycles still
  rendered the radiance data (see below); this note does not claim a material
  node graph exists.
- The headless importer did **not** honour the `comment Vertical axis: y` in the
  Brush file. The axis must be passed explicitly (`up_axis='Y'`), otherwise the
  import is treated as Z-up. The axis choice is applied as an object transform,
  not by rewriting the point data; applying that rotation later moved the
  positions but left the `rotation` quaternions unchanged.
- The GDGS compressed PLY failed: `PLY Importer: failed importing
  demo.compressed: Vertex positions are not present in the file`. The three
  standard float-property 3DGS files imported; the compressed/chunked layout did
  not.

### Render

Both engines rendered a 512x512 headless frame with a simple camera:

- EEVEE (`BLENDER_EEVEE`, 32 samples): 25.2% non-black pixels.
- Cycles CPU (16 samples, no denoise): 21.5% non-black pixels.

The images were noisy, as the article predicts: EEVEE uses dithered
transparency and Cycles treats opacity stochastically. They are adequate for an
inspection test, not for a visual-quality judgement. This note makes no claim
about how the Blender render compares with the production GDGS view.

### Crop and edit

Native point-cloud editing exists: `bpy.ops.pointcloud.delete` removed selected
points, and a Geometry Nodes `Delete Geometry` on `position.x > 0` reduced the
111,812-splat file to 74,804 points in memory while preserving all splat
attributes. So a scripted or interactive crop is technically possible.

### Export

This is the blocker for a cleanup/cropping stage:

- `bpy.ops.wm.ply_export` on the `GAUSSIAN_SPLAT` object wrote a 156-byte PLY
  with `element vertex 0`, with and without object selection.
- Converting the point cloud to a mesh (`bpy.ops.object.convert(target='MESH')`)
  preserved 111,812 vertices and most custom attributes, but the PLY exporter
  wrote `scale_x/y/z`, `rotation_x/y/z/w`, `radiance:sh_0_x...` and **omitted
  `radiance:base` entirely**. The result has no colour or opacity and is not a
  canonical 3DGS PLY.
- USD export was not tested. The article describes USD as an import path, not
  an export path.

Conclusion for Q2: Blender 5.3 is a usable **viewer** for standard 3DGS PLYs and
a usable in-memory cropper, but it is not a usable cleanup/cropping **producer**
without a custom exporter that reconstructs the canonical `f_dc_*`, `f_rest_*`,
`opacity`, `scale_*` and `rot_*` properties.

## 4. Q3: does it help the current Godot/Hunyuan workflow?

No, for three separate reasons.

1. **The Hunyuan seed path does not use splats.** `PLAN.md` records that every
   Hunyuan candidate must start from a direct frame of its original source
   video, "never a Gaussian or rendered image".
   `PLAN_IMAGE_TO_PANORAMA_DESIGN_HARNESS.md` is more explicit: "The source is a
   2D video frame, not Gaussian data. Hunyuan receives no PLY, Gaussian
   embeddings, or splat artifacts". Blender's splat support cannot touch that
   path. The separate #121 Gaussian-backed design loop uses the #100 PLY in
   Godot; that is not a Hunyuan seed.
2. **The Hunyuan conversion does not use Blender.** `convert_hunyuan_layers.py`
   loads the generated layers with `trimesh` and writes a GLB. The pipeline's
   Blender scripts are mesh-only: `mesh_photogrammetry.sh` calls
   `blender_cleanup_mesh.py` for the Stage M triangle mesh, and
   `decimate_to_glb.py` is the retired SuGaR collision path. Native splat
   support changes neither.
3. **Godot is already the production viewer.** The #100 corridor and the #121
   Gaussian-backed design loop are rendered by GDGS at the production camera;
   the current Hunyuan PSX rooms use generated meshes, not splats. Blender's
   EEVEE and Cycles use different splat models (camera-oriented dithered
   billboards; stochastic ray intersections), so a Blender image is not a proxy
   for the Godot result. Using it for visual acceptance would introduce a second
   renderer with known differences.

There is one narrow use: an operator could open a PLY in Blender to orbit it and
look for floaters or detached blobs from an angle that is awkward in Godot.
That is a manual inspection aid, not a pipeline stage, and it cannot produce a
cleaned asset. The existing `clean_splat.py` already performs deterministic
bounds/extent/opacity filtering, preserves every vertex property, and records
the centroid translation that keeps the world fixed.

## 5. Q4: relation to the open issues

| Issue | Overlap | What this note adds | Action |
|---|---|---|---|
| #103 (standard cleanup) | Same goal: remove floaters and reduce visible holes. | Blender's point delete is a manual version of the same crop. It cannot export the result. The #103 ablations already show that component and multi-view filtering cost +4.7 to +30.2 points of black; Blender does not improve that. | Do not reopen or replace #103. Its "cleanup exhausted, new coverage needed" conclusion stands. |
| #105 (document cleanup techniques) | Both document cleanup limits. | A concrete import/export limitation of Blender 5.3, plus evidence that the native editor is not a format-preserving tool. | No edit to #105's planned doc is required; this note can be referenced if that doc is written. |
| #106 (textured-mesh route) | Blender already appears in the mesh path (`blender_cleanup_mesh.py`, `decimate_to_glb.py`). | Native splat support is orthogonal: #106 deliberately avoids Gaussians in the final visual path. | No change to #106. |
| #63 (reconstruction umbrella) | Visual-quality umbrella. | A negative result for one proposed inspection/cleanup tool. | No change. |
| #153 (Blender PSX Retro Tools assessment) | Prior conclusion: no Blender runtime dependency; Godot-native materials suffice. | Native splat support does not change that conclusion; it adds no Godot runtime capability. | No change. |

## 6. Q5: recommendation

**Ignore as a pipeline stage.** Do not add Blender to the splat cleanup,
cropping or validation path, and do not open a follow-up implementation issue
for this.

Evidence:

- Import and rendering work, but direct PLY export produced zero vertices and
  the mesh-conversion fallback lost colour and opacity.
- The compressed GDGS PLY used by the Godot demo does not import.
- The Hunyuan seed path is explicitly direct-video-frame only, so there is no
  splat to inspect there.
- The current Blender pipeline scripts are mesh-only and unaffected.
- The existing deterministic cleanup is measured, preserves the canonical PLY,
  and is already wired into the Godot scenes.

Optional manual inspection is allowed for a human with Blender 5.3 installed:
open a standard 3DGS PLY, set the up axis explicitly, and use EEVEE or Cycles
only as a second view. Do not treat that render as production-view evidence.
Revisit Blender only if a future release adds a native 3DGS export, or if a
separate need justifies writing and testing a custom exporter. Any visual
judgement remains with the operator; this note makes none.

## 7. Unknown and untested

- SPZ import and USD loading were not tested (no fixture was available).
- The interactive drag-and-drop import dialog was not tested; only the headless
  `bpy.ops.wm.ply_import` path.
- Relighting, normal estimation and albedo extraction were not tested.
- Files larger than 746k splats were not tested.
- USD or other non-PLY export paths were not tested.
- The original pre-repo Blender project and its exact export settings are not
  tracked, so no claim is made about its SH, sorting or alpha handling.

## References

- Article: <https://code.blender.org/2026/10/splatting-the-gaussians-into-blender/>
- Old Blender authoring script: `scripts/apply_textures_headless.py` (tracked;
  its referenced `.blend` is not).
- Archived Bevy splat route: `archive/splat_walk/Cargo.toml`,
  `archive/splat_walk/src/splat.rs`, `archive/PLAN_splat_collider_fix.md`.
- Current pipeline: `scripts/splat_pipeline/README.md`,
  `scripts/splat_pipeline/blender_cleanup_mesh.py`,
  `scripts/splat_pipeline/decimate_to_glb.py`,
  `scripts/splat_pipeline/clean_splat.py`,
  `scripts/splat_pipeline/splat_cleanup.py`.
- Current Godot/Hunyuan direction: `PLAN.md` (Current Execution Context and
  #101 sections), `PLAN_IMAGE_TO_PANORAMA_DESIGN_HARNESS.md` (A2),
  `scripts/splat_pipeline/convert_hunyuan_layers.py`.
- Cleanup evidence: `godot_walk/assets/corridor_splat/CLEANUP.md`,
  `godot_walk/assets/corridor_splat/CANDIDATE.md`,
  `godot_walk/evidence/2026-10-07-splat-cleanup-candidate/REPORT.md`.
- Relevant commits: `8a1f91f` (NaN splats), `0a56442` (floaters), `82bc6dd`
  (glTF loader collision), `155c865` (mesh path abandoned).
