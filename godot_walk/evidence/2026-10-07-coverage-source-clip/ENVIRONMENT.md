# Environment — #107 coverage-complete source clip

Recorded 2026-10-07 (UTC) on the machine that produced the evidence.

| | |
|---|---|
| Host | `user-linux` · Linux 6.8.0-142-generic · x86_64 |
| GPU | NVIDIA GeForce RTX 4070 Ti, driver 595.91.07, 12282 MiB |
| Python | 3.12.3 (`numpy` 2.5.3, `pillow` 10.2.0) |
| ffmpeg / ffprobe | 6.1.1-3ubuntu5 |
| COLMAP | 3.10-dev (CUDA build) at `~/anaconda3/envs/nerfstudio/bin/colmap` |
| GLOMAP | `~/.local/bin/glomap` (not CUDA-compiled); aborts on this database |
| Generation | OpenRouter `google/veo-3.1-lite`, key in repo `.env` (git-ignored) |
| Godot | not required for this issue (no rendering here) |

Notes:

* COLMAP SIFT runs with `--SiftExtraction.use_gpu 0` / `--SiftMatching.use_gpu 0`
  per the repo's Stage A convention (GPU SIFT fails on 1080p frames on this host).
* The generation step needs network access to `openrouter.ai`; it is the only
  network dependency and is isolated to `scripts/generate_coverage_clip.py`.
* The clip and all COLMAP working files live under `data/`, which is
  git-ignored in this repository. The tracked evidence is this directory.
