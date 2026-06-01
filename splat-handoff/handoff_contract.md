# Handoff Contract — Front-end ↔ Back-end

**Authoritative interface between the offline reconstruction pipeline and the Bevy runtime.**

This document is the single source of truth for what the front-end produces, where
files live, and what the back-end expects. Both tracks reference this contract.
Get this right and they never block each other beyond it.

---

## 1. Per-scene deliverables

Every scene lives under `splat_walk/assets/splats/<scene_name>/`. For each scene,
the front-end pipeline produces exactly three files:

| File | Role | Consumed by |
|------|------|-------------|
| `scene.ply` | Gaussian splat, visual only | `bevy_gaussian_splatting` |
| `collision.glb` | Coarse mesh, invisible, physics only | Avian trimesh collider |
| `alignment.toml` | Up-axis + uniform scale + translation | `SceneAlignment` resource (#104) |

The full path template:

```
splat_walk/assets/splats/<scene_name>/scene.ply
splat_walk/assets/splats/<scene_name>/collision.glb
splat_walk/assets/splats/<scene_name>/alignment.toml
```

A default template lives at `splat_walk/assets/splats/_template/alignment.toml`.

---

## 2. Issue ownership

| Deliverable | Produced by | Consumed by |
|-------------|-------------|-------------|
| `scene.ply` | FE-C (#107) Brush training | BE-2 (#102), INT-5 (#110) |
| `collision.glb` | FE-D (#108) SuGaR/2DGS extraction | BE-3 (#103), INT-5 (#110) |
| `alignment.toml` | This issue (#112) schema defined; values tuned during BE-4 (#104) ritual | BE-4 (#104), INT-5 (#110) |
| `SceneAlignment` loader | BE-4 (#104) | BE-4 (#104), INT-5 (#110) |
| This contract | #112 (this issue) — authoritative doc | All front-end and back-end subissues |

---

## 3. `alignment.toml` schema

The canonical schema. This is what the `SceneAlignment` loader (#104) deserializes.

```toml
# Maps the reconstruction's arbitrary frame into Bevy world (Y-up, RH, metric).
# Applied IDENTICALLY to the splat entity and the collider entity.
#
# Default: Z-up → Y-up rotation (-90° about X), scale 1.0, translation zero.
# This default assumes a reconstruction that uses Z-up and needs no rescaling.

scale = 1.0           # uniform; top-level key — makes a known real distance match Bevy units

[rotation]            # quaternion (x, y, z, w)
x = -0.70710677       # -sin(45°) for -90° rotation about X
y = 0.0
z = 0.0
w = 0.70710677        # cos(45°) for -90° rotation about X

[translation]         # drops player spawn onto the floor
x = 0.0
y = 0.0
z = 0.0
```

### Type mapping (for the Rust loader in #104)

| TOML key | Rust type | Bevy equivalent |
|----------|-----------|-----------------|
| `scale` (top-level) | `f32` | `Vec3::splat(scale)` |
| `rotation.{x,y,z,w}` | `f32` × 4 | `Quat::from_xyzw(x, y, z, w)` |
| `translation.{x,y,z}` | `f32` × 3 | `Vec3::new(x, y, z)` |

The combined `Transform` applied to both entities:

```rust
Transform {
    translation: alignment.translation,
    rotation: alignment.rotation,
    scale: Vec3::splat(alignment.scale),
}
```

---

## 4. Coordinate-frame facts

| Frame | Up axis | Handedness | Scale | Origin |
|-------|---------|------------|-------|--------|
| COLMAP / VGGT / splat tools | Z-up or Y-down | Right | Arbitrary | Arbitrary |
| Bevy | Y-up | Right | Metric (1 unit ≈ 1 m) | World origin |

Because `scene.ply` and `collision.glb` come from the **same reconstruction** (FE-D
guarantees co-registration via SuGaR/2DGS), **one transform fixes both**. The same
`alignment.toml` values are applied identically to the splat entity and the collider
entity. This is the core assumption that makes the back-end alignment tractable.

---

## 5. The alignment ritual (tuning values per scene)

Performed once per scene as part of BE-4 (#104). The result is a tuned
`alignment.toml` committed alongside the splat and collision mesh.

1. Load splat + collider with identity transform in a debug scene.
2. Add a 1 m reference cube and origin gizmo.
3. Find the **rotation** that makes the real floor horizontal (gravity along −Y).
   Usually a single −90° about X: `Quat::from_rotation_x(-FRAC_PI_2)`.
4. Find the uniform **scale** that makes a known real distance (e.g. doorway ≈ 2 m)
   match in Bevy units.
5. Find the **translation** that drops the player spawn onto the floor.
6. Bake these constants into the scene's `alignment.toml`.

---

## 6. Symptom → cause guide

Troubleshooting: when the player's experience violates the expected physics.

| Symptom | Root cause | Check |
|---------|------------|-------|
| Falling forever | Collider missing, misaligned, or scale wrong | Verify trimesh collider is present; re-check `alignment.toml` values; ensure scale produces metric-sized geometry |
| Giant / ant-sized | Scale wrong | Recalibrate `scale` against a known real distance (doorway, meter stick) |
| Walking on walls | Up-axis not fixed | Re-check `rotation` quaternion; floor should be horizontal (gravity along −Y) |
| Splat and collider visibly offset | Co-registration broken | The mesh was not extracted from the same Gaussians (re-run FE-D with SuGaR/2DGS, not an independent mesher) |
| Splat looks correct but collision feels offset | Different transforms applied | Ensure both entities receive the **identical** `alignment.toml` transform |
| Mesh has holes / fall-through gaps | Decimation too aggressive or floor has gaps | Hand-patch floor in Blender; continuous floor is the one hard requirement |

---

## 7. References

- **BE-4 (#104)** — `SceneAlignment` resource + loader that consumes this schema.
- **FE-D (#108)** — SuGaR/2DGS collision mesh extraction (the co-registration step).
- **FE-C (#107)** — Brush splat training that produces `scene.ply`.
- **INT-5 (#110)** — End-to-end integration consuming all three deliverables.
- **PLAN.md** — Milestone #10 build order and issue table.
- **splat-handoff/PLAN_video_to_splat.md** — Full implementation plan.
- **splat-handoff/be4_alignment.md** — BE-4 scaffold (alignment ritual detail).
- **splat-handoff/epic.md** — Epic overview with workspace decisions.
