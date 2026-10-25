# #155 — two standalone Godot PSX room review candidates

Status: **operator review required**. Both rooms are playable and use the same
existing open-source PSX shader package. Neither whole room is approved or
catalog-promoted. #149 remains blocked. Godot 4.6.3 is unchanged; Bevy stays deferred.

Open [the comparison](comparison.png): left is the native Godot baseline,
right is URSC materials. Both sides retain the same existing native compositor
(pixel size 3, 24 color levels, dithering). This compares the packaged material
effects against today's native workflow, not against a completely PSX-free view.
Raw images are in `captures/{column,pocket}/{native_baseline,ursc_candidate}/`.
All eight captures use 960×540, FOV75, matched cameras and20 settling frames.
`capture_manifest.json` contains the exact poses and load-to-ready measurements.

## Existing tool selection

| Tool | Verified overlap / decision |
| --- | --- |
| [URSC1.5](https://github.com/Zorochase/ultimate-retro-shader-collection/releases/tag/1.5) | MIT shader collection: snapping, affine mapping, nearest filtering, vertex colors, documented unshaded configurations. Selected only its two common includes. Tested here on4.6.3 Vulkan Forward+. |
| [PSX Visuals GD4](https://github.com/scolastico/psx_visuals_gd4) | MIT integrated plugin with similar runtime effects and optional automatic conversion. A full editor/plugin setup adds nothing needed for this scoped comparison; not installed. |
| [PSX Look Free](https://heyheythere.itch.io/psx-look-free) | Free sampler advertises snapping, affine mapping, vertex colors and low-resolution screen rendering; unshaded brightness retained. Its screen wrapper duplicates our existing compositor responsibility. Not downloaded or runtime-tested. |

[LoFi PSX](https://emaceart.itch.io/lofi-psx) is paid and its listed requirement is
Godot4.7+; no purchase or engine upgrade. PS1ShaderMixer, GodotRetro, GarrettGunnell,
AnalogFeelings and CalinP alternatives are not required to prove this workflow:
their overlapping effects would add another implementation to validate. Their
compatibility/licensing was not established in this change.

This is **runtime overlap**, not a one-for-one replacement for Blender's offline
mesh simplification, UV work or texture baking. No Blender process, video generation,
Hunyuan inference or custom shader effect mathematics was introduced.

URSC is pinned to release1.5 / commit
`8cd971d0a275ef126151a99adf49cae1a64614c4`. MIT license and original credits are
retained under `vendor/ursc`. Common include/license are byte-identical;
utilities only gains a final newline. `provenance.json` records both local and
upstream checksums. Two tiny macro configurations select unshaded, double-sided,
fog-disabled textured/vertex-color shaders. A thin adapter copies each material's
texture, color and UV scale to fresh candidate materials. No source material is edited.

Shared preset: snapping intensity1, affine mapping ON, nearest sampling,
texture LOD reduction OFF, distance culling OFF. Hunyuan vertex colors remain in
use; both room surfaces are unshaded. The accepted column keeps its exact image
bytes, UV scale, face size and placement. Snapping changes only rendered vertices;
collision is untouched. F6 restores original native materials and back again.
URSC globals live once per review process; the editor setup script is not used
and no `project.godot` settings or global auto-converter are installed.

## Rooms and observations

**Column bay**, `godot_later_bay_column_v1`: inherits the accepted #151 four-sided
box candidate explicitly. Footprint9.9×13.8, height2.4 in the existing uncalibrated
convention. The Hunyuan room remains visible. The two cameras exactly match #151
anchor/east views. Face dimensions, transform, source image and collision snapshot
match the accepted repair. It remains a blocky prism. Surrounding Hunyuan floor
fragments/jagged visual seams remain and are more conspicuous under snapping;
this package does not repair generated geometry. Texture matching remains unresolved.

**Authored early pocket**, `godot_authored_early_pocket_v1`: a narrower6×13.8 closed
room with no column. Uses #148's original floor/ceiling visual geometry and all50
original collision triangles with their original transforms. The existing scene
report supplies wall, ceiling grid and light-panel boxes; historical wallpaper
stripe boxes are replaced visually by the existing source-video wallpaper texture.
The floor/ceiling gain planar visual UVs only; collision is unchanged. Source
textures are reused unchanged with nearest sampling. Both native and packaged
modes render the floor and ceiling double-sided, avoiding a misleading missing
ceiling baseline. The room is fully enclosed and walkable in Godot.

This is **authored architecture inspired by frames13–27**, not a recovered second
room, confirmed source connection or metric reconstruction. The views look
different from the bay, but share yellow source textures and the same preset.
Affine mapping visibly shears large floor/wall polygons; the comparison makes
that tradeoff reviewable. Acceptance of that distortion is not assumed.

Both records keep `registration_accepted=false`, `scale_calibrated=false` and
`operator_approved=false`. No Godot connector socket is tested or catalog-admitted;
both standalone collision perimeters are closed. Old Bevy catalog acceptance
does not count as acceptance of these new Godot rooms. See `room_readiness.json`.

## Verification

- Headless out-and-back routes and eight boundary pushes PASS for both rooms;
  floor support fraction1.0, no safety-net contacts. Reports in `mechanics/`.
- Four meaningful negative controls correctly return failure: remove each
  room's floor or east boundary. Failure reports show lost support/escape, not
  merely a missing target or script error.
- `test_library_rooms.gd` PASS: unchanged bay collision; exact source column
  texture/UV/size/transform; preserved50 pocket triangles/transforms; working
  native-material toggle; false calibration/approval flags; pocket double-sided
  native floor/ceiling; column obstacle ray.
- Existing column-box, round1 and round2 Godot checks PASS. All18 discovered
  project Python tests PASS. No Rust changes; Cargo is outside this change.
- Seven protected source checksums match earlier #148/#151 records. New source
  and plugin checksums are in `provenance.json`.
- Final Vulkan captures complete without shader/script warnings or errors.
  Existing editor import encountered an unrelated historical `.blend` path
  warning; these candidates use GLB/runtime loading and run without Blender.

GPU preflight enforces existing20% VRAM/25% RAM headroom before GPU runs.
Performance logs report actual frame-post-draw counters, frame-time percentiles,
process wall time and maximum RSS. Runs are capped at60; they do not establish
uncapped throughput. `capture_manifest.json` measures resource-load/instantiate/
ready CPU time during the capture run, excluding first draw/driver startup.
Only4.6.3 Vulkan Forward+ was rendered here. These pins, scenes and matched views
can be reused for the deferred4.7 assessment.

Measured at 960×540 on the RTX 4070 Ti, capped to 60 FPS:

| Room / materials | Actual FPS | p95 ms | p99 ms | Peak RSS KiB |
| --- | ---: | ---: | ---: | ---: |
| Column / native | 60.003 | 16.813 | 16.945 | 2,031,764 |
| Column / URSC | 60.003 | 16.818 | 16.918 | 2,031,684 |
| Pocket / native | 60.002 | 16.816 | 16.913 | 538,884 |
| Pocket / URSC | 60.004 | 16.795 | 16.901 | 538,660 |

Column measures 719 drawn intervals over 12 sampled poses; pocket measures 839
over 14 poses. Small rates above 60 are interval-counting/cap timing, not a
higher configured cap. Load-to-ready in the final capture process: column
2,223 ms, pocket 54 ms. Pocket loads second with shaders already cached;
these are observations rather than equivalent cold-start benchmarks.
Combined capture process: 4.21 s wall time, peak RSS 2,030,720 KiB.

## Next review

Walk both scenes using `COMMANDS.md`; decide whether each whole room and this
shared preset are acceptable. The accepted column repair stays accepted
independently. If approved, the next Godot work is explicit connection sockets,
an authored seam/transition and bidirectional traversal tests before generation.
Nothing is selected, promoted, committed, or closed by this evidence.
