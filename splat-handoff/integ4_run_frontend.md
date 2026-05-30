## Goal (Integration Step 4 — run the full front-end on one good capture)
Execute Stages A→D end-to-end on ONE good capture to produce the real per-scene
assets. First time the front-end runs as a pipeline rather than isolated stages.

## Prereqs / Blockers
- Depends on ALL front-end subissues: Stage A, Stage B (COLMAP + VGGT fallback),
  Stage C (Brush), Stage D (SuGaR/2DGS), and the scaffold/driver (Step 0).
- Need ONE conforming capture (Section 1.1 hard requirements). A short
  "walk down a corridor / through a room" capture is ideal — natural parallax and
  natural player confinement to the captured volume.

## Procedure
```bash
# Drive the whole pipeline for one scene:
scripts/splat_pipeline/run_pipeline.sh /abs/path/to/scene_dir
#   Stage A: extract + cull frames
#   Stage B: COLMAP/GLOMAP; on POSE_FAILED -> VGGT
#   Stage C: Brush -> scene.ply
#   Stage D: SuGaR -> collision.glb (+ Blender decimate)
```
Then copy assets into the Bevy app:
```bash
mkdir -p splat_walk/assets/splats/<scene_name>
cp scene_dir/scene.ply        splat_walk/assets/splats/<scene_name>/
cp scene_dir/collision.glb    splat_walk/assets/splats/<scene_name>/
cp splat_walk/assets/splats/_template/alignment.toml splat_walk/assets/splats/<scene_name>/
```

## Acceptance criteria
- `splat_walk/assets/splats/<scene_name>/` contains `scene.ply`, `collision.glb`, and
  a (placeholder) `alignment.toml`.
- `scene.ply` opens in Brush's viewer and resembles the real place.
- `collision.glb` opens in Blender with a continuous floor, <200k tris.
- The two are visibly co-registered (same frame).

## Escalation conditions
- COLMAP failed AND VGGT produced garbage → the capture violates static-scene/parallax
  requirements; RE-CAPTURE (do not try to fix in software).
- Splat good but mesh floor has holes → hand-patch in Blender before integration.
- Pipeline driver can't auto-route COLMAP→VGGT → run the stages manually for this first
  scene and file a follow-up to fix the driver.

## Output
The per-scene asset triple, staged in the Bevy app's assets. Consumed by Integration
Step 5 (full walk-around).
