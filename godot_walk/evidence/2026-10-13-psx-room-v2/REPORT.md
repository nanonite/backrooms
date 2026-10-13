# Manual PSX Room Extension v2

**Status:** runnable experiment for Chainlink #115; keep #115 and parent #113
open for visual review. Do not unblock #114 yet.

## Decision

The separate v2 scene demonstrates a repeatable manual extension around the
best preserved #100 patch without retraining, cropping, pruning, generating a
new video, or using paid models. The sampled spawn-connected standing area is
17.63 m2 at 10 cm grid resolution, and the verified out-and-back route is
13.067 m. The old bounded control's approximately 2 m2 footprint is materially
smaller, but the area figures are not from an identical sampling method.

The candidate is not a finished room. The images still show attached ceiling
smears, rough splat-to-wall junctions, and a boxy authored wing. Intermediate
views expose small black wedges that compass-only captures miss. Keep this as
a promising workflow prototype, not a replacement for #100 or a claim of
whole-room reconstruction.

## Scene And Protection

`corridor_psx_room_v2.tscn` inherits `corridor_psx.tscn` and adds the
procedural `AuthoredBoundaries` child implemented in
`scripts/psx_patch_room_extension_v2.gd`. The existing
`corridor_psx_patch_extension.tscn` remains the separate control. Authored
surfaces are explicitly game art; the splat remains the preserved visual
source.

The room shell bounds are x=-1.35..4.00 m and z=-2.80..3.40 m. The transition
partition is at x=2.80 m, with a framed opening and threshold. The authored
floor collider covers x=0.45..4.00 m and z=-2.80..3.40 m: a gross footprint of
22.01 m2 that overlaps the generated floor. The visible authored carpet is
the extension east of the partition (7.44 m2). Neither rectangle is presented
as net walkable area; inherited collision and authored boundaries constrain
where the player capsule fits.

The protected #100 assets and production scene were not edited. Recorded
SHA-256:

| Asset | SHA-256 |
|---|---|
| `corridor_clean.ply` | `88a20a95dd4df4dde98203f7fb934d17db93a9cb5d98e8c1625d478e9d7af0` |
| `alignment_manifest.json` | `85d5b51c8ca9df614b81a6f6dddf8c68015cca14b36e3b007c1a67f50be03598` |
| `collision/corridor_splat.collision.glb` | `3d3111c6e1f953f7c3cc53f5bcb3094193c01c5318252e95597f9885e9146f0d` |
| `scenes/corridor_psx.tscn` | `c6ebbb4877c94fac1e77cdcf504c49a1d83b2593e545fd540e5970c74b9a987f` |

The #104 working-run file-tree digest was also checked:
`aa7f4a3f93740450014512e4e7e71671dcf95526ad86621c3c4ee7896430dbc3`.
No #104 files were written.

## Patch And Render Evidence

The qualitative splat-only map is in [`PATCH_MAP.md`](PATCH_MAP.md). At the
`(+0.50,+1.70)` anchor, the best native directions are south/southeast; north,
northwest, and southwest remain poor or artifact-heavy. The map is based on
three sampled stations and does not imply unseen geometry was recovered.

At the patch anchor, eight matched 1280x720 headings compare production
`corridor_psx.tscn` with v2 at identical eye position and FOV. Mean black
pixels fall from 3.761% to 0.000% rounded; the maximum v2 heading is 0.001%.
The existing detached-component detector reports 20.6 mean floater pixels
before (165 maximum, one blob) and zero after. Mean changed pixels are
42.158%; this is an RGB difference, **not** an authored-contribution mask.

Across 24 v2 compass views at the patch, transition, and annex stations, the
maximum black share is 0.076% and the detached-floater detector reports zero
pixels. A 216-frame sweep over 24 yaw samples and pitches -60/0/+60 at those
three stations has 0.106% mean black pixels, 2.426% maximum, and zero measured
detached floater pixels. These established metrics do not detect attached
streaks or smears. Contact sheets: `patch_only_contact.jpg`,
`candidate/patch_anchor_contact.jpg`, `candidate/transition_contact.jpg`,
`candidate/annex_contact.jpg`, and `sweep_route_{2,3,6}_yaw.jpg`.

No exact surface-provenance mask was produced. Layer-hidden RGB differences
are not used to infer ownership. The scene keeps the production camera,
75-degree FOV, eye height, background, compositor, and PSX settings.

## Traversal And Runtime

The route is `(-0.65,2.90) -> (0.50,2.90) -> (0.50,1.70) -> (1.25,1.70) ->
(2.60,1.70) -> (2.60,0.20) -> (3.50,0.20)`, then reversed. The verifier
measures 13.067 m out-and-back, 100% floor support, zero SafetyNet contacts,
and 0.0667 m maximum tick displacement. Observed support collision contacts
are recorded separately as `AuthoredFloorExtension` (161) and
`GeneratedCollision` (35) in `physics_candidate.json`.

The verifier's area estimate samples the player's capsule on a 10 cm x/z grid,
requires a floor ray at the expected height, raises the capsule query 2 cm to
avoid counting floor tangency as a blocker, then counts the 4-neighbor
component nearest the route start. It finds 1,763 spawn-connected placements,
or 17.63 m2. This is a resolution-dependent standing-area estimate, not an
exact polygon or a fixed acceptance threshold.

Both negative controls fail as intended: removing `EastBoundary` lets the
probe cross the bounded envelope; removing both configured floor bodies
produces SafetyNet contacts and missing-support failures. The intact eight-way
boundary push test retains floor support and stays inside the envelope.

On an RTX 4070 Ti with Godot 4.6.3 Vulkan Forward+, the 1280x720 draw callback
benchmark records 60.002 fps capped (p95 16.856 ms, p99 16.923 ms) and 1,389
uncapped callbacks/s (p95 0.947 ms, p99 1.030 ms). These are
`RenderingServer.frame_post_draw` intervals, not GPU timestamp timings.

## Verification

Passed: editor import, `test_psx_scene.gd`, `verify_alignment.gd`,
`verify_scene.gd`, v2 bounded traversal, and both expected negative controls.
The current control and production scene remain runnable. See
[`COMMANDS.md`](COMMANDS.md) for exact reproduction commands.

Final visual review added a compact authored service hatch at the east
endpoint, giving the blank annex end wall a distinct landmark. It does not
resolve the attached ceiling smears or rough splat-to-wall junctions. The next
#115 pass should refine the offset transition and junctions, review the
high-pitch sweep artifacts, and keep recording human-reviewed patch quality.
Do not turn the present pixel deltas into provenance claims or start #114
until this manual loop is repeatable and accepted.
