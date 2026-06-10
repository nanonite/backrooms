# Meshroom (AliceVision) — Stage M fallback backend

Meshroom is the **fallback** mesh backend for Stage M (`mesh_photogrammetry.sh
--fallback meshroom`), used when COLMAP dense leaves floor holes or blobby
geometry. It is **not packaged in nixpkgs**, so it is acquired as an AppImage
and kept out of the nix dev shell (the shell stays light — see flake.nix / E2).

## Acquire

Download the latest Linux AppImage from the official releases:

    https://github.com/alicevision/Meshroom/releases   # Meshroom-*-linux.AppImage (or .tar.gz)

Place it under a stable path and mark it executable, e.g.:

    mkdir -p ~/.local/opt/meshroom
    mv ~/Downloads/Meshroom-*-linux.AppImage ~/.local/opt/meshroom/
    chmod +x ~/.local/opt/meshroom/Meshroom-*.AppImage

## Wire it up

`mesh_photogrammetry.sh --fallback meshroom` reads `$MESHROOM_BIN`:

    export MESHROOM_BIN="$HOME/.local/opt/meshroom/Meshroom-2023.3.0-linux.AppImage"

(Adjust the filename to the version you downloaded.) The CLI entry point used by
the script is the AppImage itself (`meshroom_batch` is bundled inside).

## Notes

- Meshroom re-runs its **own** robust SfM — it ignores our COLMAP sparse model
  and works directly from `images/`. That is expected; do not try to feed it our
  poses.
- Requires an NVIDIA GPU + recent driver for the CUDA depth-map stages (the
  RTX 4070 Ti is fine).
- GPU MVS only; no CPU fallback for the depth maps.
- Output is a textured mesh; hand it to the Blender cleanup step (M1c) exactly
  like the COLMAP dense output before glTF export (M1d).
