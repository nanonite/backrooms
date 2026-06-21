# Corridor Video Capture Spec — `corridor_walk_v2`

> **Why this exists, and what we learned the hard way.** Two clips have now failed
> COLMAP reconstruction, for two *different* reasons. Both produced spiky-needle
> splats instead of walls. The lesson is not "rotate more" — it's the opposite of
> what the first version of this spec said.
>
> | Clip | baseline | lateral/fwd | near-field | median tri-angle | failure mode |
> |------|---------:|------------:|-----------:|-----------------:|--------------|
> | Original 4 s straight dolly | 11.5 | 2.2% | 41% | 5.7° | motion *along* optical axis — points sit near the focus-of-expansion, tiny angles |
> | New 4 s "weave + look at walls" | 12.8 | 86% | **8.2%** | 4.0° | **far-field dominant** — camera travelled fine, but 92% of points are distant corridor near the vanishing point |
>
> **Key facts proven from the data:**
> 1. Parallax (triangulation angle) comes from the camera **physically translating**
>    relative to **nearby** surfaces. Turning the view (yaw/pitch/pan) does nothing —
>    pure rotation is a panorama with zero baseline.
> 2. The second clip rotated *very little* and translated *plenty* (baseline 12.8,
>    travel ratio 1.48) — yet still failed, because a straight backrooms hallway is
>    mostly **far-field**: endless receding walls near the vanishing point that
>    subtend <5° no matter how far you walk. Reprojection error was clean (1.29px),
>    so this is geometry, not AI-video warping.
> 3. Therefore the lever is **near-field coverage**: keep textured surfaces CLOSE to
>    the camera and move LATERALLY past them, and/or shoot a **bounded** space (corner,
>    doorway, alcove) instead of an open shaft to infinity.
>
> Run `scripts/splat_pipeline/preflight_parallax.py <sparse/0>` on any new clip's
> COLMAP model BEFORE training. It now names which failure mode you hit.

## Output target
- Length: **20–30 s** (longer is fine; more distance covered = more baseline)
- Frame rate: **24–30 fps** (~480–900 frames)
- Resolution: **1920×1080**, sharp; no motion blur, minimal film grain
- One continuous shot — no cuts, no teleports

## Camera motion (the whole point — create NEAR-FIELD parallax)
1. Walk forward at a slow, steady pace — but the forward dolly is *not* the source of
   parallax. It's the lateral component below that matters.
2. **Hug one wall, then cross to the other.** Pass within arm's reach of a wall, slide
   along it, then traverse diagonally to the opposite wall. Close + lateral = big angles
   on near texture. This is the single most important behavior.
3. **Keep something textured within ~1–2 m of the lens at all times** — a wall, a door
   frame, an outlet, a stain, a pipe. Never let the frame be only the far vanishing point.
4. **Prefer bounded geometry.** A corner you round, a doorway you pass through, an alcove
   — anything that puts nearby surfaces on *multiple sides* of the path. Avoid the open
   straight shaft to infinity; that is the failure case.
5. Optional: a slow **half-orbit** around one near feature (door frame, light fixture).
   Orbiting a close object gives the widest angles of all.

## Avoid
- **Open straight corridor to a distant vanishing point** (clip 2's failure — far-field).
- **Pure forward dolly down the optical axis** (clip 1's failure — focus-of-expansion).
- **Panning / "looking around" in place as a substitute for moving** — rotation adds no
  baseline. Turn the view only while *also* translating laterally.
- Fast motion, motion blur, rolling-shutter wobble.
- Flickering lights, fog, frame-to-frame texture changes (breaks feature matching).
- Blank, featureless walls — keep stains, trim, outlets, signs so COLMAP has features.

## Generator prompt (drop-in)
Continuous 25-second first-person walkthrough of a liminal backrooms corner, slow steady
forward motion while drifting laterally from one wall to the other and passing close to
the walls, door frames, and wall fixtures so nearby surfaces fill much of the frame,
rounding a corner into a connecting hallway. Camera stays close to textured surfaces, no
distant empty vanishing-point shots. Consistent rigid geometry, stable lighting, sharp
focus, no motion blur, no flicker, photorealistic, fixed camera lens.

## Hand-off
Drop the clip at `data/scenes/corridor_straight/video.mp4`, then run:
```
scripts/splat_pipeline/colmap_and_gate.sh data/scenes/corridor_straight/video.mp4 data/scenes/<name>
python3 scripts/splat_pipeline/preflight_parallax.py data/scenes/<name>/sparse/0
```
The preflight gate refuses to train if parallax is too low, and prints the failure mode.
Pass targets: **median triangulation angle ≥ 12°**, **lateral/forward ratio ≥ 20%**,
**near-field coverage ≥ 40%**.
