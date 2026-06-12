"""
Blender headless cleanup script for Stage M mesh.

Loads a mesh (.ply or .obj), scales to metric, fills non-manifold holes,
decimates to target triangle count, applies reference textures by face normal
(for PLY inputs without materials), and exports scene.glb with embedded
textures. Blender's glTF exporter handles +Z-up -> +Y-up conversion
automatically — no manual axis rotation needed.

For .obj inputs with materials (e.g. Meshroom texturedMesh.obj + .mtl + textures),
materials and UVs are preserved through to the exported GLB. External texture
assignment and UV generation are skipped when the imported mesh already has them.

The script verifies the exported GLB's Y extent matches the target
doorway height and that its horizontal footprint is wide enough to be walkable
before exiting successfully.

Usage:
    blender --background --python blender_cleanup_mesh.py -- \
        --scene-dir /path/to/scene \
        --textures-dir /path/to/textures \
        [--input-mesh /path/to/mesh.obj] \
        [--target-tris 500000] \
        [--doorway-height 2.0] \
        [--min-footprint 1.5] \
        [--min-component-faces 50]

If --input-mesh is omitted, defaults to <scene-dir>/mesh_raw.ply (COLMAP path).

The script writes progress and diagnostics to <scene_dir>/blender_cleanup.log
because snap/flatpak Blender may suppress stdout/stderr.

Textures are expected at <textures-dir>/<scene_name>_<surface>.jpg where
<scene_name> is the scene_dir basename and <surface> is ceiling/floor/front/side.
If any required texture is missing the script skips external material assignment
and keeps existing vertex colors or imported materials.
"""

import bpy
import sys
import os
import math
import argparse
from pathlib import Path
from mathutils import Matrix, Vector

DEFAULT_MIN_COMPONENT_FACES = 50
DEFAULT_MIN_FOOTPRINT = 1.5
HEIGHT_TOLERANCE = 0.25


def log(msg):
    """Append to log file; fallback to print."""
    print(msg, flush=True)
    log_path = _LOG_PATH
    try:
        with open(log_path, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass


_LOG_PATH = None


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-dir", required=True)
    parser.add_argument("--input-mesh", default=None,
                        help="Path to input mesh (.ply or .obj). Default: <scene-dir>/mesh_raw.ply")
    parser.add_argument("--textures-dir", required=True,
                        help="Path to directory containing <scene>_<surface>.jpg textures")
    parser.add_argument("--target-tris", type=int, default=500000)
    parser.add_argument("--doorway-height", type=float, default=2.0)
    parser.add_argument("--min-footprint", type=float, default=DEFAULT_MIN_FOOTPRINT,
                        help="Minimum accepted exported X/Y footprint in meters")
    parser.add_argument("--min-component-faces", type=int, default=DEFAULT_MIN_COMPONENT_FACES,
                        help="Minimum loose-component face count kept before scaling")
    parser.add_argument("--log-file", default=None)
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    # Clear mesh data
    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)
    for mat in bpy.data.materials:
        bpy.data.materials.remove(mat)
    for img in bpy.data.images:
        bpy.data.images.remove(img)


def import_ply(ply_path):
    log(f"Importing PLY: {ply_path}")
    bpy.ops.wm.ply_import(filepath=str(ply_path))
    obj = bpy.context.active_object
    if obj is None:
        raise RuntimeError("PLY import produced no object")
    log(f"  Name: {obj.name}, Type: {obj.type}")
    if obj.type == "MESH":
        log(f"  Vertices: {len(obj.data.vertices)}, Faces: {len(obj.data.polygons)}")
    return obj


def import_obj(obj_path):
    log(f"Importing OBJ: {obj_path}")
    bpy.ops.wm.obj_import(filepath=str(obj_path))
    obj = bpy.context.active_object
    if obj is None:
        raise RuntimeError("OBJ import produced no object")
    log(f"  Name: {obj.name}, Type: {obj.type}")
    if obj.type == "MESH":
        mesh = obj.data
        log(f"  Vertices: {len(mesh.vertices)}, Faces: {len(mesh.polygons)}")
        mat_count = len(obj.data.materials)
        uv_count = len(mesh.uv_layers) if mesh.uv_layers else 0
        log(f"  Materials: {mat_count}, UV layers: {uv_count}")
    return obj


def import_mesh(mesh_path):
    suffix = Path(mesh_path).suffix.lower()
    if suffix == ".obj":
        return import_obj(mesh_path)
    else:
        return import_ply(mesh_path)


def mesh_objects():
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def select_mesh_objects(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]


def bounds_for_objects(objects):
    mins = [float("inf"), float("inf"), float("inf")]
    maxs = [float("-inf"), float("-inf"), float("-inf")]
    for obj in objects:
        for vertex in obj.data.vertices:
            point = obj.matrix_world @ vertex.co
            values = (point.x, point.y, point.z)
            for index, value in enumerate(values):
                mins[index] = min(mins[index], value)
                maxs[index] = max(maxs[index], value)
    return [maxs[index] - mins[index] for index in range(3)]


def separate_loose_components(obj):
    select_mesh_objects([obj])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")


def delete_small_components(min_component_faces):
    removed = 0
    for fragment in list(mesh_objects()):
        if len(fragment.data.polygons) >= min_component_faces:
            continue
        bpy.data.objects.remove(fragment, do_unlink=True)
        removed += 1
    return removed


def join_remaining_components(original_name):
    remaining = mesh_objects()
    if not remaining:
        log("  FATAL: all mesh components were removed as floating fragments.")
        sys.exit(1)
    if len(remaining) > 1:
        log(f"  Joining {len(remaining)} kept components.")
        select_mesh_objects(remaining)
        bpy.ops.object.join()
        remaining = mesh_objects()
    remaining[0].name = original_name
    return remaining[0]


def log_component_cleanup(cleaned, removed):
    log(f"  Removed {removed} floating fragments; kept {len(cleaned.data.polygons)} faces.")
    dims = bounds_for_objects([cleaned])
    log(f"  Cleaned bounds: X={dims[0]:.3f}, Y={dims[1]:.3f}, Z={dims[2]:.3f}")


def remove_floating_components(obj, min_component_faces):
    """Remove tiny disconnected fragments and return one joined mesh object."""
    log(f"Removing loose components under {min_component_faces} faces...")
    original_name = obj.name
    separate_loose_components(obj)
    removed = delete_small_components(min_component_faces)
    cleaned = join_remaining_components(original_name)
    log_component_cleanup(cleaned, removed)
    return cleaned


def validate_export_bounds(objects, target_doorway_height, min_footprint):
    dims = bounds_for_objects(objects)
    x_extent, y_extent, z_extent = dims
    log(f"  BOUNDS CHECK: X={x_extent:.3f}, Y={y_extent:.3f}, Z height={z_extent:.3f}")
    log(f"  BOUNDS CHECK: target height={target_doorway_height:.1f}m, min footprint={min_footprint:.1f}m")

    if abs(z_extent - target_doorway_height) > HEIGHT_TOLERANCE:
        log(f"  FATAL: height {z_extent:.3f} differs from target {target_doorway_height:.1f}m by >{HEIGHT_TOLERANCE:.2f}m")
        log("  The exported GLB does not satisfy the Y-up/meters contract.")
        sys.exit(1)

    if min(x_extent, y_extent) < min_footprint:
        log(f"  FATAL: footprint {x_extent:.3f} x {y_extent:.3f}m is below {min_footprint:.1f}m minimum")
        log("  The exported GLB is too narrow to represent a walkable corridor.")
        sys.exit(1)

    log("  BOUNDS CHECK: passed.")


def estimate_scale(obj, target_doorway_height=2.0):
    """
    Estimate metric scale by measuring the vertical extent and assuming a
    ~2.0m doorway/corridor height.

    The mesh is in Blender's internal Z-up coordinate system (imported from
    COLMAP PLY). Blender's glTF exporter will convert to Y-up on export,
    so the vertical axis here is Z.
    """
    mesh = obj.data
    verts = [obj.matrix_world @ v.co for v in mesh.vertices]
    z_vals = [v.z for v in verts]
    z_min, z_max = min(z_vals), max(z_vals)
    extent_z = z_max - z_min

    if extent_z < 0.01:
        log("  WARNING: Z extent too small, cannot estimate scale.")
        log("  Using scale factor 1.0 (no scaling).")
        return 1.0

    scale_factor = target_doorway_height / extent_z
    log(f"  Z extent (height): {extent_z:.3f} units")
    log(f"  Target doorway height: {target_doorway_height:.1f} m")
    log(f"  Computed scale factor: {scale_factor:.4f}")

    return scale_factor


def apply_transform(obj, scale_factor):
    """Apply scale factor and rotation as object transform, then apply all transforms."""
    log(f"  Applying scale factor {scale_factor:.4f}...")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.scale = (scale_factor, scale_factor, scale_factor)

    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    log("  Transforms applied.")


def fill_non_manifold(obj):
    """Select and fill non-manifold geometry (especially floor holes)."""
    log("Filling non-manifold geometry...")
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.mesh.select_non_manifold()

    bpy.ops.mesh.fill()
    bpy.ops.object.mode_set(mode="OBJECT")
    log("  Non-manifold fill completed.")


def decimate(obj, target_tris):
    """Decimate mesh to target triangle count using collapse decimation."""
    current_tris = len(obj.data.polygons)
    if current_tris <= target_tris:
        log(f"  Already at {current_tris} tris (target: {target_tris}). Skipping decimation.")
        return

    target_ratio = target_tris / current_tris
    log(f"Decimating from {current_tris} to ~{target_tris} tris (ratio: {target_ratio:.3f})...")

    mod = obj.modifiers.new(name="Decimate", type="DECIMATE")
    mod.ratio = target_ratio
    mod.use_collapse_triangulate = True

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier="Decimate")

    new_tris = len(obj.data.polygons)
    log(f"  After decimation: {new_tris} tris")


def assign_materials_by_normal(obj, scene_dir, textures_dir):
    """
    Assign materials with reference textures based on face normal direction.
    - Faces with normal pointing mostly +Z (Z-up) -> ceiling texture
    - Faces with normal pointing mostly -Z -> floor texture
    - Others -> wall textures (front/side)

    Textures are looked up at <textures_dir>/<scene_name>_<surface>.{jpg,png}.
    If any required texture is missing, external material assignment is skipped
    and the mesh keeps its existing vertex colors from the photogrammetry export.

    All work done in OBJECT mode to avoid Blender mode-switching crashes.
    """
    log("Assigning materials by face normal...")
    mesh = obj.data

    scene_name = Path(scene_dir).name
    textures_path = Path(textures_dir)

    texture_map = {
        "ceiling": f"{scene_name}_ceiling",
        "floor": f"{scene_name}_floor",
        "front": f"{scene_name}_front",
        "side": f"{scene_name}_side",
    }

    # Resolve actual file paths, trying .jpg then .png
    resolved = {}
    for surface, basename in texture_map.items():
        for ext in (".jpg", ".png"):
            tex_path = textures_path / f"{basename}{ext}"
            if tex_path.exists():
                resolved[surface] = tex_path
                break

    missing = [s for s in texture_map if s not in resolved]
    if missing:
        log("WARNING: External textures not found, keeping vertex colors.")
        log(f"  Missing ({', '.join(missing)}) in {textures_path}")
        log("  Expected: <scene>_{ceiling,floor,front,side}.jpg or .png")
        return

    # Ensure we are in OBJECT mode
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Create materials
    for surface in ("ceiling", "floor", "front", "side"):
        tex_path = resolved[surface]
        filename = tex_path.name
        mat = bpy.data.materials.new(name=f"mat_{surface}")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        nodes.clear()

        bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)
        output = nodes.new(type="ShaderNodeOutputMaterial")
        output.location = (300, 0)
        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

        img = bpy.data.images.load(str(tex_path))
        tex_node = nodes.new(type="ShaderNodeTexImage")
        tex_node.image = img
        tex_node.location = (-300, 0)
        links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
        log(f"  {surface}: loaded {filename}")

        obj.data.materials.append(mat)

    # Assign material indices by face normal in OBJECT mode.
    # Mesh is in Blender's Z-up internal frame; glTF exporter converts to Y-up.
    mat_world = obj.matrix_world
    for poly in mesh.polygons:
        normal = mat_world.to_3x3() @ poly.normal
        normal.normalize()

        if normal.z > 0.7:
            mat_idx = 0  # ceiling
        elif normal.z < -0.7:
            mat_idx = 1  # floor
        elif abs(normal.x) > abs(normal.y):
            mat_idx = 3  # side wall
        else:
            mat_idx = 2  # front/back wall

        poly.material_index = mat_idx

    log(f"  Material assignment complete ({len(obj.data.materials)} materials).")


def clear_custom_normals(obj):
    """Clear custom split normals to fix mesh validity warnings."""
    log("Clearing custom split normals...")
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    mesh = obj.data
    if mesh.has_custom_normals:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
        log("  Custom split normals cleared.")
    else:
        log("  No custom normals to clear.")


def generate_uvs(obj):
    """Generate UV coordinates via Smart UV Project for all faces."""
    log("Generating UV coordinates...")
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")

    # Smart UV project - good for architectural geometry
    bpy.ops.uv.smart_project(
        angle_limit=66.0,
        island_margin=0.001,
        area_weight=0.0,
        correct_aspect=True,
        scale_to_bounds=False,
    )

    bpy.ops.object.mode_set(mode="OBJECT")
    log("  UV generation complete.")


def export_glb(obj, output_path, target_doorway_height, min_footprint):
    """
    Export as glTF 2.0 GLB with embedded textures, then re-import to verify
    metric height and corridor footprint contracts.
    """
    log(f"Exporting to: {output_path}")

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    bpy.ops.export_scene.gltf(
        filepath=str(output_path),
        export_format="GLB",
        use_selection=True,
        export_apply=False,
        export_image_format="JPEG",
        export_texture_dir="",
        export_keep_originals=False,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
    )

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    log(f"  Exported {output_path} ({size_mb:.1f} MB)")

    # Re-import the GLB to verify the metric height contract.
    # glTF uses Y-up; Blender imports as Z-up (its internal convention).
    # So the height we scaled on Z before export -> Y in GLB -> Z again after re-import.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(output_path))

    imported = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not imported:
        log("  BOUNDS CHECK: failed to re-import GLB for verification")
        sys.exit(1)

    # After re-import, Blender converts glTF Y-up back to Z-up.
    validate_export_bounds(imported, target_doorway_height, min_footprint)


def write_scene_transform(output_path, scale_factor):
    """Write scene_transform.txt recording the scale applied for v2 splat alignment."""
    with open(output_path, "w") as f:
        f.write("# scene_transform.txt — recorded during Blender cleanup (Stage M)\n")
        f.write("# Z-up -> Y-up conversion handled by Blender glTF exporter (no manual rotation).\n")
        f.write("# Scale factor applied to match metric doorway height.\n")
        f.write(f"scale: {scale_factor:.6f}\n")
    log(f"  Wrote {output_path}")


def main():
    global _LOG_PATH

    args = parse_args()
    scene_dir = Path(args.scene_dir)
    textures_dir = args.textures_dir
    target_tris = args.target_tris
    doorway_height = args.doorway_height
    min_footprint = args.min_footprint
    min_component_faces = args.min_component_faces

    _LOG_PATH = str(scene_dir / "blender_cleanup.log")
    log(f"=== Blender cleanup script ===")
    log(f"Scene dir: {scene_dir}")
    log(f"Textures dir: {textures_dir}")
    log(f"Target tris: {target_tris}")
    log(f"Doorway height: {doorway_height}m")
    log(f"Min footprint: {min_footprint}m")
    log(f"Min component faces: {min_component_faces}")

    input_mesh = Path(args.input_mesh) if args.input_mesh else scene_dir / "mesh_raw.ply"
    if not input_mesh.exists():
        log(f"ERROR: input mesh not found at {input_mesh}")
        sys.exit(1)

    clear_scene()

    obj = import_mesh(input_mesh)
    obj = remove_floating_components(obj, min_component_faces)
    has_materials = bool(obj.data.materials)
    has_uvs = bool(obj.data.uv_layers)

    scale_factor = estimate_scale(obj, doorway_height)
    apply_transform(obj, scale_factor)

    fill_non_manifold(obj)
    decimate(obj, target_tris)

    if has_materials:
        log("Mesh already has materials (from import), skipping external texture assignment.")
    else:
        assign_materials_by_normal(obj, str(scene_dir), textures_dir)

    clear_custom_normals(obj)

    if has_uvs:
        log("Mesh already has UV coordinates (from import), skipping UV generation.")
    else:
        generate_uvs(obj)

    output_glb = scene_dir / "scene.glb"
    export_glb(obj, output_glb, doorway_height, min_footprint)

    transform_path = scene_dir / "scene_transform.txt"
    write_scene_transform(transform_path, scale_factor)

    log("=== Done ===")


if __name__ == "__main__":
    main()
