# Issue 286: capturing rugged wall faces from source footage

Research only. No code, asset, hash-pinned file, model, download or GPU work was
performed for this document. Issue #286 and its comments were read on 2026-11-19
(`chainlink issue show 286 --json`): status open, label `research`, `comments=[]`,
`blocked_by=[]`, related to closed #273. No operator comment beyond the issue
description applies.

Web access was available on 2026-11-19. Every external project, method and
library API named below has an identifiable source link and a check date in the
[Source-check log](#source-check-log). Nothing is asserted about a project whose
licence, maintenance or platform support was not checked; those items are
explicitly marked **unverified**. Nothing was installed, downloaded or run.

## The local baseline this research starts from

Facts verified from the named local files (no new measurement or inference):

- `docs/research/issue-257-depth-non-orthogonal-walls.md` recommended a
  controlled authored-detail comparison inside the existing footprint. Its
  "Ready-to-file first implementation slice" became #273.
- `godot_walk/evidence/2026-11-17-issue-273-canyon-depth-cues/REPORT.md` records
  that v2 added **23 visual-only `MeshInstance3D` nodes** (15 wall fins, 5
  overhead ledges, 3 boulder caps) to the accepted v1 canyon. Footprint,
  colliders, seed, panorama, camera and PSX settings are identical to v1; there
  is no new collider. Mechanical checks passed (collider parity, negative
  controls, matched camera poses, frozen hashes). Appearance was left pending:
  "Agents cannot judge appearance."
- `.../rooms/slot-canyon-courtyard-v2/room.gd` shows the relief is authored
  constant arrays of thin `BoxMesh`es; `visual_relief_node_count` is 23 and
  `visual_relief_visual_only` is true. No entry creates a `StaticBody3D`,
  `CollisionShape3D` or `BoxShape3D`.
- `.../v2/adaptation_candidate.json` records the source evidence actually
  available: a 1280×720, 1541-frame, ~51.5 s video; a single operator-selected
  direct frame `frame_1363` (index 1362, PTS 45.4454 s); five direct rectangular
  crops of that frame (`wall_strata_dark`, `wall_strata_warm`, `sandy_floor`,
  `slot_glow`, `rock_rubble`); and a 512×256 Hunyuan panorama used only as a
  camera-centred background with no parallax. All geometry is in uncalibrated
  design units; `registration_accepted=false`, `scale_calibrated=false`.
  The doc explicitly records that all v2 relief is **invented, not measured or
  inferred from the source**, and that the relief has no collider and can
  visually overlap collidable walls.
- `godot_walk/room_catalog/MATERIAL_LANGUAGE.md` (read only) records the shared
  PSX profile: Godot 4.6.3, pinned URSC 1.5 subset, affine mapping off via the
  project override, nearest filtering, unshaded source-derived materials,
  vertex snap 1. It warns against global UV rotation to hide a local seam and
  against treating pixel differences as a quality score.
- **Locally verified renderer constraint:** `godot_walk/scripts/library_psx_preset.gd`
  converts every `StandardMaterial3D` into a `ShaderMaterial` using
  `godot_walk/shaders/library_psx_{textured,vertex}.gdshader` and copies only
  `albedo_color`, `albedo_texture` and `uv_scale`. The shaders are unshaded URSC
  wrappers. A grep over `godot_walk/shaders` and `godot_walk/vendor/ursc` found
  no `parallax`, normal-map, height or displacement parameter in use. Therefore
  any method whose effect lives in a normal/height/parallax material property
  would be **discarded by the current PSX conversion** and would require changes
  to renderer code, not just content. That is out of scope for this research and
  is not proposed in the first slice.

The question is whether a repeatable process could derive wall relief from this
source evidence for canyon, rock, brick, rough-plaster or ruins rooms instead of
hand-authoring each variant. No such derivation is claimed or tested here.

## Acceptance 1 — at least five candidate methods

Each entry states what it returns, its link, licence, maintenance status and
Linux/CPU needs. "Unverified" means it was not independently checked on
2026-11-19.

### Method 1 — Luminance-as-heightfield from one accepted frame crop

- **What it is / returns:** Treat a greyscale (luminance) reading of an accepted
  direct wall crop as a relative height profile; emit either a greyscale height
  image or sampled vertex offsets for a visual-only mesh. No external tool is
  needed: the crop is already in the room, and mesh generation uses Godot's
  in-engine `SurfaceTool`/`ArrayMesh` API (procedural geometry runs on the CPU).
- **Link:** https://docs.godotengine.org/en/stable/classes/class_surfacetool.html
  and https://docs.godotengine.org/en/stable/tutorials/3d/procedural_geometry
  (checked 2026-11-19).
- **Licence:** Project-owned pipeline and project-owned crop. The licence and
  redistribution terms of the **source video itself are unverified**; this must
  not be assumed. Godot's engine licence was not checked in this research.
- **Maintenance:** The local files are the current project files; the Godot API
  is documented in current stable docs. No separate project to maintain.
- **Linux/CPU needs:** Linux already used by the project; mesh generation is
  CPU-side (verified by the Godot procedural-geometry docs). No GPU, no install.
- **Unverified:** Whether luminance of these particular dark/warm strata crops
  correlates with real wall shape. It is a *texture-derived profile*, not a
  reconstruction; bright/dark may be lighting or watermark, not geometry.

### Method 2 — Tileable crop-based relief from source frames (current approach)

- **What it is / returns:** This is the v1/v2 approach generalised: direct
  rectangular crops of one (or several) frames become albedo textures on
  authored boxes; relief is added as more boxes with different sizes, tilts and
  staggered heights. Returns PNG crops plus authored scene nodes; no depth map,
  no mesh derived from the image, no collider.
- **Link:** local evidence — `.../v2/adaptation_candidate.json` crops section
  and `.../v2/room.gd` `RELIEF_FINS`/`RELIEF_LEDGES`/`RELIEF_ROCK_CAPS`;
  `godot_walk/room_catalog/MATERIAL_LANGUAGE.md` (read 2026-11-19).
- **Licence:** Project-owned crop definitions. Source-video licence unverified.
- **Maintenance:** Current project code; no third-party dependency.
- **Linux/CPU needs:** File I/O and scene authoring only; no GPU, no install.
- **Unverified:** The existing crops are **not** made seamless — the material
  kit explicitly warns about seams. Calling this "tileable" would be wrong;
  a genuine seamless-crop workflow (crop selection, seam blending) was not
  designed, tested or verified here.

### Method 3 — Normal map from an image, via a command-line tool

- **What it is / returns:** Convert a greyscale height image into a tangent-space
  normal-map PNG. A concrete Linux/CPU candidate is `realh/normalmap`: a C
  command-line utility that converts a PNG to greyscale, applies a 3×3 Sobel
  filter and writes a normal map; options cover scale, normalisation and wrap
  for tiling.
- **Link:** https://github.com/realh/normalmap (checked 2026-11-19).
- **Licence:** GPL-3.0 (verified from the repository licence metadata).
- **Maintenance:** Repository present with 39 commits and 23 stars, created
  2016; **recent maintenance activity not independently verified**. Do not
  assume it is actively maintained.
- **Linux/CPU needs:** Builds on Linux/Unix with autotools, `libpng` ≥1.6 and
  `popt`; CPU-only (verified from its README). No GPU.
- **Unverified / blocking for this project:** The current PSX preset copies only
  albedo into the custom shader (see local constraint above), and the surfaces
  are unshaded, so a normal map would have **no visible effect** without
  renderer changes. Whether any normal-map workflow can be made compatible with
  the pinned PSX look without editing hash-pinned renderer files is untested.

### Method 4 — Parallax / relief mapping in the material

- **What it is / returns:** A height texture sampled in the fragment shader to
  offset UVs along the view direction, producing an illusion of cavities without
  moving vertices or changing collision. Godot's `BaseMaterial3D` exposes
  `heightmap_enabled`, `heightmap_scale` and `heightmap_deep_parallax` (the last
  uses parallax occlusion mapping and is documented as more expensive on the
  GPU); the manual describes the height map as a ray-marched depth *illusion*,
  not real geometry, and recommends combining it with normal mapping.
- **Link:** https://docs.godotengine.org/en/4.6/classes/class_basematerial3d.html
  and https://docs.godotengine.org/en/stable/tutorials/3d/standard_material_3d.html
  (checked 2026-11-19).
- **Licence:** Godot engine licence not checked in this research (already a
  project dependency). No new third-party asset.
- **Maintenance:** Godot is actively documented; the 4.6 class docs and current
  stable docs both describe these properties. The project is pinned to 4.6.3.
- **Linux/CPU needs:** Runs on the project's Linux/Godot setup, but it is **GPU
  fragment work** and explicitly more expensive with deep parallax — a conflict
  with this task's no-GPU stance for *research*, and a runtime cost to evaluate
  separately. No install.
- **Unverified:** The local preset converts `StandardMaterial3D` to the URSC
  shader and drops height/normal properties, so built-in parallax would not
  survive. Tangent availability on our `BoxMesh`/`ArrayMesh` relief and behaviour
  under the unshaded URSC subset were not tested. This method needs renderer
  code changes; it is not a content-only change.

### Method 5 — Monocular relative depth from a single frame (offline guide)

- **What it is / returns:** A model that estimates a per-pixel **relative** depth
  map from one image. A concrete candidate is Depth Anything V2 (NeurIPS 2024):
  Small/Base/Large checkpoints, with separate metric checkpoints. Returns a
  depth image, not a mesh, not a collider, not metric scale by default.
- **Link:** https://github.com/DepthAnything/Depth-Anything-V2 and
  https://depth-anything-v2.github.io/ (checked 2026-11-19).
- **Licence:** Code Apache-2.0; **Small weights Apache-2.0**, while
  Base/Large/Giant weights are CC-BY-NC-4.0 (verified from the repository
  README and licence file). Check weight licence before any use.
- **Maintenance:** Repository present, created 2024-06, 21 commits, ~7.2k stars;
  upstream news entries run to 2025-01-22. **Current maintenance tempo not
  independently verified.**
- **Linux/CPU needs:** Python/PyTorch; GPU inference is the common path.
  CPU-only feasibility and speed on this machine were **not verified**. Using it
  would require a model download and a model run, both forbidden for this task.
- **Unverified:** Accuracy on this dark, watermarked canyon frame; scale/affine
  fit to design units; stability between frames. Single-view estimates can
  mistake lighting for geometry, have unknown scale and omit occluded surfaces.

### Method 6 — Multi-view photogrammetry / MVS depth from several frames

- **What it is / returns:** Structure-from-Motion and Multi-View Stereo over a
  set of overlapping frames. A concrete candidate is COLMAP (already present in
  the project environment per `AGENTS.md`): returns camera poses, sparse points,
  per-image depth and normal maps, a fused point cloud and an optional textured
  mesh (verified from the COLMAP tutorial and FAQ).
- **Link:** https://github.com/colmap/colmap , https://colmap.github.io/tutorial.html
  and https://colmap.github.io/faq.html (checked 2026-11-19).
- **Licence:** BSD-3-Clause for the COLMAP library itself; third-party
  dependencies are separately licensed (verified from the COLMAP licence page).
- **Maintenance:** Actively maintained project (current docs show ongoing
  development; repository created 2014 with large community use). Verified.
- **Linux/CPU needs:** Linux builds supported. Sparse/SfM steps can run on CPU
  with explicit flags (e.g. `--FeatureExtraction.use_gpu=false`), but the
  **dense patch-match stereo stage requires a CUDA GPU** per the COLMAP FAQ;
  CPU-only dense reconstruction is not available. This is a one-time offline
  input, not a runtime component.
- **Unverified:** Whether the 1541 source frames are suitable (moving camera,
  narrow canyon, low light, watermark); whether sufficient overlap and stable
  poses exist; whether a reconstruction would align with the authored footprint.
  No reconstruction was attempted.

## Acceptance 2 — collision, determinism, PSX fit and source evidence

| Method | Collision separate from visuals? | Deterministic? | Keeps PSX look? | Source evidence it needs |
|---|---|---|---|---|
| 1. Luminance heightfield / displaced strips | Yes, if emitted as `MeshInstance3D` with no collider and bounded offset | Yes, if crop hash, sample grid, seed and parameters are fixed and recorded | Yes: geometry passes through the existing URSC conversion unshaded; no new shader | **Single frame** (one accepted crop) |
| 2. Crop-based relief (current) | Yes, demonstrated by #273 visual-only nodes | Yes: byte-fixed crops + authored constants + recorded hashes | Yes, already accepted path | **Single frame** today; several frames only if new crops are added |
| 3. Normal map from image | Yes, texture only | Conversion deterministic for a pinned tool version and parameters | **No, not as-is:** PSX preset drops normal maps and surfaces are unshaded; renderer changes needed | **Single frame** height/normal source |
| 4. Parallax / relief mapping | Yes, illusion only, no collider | Deterministic math for fixed height map | **No, not as-is:** preset drops height properties; GPU cost and tangents unverified | **Single frame** height map |
| 5. Monocular depth (offline) | Yes, used only as guidance | Conditional: pinned weights/params, but bit-reproducibility and GPU nondeterminism **unverified** | No direct runtime effect unless converted to geometry/material (not tested) | **Single frame** |
| 6. COLMAP SfM/MVS (offline) | Yes, offline output only | Conditional: pinned version/params; solvers not claimed bit-reproducible | No direct runtime effect; **GPU/CUDA** needed for dense stage | **Several overlapping frames** |

The #273 rule is preserved only by methods that emit visual nodes and never a
collider, with a bounded visible-to-collision difference. Methods 3–6 can
*inform* such nodes, but none of them was run here and none is recommended as a
runtime replacement for the authored colliders.

## Acceptance 3 — mechanical validation versus operator-only judgment

### Mechanically checkable (agents can assert these)

- **No new colliders:** compare the full collider signature (names, centres,
  sizes, layers of every `StaticBody3D`/`CollisionShape3D`) against the accepted
  baseline; assert floor bodies, six perimeter walls and three rock obstacles
  are unchanged; assert obstacle and floor counts are unchanged. #273 already
  has this comparator and a 23-node visual-count assertion to reuse in pattern.
- **Negative controls:** disable one wall → boundary ray misses; disable all six
  walls → boundary ray misses; remove a floor collider → floor ray misses;
  restore between checks. These prove the parity check can detect an escape or
  a missing boundary, not that appearance improved.
- **Displacement bounds:** assert every visual node's offset is within a declared
  per-axis bound and inside the existing visual envelope AABB
  (`min [-4.3,-0.24,-10.3]`, `max [11.3,7.2,8.3]` from
  `.../v2/adaptation_candidate.json`); assert overhead nodes remain above the
  capsule top (Y > 1.2 in v2); assert no relief node intrudes into the asserted
  walk lane; assert the visible-to-collision difference stays under a recorded
  limit. Any proposed numbers are authored limits, not measured source dimensions.
- **Determinism / provenance:** record the input crop hash, sample grid, seed,
  parameters and output hash; re-run with identical inputs and assert identical
  outputs; use a read-only verifier so no ledger event or hash is hand-written.
- **Matched camera poses:** one paired-capture harness for baseline and variant;
  identical camera `fov/near/far` and identical view and walk-step poses; clean
  guard receipts (`return_code=0`, `timed_out=false`, `error=null`); matched view
  set (spawn, bend, wall, sky slot) plus the deterministic walk path.
- **Frozen artifacts:** unchanged hashes for hash-pinned files, accepted rooms,
  contracts, `catalog.json`, `MATERIAL_LANGUAGE.md`, `PALETTES.md`,
  `project.godot` and `scripts/player.gd`; `registration_accepted=false` and
  `scale_calibrated=false` throughout.
- **Registration sanity:** `python3 godot_walk/scripts/register_video_sources.py validate`
  → `{ "valid": true, "registered_count": 13 }` (run for this document, 2026-11-19).

### Only the operator can judge

- Whether the relief **looks right**, reads as a canyon/rock/brick/plaster/ruins
  face, and improves perceived depth and wall character; whether it worsened or
  stayed unchanged.
- Whether the visible-to-collision mismatch (relief with no collider, possible
  overlap with wall/boulder colliders, flat-looking slabs up close) is acceptable.
- Whether any invented detail looks measured rather than authored.
- Whether a generalisation is worth the cost for other rooms, and any
  acceptance, catalog admission, registration or calibration decision.

**No agent can judge whether the relief looks right.** A passing validator,
clean capture or deterministic profile is not approval. Any future report must
record the visual decision separately and leave it pending when the operator has
not reviewed paired captures.

## Acceptance 4 — comparison, recommendation and a bounded first slice

### Short comparison

| Method | Cost / risk | Fit with #273 rule and PSX profile |
|---|---|---|
| 1. Luminance heightfield / strips | Low: in-engine, one crop, no install; risk of meaningless "height" from lighting | Best fit; visual-only, deterministic, PSX-safe |
| 2. Crop-based relief | Low, already proven; risk of seam/flat-slab appearance | Best fit; this is the accepted baseline method |
| 3. Normal map | Low-medium tool cost; **blocked** by unshaded/preset dropping normal maps | Needs renderer changes; not content-only |
| 4. Parallax | Medium; **blocked** by preset dropping height, plus GPU cost | Needs renderer changes; conflicts with no-GPU stance |
| 5. Monocular depth | Medium-high; model download/run forbidden here, scale unknown | Offline guide only; would still need a visual-only emission step |
| 6. COLMAP | High; several frames, CPU SfM + CUDA dense, alignment unknown | Offline input only; heavyweight for a bounded room experiment |

### Recommendation

Generalise **methods 2 + 1 first**: keep the accepted crop-and-box pipeline, and
add a deterministic height profile sampled from an already-accepted wall crop to
drive a small number of visual-only displaced strips along an *authored* wall
polyline. This preserves the #273 invariants, determinism, PSX look and the
visual/collision separation without any install, model, GPU or renderer change.
It is a repeatable *authoring aid*, not a measurement or a reconstruction.

Defer methods 3 and 4 until a separately authorised renderer experiment can
show the PSX look survives; defer 5 and 6 until a concrete compute environment,
licence check and offline-input evaluation are authorised. Do not let any model
output become a collider, a calibration claim or a registration claim.

### Ready-to-file first implementation slice

**Title:** Deterministic visual-only wall relief from a seed-frame height profile (canyon v3 experiment)

**Scope:** Create a new `slot-canyon-courtyard-v3` folder and candidate based on
the accepted v1 / reviewed v2 canyon, reusing the same seed `frame_1363`, the
five accepted direct crops, the accepted panorama, declared L-shaped XZ
footprint, spawn, colliders, camera and PSX profile. For one bounded family of
inner wall faces, sample a low-resolution 1-D height profile from the luminance
of an accepted wall-strata crop and emit a small, fixed number of visual-only
`MeshInstance3D` strips (or displaced strips) with offsets derived from that
profile. Record the input crop hash, sample grid, seed, parameters and output
hash. Proposed caps to fix in the slice, not source measurements: ≤30 added
visual nodes and per-node offset ≤0.2 authored design units, all inside the
existing visual envelope and above the walk lane. No collider, no new crop, no
model, no download, no GPU, no shader change and no contract change. Both
`registration_accepted` and `scale_calibrated` stay false; this is an
experiment, not catalog admission.

**Acceptance:** A separate candidate and provenance record identify baseline and
variant; matched captures from the existing spawn, bend and wall viewpoints plus
the repeatable walk path support comparison. Automated checks confirm unchanged
declared footprint, spawn, traversal and containment, full collider parity with
the baseline, no new collidable obstacle, deterministic reproduction of the
profile/hashes, all offsets within the declared bounds, and the existing
floor/boundary/missing-boundary negative controls. Frozen artifacts and accepted
files are unchanged. No improvement is presumed by a passing mechanical check.
The operator reviews paired captures and records whether perceived depth and
wall character improved, worsened or stayed unchanged, plus whether the
visible-to-collision mismatch is acceptable. An agent does not approve appearance.

**Verification:** Run the baseline and v3 headless room tests; run the candidate
validator for v3; run the new read-only verifier and mutation tests for
collider parity, displacement bounds, node count, determinism, matched camera
poses, negative controls and frozen hashes; run the guarded paired captures
through the existing guard wrapper; run
`python3 godot_walk/scripts/register_video_sources.py validate`. Record commands,
result lines and exit codes. If rendering or operator access is unavailable,
report that limitation and leave the visual decision pending. Do not push and
do not close the issue.

## Acceptance 5 — unknowns not tested

- No implementation, crop, model, download, install, GPU run, render capture,
  photogrammetry solve or perceptual study was performed for this document.
- The licence and redistribution terms of the source video are unverified. No
  licence or maintenance claim is made for any project not named above.
- Whether luminance of the accepted wall crops tracks real wall shape is untested;
  bright/dark regions may be lighting or watermark rather than geometry.
- Whether the 1541 frames contain enough stable, overlapping camera poses for
  COLMAP SfM, and whether any output would align with the authored footprint, is
  untested.
- Accuracy, scale behaviour, CPU feasibility and cross-frame stability of
  Depth Anything V2 on this specific dark, watermarked frame are untested.
- Whether built-in Godot height/parallax works with the pinned URSC preset, and
  whether our meshes provide the required tangents, are untested. The local
  preset is known to drop height/normal properties.
- Whether a normal-map workflow can preserve the unshaded PSX look without
  editing hash-pinned renderer files is untested.
- Generalisation to brick, rough plaster, ruins or other rock rooms, and the
  performance/compatibility cost of any renderer change, are untested.
- True canyon dimensions, camera pose, hidden surfaces and metric depth remain
  unknown; all units are authored and uncalibrated.
- Whether the operator will accept any visible-to-collision mismatch, or judge
  any relief to look right, is undecided and is explicitly not an agent judgment.

## Source-check log

All links below were checked on **2026-11-19**; "verified" means the linked page
stated the fact at check time, not that a tool was run or installed.

| Source | What was verified |
|---|---|
| https://www.blender.org/about/license/ , https://www.blender.org/releases/ | Blender code GPL-2.0-or-later (binaries GPL-3.0-or-later; artwork remains the user's); active releases incl. 5.3 stable released 2026-11-10 and LTS lines. Used only as background for the height→normal bake idea; no Blender method is recommended in the first slice. |
| https://docs.blender.org/manual/en/latest/render/shader_nodes/displacement/bump.html | Bump node generates a perturbed normal from a height texture; baking normals from a height/shader setup is the documented route. |
| https://github.com/realh/normalmap | C CLI, GPL-3.0, Linux build via autotools with libpng/popt, 3×3 Sobel PNG→normal map, wrap option; 39 commits / 23 stars, recent maintenance unverified. |
| https://colmap.github.io/license.html , https://github.com/colmap/colmap | COLMAP library BSD-3-Clause (third-party deps separate); active project. |
| https://colmap.github.io/tutorial.html , https://colmap.github.io/faq.html | SfM/MVS outputs (poses, depth+normal maps, fused cloud, textured mesh); CPU flag for feature extraction; dense patch-match stereo requires CUDA GPU. |
| https://github.com/DepthAnything/Depth-Anything-V2 , https://depth-anything-v2.github.io/ | NeurIPS 2024 monocular depth; code Apache-2.0, Small weights Apache-2.0, Base/Large/Giant CC-BY-NC-4.0; repo created 2024-06, news to 2025-01. |
| https://docs.godotengine.org/en/stable/classes/class_surfacetool.html , https://docs.godotengine.org/en/stable/tutorials/3d/procedural_geometry | `SurfaceTool`/`ArrayMesh` build meshes from script; procedural geometry generation runs on the CPU. |
| https://docs.godotengine.org/en/4.6/classes/class_basematerial3d.html , https://docs.godotengine.org/en/stable/tutorials/3d/standard_material_3d.html | `heightmap_enabled`, `heightmap_scale`, `heightmap_deep_parallax`; height map is an illusion, not geometry, and is recommended with normal mapping; deep parallax is GPU-expensive. |
| Local files listed in "The local baseline" | All local claims (23 visual-only nodes, crop/panorama/source identities, PSX profile, preset dropping material properties, frozen-hash policy, #273 acceptance) were read from the repository, not from the web. |
