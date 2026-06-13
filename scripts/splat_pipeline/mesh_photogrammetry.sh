#!/usr/bin/env bash
# mesh_photogrammetry.sh — Stage M: photogrammetry textured mesh (the v1 deliverable).
#
# Architectural rule (see fable-plan.md §0): the textured mesh IS the world — it
# is BOTH the visual and the collider. DO NOT extract this mesh from a Gaussian
# splat (the entire Bevy failure mode). This stage consumes the sparse model's
# images + poses and runs multi-view stereo.
#
# Usage:
#   mesh_photogrammetry.sh <scene_dir> [--fallback meshroom]
#       [--mesher delaunay|poisson] [--keep-dense]
#
#   scene_dir         Per-scene directory. Must contain images/ and sparse/0/
#                     (cameras,images,points3D).bin from Stage B (pose_colmap.sh).
#   --fallback meshroom
#                     Use the Meshroom (AliceVision) path instead of COLMAP dense.
#                     Meshroom re-runs its own robust SfM (ignore — it is robust).
#                     Use when COLMAP dense leaves floor holes / blobby geometry.
#   --mesher delaunay|poisson
#                     Select the COLMAP dense mesher. Default: delaunay.
#   --keep-dense      Keep the intermediate dense/ workspace (default: delete).
#
# Default backend: COLMAP dense + Delaunay
#   image_undistorter -> patch_match_stereo -> stereo_fusion -> delaunay_mesher
#   (CUDA MVS; verified present in the flake's pkgs.colmap — RTX 4070 Ti.)
#
# Output (contract):
#   $scene_dir/mesh_raw.ply        dense MVS mesh, arbitrary frame/scale (M1a/M1b)
#   $scene_dir/scene.glb           cleaned, Y-up, metric, textured (M1c/M1d)
#   $scene_dir/scene_transform.txt rotation+scale baked in Blender, for v2 splat (M1d)
#
# Exit codes:
#   0  Success.
#   1  Usage error.
#   2  Missing dependencies (colmap, blender, or meshroom AppImage for --fallback).
#   3  Input validation failed (no images/ or sparse/0/).
#   4  Photogrammetry step failed (COLMAP dense or Meshroom pipeline).
#   5  Blender cleanup/export failed.
#
# Requirements:
#   - COLMAP with CUDA MVS (pkgs.colmap provides patch_match_stereo,
#     stereo_fusion, poisson_mesher, delaunay_mesher, image_undistorter).
#   - Meshroom is NOT in nixpkgs — the fallback uses an AppImage. See
#     environment/meshroom.md for acquisition + the MESHROOM_BIN env var.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: mesh_photogrammetry.sh <scene_dir> [--fallback meshroom] [--mesher delaunay|poisson] [--keep-dense]

  scene_dir              Per-scene dir with images/ + sparse/0/ from Stage B.

Options:
  --fallback meshroom    Use Meshroom (AliceVision) AppImage instead of COLMAP dense.
  --mesher delaunay      Use COLMAP Delaunay meshing (default; free-space aware).
  --mesher poisson       Use COLMAP Poisson meshing on fused.ply.
  --keep-dense           Keep the intermediate dense/ workspace.

Environment:
  MESHROOM_BIN           Path to Meshroom_*.AppImage (required for --fallback).
                         See environment/meshroom.md.
  TEXTURES_DIR           Optional override for external texture directory
                         (<scene>_{ceiling,floor,front,side}.jpg or .png).
                         Mesh keeps vertex colors when textures are absent.

  Exit codes:
  0 success  1 usage  2 missing deps  3 bad input  4 pipeline failed  5 blender failed
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
MESHER="delaunay"
KEEP_DENSE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fallback)
            shift
            [[ "${1:-}" == "meshroom" ]] || die 1 "--fallback expects 'meshroom'."
            BACKEND="meshroom"
            ;;
        --mesher)
            shift
            case "${1:-}" in
                delaunay|poisson) MESHER="$1" ;;
                *) die 1 "--mesher expects 'delaunay' or 'poisson'." ;;
            esac
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

echo "=== Stage M: photogrammetry textured mesh ==="
echo "Scene:    $SCENE_DIR"
echo "Backend:  $BACKEND"
if [[ "$BACKEND" == "colmap" ]]; then
    echo "Mesher:   $MESHER"
fi
echo

# ---------------------------------------------------------------------------
# Dependency + input contract
# ---------------------------------------------------------------------------

if [[ "$BACKEND" == "colmap" ]]; then
    command -v colmap >/dev/null 2>&1 \
        || die 2 "colmap not in PATH. Enter the nix dev shell (flake pkgs.colmap)."
    REQUIRED_COLMAP_SUBCOMMANDS=(image_undistorter patch_match_stereo stereo_fusion)
    if [[ "$MESHER" == "delaunay" ]]; then
        REQUIRED_COLMAP_SUBCOMMANDS+=(delaunay_mesher)
    else
        REQUIRED_COLMAP_SUBCOMMANDS+=(poisson_mesher)
    fi
    COLMAP_HELP="$(colmap -h 2>&1 || true)"
    for sub in "${REQUIRED_COLMAP_SUBCOMMANDS[@]}"; do
        grep -Fq "$sub" <<<"$COLMAP_HELP" \
            || die 2 "colmap lacks '$sub' (no CUDA MVS build?). If delaunay_mesher is unavailable, route to #71 Meshroom."
    done
else
    [[ -n "${MESHROOM_BIN:-}" && -x "${MESHROOM_BIN:-}" ]] \
        || die 2 "MESHROOM_BIN unset or not executable. See environment/meshroom.md."
fi

[[ -d "$IMAGES_DIR" ]] || die 3 "images/ not found: $IMAGES_DIR. Run Stage A/B first."
[[ -f "$SPARSE_MODEL_DIR/cameras.bin" ]] \
    || die 3 "sparse/0/cameras.bin not found. Run pose_colmap.sh (Stage B) first."

BLENDER_BIN="${BLENDER_BIN:-blender}"
command -v "$BLENDER_BIN" >/dev/null 2>&1 \
    || die 2 "blender not in PATH. Set BLENDER_BIN=/path/to/blender."

# Resolve textures directory for Blender cleanup (optional — mesh keeps
# vertex colors when external textures are absent).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEXTURES_DIR="${TEXTURES_DIR:-$REPO_ROOT/data/textures}"

echo "Dependency + input contract satisfied."
echo

# ---------------------------------------------------------------------------
# Stage body
# ---------------------------------------------------------------------------

if [[ "$BACKEND" == "colmap" ]]; then
    DENSE_DIR="$SCENE_DIR/dense"
    DATABASE_PATH="$SCENE_DIR/database.db"

    echo "--- Build COLMAP database (features + matches for neighbor info) ---"
    if [[ -s "$DATABASE_PATH" ]]; then
        echo "Using existing database: $DATABASE_PATH"
    else
        colmap feature_extractor \
            --database_path "$DATABASE_PATH" \
            --image_path "$IMAGES_DIR" \
            --ImageReader.single_camera 1 \
            || die 4 "feature_extractor failed."

        colmap exhaustive_matcher \
            --database_path "$DATABASE_PATH" \
            || die 4 "exhaustive_matcher failed."
    fi

    echo "--- Image undistortion ---"
    colmap image_undistorter \
        --image_path "$IMAGES_DIR" \
        --input_path "$SPARSE_MODEL_DIR" \
        --output_path "$DENSE_DIR" \
        --output_type COLMAP \
        || die 4 "image_undistorter failed."

    echo "--- Build patch-match.cfg from database matches ---"
    python3 - "$DENSE_DIR" "$DATABASE_PATH" <<'PYEOF' || die 4 "Failed to build patch-match.cfg."
import sys, sqlite3, os
dense_stereo = os.path.join(sys.argv[1], 'stereo')
db = sqlite3.connect(sys.argv[2])
img_map = {}
for row in db.execute("SELECT image_id, name FROM images ORDER BY image_id"):
    img_map[row[0]] = row[1]
BASE = 2147483647
neighbors = {name: [] for name in img_map.values()}
for row in db.execute("SELECT pair_id, rows FROM two_view_geometries"):
    pid, num = row
    i2 = pid % BASE
    i1 = pid // BASE
    if i1 in img_map and i2 in img_map:
        n1, n2 = img_map[i1], img_map[i2]
        neighbors[n1].append((n2, num))
        neighbors[n2].append((n1, num))
MAX_NBR = 10
with open(os.path.join(dense_stereo, 'patch-match.cfg'), 'w') as f:
    for img_name in sorted(neighbors.keys()):
        nbrs = sorted(neighbors[img_name], key=lambda x: -x[1])[:MAX_NBR]
        if not nbrs:
            continue
        f.write(f"{img_name}\n")
        f.write(", ".join(n[0] for n in nbrs) + "\n")
db.close()
PYEOF
    echo "  patch-match.cfg written with explicit neighbors."

    echo "--- Patch match stereo ---"
    colmap patch_match_stereo \
        --workspace_path "$DENSE_DIR" \
        --PatchMatchStereo.window_radius 5 \
        --PatchMatchStereo.window_step 2 \
        --PatchMatchStereo.geom_consistency true \
        --PatchMatchStereo.filter true \
        --PatchMatchStereo.write_consistency_graph true \
        || die 4 "patch_match_stereo failed."

    FUSION_MIN_PIXELS="${FUSION_MIN_PIXELS:-3}"
    FUSION_MAX_REPROJ_ERROR="${FUSION_MAX_REPROJ_ERROR:-2}"
    FUSION_MAX_DEPTH_ERROR="${FUSION_MAX_DEPTH_ERROR:-0.01}"
    FUSION_CHECK_NUM_IMAGES="${FUSION_CHECK_NUM_IMAGES:-3}"

    echo "--- Stereo fusion ---"
    colmap stereo_fusion \
        --workspace_path "$DENSE_DIR" \
        --output_path "$DENSE_DIR/fused_full.ply" \
        --StereoFusion.min_num_pixels "$FUSION_MIN_PIXELS" \
        --StereoFusion.max_reproj_error "$FUSION_MAX_REPROJ_ERROR" \
        --StereoFusion.max_depth_error "$FUSION_MAX_DEPTH_ERROR" \
        --StereoFusion.max_normal_error 30 \
        --StereoFusion.check_num_images "$FUSION_CHECK_NUM_IMAGES" \
        || die 4 "stereo_fusion failed."

    if [[ "$MESHER" == "delaunay" ]]; then
        echo "--- Delaunay meshing ---"
        colmap delaunay_mesher \
            --input_path "$DENSE_DIR" \
            --input_type dense \
            --output_path "$SCENE_DIR/mesh_raw.ply" \
            || die 4 "delaunay_mesher failed."
    else
        echo "--- Subsampling fused cloud (~500k points for Poisson) ---"
        python3 - "$DENSE_DIR" <<'PYEOF' || die 4 "Subsampling failed."
import sys, struct, os, numpy as np
dense = sys.argv[1]
fused = os.path.join(dense, 'fused_full.ply')
output = os.path.join(dense, 'fused.ply')
if not os.path.exists(fused):
    sys.exit(1)
with open(fused, 'rb') as f:
    header = b''
    while True:
        line = f.readline()
        header += line
        if line.strip() == b'end_header':
            break
total = 0
for line in header.decode().split('\n'):
    if 'element vertex' in line:
        total = int(line.split()[-1])
if total == 0:
    sys.exit(1)
sample_rate = min(1.0, 500000.0 / total)
vertex_size = 4*3 + 4*3 + 3  # xyz + nxyz + rgb
rng = np.random.RandomState(42)
kept = []
with open(fused, 'rb') as f:
    f.seek(len(header))
    for i in range(total):
        data = f.read(vertex_size)
        if rng.random() < sample_rate:
            kept.append(data)
with open(output, 'wb') as f:
    f.write(b'ply\nformat binary_little_endian 1.0\n')
    f.write(f'element vertex {len(kept)}\n'.encode())
    f.write(b'property float x\nproperty float y\nproperty float z\n')
    f.write(b'property float nx\nproperty float ny\nproperty float nz\n')
    f.write(b'property uchar red\nproperty uchar green\nproperty uchar blue\n')
    f.write(b'end_header\n')
    for v in kept:
        f.write(v)
PYEOF

        echo "--- Poisson meshing ---"
        colmap poisson_mesher \
            --input_path "$DENSE_DIR/fused.ply" \
            --output_path "$SCENE_DIR/mesh_raw.ply" \
            --PoissonMeshing.depth 10 \
            --PoissonMeshing.trim 7 \
            || die 4 "poisson_mesher failed."
    fi

    echo "COLMAP dense complete: $SCENE_DIR/mesh_raw.ply"

    echo
    echo "--- Blender cleanup + glTF export ---"
    "$BLENDER_BIN" --background \
        --python "$SCRIPT_DIR/blender_cleanup_mesh.py" -- \
        --scene-dir "$SCENE_DIR" \
        --textures-dir "$TEXTURES_DIR" \
        --target-tris "${MESH_TARGET_TRIS:-500000}" \
        || die 5 "Blender cleanup failed. See $SCENE_DIR/blender_cleanup.log"

    if [[ ! -f "$SCENE_DIR/scene.glb" ]]; then
        die 5 "Blender exited 0 but scene.glb not found at $SCENE_DIR/scene.glb"
    fi
    GLB_SIZE=$(stat -c%s "$SCENE_DIR/scene.glb" 2>/dev/null || echo "0")
    if [[ "$GLB_SIZE" -eq 0 ]]; then
        die 5 "scene.glb is empty (0 bytes)"
    fi
    echo "scene.glb produced ($GLB_SIZE bytes)."

    if [[ ! -f "$SCENE_DIR/scene_transform.txt" ]]; then
        die 5 "scene_transform.txt not found"
    fi
    echo "scene_transform.txt written."

    if ! $KEEP_DENSE; then
        rm -rf "$DENSE_DIR"
        echo "Removed dense workspace."
    fi
else
    # --- Meshroom (AliceVision) path ---
    MESHROOM_OUT="$SCENE_DIR/meshroom_out"

    echo "--- Running Meshroom (AliceVision) pipeline ---"
    echo "Input:  $IMAGES_DIR"
    echo "Output: $MESHROOM_OUT"

    "$MESHROOM_BIN" \
        --input "$IMAGES_DIR" \
        --output "$MESHROOM_OUT" \
        || die 4 "Meshroom pipeline failed. See MeshroomCache/ logs under $MESHROOM_OUT"

    echo "Meshroom pipeline complete. Locating output mesh..."

    # Meshroom's Texturing node writes texturedMesh.obj into
    # MeshroomCache/Texturing/<hash>/; fall back to Meshing node's mesh.obj.
    # Prefer texturedMesh.obj first (has textures), then mesh.obj.
    # Use -print -quit instead of piping through head -1: under pipefail,
    # head exiting after first line can SIGPIPE find and abort the script.
    MESHROOM_MESH=$(find "$MESHROOM_OUT" -type f \
        -name "texturedMesh.obj" -print -quit 2>/dev/null)
    if [[ -z "$MESHROOM_MESH" ]]; then
        MESHROOM_MESH=$(find "$MESHROOM_OUT" -type f \
            -name "mesh.obj" -print -quit 2>/dev/null)
    fi

    if [[ -z "$MESHROOM_MESH" ]]; then
        die 4 "Meshroom completed (exit 0) but no output mesh found. Looked for texturedMesh.obj / mesh.obj under $MESHROOM_OUT/MeshroomCache/"
    fi

    echo "Found: $MESHROOM_MESH"

    # Pass the OBJ (with its .mtl + texture images) directly to Blender so
    # materials, UVs, and textures survive into scene.glb. Copy the OBJ's
    # directory to a stable location since meshroom_out may be cleaned up.
    MESHROOM_IMPORT_DIR="$SCENE_DIR/meshroom_import"
    if [[ "$MESHROOM_MESH" == *.obj ]]; then
        MESHROOM_SRC_DIR="$(dirname "$MESHROOM_MESH")"
        MESHROOM_OBJ_BASENAME="$(basename "$MESHROOM_MESH")"
        rm -rf "$MESHROOM_IMPORT_DIR"
        mkdir -p "$MESHROOM_IMPORT_DIR"
        cp "$MESHROOM_SRC_DIR"/* "$MESHROOM_IMPORT_DIR"/ 2>/dev/null || true
        BLENDER_INPUT_MESH="$MESHROOM_IMPORT_DIR/$MESHROOM_OBJ_BASENAME"
        echo "Meshroom OBJ + companion files staged at $MESHROOM_IMPORT_DIR"
        echo "Blender input: $BLENDER_INPUT_MESH"

        # Produce mesh_raw.ply (geometry-only, no textures) for contract.
        # Blender gets the OBJ directly to preserve materials; this PLY is
        # the intermediate artifact (M1a/M1b) for downstream consumers.
        echo "Writing mesh_raw.ply (contract artifact)..."
        python3 - "$MESHROOM_MESH" "$SCENE_DIR/mesh_raw.ply" <<'PYEOF' || die 4 "OBJ to PLY conversion for mesh_raw.ply failed."
import sys
inp, outp = sys.argv[1], sys.argv[2]
verts, faces = [], []
with open(inp) as f:
    for line in f:
        p = line.strip().split()
        if not p:
            continue
        if p[0] == 'v':
            verts.append([float(x) for x in p[1:4]])
        elif p[0] == 'f':
            face = []
            for v in p[1:]:
                vidx = int(v.split('/')[0])
                face.append(vidx - 1 if vidx > 0 else len(verts) + vidx)
            if len(face) >= 3:
                faces.append(face)
if not verts:
    sys.exit(1)
with open(outp, 'w') as f:
    f.write("ply\nformat ascii 1.0\n")
    f.write(f"element vertex {len(verts)}\n")
    f.write("property float x\nproperty float y\nproperty float z\n")
    f.write(f"element face {len(faces)}\n")
    f.write("property list uchar int vertex_indices\n")
    f.write("end_header\n")
    for v in verts:
        f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
    for face in faces:
        f.write(f"{len(face)} {' '.join(str(i) for i in face)}\n")
PYEOF
        echo "mesh_raw.ply written."
    else
        cp "$MESHROOM_MESH" "$SCENE_DIR/mesh_raw.ply"
        BLENDER_INPUT_MESH="$SCENE_DIR/mesh_raw.ply"
    fi

    echo
    echo "--- Blender cleanup + glTF export ---"
    "$BLENDER_BIN" --background \
        --python "$SCRIPT_DIR/blender_cleanup_mesh.py" -- \
        --scene-dir "$SCENE_DIR" \
        --input-mesh "$BLENDER_INPUT_MESH" \
        --textures-dir "$TEXTURES_DIR" \
        --target-tris "${MESH_TARGET_TRIS:-500000}" \
        || die 5 "Blender cleanup failed. See $SCENE_DIR/blender_cleanup.log"

    if [[ ! -f "$SCENE_DIR/scene.glb" ]]; then
        die 5 "Blender exited 0 but scene.glb not found at $SCENE_DIR/scene.glb"
    fi
    GLB_SIZE=$(stat -c%s "$SCENE_DIR/scene.glb" 2>/dev/null || echo "0")
    if [[ "$GLB_SIZE" -eq 0 ]]; then
        die 5 "scene.glb is empty (0 bytes)"
    fi
    echo "scene.glb produced ($GLB_SIZE bytes)."

    if [[ ! -f "$SCENE_DIR/scene_transform.txt" ]]; then
        die 5 "scene_transform.txt not found"
    fi
    echo "scene_transform.txt written."

    if ! $KEEP_DENSE; then
        rm -rf "$MESHROOM_OUT"
        echo "Removed meshroom_out workspace."
    fi
fi

echo
echo "=== Stage M complete ==="
echo "Mesh:    $SCENE_DIR/mesh_raw.ply"
echo "glTF:    $SCENE_DIR/scene.glb"
echo "Transform: $SCENE_DIR/scene_transform.txt"
