# PSX Design Variants

These candidate configs inherit the #115 room-v2 scene without editing it.
The initial comparison isolated the east-end service hatch because the live
review found it visually arbitrary and out of alignment. Later #121 rounds add
bounded visual treatments for walls, floors, ceilings, and the column; the
splat, route, PSX compositor, and collision remain fixed.

## Design Brief

- Preserve the smooth, fully supported 13.067 m route and the current
  spawn-connected room.
- Make authored details feel integrated with the room rather than decorative
  add-ons.
- Preserve the Gaussian source and accept residual artifacts only when they
  do not undermine the room's coherence. Do not alter the PLY in this track.
- Keep the current column face and splat-to-authored transition fixed in this
  first comparison. The artifact-facing column side needs a named camera/face
  annotation before an overlay can be placed responsibly.

## Variant Contract

`schema_version` is `1`. The candidate scene loads named JSON
files; arbitrary file paths are not accepted. Each config records a unique ID,
parent, Gaussian source type, hypothesis, and change summary.

`design.layout`, `design.transition`, and `design.materials` remain on the v2
values. `design.column_face_treatment`, `design.junction_treatment`, and
`design.surface_treatment` select bounded visual treatments declared in the
catalog. Material IDs map to the
existing v2 builder: `wallpaper_v2`, `carpet_v2`, `ceiling_v2`,
`olive_wainscot_v2`, `walnut_trim_v2`, `warm_emissive_v2`,
`service_green_v2`, and `brass_v2`. Collision bounds include the room shell,
wall thickness, floor extension, transition partition, and portal aperture;
they are copied from the v2 builder and validated exactly. A candidate cannot
move the floor, shell, portal, or route.

The Round 1 hatch comparison varies `design.doorway_policy`:

- `as_built`: preserve v2 door meshes and transforms.
- `flush_to_wall_face`: move the door leaf and its details 0.0155 m toward +X;
  leave the existing frame in place. This aligns the leaf with the frame's
  room-facing surface.
- `omit`: hide the door, frame, and details. These meshes have no collision,
  so the collision contract is unchanged.
- `wall_endcap`: hide the hatch and overlay existing PSX wall, wainscot, and
  trim materials across the east end. The overlay is visual-only and adds no
  collision.

Each value is an intentional discrete choice, not a free-form geometry input.
New material IDs, wall extents, door offsets outside the one supported flush
shift, other column placements, and collision changes require a separately
reviewed schema change with bounds and evidence.

## Run And Check

Run a candidate in the editor by opening
`res://scenes/corridor_psx_design_candidate.tscn` and choosing `variant_id` on
`VariantDriver`, or pass a variant on the command line:

```sh
godot4 --path godot_walk --scene res://scenes/corridor_psx_design_candidate.tscn -- --variant=door_flush
```

The supported IDs include `v2_control`, `door_flush`, `door_removed`,
`wall_endcap`, `north_wall_smooth`, `north_wall_source_texture`, `clean_ceiling`,
`source_texture_cleanup`, `source_floor_single_column`, and
`source_floor_ceiling_single_column`. The source-texture candidates
sample registered raw source-video frame 1; they do not sample a Gaussian
render. Verify
the schema and live scene variants with:

```sh
godot4 --headless --path godot_walk --script res://scripts/test_psx_design_variants.gd
```

The visual variant driver does not alter collision. Use the existing bounded
PSX verifier on each candidate before visual comparison.

## Deterministic Review Bundle (#120)

Run the full local review from the repository root with a Vulkan display:

```sh
DISPLAY=:1 python3 godot_walk/scripts/build_psx_design_review.py
```

The runner records three control repeats and one run per alternative, then
produces `godot_walk/evidence/2026-10-13-psx-design-review/index.html`.
That bundle contains matched 1280x720 captures, station contact sheets, ODiff
diff images and per-view changed-pixel counts, repeated route-state traces,
route/floor/boundary checks, boundary/floor negative controls, and uncapped and
60 FPS-capped measurements. It uses the viewport `get_image()` capture path;
it does not use MovieWriter or hidden-layer RGB as provenance.

The runner uses the installed `odiff` command when available. Otherwise it
invokes the pinned `odiff-bin@4.5.0` package through `npx`; the first invocation
may need npm network access. Godot must be available as `godot4` (or
`GODOT_BIN`), and the capture session needs the same GPU display used for
interactive previews. Use `--out-dir` to choose a fresh evidence directory;
the runner refuses to overwrite a non-empty directory.
If capture completed but report generation needs to be rerun, use
`python3 godot_walk/scripts/build_psx_design_review.py --report-only`.

The Round 1 hatch comparison remains intentionally narrow: only the hatch policy varies.
ODiff reports pixel differences, not room quality. The three control repeats
measure renderer and route noise before candidate deltas are interpreted; the
ODiff threshold is recorded at its explicit default value and is not tuned by
that experiment. The #100 splat, room-v2 geometry, collision, route, and native
column face remain unchanged in Round 1; later rounds add separately named
visual-only overlays and retain their own matched evidence.

## Human-Directed Design Round 1 (#121)

The first iteration round compares three east-end treatments: the as-built
hatch (`v2_control`), a wall-flush hatch (`door_flush`), and an authored PSX
end wall (`wall_endcap`). The last option hides the hatch and covers its noisy
view with existing wall, wainscot, and trim materials. The other production
visuals and the walkability contract remain fixed.

Run the full round with a Vulkan display:

```sh
DISPLAY=:1 python3 godot_walk/scripts/build_psx_design_round.py
```

The review bundle is written to
`godot_walk/evidence/2026-10-13-psx-design-round-1-final/index.html`. It includes
matched captures, ODiff diagnostics, route checks, negative controls, and
performance measurements. Route replay drift and a pairwise feedback sheet are
linked from the report. Review the far-room and column views first, then
choose, reject, or rank candidates with a reason. ODiff does not select a
winner. If only report generation needs rerunning, use:

```sh
python3 godot_walk/scripts/build_psx_design_round.py --report-only
```

The flush policy moves the door leaf and its details while keeping the frame
fixed. The wall-endcap policy adds visual meshes only; it does not alter
collision or the route. The round remains open until the operator reviews the
live walk and names the traits to carry into the next candidate.

## Human-Directed Design Round 2 (#121)

The operator selected `door_flush` at all four east-facing views. Their next
notes were that the right-hand wall feels incoherent and the ceiling still has
distracting Gaussian artifacts. Round 2 keeps the selected hatch and compares
it with a smooth panel treatment on the north wall and a lowered visual-only
ceiling grid. Both treatments leave the splat, route, collision, and room
envelope fixed.

Run the feedback-driven round with a Vulkan display:

```sh
DISPLAY=:1 python3 godot_walk/scripts/run_psx_design_round_2.py
```

The review page is
`godot_walk/evidence/2026-10-13-psx-design-round-2-final/index.html`. The
panel treatment visibly changes the north wall. The lowered ceiling changes
matched views only slightly, and ceiling Gaussian artifacts remain visible;
do not describe it as a fix. The route, negative controls, and capped frame
rate pass for all candidates. #121 remains open until the operator reviews
this round and approves a candidate.

## Human-Directed Design Round 3 (#121)

The operator said `north_wall_smooth` has the right shape but loses the original
Backrooms wallpaper. `north_wall_source_texture` keeps that exact wall treatment
and maps a crop from registered frame 1 of the #100 source video,
`data/scenes/corridor_travel/video.mp4`. The crop is x=1550, y=320, width=370,
height=380 pixels from `data/scenes/corridor_travel/images/frame_0001.jpg`; no
Gaussian render is used for the material. The room, hatch, route, splat, and
collision stay fixed.

Run the comparison with a Vulkan display:

```sh
DISPLAY=:1 python3 godot_walk/scripts/run_psx_design_round_3.py
```

The corrected review is
`godot_walk/evidence/2026-10-13-psx-design-round-3-source100/index.html`.
It passes the 13.067 m route, floor and boundary negative controls, and capped
60 FPS. Repeat noise is at most 0.11%. ODiff changes are diagnostics only; the
operator decides whether the crop's pattern scale and color fit. An earlier
round-3 check used the #107 coverage video by mistake and is superseded.

## Human-Directed Design Round 4 (#121)

The operator confirmed that texture preference changes with viewing angle.
`door_flush` preserves the native wall texture better in transition-west and
far-room-west, while source-textured walls help in several patch-anchor and
column views. Their remaining requests are square, artifact-free wall corners,
a finished column, and cleaner floor and ceiling surfaces. The operator also
reported a consistent, improving walk with no falls through the floor.

`source_texture_cleanup` keeps the flush door and leaves the far-end wall in its
original position so the door remains visible. It applies a visual-only
source-video crop to the north wall, ceiling, floor, and column, leaving the
Gaussian PLY and all collision unchanged. Crops come from registered raw frame
1 of the #100 source video. The north wall face moves 0.08 m toward the room to
cover the artifact layer; the floor, ceiling, and column covers add no collision.

Run the complete comparison with the local Vulkan display:

```sh
DISPLAY=:1 python3 godot_walk/scripts/run_psx_design_round_4.py
```

The corrected review bundle is
`godot_walk/evidence/2026-10-14-psx-design-round-4-final/index.html`. It
includes matched views, three control repeats, route and negative-control
checks, and capped/uncapped runtime measurements. The source-textured candidate
preserves the 13.067 m route with full floor support and no SafetyNet contacts;
capped performance is approximately 60 FPS. Review texture scale and fit by
view before treating this as the new baseline. ODiff is diagnostic only.

## Human-Directed Design Round 5 (#121)

Round 4 review found that its source-textured column cover appeared as a second
column. The authored cover was placed at z=2.55 m, away from the existing
column visible along the far-room z=0.2 m route. Round 5 keeps the round-4
candidate unchanged and compares two new visual-only treatments against
`door_flush`: a clean source-textured floor with one column cover aligned to the
existing centerline, and that same treatment plus a lowered source ceiling,
visually shortened boundary walls, and perimeter corner trim. Both variants
preserve the flush-door walls; neither edits the #100 PLY or collision.

Run the full comparison with the local Vulkan display:

```sh
DISPLAY=:1 python3 godot_walk/scripts/run_psx_design_round_5.py
```

The bundle is
`godot_walk/evidence/2026-10-14-psx-design-round-5-final/index.html`. The
aligned cover presents as one column in the far-room comparison. The lower
ceiling still shows bright and Gaussian artifacts and has more prominent trim;
it is exploratory, not a selected design. The 13.067 m route has 100% floor
support and zero SafetyNet contacts for all candidates; boundary and floor
negative controls fail as expected. Capped performance is approximately 60 FPS,
control repeat noise is at most 0.02%, and protected inputs are unchanged.
ODiff is diagnostic only. Keep #121 open for operator review and do not promote
either treatment to the control without a live walkthrough decision.
