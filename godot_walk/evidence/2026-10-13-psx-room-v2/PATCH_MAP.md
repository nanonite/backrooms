# Splat-Only Patch Map

These captures hide `AuthoredBoundaries` and keep the production #100 splat,
camera, FOV, eye height, and compositor unchanged. Labels are human review of
recognizable structure and visible smearing; they are not thresholded quality
scores or pixel-ownership masks.

| Station | Eye x/z (m) | Good | Marginal | Poor |
|---|---:|---|---|---|
| `route_1` | +0.50 / +2.90 | S, SE | E, NE, NW, W | N, SW |
| `route_2` | +0.50 / +1.70 | E, S, SE | NE, W | N, NW, SW |
| `route_3` | +1.25 / +1.70 | S, SE | NW, W, SW | E, NE, N |

The most dependable native views are south and southeast around the
`(+0.50, +1.70)` patch anchor. North/northwest reveal holes or unstable
surfaces. The southwest view has a large foreground smear, and moving toward
the east-side transition makes east/northeast views deteriorate. Black-pixel
measurements alone do not capture these attached artifacts.

This map supports a manual composition choice: preserve the south/southeast
patch as the recognizable room, then use a framed, offset transition into
authored space. It does not establish clean native 360-degree coverage or
reconstruct unseen surfaces.

Evidence: [`patch_only_contact.jpg`](patch_only_contact.jpg), with individual
captures under `patch_only/route_1`, `patch_only/route_2`, and `patch_only/route_3`.
