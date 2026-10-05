# Environment — GDGS visual/alignment evidence run (2026-10-05)

Chainlink task #74. Real-GPU capture on the desktop session, not headless/xvfb.

## Renderer / GPU / version details

| Property | Value | Source |
|---|---|---|
| Engine | Godot 4.6.3.stable.official.7d41c59c4 | `godot4 --version`, capture logs |
| Godot binary | `/home/user/.local/bin/godot4` (non-snap, 138 MB) | `readlink -f` |
| Rendering method | Forward+ | capture logs, `project.godot` |
| Graphics API | Vulkan 1.4.329 | capture logs |
| GPU | NVIDIA GeForce RTX 4070 Ti (12 GB) | `nvidia-smi`, capture logs |
| Driver | 595.91.07 (CUDA 13.2) | `nvidia-smi` |
| Display | `DISPLAY=:1` (real desktop, not xvfb) | shell env |
| Capture resolution | 1280x720 | `--resolution` flag |
| Asset | `res://assets/corridor_splat/corridor.ply` (45 MB, 182,569 splats) | manifest `asset` |
| Asset md5 | `2f6c2fd5417ffe771ef4147e369d80c5` | `md5sum`, matches manifest |
| Collision GLB md5 | `c8f7a46effade8002a9bc51f74e3b11e` | `md5sum`, matches TRAVERSAL.md |

## Scenes captured

| Scene | Role | Screenshots |
|---|---|---|
| `res://scenes/corridor_splat.tscn` | inspection (splat + compositor + lights) | `corridor_splat-*.png` |
| `res://scenes/corridor.tscn` | walkable main scene (splat + GeneratedCollision + SafetyNet + Player) | `corridor-*.png` |

## Headless verification (no GPU)

| Script | Result |
|---|---|
| `res://scripts/verify_alignment.gd` | exit 0 — both scenes verified against the contract |
| `res://scripts/test_splat_alignment.gd` | exit 0 — 27/27 unit tests pass |
| `res://scripts/verify_scene.gd` | exit 0 — collision bodies, 10178 triangles, capsule, spawn placement |

Logs: `verify_alignment.log`, `test_splat_alignment.log`, `verify_scene.log`.
