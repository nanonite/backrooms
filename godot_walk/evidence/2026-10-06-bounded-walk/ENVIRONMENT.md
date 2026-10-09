# Environment -- #101 bounded-walk assessment

All captures and benchmarks 2026-10-06 on the local desktop session.

| Item | Value |
|---|---|
| Godot | `4.6.3.stable.official.7d41c59c4`, `/home/user/.local/bin/godot4` |
| Rendering driver | Vulkan `1.4.329`, Forward+ |
| GPU | NVIDIA GeForce RTX 4070 Ti, driver `595.91.07`, 12,282 MiB |
| Display | `DISPLAY=:1` (real desktop, not xvfb) |
| Capture resolution | 1280x720, FOV 75 |
| Python | `/usr/bin/python3`, numpy 2.5.3, Pillow (black-fraction analysis) |
| Production scene | `godot_walk/scenes/corridor_psx.tscn` (cleaned splat + PSX pass) |
| Source asset | `corridor.ply`, md5 `2f6c2fd5417ffe771ef4147e369d80c5`, 182,569 splats |
| Filtered asset | `corridor_clean.ply`, md5 `c5ac214d8cbc77880aaaa5d65fc9a8f5`, 124,564 splats |
| Collision | `corridor_splat.collision.glb`, md5 `c8f7a46effade8002a9bc51f74e3b11e`, 10,178 triangles |

The source clip (`data/scenes/corridor_travel/video.mp4`, synthetic) is
**rejected by the current capture gate** (`camera_path_too_short` 0.17 vs >=
0.25 frame widths, plus `rotation_dominant` warnings); `corridor_splat` is a
historical staged asset, not a fresh pipeline product. `corridor_x.mp4`
(ACCEPTED_WITH_WARNINGS) and `room_large.mp4` (ACCEPTED) are the supported
synthetic candidates, but neither has a reconstructed splat yet. Nothing here
is evidence of real-video reconstruction.
