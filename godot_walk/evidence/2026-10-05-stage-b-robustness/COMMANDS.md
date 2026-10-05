# Commands — Stage B robustness (#99)

All commands run from `/workspace/backrooms-workspace` on 2026-10-05 (UTC).

## GLOMAP build (inside nix develop)

```bash
# Enter the nix dev shell (provides cmake, gcc 15.2, C++ deps)
nix develop

# Configure GLOMAP against conda COLMAP 3.10
# The RPATH flags are required: without them the installed binary cannot find
# its shared libraries (libgmpxx, libmetis, libceres, libglog, libcholmod, ...)
# and fails with "error while loading shared libraries".
cmake -S $HOME/src/glomap -B $HOME/src/glomap/build \
    -GNinja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=$HOME/.local \
    -DCUDA_ENABLED=OFF \
    -DCOLMAP_DIR=$HOME/anaconda3/envs/nerfstudio/share/colmap \
    -DCMAKE_PREFIX_PATH=$HOME/anaconda3/envs/nerfstudio \
    -DCMAKE_INSTALL_RPATH=$HOME/anaconda3/envs/nerfstudio/lib \
    -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=ON

# Build (uses all cores)
cmake --build $HOME/src/glomap/build --parallel $(nproc)

# Install to ~/.local/bin
cmake --install $HOME/src/glomap/build

# Verify
glomap --help
```

## VGGT acceptance runs

```bash
# corridor_x_e2e (31 frames) — OOM backoff: 24 → 12
VGGT_PYTHON=$HOME/anaconda3/envs/nerfstudio/bin/python3 \
    VGGT_MAX_FRAMES=24 VGGT_MIN_FRAMES=4 \
    bash scripts/splat_pipeline/pose_vggt.sh data/scenes/corridor_x_e2e

# room_large_e2e (50 frames) — OOM backoff: 24 → 12
VGGT_PYTHON=$HOME/anaconda3/envs/nerfstudio/bin/python3 \
    VGGT_MAX_FRAMES=24 VGGT_MIN_FRAMES=4 \
    bash scripts/splat_pipeline/pose_vggt.sh data/scenes/room_large_e2e

# Bounded refusal (min == max, single attempt OOMs)
VGGT_PYTHON=$HOME/anaconda3/envs/nerfstudio/bin/python3 \
    VGGT_MAX_FRAMES=24 VGGT_MIN_FRAMES=24 \
    bash scripts/splat_pipeline/pose_vggt.sh data/scenes/corridor_x_e2e
```

## Tests

```bash
# VGGT budget policy tests
python3 -m pytest scripts/splat_pipeline/tests/test_vggt_budget.py -v

# pose_vggt.sh integration tests
python3 -m pytest scripts/splat_pipeline/tests/test_pose_vggt.py -v

# Full pipeline test suite
python3 -m pytest scripts/splat_pipeline/tests/ -v
```

## GLOMAP install via setup-pipeline-tools.sh

```bash
# Inside nix develop, with the conda env active:
nix develop
./environment/setup-pipeline-tools.sh install-glomap
```
