#!/usr/bin/env bash
# setup-pipeline-tools.sh — Install pipeline tools missing from the conda env.
#
# Installs: GLOMAP (C++, from source), Brush (Rust, via cargo), VGGT (Python),
# SuGaR (Python). These four tools are NOT in the nerfstudio conda env.
# COLMAP 3.10 and everything else is already covered by environment/nerfstudio.yml.
#
# Usage:
#   ./environment/setup-pipeline-tools.sh              # install all missing tools
#   ./environment/setup-pipeline-tools.sh install-glomap
#   ./environment/setup-pipeline-tools.sh install-brush
#   ./environment/setup-pipeline-tools.sh install-vggt
#   ./environment/setup-pipeline-tools.sh install-sugar
#   ./environment/setup-pipeline-tools.sh status       # check what's installed
#
# Environment:
#   PIPELINE_TOOLS_PREFIX   Install prefix for compiled binaries (default: $HOME/.local)
#   VGGT_ROOT               Where to clone VGGT   (default: $HOME/vggt)
#   SUGAR_ROOT              Where to clone SuGaR  (default: $HOME/SuGaR)
#   CONDA_ENV               Conda env name for pip installs (default: nerfstudio)
#   GLOMAP_SRC              Where to clone GLOMAP (default: $HOME/src/glomap)
#
# Prerequisites:
#   - nix develop (or the packages from flake.nix) for C++ deps
#   - Conda env 'nerfstudio' created from environment/nerfstudio.yml
#   - CUDA 12.x on the system PATH (for Brush GPU training)

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PREFIX="${PIPELINE_TOOLS_PREFIX:-$HOME/.local}"
VGGT_ROOT="${VGGT_ROOT:-$HOME/vggt}"
SUGAR_ROOT="${SUGAR_ROOT:-$HOME/SuGaR}"
CONDA_ENV="${CONDA_ENV:-nerfstudio}"
GLOMAP_SRC="${GLOMAP_SRC:-$HOME/src/glomap}"
GLOMAP_VERSION="1.2.0"
GLOMAP_REPO="https://github.com/colmap/glomap"
VGGT_REPO="https://github.com/facebookresearch/vggt"
SUGAR_REPO="https://github.com/Anttwo/SuGaR"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }
ok()   { echo "    OK: $*"; }

# Run pip inside the conda env without activating it (avoids shell sourcing).
conda_pip() {
    conda run -n "$CONDA_ENV" pip "$@"
}

# Check if a binary is in PATH.
has_cmd() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# install-glomap
# ---------------------------------------------------------------------------

install_glomap() {
    info "Installing GLOMAP $GLOMAP_VERSION …"

    if has_cmd glomap; then
        if glomap --help >/dev/null 2>&1; then
            ok "glomap already in PATH — skipping."
            return 0
        else
            echo "WARN: glomap is in PATH but cannot execute — rebuilding." >&2
        fi
    fi

    # Ensure build deps present (must be inside nix develop or have cmake etc.)
    for dep in cmake ninja pkg-config; do
        has_cmd "$dep" || die "$dep not found. Enter 'nix develop' first."
    done

    mkdir -p "$HOME/src"
    if [[ ! -d "$GLOMAP_SRC/.git" ]]; then
        git clone --depth 1 --branch "$GLOMAP_VERSION" "$GLOMAP_REPO" "$GLOMAP_SRC"
    else
        info "GLOMAP source already cloned at $GLOMAP_SRC"
    fi

    BUILD_DIR="$GLOMAP_SRC/build"
    mkdir -p "$BUILD_DIR"

    # GLOMAP builds against the conda env's COLMAP 3.10 (the pipeline standard).
    # The nixpkgs colmap is 4.x, whose Rigid3d API breaks GLOMAP 1.2.0
    # compilation. CUDA is disabled because the dev shell has no CUDA toolkit.
    # Full cmake output is captured to a log — a configure failure buries the
    # real error (a missing find_package dependency) under a tail of warnings.
    CONDA_COLMAP_DIR="${CONDA_PREFIX:-$HOME/anaconda3/envs/nerfstudio}"
    CMAKE_LOG="$BUILD_DIR/cmake_configure.log"
    info "Configuring GLOMAP against conda COLMAP 3.10 (log: $CMAKE_LOG) …"
    if ! cmake -S "$GLOMAP_SRC" -B "$BUILD_DIR" \
        -GNinja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="$PREFIX" \
        -DCUDA_ENABLED=OFF \
        -DCOLMAP_DIR="$CONDA_COLMAP_DIR/share/colmap" \
        -DCMAKE_PREFIX_PATH="$CONDA_COLMAP_DIR" \
        -DCMAKE_INSTALL_RPATH="$CONDA_COLMAP_DIR/lib" \
        -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=ON \
        > "$CMAKE_LOG" 2>&1; then
        echo "ERROR: cmake configure failed. The full log is at $CMAKE_LOG." >&2
        echo "Common causes and their fixes:" >&2
        grep -E "Could not find a package configuration file provided by|CMake Error" "$CMAKE_LOG" \
            | sed 's/^/  /' >&2 || true
        echo "  - PoseLib/faiss/metis/glew/onnxruntime missing: re-enter 'nix develop'" >&2
        echo "    (the dev shell provides them) and re-run." >&2
        echo "  - COLMAP API errors: the fetched COLMAP is incompatible with" >&2
        echo "    GLOMAP $GLOMAP_VERSION; check GLOMAP_VERSION in this script." >&2
        return 1
    fi

    info "Building GLOMAP (this builds COLMAP from source; takes a while) …"
    cmake --build "$BUILD_DIR" --parallel "$(nproc)" || {
        echo "ERROR: GLOMAP build failed. See $BUILD_DIR for the compiler output." >&2
        return 1
    }
    cmake --install "$BUILD_DIR" || {
        echo "ERROR: GLOMAP install failed." >&2
        return 1
    }

    ok "glomap installed to $PREFIX/bin/glomap"
}

# ---------------------------------------------------------------------------
# install-brush
# ---------------------------------------------------------------------------

install_brush() {
    info "Installing Brush (brush-app) via cargo …"

    if has_cmd brush; then
        ok "brush already in PATH — skipping."
        return 0
    fi

    has_cmd cargo || die "cargo not found. Enter 'nix develop' first."

    # brush-app is the CLI entry point in the Brush workspace.
    # --locked pins the dependency graph from the published Cargo.lock.
    cargo install brush-app \
        --locked \
        --root "$PREFIX"

    ok "brush installed to $PREFIX/bin/brush"
}

# ---------------------------------------------------------------------------
# install-vggt
# ---------------------------------------------------------------------------

install_vggt() {
    info "Installing VGGT (facebookresearch/vggt) …"

    if [[ -f "$VGGT_ROOT/demo_colmap.py" ]]; then
        ok "VGGT already present at $VGGT_ROOT — skipping clone."
    else
        git clone --depth 1 "$VGGT_REPO" "$VGGT_ROOT"
    fi

    # Install Python deps into the conda env so pose_vggt.sh can call it.
    if [[ -f "$VGGT_ROOT/requirements.txt" ]]; then
        info "Installing VGGT Python requirements into conda env '$CONDA_ENV' …"
        conda_pip install -r "$VGGT_ROOT/requirements.txt"
    fi

    # Editable install so `import vggt` resolves.
    if [[ -f "$VGGT_ROOT/setup.py" ]] || [[ -f "$VGGT_ROOT/pyproject.toml" ]]; then
        conda_pip install -e "$VGGT_ROOT"
    fi

    ok "VGGT ready at $VGGT_ROOT"
}

# ---------------------------------------------------------------------------
# install-sugar
# ---------------------------------------------------------------------------

install_sugar() {
    info "Installing SuGaR (Anttwo/SuGaR) …"

    if [[ -f "$SUGAR_ROOT/extract_mesh.py" ]]; then
        ok "SuGaR already present at $SUGAR_ROOT — skipping clone."
    else
        git clone --recurse-submodules "$SUGAR_REPO" "$SUGAR_ROOT"
    fi

    if [[ -f "$SUGAR_ROOT/requirements.txt" ]]; then
        info "Installing SuGaR Python requirements into conda env '$CONDA_ENV' …"
        conda_pip install -r "$SUGAR_ROOT/requirements.txt"
    fi

    if [[ -f "$SUGAR_ROOT/setup.py" ]] || [[ -f "$SUGAR_ROOT/pyproject.toml" ]]; then
        conda_pip install -e "$SUGAR_ROOT"
    fi

    ok "SuGaR ready at $SUGAR_ROOT"
    echo ""
    echo "    NOTE: extract_mesh.sh reads SUGAR_ROOT from the environment."
    echo "    Add to your shell profile or .envrc:"
    echo "      export SUGAR_ROOT=\"$SUGAR_ROOT\""
}

# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

print_status() {
    _ok()   { printf "  [x] %-8s %s\n" "$1" "$2"; }
    _miss() { printf "  [ ] %-8s %s\n" "$1" "$2"; }

    echo ""
    echo "Pipeline tool status:"

    has_cmd colmap \
        && _ok  colmap  "$(colmap --version 2>&1 | head -1)" \
        || _miss colmap "not in PATH — activate conda env 'nerfstudio'"

    if has_cmd glomap; then
        if glomap --help >/dev/null 2>&1; then
            _ok  glomap  found
        else
            _miss glomap "installed but cannot execute — missing shared libraries"
        fi
    else
        _miss glomap "run: $0 install-glomap"
    fi

    has_cmd brush \
        && _ok  brush   found \
        || _miss brush  "run: $0 install-brush"

    [[ -f "$VGGT_ROOT/demo_colmap.py" ]] \
        && _ok  vggt    "$VGGT_ROOT" \
        || _miss vggt   "run: $0 install-vggt"

    [[ -f "$SUGAR_ROOT/extract_mesh.py" ]] \
        && _ok  sugar   "$SUGAR_ROOT" \
        || _miss sugar  "run: $0 install-sugar"

    has_cmd ffmpeg \
        && _ok  ffmpeg  "$(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f1-3)" \
        || _miss ffmpeg "not found (install via nix or apt)"

    echo ""
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

CMD="${1:-all}"

case "$CMD" in
    install-glomap) install_glomap ;;
    install-brush)  install_brush  ;;
    install-vggt)   install_vggt   ;;
    install-sugar)  install_sugar  ;;
    status)         print_status   ;;
    all)
        print_status
        echo "Installing all missing tools …"
        echo ""
        install_glomap || echo "WARN: glomap install failed (continuing)"
        install_brush  || echo "WARN: brush install failed (continuing)"
        install_vggt   || echo "WARN: vggt install failed (continuing)"
        install_sugar  || echo "WARN: sugar install failed (continuing)"
        echo ""
        print_status
        ;;
    *)
        echo "Usage: $0 [all|install-glomap|install-brush|install-vggt|install-sugar|status]"
        exit 1
        ;;
esac
