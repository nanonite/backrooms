## Goal (Handoff contract — front-end ↔ back-end interface)
Define and document the exact interface where the two halves meet, so they can be
built in PARALLEL. Get this right and the front-end and back-end never block each
other beyond this contract.

## Prereqs / Blockers
- No hard code dependency; can (and should) be written EARLY.
- Relates to: Stage D (produces the co-registered pair) and Back-end Step 4 (consumes
  `alignment.toml`).

## The contract — per scene, the front-end produces EXACTLY:
| File | Role | Consumed by |
|------|------|-------------|
| `scene.ply` | Gaussian splat, visual only | `bevy_gaussian_splatting` |
| `collision.glb` | coarse mesh, invisible, physics only | Avian trimesh collider |
| `alignment.toml` | up-axis + uniform scale + translation | `SceneAlignment` resource |

Asset location consumed by the Bevy app:
`splat_walk/assets/splats/<scene_name>/{scene.ply, collision.glb, alignment.toml}`

## `alignment.toml` schema (define here; loader implemented in Back-end Step 4)
```toml
# Maps the reconstruction's arbitrary frame into Bevy world (Y-up, RH, metric).
# Applied IDENTICALLY to the splat entity and the collider entity.
[rotation]            # quaternion (x, y, z, w); default = Z-up -> Y-up (-90deg about X)
x = -0.70710677
y = 0.0
z = 0.0
w = 0.70710677

scale = 1.0           # uniform; makes a known real distance match Bevy units

[translation]         # drops player spawn onto the floor
x = 0.0
y = 0.0
z = 0.0
```

## Coordinate-frame facts (the why)
- COLMAP/VGGT/splat tools: Z-up or Y-down, ARBITRARY scale + origin.
- Bevy: Y-up, right-handed, roughly METRIC (1.7m capsule, 9.8 m/s² must feel right).
- `scene.ply` and `collision.glb` come from the SAME reconstruction (Stage D
  co-registration) → ONE transform fixes BOTH.

## Files to create
- `splat-handoff/HANDOFF_CONTRACT.md` (or fold into `scripts/splat_pipeline/README.md`)
  — the authoritative copy of the table + schema above.
- A committed `alignment.toml` template at
  `splat_walk/assets/splats/_template/alignment.toml`.

## Acceptance criteria
- The three deliverables, their locations, and the TOML schema are documented in ONE
  authoritative place referenced by both tracks.
- A template `alignment.toml` exists and deserializes into `SceneAlignment` (default
  = Z-up→Y-up, scale 1.0, translation 0).

## Symptom → cause guide (include in the doc)
- Falling forever     → collider below/misaligned OR scale wrong.
- Giant / ant-sized   → scale wrong.
- Walking on walls    → rotation wrong (up-axis not fixed).
