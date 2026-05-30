## Goal (Front-end Stage D — extract collision mesh) [THE co-registration step]
Extract a triangle mesh (`collision.glb`) — the PHYSICS asset — from the trained
splat. This is the mesh the character controller stands on. It is NEVER rendered.

## Why SuGaR / 2DGS (and why this matters most)
Use SuGaR (Anttwo/SuGaR) or 2D Gaussian Splatting (2DGS). KEY PROPERTY: the extracted
mesh is SURFACE-ALIGNED to the SAME Gaussians, so the mesh and the splat share ONE
coordinate frame automatically — they are CO-REGISTERED FOR FREE. This is precisely
what makes back-end alignment tractable (one transform fixes both — see Back-end Step 4).
Do NOT extract the mesh by some independent method that breaks co-registration.

## Prereqs / Blockers
- Depends on Stage C (`scene.ply` + the gs checkpoint Brush/SuGaR uses).
- Requires SuGaR install. WARNING: SuGaR's Poisson/texture baking is VRAM-heavy; on
  12GB it may OOM. We do NOT need a textured mesh — coarse, low-poly, vertex-only
  geometry is enough for collision. Use `--low_poly True` and skip texture baking.

## Commands
```bash
# Coarse mesh is enough for collision. The mesh can be UGLY and low-poly.
python train.py -s scene_dir/ -c <gs_checkpoint> -r density \
    --export_obj True --low_poly True
# produces a .obj co-registered with the splat
```

## Optional cleanup (Blender — repo already has Blender tooling)
- Open the mesh, delete floating junk, decimate AGGRESSIVELY to <200k triangles.
- Ensure the main FLOOR is a continuous surface (gaps = fall-through).
- Export as `.glb` (Bevy-native) → `scene_dir/collision.glb`.
- Floors/walls extract cleanly; vegetation/thin rails come out blobby — ACCEPTABLE
  (collision just feels slightly lumpy there; never rendered).

## Files to create
- `scripts/splat_pipeline/extract_mesh.sh` — wraps SuGaR export, parameterized.
- `scripts/splat_pipeline/decimate_to_glb.py` — headless Blender decimate + glb export.
  NOTE (repo gotcha): Snap Blender suppresses stdout/stderr — headless scripts must
  write to a LOG FILE, not print(). Use the log()/write_log() pattern from
  `scripts/bake_ao_vertex_colors.py`.

## Acceptance criteria
- `scene_dir/collision.glb` exists, <200k triangles, continuous floor.
- Loads in Bevy as a mesh (for the trimesh collider) — verified at integration.
- Shares the splat's coordinate frame (co-registered) — verified when ONE transform
  aligns both at Back-end Step 4.

## Escalation conditions
- SuGaR OOMs on 12GB → ensure texture baking is OFF, use `--low_poly`, lower density;
  we only need collision geometry, never appearance.
- Floor has holes → hand-patch in Blender; a continuous floor is the one hard
  requirement (everything else lumpy is fine).
- Co-registration looks off (mesh and splat don't share a frame) → do NOT proceed to
  integration; re-extract with SuGaR/2DGS rather than an independent mesher.

## Output
`scene_dir/collision.glb` — the PHYSICS asset, co-registered with `scene.ply`.
