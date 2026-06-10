#!/usr/bin/env bash
# mesh_photogrammetry.sh — Stage M: photogrammetry textured mesh (the v1 deliverable).
#
# CONTRACT / STUB ONLY. This file defines the interface and dependency contract
# for Stage M; the stage bodies are NOT implemented here. Implementation is the
# job of chainlink #43 (M1) and its subissues:
#   - M1a (#51): COLMAP dense path body (the DEFAULT below).
#   - M1b (#52): Meshroom fallback body (--fallback meshroom).
#   - M1c (#53): Blender cleanup (Y-up, metric, fill non-manifold, decimate) — separate step.
#   - M1d (#54): glTF export + scene_transform.txt — separate step.
#
# Architectural rule (see fable-plan.md §0): the textured mesh IS the world — it
# is BOTH the visual and the collider. DO NOT extract this mesh from a Gaussian
# splat (the entire Bevy failure mode). This stage consumes the sparse model's
# images + poses and runs multi-view stereo.
#
# Usage:
#   mesh_photogrammetry.sh <scene_dir> [--fallback meshroom] [--keep-dense]
#
#   scene_dir         Per-scene directory. Must contain images/ and sparse/0/
#                     (cameras,images,points3D).bin from Stage B (pose_colmap.sh).
#   --fallback meshroom
#                     Use the Meshroom (AliceVision) path instead of COLMAP dense.
#                     Meshroom re-runs its own robust SfM (ignore — it is robust).
#                     Use when COLMAP dense leaves floor holes / blobby geometry.
#   --keep-dense      Keep the intermediate dense/ workspace (default: delete).
#
# Default backend: COLMAP dense + Poisson
#   image_undistorter -> patch_match_stereo -> stereo_fusion -> poisson_mesher
#   (CUDA MVS; verified present in the flake's pkgs.colmap — RTX 4070 Ti.)
#
# Output (contract — produced by the full M1 chain, not this stub):
#   $scene_dir/mesh_raw.ply        dense MVS mesh, arbitrary frame/scale (M1a/M1b)
#   $scene_dir/scene.glb           cleaned, Y-up, metric, textured (M1c/M1d)
#   $scene_dir/scene_transform.txt rotation+scale baked in Blender, for v2 splat (M1d)
#
# Exit codes:
#   0  Success (full implementation only).
#   1  Usage error.
#   2  Missing dependencies (colmap, or meshroom AppImage for --fallback).
#   3  Input validation failed (no images/ or sparse/0/).
#   7  STUB — stage body not yet implemented (this file). M1 replaces this.
#
# Requirements:
#   - COLMAP with CUDA MVS (flake pkgs.colmap provides patch_match_stereo,
#     stereo_fusion, poisson_mesher, delaunay_mesher, image_undistorter).
#   - Meshroom is NOT in nixpkgs — the fallback uses an AppImage. See
#     environment/meshroom.md for acquisition + the MESHROOM_BIN env var.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: mesh_photogrammetry.sh <scene_dir> [--fallback meshroom] [--keep-dense]

  scene_dir              Per-scene dir with images/ + sparse/0/ from Stage B.

Options:
  --fallback meshroom    Use Meshroom (AliceVision) AppImage instead of COLMAP dense.
  --keep-dense           Keep the intermediate dense/ workspace.

Environment:
  MESHROOM_BIN           Path to Meshroom_*.AppImage (required for --fallback).
                         See environment/meshroom.md.

Exit codes:
  0 success  1 usage  2 missing deps  3 bad input  7 STUB (not implemented)
EOF
    exit 0
}

die() { local code="$1"; shift; echo "ERROR: $*" >&2; exit "$code"; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

[[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && usage
[[ $# -lt 1 ]] && die 1 "scene_dir argument required. Use --help for usage."

SCENE_DIR="$1"; shift
BACKEND="colmap"
KEEP_DENSE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fallback)
            shift
            [[ "${1:-}" == "meshroom" ]] || die 1 "--fallback expects 'meshroom'."
            BACKEND="meshroom"
            ;;
        --keep-dense) KEEP_DENSE=true ;;
        --help|-h) usage ;;
        *) die 1 "Unknown option: $1. Use --help for usage." ;;
    esac
    shift
done

SCENE_DIR="$(realpath "$SCENE_DIR")"
IMAGES_DIR="$SCENE_DIR/images"
SPARSE_MODEL_DIR="$SCENE_DIR/sparse/0"

echo "=== Stage M: photogrammetry textured mesh (CONTRACT/STUB) ==="
echo "Scene:    $SCENE_DIR"
echo "Backend:  $BACKEND"
echo

# ---------------------------------------------------------------------------
# Dependency + input contract (these checks ARE active in the stub)
# ---------------------------------------------------------------------------

if [[ "$BACKEND" == "colmap" ]]; then
    command -v colmap >/dev/null 2>&1 \
        || die 2 "colmap not in PATH. Enter the nix dev shell (flake pkgs.colmap)."
    for sub in image_undistorter patch_match_stereo stereo_fusion poisson_mesher; do
        colmap -h 2>&1 | grep -q "$sub" \
            || die 2 "colmap lacks '$sub' (no CUDA MVS build?). See E2 / flake."
    done
else
    [[ -n "${MESHROOM_BIN:-}" && -x "${MESHROOM_BIN:-}" ]] \
        || die 2 "MESHROOM_BIN unset or not executable. See environment/meshroom.md."
fi

[[ -d "$IMAGES_DIR" ]] || die 3 "images/ not found: $IMAGES_DIR. Run Stage A/B first."
[[ -f "$SPARSE_MODEL_DIR/cameras.bin" ]] \
    || die 3 "sparse/0/cameras.bin not found. Run pose_colmap.sh (Stage B) first."

echo "Dependency + input contract satisfied."
echo

# ---------------------------------------------------------------------------
# Stage bodies — NOT IMPLEMENTED (M1 fills these in)
# ---------------------------------------------------------------------------

if [[ "$BACKEND" == "colmap" ]]; then
    cat <<'PLAN'
[STUB] COLMAP dense path to implement in M1a (#51):
  colmap image_undistorter  --image_path images --input_path sparse/0 \
                            --output_path dense --output_type COLMAP
  colmap patch_match_stereo --workspace_path dense
  colmap stereo_fusion      --workspace_path dense --output_path dense/fused.ply
  colmap poisson_mesher     --input_path dense/fused.ply \
                            --output_path mesh_raw.ply
  # then hand mesh_raw.ply to Blender cleanup (M1c) + glTF export (M1d).
PLAN
else
    cat <<'PLAN'
[STUB] Meshroom fallback to implement in M1b (#52):
  "$MESHROOM_BIN" --input images --output meshroom_out \
      # Meshroom re-runs its own SfM; export textured mesh, then Blender cleanup.
PLAN
fi

echo
die 7 "STUB: Stage M body not implemented — owned by chainlink #43 (M1)."
