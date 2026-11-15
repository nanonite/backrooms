{
  description = "Backrooms pipeline — build-time toolchain for GLOMAP and Brush";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    rust-overlay = {
      url = "github:oxalica/rust-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nixgl = {
      url = "github:nix-community/nixGL";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, rust-overlay, nixgl }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        overlays = [ (import rust-overlay) ];
        pkgs = import nixpkgs {
          inherit system overlays;
          config.allowUnfree = true;
        };

        # Stable Rust — brush-app requires stable.
        rustToolchain = pkgs.rust-bin.stable.latest.default;

        # nixGL wrappers bridge nix-built godot4's GL/Vulkan loading to the
        # host's proprietary NVIDIA driver on non-NixOS. They are intentionally
        # NOT pulled into the devShell `packages` below: nixGL's NVIDIA wrapper
        # auto-detects the driver version via an impure derivation that is
        # incompatible with the pinned nixpkgs and aborts evaluation with
        # "cannot coerce null to a string", which previously blocked shell entry
        # entirely. The wrapper is instead invoked lazily inside `godot4-gl`
        # (see shellHook), so a broken nixGL can never stop the shell from
        # opening. `nixgl` stays an input only for that on-demand `nix run`.

      in {
        devShells.default = let
          # Libraries needed at runtime for dlopen (xkbcommon, vulkan, etc.)
          runtimeLibs = with pkgs; [
            wayland
            systemdLibs
            alsa-lib
            xorg.libX11
            xorg.libXcursor
            xorg.libXrandr
            xorg.libXi
            libxkbcommon
            libGL
            vulkan-loader
            stdenv.cc.cc.lib
            zlib
          ];

          runtimeLibPath = pkgs.lib.makeLibraryPath runtimeLibs;

        in pkgs.mkShell {
          name = "backrooms-pipeline";

          packages = with pkgs; [
            # ------------------------------------------------------------------
            # C++ build tools — needed to compile GLOMAP from source
            # ------------------------------------------------------------------
            cmake
            ninja
            pkg-config
            git

            # GLOMAP C++ deps (links against libcolmap). COLMAP 4.x's CMake
            # config does find_package for each of these, so the dev shell
            # must provide them even though nixpkgs' colmap does not
            # propagate them as cmake-discoverable packages.
            colmap
            poselib
            faiss
            glew
            metis
            onnxruntime
            curl
            eigen
            ceres-solver
            boost
            sqlite
            gflags
            glog
            cgal
            openimageio

            # ------------------------------------------------------------------
            # Rust toolchain — cargo install brush-app
            # ------------------------------------------------------------------
            rustToolchain

            # ------------------------------------------------------------------
            # Pipeline runtime tools
            # ------------------------------------------------------------------
            ffmpeg        # Stage A frame extraction

            # ------------------------------------------------------------------
            # Godot 4 — v1 walkable runtime (Forward+; GDScript, no -mono).
            # Reuses the Vulkan/xkb/GL runtimeLibs above for Forward+ + headless.
            # ------------------------------------------------------------------
            godot_4       # godot4 binary; headless import for the G-track
            # nixGL NVIDIA wrappers deliberately omitted — invoked lazily in
            # godot4-gl so their broken impure eval can't block shell entry.

            # Python headers available; actual packages live in the conda env.
            python3
          ] ++ runtimeLibs;

          shellHook = ''
            # Make dlopen-able libraries discoverable at runtime.
            export LD_LIBRARY_PATH=${runtimeLibPath}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
            export LIBRARY_PATH=${runtimeLibPath}''${LIBRARY_PATH:+:$LIBRARY_PATH}
          '' + ''
            # Prepend conda nerfstudio env so colmap 3.10 / ns-* resolve first.
            CONDA_ENV_BIN="$HOME/anaconda3/envs/nerfstudio/bin"
            if [[ -d "$CONDA_ENV_BIN" ]]; then
              export PATH="$CONDA_ENV_BIN:$PATH"
            fi

            # Tools installed by setup-pipeline-tools.sh land here.
            export PIPELINE_TOOLS_PREFIX="$HOME/.local"
            export PATH="$PIPELINE_TOOLS_PREFIX/bin:$PATH"

            # Default roots — scripts honour these env vars.
            export VGGT_ROOT="''${VGGT_ROOT:-$HOME/vggt}"
            export SUGAR_ROOT="''${SUGAR_ROOT:-$HOME/SuGaR}"

            echo ""
            echo "=== backrooms-pipeline dev shell ==="
            _ok()   { printf "  [x] %-8s %s\n" "$1" "$2"; }
            _miss() { printf "  [ ] %-8s %s\n" "$1" "$2"; }

            command -v colmap >/dev/null 2>&1 \
              && _ok  colmap  "$(colmap --version 2>&1 | head -1)" \
              || _miss colmap  "not found — run setup-pipeline-tools.sh"
            command -v glomap >/dev/null 2>&1 \
              && _ok  glomap  found \
              || _miss glomap  "run: ./environment/setup-pipeline-tools.sh install-glomap"
            command -v brush  >/dev/null 2>&1 \
              && _ok  brush   found \
              || _miss brush   "run: ./environment/setup-pipeline-tools.sh install-brush"
            [[ -f "$VGGT_ROOT/demo_colmap.py" ]] \
              && _ok  vggt    "$VGGT_ROOT" \
              || _miss vggt    "run: ./environment/setup-pipeline-tools.sh install-vggt"
            [[ -f "$SUGAR_ROOT/extract_mesh.py" ]] \
              && _ok  sugar   "$SUGAR_ROOT" \
              || _miss sugar   "run: ./environment/setup-pipeline-tools.sh install-sugar"
            command -v ffmpeg >/dev/null 2>&1 \
              && _ok  ffmpeg  "$(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f1-3)" \
              || _miss ffmpeg  "not found"
            command -v godot4 >/dev/null 2>&1 \
              && _ok  godot   "$(godot4 --version 2>&1 | head -1)" \
              || _miss godot   "not found — godot_4 should be in packages"

            # Wrapper for GUI/GPU runs (--editor, etc.) on non-NixOS hosts:
            # routes GL + Vulkan through the host's proprietary NVIDIA driver.
            # nixGL is evaluated LAZILY here and only if it actually builds —
            # its NVIDIA wrapper currently fails to evaluate against the pinned
            # nixpkgs, so we fall back to plain godot4 (the host Vulkan ICD works
            # directly for headless capture and most GPU runs on this machine).
            godot4-gl() {
              local nixgl_ref="github:nix-community/nixGL#nixGLNvidia"
              if NIXGL_NVIDIA_VERSION="$(cat /sys/module/nvidia/version 2>/dev/null)" \
                 nix build --impure --no-link "$nixgl_ref" >/dev/null 2>&1; then
                NIXGL_NVIDIA_VERSION="$(cat /sys/module/nvidia/version 2>/dev/null)" \
                  nix run --impure "$nixgl_ref" -- godot4 "$@"
              else
                echo "godot4-gl: nixGL NVIDIA wrapper unavailable (impure eval failed);" >&2
                echo "           running plain godot4 — host Vulkan/GL is used directly." >&2
                godot4 "$@"
              fi
            }
            export -f godot4-gl

            echo ""
            echo "Missing tools? Run: ./environment/setup-pipeline-tools.sh"
            echo "===================================="
          '';
        };

        # ------------------------------------------------------------------
        # Hunyuan Panogen runtime (issue #251).
        #
        # Nix only provides the tool (`uv`) and the shared libraries that the
        # PyPI wheels dlopen at import time. Python and every Python package
        # come from uv, pinned by tools/hunyuan_runtime/pyproject.toml and
        # uv.lock. Python 3.10 is uv-managed (uv python install 3.10) because
        # this nixpkgs no longer ships python310.
        #
        # The venv is created outside the repository, at the exact path that
        # godot_walk/scripts/source_ingestion_gpu.py expects for HUNYUAN_PYTHON:
        #   /mnt/sharedOs/backrooms-track-a-runtime/hunyuan-env
        # ------------------------------------------------------------------
        devShells.hunyuan = let
          pythonRuntimeLibs = with pkgs; [
            stdenv.cc.cc.lib
            zlib
            glib
            libGL
            libGLU
            libx11
            libxext
            libxrender
            libsm
            libice
            libxkbcommon
          ];

          pythonRuntimeLibPath = pkgs.lib.makeLibraryPath pythonRuntimeLibs;
        in pkgs.mkShell {
          name = "backrooms-hunyuan";

          packages = with pkgs; [
            uv
            git
          ] ++ pythonRuntimeLibs;

          shellHook = ''
            export LD_LIBRARY_PATH=${pythonRuntimeLibPath}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}

            # Paths the frozen ingestion scripts expect. Keep them in sync with
            # godot_walk/scripts/source_ingestion_gpu.py (HUNYUAN_* constants).
            export HUNYUAN_RUNTIME_ROOT="''${HUNYUAN_RUNTIME_ROOT:-/mnt/sharedOs/backrooms-track-a-runtime}"
            export HUNYUAN_RUNTIME="$HUNYUAN_RUNTIME_ROOT/HunyuanWorld-1.0"
            export HUNYUAN_CACHE="$HUNYUAN_RUNTIME_ROOT/hf-cache"
            export HUNYUAN_ENV="$HUNYUAN_RUNTIME_ROOT/hunyuan-env"

            # uv project = tools/hunyuan_runtime, venv = $HUNYUAN_ENV.
            # Invoke this shell from the repository root.
            export HUNYUAN_PROJECT="$PWD/tools/hunyuan_runtime"
            export UV_PROJECT_ENVIRONMENT="$HUNYUAN_ENV"

            echo ""
            echo "=== backrooms-hunyuan dev shell ==="
            _ok()   { printf "  [x] %-10s %s\n" "$1" "$2"; }
            _miss() { printf "  [ ] %-10s %s\n" "$1" "$2"; }

            command -v uv >/dev/null 2>&1 \
              && _ok uv "$(uv --version 2>&1)" \
              || _miss uv "not found — flake.nix should provide it"

            if [[ -x "$HUNYUAN_ENV/bin/python" ]]; then
              _ok python "$("$HUNYUAN_ENV/bin/python" --version 2>&1) at $HUNYUAN_ENV"
            else
              _miss python "no venv at $HUNYUAN_ENV"
              echo "             rebuild: cd tools/hunyuan_runtime && uv sync --locked"
            fi

            if git -C "$HUNYUAN_RUNTIME" rev-parse --verify HEAD >/dev/null 2>&1; then
              _ok checkout "$(git -C "$HUNYUAN_RUNTIME" rev-parse --short HEAD) at $HUNYUAN_RUNTIME"
            else
              _miss checkout "no git checkout at $HUNYUAN_RUNTIME"
            fi

            [[ -d "$HUNYUAN_CACHE/hub" ]] \
              && _ok hf-cache "$HUNYUAN_CACHE" \
              || _miss hf-cache "missing $HUNYUAN_CACHE/hub"

            echo ""
            echo "Rebuild docs: tools/hunyuan_runtime/README.md"
            echo "===================================="
          '';
        };
      }
    );
}
