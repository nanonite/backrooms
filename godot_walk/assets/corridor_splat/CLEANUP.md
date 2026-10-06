# Bounded splat cleanup for the corridor asset (#100)

The shipped `corridor.ply` renders a recognisable room only at its centre. Away
from the reconstruction camera path it is dominated by **floaters**: Gaussians
that sit in empty space and accumulate into a yellow-green haze. The forward
player POV was hazy over the room and the reverse view was almost fully
obscured.

This file records the cleanup that fixes that, why each threshold is what it is,
and the one trap that makes a filtered derivative different from the source.

## The measured problem

Measured on `corridor.ply` (182,569 splats) against
`alignment_manifest.json`:

| Quantity | Value |
|---|---|
| splats inside the contract's observed room | 78,892 (43.2%) |
| splats outside it | 103,677 (56.8%) |
| opacity (sigmoid) of the outside splats: median / p90 / p99 | 0.995 / 0.99998 / 0.999997 |
| largest Gaussian extent | 47.0 reconstruction units = **241 m** |
| rendered full-cloud AABB | 139.47 x 97.01 x 134.52 m |
| contract observed room | 18.84 x 2.40 x 14.39 m |

Two consequences fall straight out:

1. **The existing compositor `alpha_cutoff` cannot fix this.** It drops faint
   splats, and the floaters are not faint -- their median opacity is 0.995. The
   far-field haze survives every alpha cutoff that leaves real surfaces alone.
   This was tested before adding anything new.
2. **The crop is the load-bearing control.** The floaters are removed by *where
   they are*, not by how transparent they are. An extent threshold alone leaves
   a large AABB; an opacity threshold alone barely moves it.

## The filter

`scripts/splat_pipeline/clean_splat.py` writes a filtered derivative; the
decision logic lives in `scripts/splat_pipeline/splat_cleanup.py` and is unit
tested. The source PLY is never modified.

Applied in order, each a boolean over the survivors of the previous stage:

| Stage | Parameter (default) | What it removes |
|---|---|---|
| bounds | room + **0.5 m** margin | far-field floaters outside the observed room |
| extent | **0.30 m** max Gaussian extent | giant splats that stay inside the box but smear |
| opacity | **0.0** (disabled) | faint splats -- off, because the floaters are opaque and this risks real surfaces |

No percentile is used: a percentile threshold is a function of the very outliers
it is meant to drop, so a future asset would silently change it. Every threshold
is an explicit parameter, recorded in the report.

Shipped run (`corridor_clean.report.json`):

```
source=182569 kept=124564 removed=58005
removed per stage: {"bounds": 56437, "extent": 1568, "opacity": 0}
kept AABB: 19.83 x 3.40 x 15.39 m
```

## The centroid trap (why the presentation node has a translation)

`gaussian_resource_builder.gd` subtracts the **mean of the loaded PLY** at
import, and a scene's splat node carries the contract's **zero** translation
because that mean is the contract's `origin_ply_units`. Filtering removes
splats, so the filtered mean differs from the source mean, and a zero-translation
node would shift the world by

```
t_node = M * (centroid_filtered - centroid_source)
       = (0.2404, 0.0082, 1.5605) m   on this asset
```

`clean_splat.py` computes that vector and records it as
`node_translation_world`. `corridor_psx.tscn` carries it; `test_psx_scene.gd`
asserts the resulting world mapping equals the source contract. Without it the
room still imports and still renders -- just 1.56 m away in Z.

The cleanup itself does **not** move the world: kept splats keep their world
positions, and collision, SafetyNet and spawn are byte-for-byte the accepted
`corridor.tscn` values. `test_psx_scene.gd` asserts that too.

## Reuse for a future real-video fixture

```bash
python3 scripts/splat_pipeline/clean_splat.py \
    --ply        <asset>/scene.ply \
    --manifest   <asset>/alignment_manifest.json \
    --out        <asset>/scene_clean.ply \
    --report     <asset>/scene_clean.report.json \
    --margin-m 0.5 --max-extent-m 0.30
```

Then give the presentation scene's splat node the contract basis and the
report's `node_translation_world`, and add the PSX effect if desired. The
parameters are asset-independent starting points; re-measure the artifact mix
first (the module's docstring shows how) because a real capture's floaters may
not be opaque the way these are.

## Presentation effects

`res://scenes/corridor_psx.tscn` adds an optional PSX pass
(`scripts/psx/psx_post_effect.gd`): a coarse pixel grid plus ordered-dither
colour-depth reduction. It is presentation only -- it runs on the finished
colour buffer, never touches geometry or collision -- and it is switchable off
independently (`psx_enabled = false`, `--no-psx` on the command line, or by
removing the effect). The geometry/alignment review scenes
(`corridor.tscn`, `corridor_splat.tscn`) load the **source** asset and carry **no**
presentation effects, so `verify_alignment.gd` keeps checking the full cloud.
