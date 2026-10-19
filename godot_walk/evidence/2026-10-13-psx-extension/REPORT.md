# #113 Patch-to-PSX Room Control

## Decision

This is a separate, runnable **art-directed control**, not the generator result
or completion of #113. It wraps the strongest connected patch from the
production #100 splat in a textured, PSX-style room and keeps the original
micro-route. The current extension is substantially authored: use it to review
the patch-to-room hypothesis, not as recovered video geometry or as a
replacement for #100.

#113 remains open. Its next experiment is to refine the manual PSX room-building
loop, improve the authored composition and splat-to-room transitions, and
measure the visual contribution and runtime more completely. Optional free/open
local geometry-generation research must not gate that work. #114 remains
blocked on a reproducible #113 loop. Nothing here changes #104's full-coverage
Gaussian acceptance.

## Candidate

`scenes/corridor_psx_patch_extension.tscn` instances the unchanged
`scenes/corridor_psx.tscn` and adds `scripts/psx_patch_room_extension.gd` as a
separate authored boundary layer. It uses image-generated wallpaper, carpet,
and ceiling textures; textured shell geometry; trimmed waist-high dividers;
and a sealed door used only as visual room context. Its outer walls and
dividers have explicit collision. The floor and ceiling backstops are visual
only; existing `GeneratedCollision` remains the sole floor support for the
route. Materials use nearest filtering and unshaded rendering, while the
production lighting, 75-degree FOV, player eye, background, pixel compositor,
and color quantization remain inherited from #100.

The route remains spawn (-0.65, 2.90 m), east to (+0.50, 2.90 m), south to
(+0.50, 1.70 m), and back: about **2 m2 usable area** and **4.308 m**
out-and-back. It does not improve the prototype's small footprint. Half-wall
caps make the partitions read as room dividers/counters, but they still occupy
large portions of some views. The door, trim, and generated materials are
visual hypotheses, not a finished style guide.

## Matched Views

Godot 4.6.3, Vulkan Forward+, RTX 4070 Ti, 1280x720, 200 settle frames,
production FOV and eye height. Three route positions, eight compass headings
each, are captured for the unchanged production scene and this candidate.
Capture and comparison commands are in `COMMANDS.md`; full-resolution images
are under `baseline/` and `candidate/`; the candidate contact sheet is
`candidate_contact.jpg`.

| Metric over 24 matched views | #100 baseline | Extension control |
|---|---:|---:|
| Mean black/background pixels | 7.57% | 0.00% rounded; 0.001% maximum |
| Mean detached floater pixels | 388 px | 0 px |
| Mean image-change share | -- | 54.46% |

The image-change share is the existing fixed-threshold pixel delta, not an
authored-versus-splat pixel mask. Exact screen contribution, junction quality
at intermediate yaw/pitch, and runtime are still unmeasured. At the strongest
patch (+0.50, 1.70), east/south views retain the original splat as the visual
anchor; north/west views are intentionally supplied by authored room surfaces.
Zero measured detached components does not rule out attached streaks or
smears. The earlier bounded study's 54.9% authored-depth-reject result is a
lower bound for its geometry and must not be reused as a measurement for this
slightly expanded control.

## Traversal And Protection

The physics verifier reports a **4.3077 m** route, **100% floor support**,
zero SafetyNet contacts, and a **0.0687 m** maximum tick step. All eight
240-tick boundary pushes remain inside the prior envelope. A negative control
that deletes the east divider escapes and fails the boundary gate. No authored
floor collision is used.

The production asset and presentation scene still match their pre-run
identities:

| Protected file | SHA-256 |
|---|---|
| `assets/corridor_splat/corridor_clean.ply` | `88a20a95dd4df4dde98203f7fb934d17db93a9cb5d98f9e8c1625d478e9d7af0` |
| `assets/corridor_splat/collision/corridor_splat.collision.glb` | `3d3111c6e1f953f7c3cc53f5bcb3094193c01c5318252e95597f9885e9146f0d` |
| `scenes/corridor_psx.tscn` | `c6ebbb4877c94fac1e77cdcf504c49a1d83b2593e545fd540e5970c74b9a987f` |

The #104 run and the existing `corridor_bounded_psx.tscn` candidate were not
edited. No PLY pruning, retraining, or new video was performed.

## Optional Model Research

The PoC does not require a world-generation model, paid service, or access to a
model's latent embeddings. Its target is a manually authored, editable PSX room
around a reliable Gaussian patch. The three PNGs in
`assets/psx_extension/textures/` are generated 2D material references from the
existing Backrooms palette; they are not mesh generation and are optional to
the manual workflow.

Earlier reconnaissance noted [HunyuanWorld 1.0](https://github.com/Tencent-Hunyuan/HunyuanWorld-1.0),
[HY-World 2.0](https://github.com/Tencent-Hunyuan/HY-World-2.0), and
[Stable Fast 3D](https://github.com/Stability-AI/stable-fast-3d) as possible
research leads, not selected dependencies. None was installed or tested for
this experiment. Revisit model tooling only if a free/open model is readily
runnable locally and produces useful editable geometry through an available
workflow; it must not delay or gate the manual PSX extension loop.

## Verification

- `verify_bounded_psx.gd` on the new scene: pass.
- Boundary-removal negative control: expected failure, escaped envelope.
- `test_psx_scene.gd`: pass; production mapping, collision, spawn, player, and presentation scene remain valid.
- `verify_alignment.gd`: pass across both production scenes.
- GPU captures and render metrics: pass; 24 matched views, 200 settle frames.
- Full yaw/pitch sweep and FPS benchmark: not run for this control.
