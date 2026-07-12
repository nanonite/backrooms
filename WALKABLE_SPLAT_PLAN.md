# Walkable Splat Plan — Collider From The Splat, Not By Hand

**Chainlink umbrella: #78** (sub-issues created from this plan). Supersedes the
manual-box approach in #75. Related: #80 (navmesh builds on the same collision mesh).

## Why we're stuck (diagnosis, 2026-07-11)

The pattern itself — **Gaussian splat for visuals + invisible collision geometry
for physics** — is the industry-standard way to make splats walkable (Unity/UE
splat walkthroughs all do this). Nothing about the approach is broken. Two
specific defects are blocking us:

### Defect 1 — the two scenes disagree about the splat's orientation
- `godot_walk/scenes/corridor_splat.tscn` renders the splat node with a **180°
  Z rotation**: `Transform3D(-1, -8.742278e-08, 0, 8.742278e-08, -1, 0, 0, 0, 1, 0, 0, 0)`
  (flips X and Y).
- `godot_walk/scenes/corridor.tscn` (the walkable scene) renders the same splat
  with **identity** transform.
- Colliders were hand-tuned from *raw PLY percentile bounds* while the visual
  was flipped relative to those numbers. This is the unsolved "floor axis
  doesn't match PLY Y" mystery in LESSONS_LEARNED §5.2. It's not a GDGS
  mystery; it's a transform mismatch between our own scenes.

### Defect 2 — manual box fitting doesn't converge (proven, 3 failed iterations)
Hand-tuning six planes + a column via in-game position overlay is a dead end
(LESSONS_LEARNED §6.1). The splat centers ARE a clean point cloud of the room —
generate the collision mesh from them programmatically.

## The fix (three work items)

### W1 — Canonical splat transform (fixes Defect 1)
Pick ONE canonical transform for the splat node (validate right-side-up via the
screenshot harness), apply it identically in `corridor.tscn` and
`corridor_splat.tscn`, and put the collider container node under the **same**
transform. Rule going forward: **colliders are authored/generated in raw PLY
space; the shared parent transform maps both splat and colliders into world
space.** Alignment then holds by construction — no eyeballing, ever.

Document the canonical transform in `godot_walk/assets/corridor_splat/README.md`.

### W2 — `scripts/splat_pipeline/fit_collider.py` (fixes Defect 2)
Generate a collision mesh from the splat PLY, entirely in raw PLY coordinates:

1. Load `godot_walk/assets/corridor_splat/corridor.ply` (numpy + plyfile).
2. Filter: sigmoid(opacity) ≥ 0.5, then percentile crop (P2–P98 per axis) to
   drop floaters.
3. Voxelize surviving centers at 0.15 m.
4. Extract exposed voxel faces (occupied voxel face adjacent to empty voxel) →
   quads → triangles.
5. Write `godot_walk/assets/corridor_collision/corridor_collision.obj`
   (raw PLY space — **no rotation, no axis swap, no scale** in the script).

Splat centers lie on surfaces (walls/floor/ceiling/column), so interior air is
empty voxels — the player volume is naturally hollow. Backrooms geometry is
boxy; a chunky 0.15 m voxel surface is plenty because the splat renders over it.

### W3 — Wire the mesh into Godot + walk-test gate
1. Import the OBJ; build a `ConcavePolygonShape3D` from its faces (editor-baked
   trimesh collision, or `shape.set_faces(mesh.get_faces())` at `_ready`).
2. Place it under the transform-matched collider parent from W1. Delete the
   hand-tuned boxes (keep the SafetyNet).
3. Verify headless: `verify_scene.gd` + walker — player `is_on_floor()` after
   90 frames, can traverse the room's X span, and the navigability assertion
   from #75's re-scope (traversable gap ≥ 0.6 m player diameter + margin).
4. Interactive check with **Debug → Visible Collision Shapes** enabled.

## Delegation order

| Order | Issue | Depends on | Parallel-safe |
|---|---|---|---|
| 1 | W1 canonical transform | — | yes, with W2 |
| 1 | W2 fit_collider.py | — | yes, with W1 (pure Python, raw PLY space) |
| 2 | W3 Godot integration + gate | W1 + W2 | no |

On W3 done: close #78 and #75 (superseded), unblock #80 (navmesh bakes over the
same collision mesh) and #79 (multi-room reuses `fit_collider.py` per room).

## Honest fidelity ceiling (so nobody chases ghosts)

A splat only looks good near its training trajectory. One 8 s orbit clip ≈ a
2–3 m bubble of good viewpoints; outside it you get smears and holes. Veo clips
can't be merged (each hallucinates a different room), so **one clip = one
room's viewing volume**. The achievable product is *walkable dioramas connected
by portals* (#79) — colliders that keep the player inside the well-observed
core are a feature, not a limitation. Full free-roam in one large space would
require real captured video or modeled geometry (splat-as-scan, retopo in
Blender), which is out of scope for this track.
