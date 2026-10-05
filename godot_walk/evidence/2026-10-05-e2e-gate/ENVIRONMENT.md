# Environment — end-to-end acceptance gate (#91)

Chainlink task #91. All measurements below were taken on this host on
2026-10-05 (UTC), unattended, from the repository root
`/workspace/backrooms-workspace`.

## Host

| Property | Value | Source |
|---|---|---|
| OS | Ubuntu 24.04.5 LTS | `/etc/os-release` |
| Kernel | 6.8.0-142-generic | `uname -r` |
| CPU | AMD Ryzen 9 7900X 12-Core | `/proc/cpuinfo` |
| RAM | 62.5 GiB total | `/proc/meminfo` |
| Display | `DISPLAY=:1` — real X11 desktop, not xvfb | shell env, `/tmp/.X11-unix/X1` |

## GPU

| Property | Value | Source |
|---|---|---|
| GPU | NVIDIA GeForce RTX 4070 Ti (12 GiB, 12282 MiB) | `nvidia-smi` |
| Driver | 595.91.07 (CUDA 13.2 reported) | `nvidia-smi` |
| Compute capability | 8.9 | `nvidia-smi` |
| Idle VRAM held by desktop | ~2.3 GiB (Xorg + gnome-shell) | `nvidia-smi` |

## Engine / renderer

| Property | Value | Source |
|---|---|---|
| Engine | Godot 4.6.3.stable.official.7d41c59c4 | `godot4 --version`, capture log |
| Godot binary | `/home/user/.local/bin/godot4` (non-snap, 138 MB) | `readlink -f` |
| Rendering method | Forward+ | capture log |
| Graphics API | Vulkan 1.4.329 | capture log |
| Capture resolution | 1280x720 | `--resolution` flag |

## Pipeline tools

| Tool | Version | Status | Source |
|---|---|---|---|
| ffmpeg | 6.1.1-3ubuntu5 | present | `ffmpeg -version` |
| node / npm | v22.5.1 / 10.8.2 | present | `node --version` |
| COLMAP (conda `nerfstudio`) | **3.10-dev** | present (not on default PATH) | `colmap -h` |
| GLOMAP | — | **MISSING** | `command -v glomap` |
| nerfstudio | 1.1.5 | present (conda `nerfstudio`) | `importlib.metadata` |
| gsplat | 1.4.0+pt23cu121 | present | `importlib.metadata` |
| PyTorch | 2.3.1+cu121 | present | `torch.__version__` |
| nvcc | 12.4.99 (system `/usr/local/cuda-12.4`) | present | `nvcc --version` |
| `@playcanvas/splat-transform` | 3.9.0 (435b972) | installed for this run | `splat-transform --version` |
| brush-cli | 0.3.0 | present but unusable (no wgpu adapter) | `brush --version` |
| VGGT | facebookresearch/vggt at `/home/user/vggt`, deps installed | present; model weights `model.pt` (5.0 GB) in torch hub cache | repo, run log |
| Blender | 5.2.2 LTS | present | (not used this run) |
| Python (system) | 3.12.3 | present | `/usr/bin/python3 --version` |
| Python (conda `nerfstudio`) | 3.10.20 | used for the pipeline | conda bin |

### gsplat / Splatfacto workaround used this run

The `#89` preflight (`HARDWARE_BUDGET.md`) recorded Splatfacto as **BLOCKED**:
gsplat JIT-compiles its CUDA extension with `nvcc 12.4` against torch 2.3.1's
headers and fails (`boxing.h: expected primary-expression before '>'`).

That finding is reproducible, but it is caused by import precedence: the user
site `~/.local/lib/python3.10/site-packages` shadows the conda env, so a
*second* gsplat (no prebuilt `csrc.so`) is imported and JIT is attempted. The
conda env ships a prebuilt `csrc.so` (`gsplat 1.4.0+pt23cu121`, 38 MB). Running
with `PYTHONNOUSERSITE=1` selects the conda gsplat and its prebuilt extension,
which loads and executes a real CUDA rasterization op (verified: a 1-Gaussian
render returned a 128x128 RGB image). This run therefore sets
`PYTHONNOUSERSITE=1` for all pipeline invocations. It is a host-configuration
workaround, not a pipeline change.

## Asset provenance (existing calibrated corridor scene)

| Asset | md5 | Note |
|---|---|---|
| `godot_walk/assets/corridor_splat/corridor.ply` | `2f6c2fd5417ffe771ef4147e369d80c5` | 182,569 Gaussians, same bytes as `exports/corridor_travel_v1/splat.ply` |
| `.../collision/corridor_splat.collision.glb` | `c8f7a46effade8002a9bc51f74e3b11e` | 10,178 triangles (#84) |
| `.../alignment_manifest.json` | `bf0f58e86ab0685c5f374aaeeede43d1` | #83/#74 contract |
| `.../traversal_manifest.json` | `aff59d408c0b9fd605751d09b0b7bda2` | #85 plan |
| `godot_walk/assets/gdgs_demo/demo.compressed.ply` | `041ea0fb77d369a151135801c3c96abf` | PlayCanvas demo splat (real-room visual asset, no capture video, no contract) |

Fixture hashes are in `logs/hashes.txt`.
