# SceneGen Layer And Export Findings

Inspected upstream HunyuanWorld-1.0 commit
`57fa9f3a79eae1079c279968cdb9d82c75fa7c86`, the local indoor adapter, run-05
outputs, and the generated GLB. No inference was run for this inspection.
The code path is `demo_scenegen.py`, `hy3dworld/models/layer_decomposer.py`,
`hy3dworld/utils/seg_utils.py`, `hy3dworld/utils/layer_utils.py`,
`hy3dworld/models/world_composer.py`, and
`hy3dworld/utils/general_utils.py`; the local adapter is
`scripts/splat_pipeline/hunyuan_scenegen_runtime.py`.

## What A Layer Means

The upstream demo accepts `labels_fg1` and `labels_fg2` as text prompts. For
each foreground pass, GroundingDINO proposes detections and ZIM produces masks.
The mask JSON stores each detected label, box, score, and area. The mask PNG
combines all detections in that pass. The second foreground pass runs against
the image with the first foreground removed. FLUX inpainting fills those masked
regions to make residual panorama images. The sky pass is for outdoor scenes.

These are prompted segmentation and inpainting groups, not independently
reconstructed object assets. `WorldComposer` combines all detections in a
foreground pass into one mask and one mesh. It predicts panorama depth, aligns
the inpainted background depth to the original, and converts RGB, depth, and
camera rays into a triangulated image sheet. A vertex is computed as
`distance * ray` from the panorama origin. Foreground masks omit sheet quads;
background and optional sky become additional sheets. The depth is generated
from one panorama and has no calibrated metric unit.

The local indoor adapter calls foreground pass 1 and pass 2, then composes the
mesh. It omits the unused sky model and sky pass. In run-05, pass 2 has no
labels; `fg1.json` contains two `columns` detections, while there is no
`fg2.json` or `fg2_mask.png`. The composer therefore returns the foreground
sheet and then the background sheet. The exported `mesh_layer0.ply` is the
combined foreground, and `mesh_layer1.ply` is the residual background. There
is no second foreground mesh in this run.

The index is only the position in the composer's returned mesh list. The demo
discards each entry's `type` and writes `mesh_layer{index}.ply`. Missing masks
can shift all later indices. A default outdoor run can return foreground 1,
foreground 2, background, and sky, but an index alone still does not identify
any of those roles. The label-to-mask records stay in sidecar JSON; the GLB
does not contain the labels, boxes, or instance identities.

## Mesh And Conversion

The PLY is a binary little-endian triangle mesh. Its header declares double XYZ
and normal coordinates, byte RGB vertex colors, and triangular vertex-index
faces. It has no UV coordinates. The optional upstream `export_drc` path writes
a raw Draco `.drc` bitstream of the PLY mesh through Trimesh; it is disabled by
default and does not add semantic labels, metric scale, collision geometry, or
a glTF scene wrapper.

The local converter creates a glTF 2.0 binary scene with one identity-transform
node per input mesh. Inspection of the run-05 GLB confirms `POSITION` and
`COLOR_0` vertex attributes and triangle primitives. It has no explicit
`NORMAL`, `TEXCOORD_0`, materials, textures, or semantic extras, even though
the PLY header has normals. The 343 MiB GLB has 1,603,955 vertices / 3,235,413
triangles in the foreground node and 7,372,800 vertices / 14,783,952 triangles
in the background node. The converter does not rescale, decimate, repair
topology, or create collision data. Both source layers are open and
non-watertight; winding is inconsistent. See
[`hunyuan_layer_conversion_full_run.json`](hunyuan_layer_conversion_full_run.json)
and [`mesh_evaluation.json`](mesh_evaluation.json).

## Bevy And Harness Implications

This GLB is a standard static triangle-mesh asset, so it is a plausible input
to Bevy's glTF asset path. The exact asset still needs the Bevy fixture in
#133: verify import, vertex-color rendering, node names, orientation, memory,
and appearance without explicit normals. It is not a Gaussian-splat PLY and
does not replace the harness's splat asset contract by itself.

Keep the generated mesh as a visual candidate until the other gates pass:

- #133 verifies Bevy import and presentation.
- #134 calibrates scale and alignment against registered source-video poses.
- #136 investigates a collision representation suited to the task; the open,
  depth-sheet meshes are not accepted as player collision.
- #137 brings the accepted visual and collision assets into the design harness.

For a more useful handoff, preserve a sidecar mapping from output node to
composer role and source label/mask, retain the calibration transform, and keep
collision as a separately validated product. Do not infer role from
`mesh_layerN` or derive walkable collision directly from these panorama sheets.
