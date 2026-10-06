# Environment — #100 PSX cleanup evidence

All captures and benchmarks 2026-10-05/06 on the local desktop session.

| Item | Value |
|---|---|
| Godot | `4.6.3.stable.official.7d41c59c4`, `/home/user/.local/bin/godot4` |
| Rendering driver | Vulkan `1.4.329`, Forward+ |
| GPU | NVIDIA GeForce RTX 4070 Ti, driver `595.91.07`, 12,282 MiB |
| Display | `DISPLAY=:1` (real desktop, not xvfb) |
| Capture resolution | 1280x720 |
| Python | `/usr/bin/python3`, numpy 1.26.4 |
| Source asset | `godot_walk/assets/corridor_splat/corridor.ply`, md5 `2f6c2fd5417ffe771ef4147e369d80c5`, 182,569 splats |
| Filtered asset | `godot_walk/assets/corridor_splat/corridor_clean.ply`, md5 `c5ac214d8cbc77880aaaa5d65fc9a8f5`, 124,564 splats |

`corridor.ply` and `corridor_clean.ply` are gitignored (`.ply`), so both are
local; `corridor_clean.report.json` records their digests and the deterministic
parameters and is tracked.

The source clip (`data/scenes/corridor_travel/video.mp4`) is **synthetic** (Veo
3.1) and is **rejected by the current capture gate**; `corridor_splat` is a
historical calibrated asset, not a fresh pipeline product. Nothing here is
evidence of real-video reconstruction.
