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

            # GLOMAP C++ deps (links against libcolmap)
            colmap
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
            export VGGT_ROOT="''${VGGT_ROOT:-/home/user/backrooms-workspace/build/vggt}"
            export SUGAR_ROOT="''${SUGAR_ROOT:-/home/user/backrooms-workspace/build/SuGaR}"

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
      }
    );
}
