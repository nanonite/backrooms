# Repeatable capture commands — task #74

All commands run from the repository root (`/workspace/backrooms-workspace`).
The real-GPU captures require the desktop session: `DISPLAY` set to the real
X display (here `:1`), an NVIDIA GPU, and the non-snap Godot 4.6.3 binary.

## 1. Headless numerical verification (no GPU)

```bash
cd godot_walk
godot4 --headless --path . --script res://scripts/verify_alignment.gd
godot4 --headless --path . --script res://scripts/test_splat_alignment.gd
godot4 --headless --path . --script res://scripts/verify_scene.gd
```

Expected: all three exit 0. `verify_alignment.gd` prints per-scene OK lines for
cameras, landmarks, rendered AABB, and spawn. `test_splat_alignment.gd` prints
`27 passed, 0 failed`.

## 2. Real-GPU capture — inspection scene (`corridor_splat.tscn`)

```bash
DISPLAY=:1 bash godot_walk/tools/verify_corridor_splat.sh
```

This renders `res://scenes/corridor_splat.tscn` on Vulkan/Forward+, writes four
screenshots (`overhead_orbit`, `player_pov`, `player_pov_reverse`, `top_down`)
to `godot_walk/screenshots/`, and tees the log to
`godot_walk/screenshots/corridor-splat-vulkan.log`. The script refuses to run
without a real `DISPLAY` (rejects xvfb `:99*`), rejects OpenGL/llvmpipe
fallback, and fails blank/background-only PNGs.

## 3. Real-GPU capture — walkable scene (`corridor.tscn`)

```bash
cd godot_walk
DISPLAY=:1 godot4 --path . --rendering-driver vulkan \
    --resolution 1280x720 \
    --script res://scripts/screenshot_scene.gd -- \
    res://scenes/corridor.tscn
```

Writes the same four screenshot names plus `corridor-walkable-vulkan.log`.
The walkable scene additionally instantiates `GeneratedCollision` (10,178
triangles), `SafetyNet`, and the `Player` CharacterBody3D; the `player_pov`
frame carries the player's live position label.

## 4. What each screenshot shows

| Viewpoint | Camera | What it proves |
|---|---|---|
| `player_pov` | 75° perspective at eye height, near end of corridor looking far | corridor upright: floor below, ceiling + light band above, walls vertical |
| `player_pov_reverse` | same, reversed direction | reverse view of the corridor; heavily floater-obscured, so the numeric checks carry the orientation evidence |
| `overhead_orbit` | 60° perspective from above at room radius | whole-room context; dominated by far-field floaters (expected) |
| `top_down` | orthographic from 1.6× radius above | sparse, floater-dominated cloud view from above; not a floor plan |

## 5. Preserving the evidence

`godot_walk/screenshots/` is gitignored. To retain a run, copy the PNGs and
logs into a tracked directory with scene-distinct names:

```bash
mkdir -p evidence/2026-10-05-gdgs-alignment/screenshots
cp screenshots/overhead_orbit.png evidence/2026-10-05-gdgs-alignment/screenshots/corridor_splat-overhead_orbit.png
cp screenshots/player_pov.png      evidence/2026-10-05-gdgs-alignment/screenshots/corridor_splat-player_pov.png
cp screenshots/player_pov_reverse.png evidence/2026-10-05-gdgs-alignment/screenshots/corridor_splat-player_pov_reverse.png
cp screenshots/top_down.png         evidence/2026-10-05-gdgs-alignment/screenshots/corridor_splat-top_down.png
cp screenshots/corridor-splat-vulkan.log evidence/2026-10-05-gdgs-alignment/
```
