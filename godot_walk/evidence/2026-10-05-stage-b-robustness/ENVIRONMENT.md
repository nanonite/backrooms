# Environment — Stage B robustness (#99)

Chainlink task #99. All measurements below were taken on this host on
2026-10-05 (UTC), unattended, from the repository root
`/workspace/backrooms-workspace`.

## Host

| Property | Value | Source |
|---|---|---|
| OS | Ubuntu 24.04.5 LTS | `/etc/os-release` |
| Kernel | 6.8.0-142-generic | `uname -r` |
| CPU | AMD Ryzen 9 7900X 12-Core | `/proc/cpuinfo` |
| RAM | 62.5 GiB total | `/proc/meminfo` |

## GPU

| Property | Value | Source |
|---|---|---|
| GPU | NVIDIA GeForce RTX 4070 Ti (12 GiB, 12282 MiB) | `nvidia-smi` |
| Driver | 595.91.07 (CUDA 13.2 reported) | `nvidia-smi` |
| Compute capability | 8.9 | `nvidia-smi` |
| Idle VRAM held by desktop | ~2.2 GiB (Xorg + gnome-shell) | `nvidia-smi` |

## Pipeline tools

| Tool | Version | Status | Source |
|---|---|---|---|
| ffmpeg | 6.1.1-3ubuntu5 | present | `ffmpeg -version` |
| COLMAP (conda `nerfstudio`) | 3.10-dev | present | `colmap -h` |
| GLOMAP | 1.2.0 (built from source) | **present** (this task) | `glomap --help` |
| nerfstudio | 1.1.5 | present (conda `nerfstudio`) | `importlib.metadata` |
| PyTorch | 2.3.1+cu121 | present (conda `nerfstudio`) | `torch.__version__` |
| VGGT | facebookresearch/vggt at `/home/user/vggt` | present; model weights `model.pt` (5.0 GB) in torch hub cache | repo, run log |
| Python (conda `nerfstudio`) | 3.10.20 | used for VGGT | conda bin |
| Python (system) | 3.12.3 | present | `/usr/bin/python3 --version` |
| nix | 2.x | present | `nix --version` |
| cmake | 4.1.2 (nixpkgs) | present | `cmake --version` |
| gcc (nix) | 15.2.0 | present (nix dev shell) | `gcc --version` |
| gcc (system) | 13.3.0 | present | `gcc --version` |

## Environment activation

Two distinct environments are used, matching the pipeline's intended boundary:

1. **Nix dev shell** (`nix develop`): provides cmake, ninja, gcc 15.2, and the
   C++ build deps (Eigen, Ceres, Boost, CGAL, glog, etc.). Used to build GLOMAP.
2. **Conda `nerfstudio` env**: provides COLMAP 3.10, nerfstudio, PyTorch, and
   VGGT's Python deps. Used for all Python pipeline stages.

The conda env is activated by prepending `$HOME/anaconda3/envs/nerfstudio/bin`
to PATH (the flake.nix shellHook does this automatically). VGGT runs with
`VGGT_PYTHON=$HOME/anaconda3/envs/nerfstudio/bin/python3` so it uses the
conda env's Python (which has torch).

## GLOMAP build

GLOMAP 1.2.0 was built against the conda env's COLMAP 3.10 (the pipeline's
standard version). The nixpkgs COLMAP 4.0.4 is incompatible with GLOMAP 1.2.0
(`Rigid3d::translation` changed from field to method in COLMAP 4.0).

Build command (inside `nix develop`):

```bash
cmake -S $HOME/src/glomap -B $HOME/src/glomap/build \
    -GNinja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=$HOME/.local \
    -DCUDA_ENABLED=OFF \
    -DCOLMAP_DIR=$HOME/anaconda3/envs/nerfstudio/share/colmap \
    -DCMAKE_PREFIX_PATH=$HOME/anaconda3/envs/nerfstudio
cmake --build $HOME/src/glomap/build --parallel $(nproc)
cmake --install $HOME/src/glomap/build
```

Result: `glomap` installed to `$HOME/.local/bin/glomap` (8.5 MB).

## VGGT acceptance runs

Two synthetic fixtures were run through `pose_vggt.sh` with real VGGT:

### corridor_x_e2e (31 frames)

- **Attempt 1**: 24 frames (capped from 31) → OOM at ~11.6 GiB peak
- **Attempt 2**: 12 frames (backoff halving) → **SUCCESS**
- Peak GPU: 11643 MiB (12 frames)
- Output: `sparse/0/{cameras,images,points3D}.bin` produced

### room_large_e2e (50 frames)

- **Attempt 1**: 24 frames (capped from 50) → OOM at ~11.6 GiB peak
- **Attempt 2**: 12 frames (backoff halving) → **SUCCESS**
- Output: `sparse/0/{cameras,images,points3D}.bin` produced

### Bounded refusal test (corridor_x_e2e, VGGT_MAX_FRAMES=24 VGGT_MIN_FRAMES=24)

- **Attempt 1**: 24 frames → OOM
- No further attempts (min == max) → **POSE_REFUSED** written, exit 7
- POSE_REFUSED content:
  ```
  POSE_REFUSED: CUDA out of memory at 24 frame(s)
    budget: RTX 4070 Ti 12 GiB (target); 31 input images; attempts: 24
    suggested: lower VGGT_MAX_FRAMES (currently 24) or VGGT_MIN_FRAMES (currently 24), or free VRAM and re-run
  ```

## Resource peaks

| Run | Frames | Peak GPU (MiB) | Result |
|---|---|---|---|
| corridor_x_e2e | 12 (backoff) | 11643 (measured) | SUCCESS |
| corridor_x_e2e | 24 (capped from 31) | not sampled | OOM |
| room_large_e2e | 24 (capped from 50) | not sampled | OOM |
| room_large_e2e | 12 (backoff) | not sampled | SUCCESS |
| corridor_x_e2e (refusal) | 24 (min==max) | not sampled | POSE_REFUSED |

Only the 12-frame corridor_x_e2e run has a resource log
(`logs/vggt_corridor_x_12frames_resources.log`). The 24-frame OOM peaks
were not sampled; the OOM is reported by VGGT's own error output.

## Fallback decisions

1. **Frame cap**: 31 and 50 frame inputs are subsampled to 24 frames (evenly
   spaced, both endpoints included). This is deterministic.
2. **OOM backoff**: 24 frames OOMs → retry with 12 frames (halving). 12 frames
   succeeds.
3. **Bounded refusal**: When VGGT_MIN_FRAMES == VGGT_MAX_FRAMES and the single
   attempt OOMs, the script writes POSE_REFUSED and exits 7. The refusal names
   the budget and the settings that would change it.
