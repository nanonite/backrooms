#!/usr/bin/env python3
"""
decimate_to_glb.py — Headless Blender script for mesh decimation and GLB export.

Imports the Stage D mesh (OBJ), removes floating junk, decimates aggressively
to a configurable target below 200k triangles, exports scene_dir/collision.glb,
and writes diagnostics to a log file.

IMPORTANT: When run inside Blender (--background --python ... -- <args>),
snap/flatpak Blender may suppress stdout/stderr. All diagnostics MUST be
written to the log file via write_log() — do NOT rely on print() for
critical output.

Usage (inside Blender):
    blender --background --python decimate_to_glb.py -- \\
        --scene-dir <scene_dir> \\
        [--input-mesh <path>] [--output <path>] \\
        [--target-triangles N] [--log-file <path>]

Usage (outside Blender, for argument validation testing):
    python3 decimate_to_glb.py --validate-args \\
        --scene-dir <scene_dir> [--target-triangles N]
"""

import argparse
import os
import sys
from pathlib import Path

DEFAULT_TARGET_TRIANGLES = 200000
DEFAULT_INPUT_NAME = "mesh_export.obj"
DEFAULT_OUTPUT_NAME = "collision.glb"
DEFAULT_LOG_NAME = "decimate_to_glb.log"


# ---------------------------------------------------------------------------
# Pure helpers — testable without Blender
# ---------------------------------------------------------------------------


def calculate_decimation_ratio(current_triangles: int, target_triangles: int) -> float:
    """Return a decimation ratio that brings current under target (>0, <=1)."""
    if current_triangles <= 0:
        raise ValueError("current_triangles must be positive")
    if target_triangles <= 0:
        raise ValueError("target_triangles must be positive")
    if current_triangles <= target_triangles:
        return 1.0
    ratio = target_triangles / current_triangles
    return max(ratio, 0.001)


def write_log(log_file: Path, message: str) -> None:
    """Append a timestamped message to the log file."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a") as f:
        f.write(f"{message}\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Decimate mesh and export as GLB (headless Blender)."
    )
    parser.add_argument(
        "--scene-dir",
        type=str,
        required=True,
        help="Path to the scene directory.",
    )
    parser.add_argument(
        "--input-mesh",
        type=str,
        default=None,
        help=(
            "Path to the input mesh (default: <scene_dir>/mesh_export.obj). "
            "SuGaR produces .obj; set manually if the exporter produces "
            "a different format."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Path for the output GLB (default: <scene_dir>/collision.glb)."
        ),
    )
    parser.add_argument(
        "--target-triangles",
        type=int,
        default=DEFAULT_TARGET_TRIANGLES,
        help=f"Maximum triangle count after decimation (default: {DEFAULT_TARGET_TRIANGLES}).",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help=(
            "Path for the diagnostic log file "
            "(default: <scene_dir>/decimate_to_glb.log)."
        ),
    )
    parser.add_argument(
        "--validate-args",
        action="store_true",
        help=(
            "Validate arguments and exit (for testing outside Blender). "
            "Does not require Blender."
        ),
    )
    parser.add_argument(
        "--min-component-faces",
        type=int,
        default=50,
        help=(
            "Minimum face count for a disconnected component to be kept "
            "(default: 50). Smaller components are deleted as floating junk."
        ),
    )
    return parser.parse_args(argv)


def validate_triangle_budget(
    target_triangles: int, log_file: Path
) -> None:
    """Validate the target triangle budget, writing issues to the log."""
    if target_triangles < 100:
        write_log(log_file, f"WARN: target-triangles ({target_triangles}) is very low; collision may lose detail.")
    if target_triangles > DEFAULT_TARGET_TRIANGLES:
        write_log(log_file, f"WARN: target-triangles ({target_triangles}) exceeds recommended maximum ({DEFAULT_TARGET_TRIANGLES}).")


# ---------------------------------------------------------------------------
# Blender-mode operations — require bpy
# ---------------------------------------------------------------------------


def _select_mesh_objects() -> list:
    """Select all mesh objects in the scene. Returns list of mesh objects."""
    import bpy
    bpy.ops.object.select_all(action='DESELECT')
    mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']
    if not mesh_objects:
        return []
    for obj in mesh_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_objects[0]
    return mesh_objects


def _remove_floating_junk(min_component_faces: int, log_file: Path) -> int:
    """Delete small disconnected components. Returns count of removed faces."""
    import bpy
    removed_total = 0

    mesh_objects = _select_mesh_objects()
    if not mesh_objects:
        write_log(log_file, "WARN: no mesh objects found — nothing to clean.")
        return 0

    for obj in mesh_objects:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')

        try:
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.separate(type='LOOSE')
        except RuntimeError:
            bpy.ops.object.mode_set(mode='OBJECT')
            continue

        bpy.ops.object.mode_set(mode='OBJECT')

        # Delete tiny separated fragments
        fragments_removed = 0
        for frag in bpy.data.objects:
            # Newly separated fragments inherit type MESH from the original
            if frag.type != 'MESH':
                continue
            if frag.name == obj.name:
                continue
            if frag.data is None:
                continue
            if len(frag.data.polygons) < min_component_faces:
                bpy.data.objects.remove(frag, do_unlink=True)
                fragments_removed += 1

        if fragments_removed > 0:
            write_log(log_file, f"CLEAN: removed {fragments_removed} floating fragments from '{obj.name}'.")
            removed_total += fragments_removed

    return removed_total


def _count_triangles(obj) -> int:
    """Return the triangulated face count for a Blender mesh object."""
    import bpy
    mesh = obj.data
    if mesh is None:
        return 0
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='OBJECT')
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def _decimate_mesh(target_triangles: int, log_file: Path) -> int:
    """Apply decimation modifier only if under budget.
    Returns the final total triangle count."""
    import bpy
    total_triangles = 0

    mesh_objects = _select_mesh_objects()
    if not mesh_objects:
        write_log(log_file, "ERROR: no mesh objects to decimate.")
        return 0

    for obj in mesh_objects:
        total_triangles += _count_triangles(obj)

    write_log(log_file, f"TRIANGLES: {total_triangles} triangles (triangulated).")

    if total_triangles <= target_triangles:
        write_log(log_file, f"TRIANGLES: already under target (no decimation needed).")
        return total_triangles

    ratio = calculate_decimation_ratio(total_triangles, target_triangles)
    write_log(log_file, f"DECIMATE: applying ratio {ratio:.3f} to reach target {target_triangles} (current: {total_triangles}).")

    for obj in mesh_objects:
        bpy.context.view_layer.objects.active = obj
        modifier = obj.modifiers.new(name="Decimate", type='DECIMATE')
        modifier.ratio = ratio
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier="Decimate")

    total_triangles = 0
    for obj in mesh_objects:
        total_triangles += _count_triangles(obj)

    write_log(log_file, f"TRIANGLES: {total_triangles} triangles after decimation.")
    return total_triangles


def _export_glb(output_path: Path, log_file: Path) -> None:
    """Export selected mesh objects as GLB."""
    import bpy

    mesh_objects = _select_mesh_objects()
    if not mesh_objects:
        write_log(log_file, "ERROR: no mesh objects to export.")
        raise RuntimeError("No mesh objects to export")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.export_scene.gltf(
        filepath=str(output_path),
        export_format='GLB',
        use_selection=True,
        export_materials='NONE',
        export_apply=True,
    )
    write_log(log_file, f"EXPORT: wrote {output_path} ({output_path.stat().st_size} bytes).")


def _import_mesh(input_path: Path, log_file: Path) -> None:
    """Import a mesh file (OBJ, GLB, etc.) into the current Blender scene."""
    import bpy

    ext = input_path.suffix.lower()

    write_log(log_file, f"IMPORT: reading {input_path} ({input_path.stat().st_size} bytes).")

    if ext == '.obj':
        bpy.ops.wm.obj_import(filepath=str(input_path))
    elif ext in ('.glb', '.gltf'):
        bpy.ops.import_scene.gltf(filepath=str(input_path))
    elif ext == '.ply':
        bpy.ops.wm.ply_import(filepath=str(input_path))
    elif ext in ('.fbx',):
        bpy.ops.import_scene.fbx(filepath=str(input_path))
    elif ext == '.stl':
        bpy.ops.wm.stl_import(filepath=str(input_path))
    else:
        write_log(log_file, f"ERROR: unsupported mesh format: {ext}")
        raise RuntimeError(f"Unsupported mesh format: {ext}")


def main_blender(args: argparse.Namespace) -> None:
    """Run the full Blender pipeline: import, clean, decimate, export."""
    import bpy

    scene_dir = Path(args.scene_dir).resolve()
    input_mesh = Path(args.input_mesh or (scene_dir / DEFAULT_INPUT_NAME)).resolve()
    output_path = Path(args.output or (scene_dir / DEFAULT_OUTPUT_NAME)).resolve()
    log_file = Path(args.log_file or (scene_dir / DEFAULT_LOG_NAME)).resolve()
    target_triangles = args.target_triangles
    min_component_faces = args.min_component_faces

    write_log(log_file, f"=== decimate_to_glb.py ===")
    write_log(log_file, f"Scene dir:       {scene_dir}")
    write_log(log_file, f"Input mesh:      {input_mesh}")
    write_log(log_file, f"Output:          {output_path}")
    write_log(log_file, f"Target tris:     {target_triangles}")
    write_log(log_file, f"Min comp faces:  {min_component_faces}")
    write_log(log_file, f"Blender version: {bpy.app.version_string}")

    if not input_mesh.exists():
        write_log(log_file, f"ERROR: input mesh not found: {input_mesh}")
        raise FileNotFoundError(f"Input mesh not found: {input_mesh}")

    validate_triangle_budget(target_triangles, log_file)

    # Clear default scene objects (cube, camera, light)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_confirm=False)

    _import_mesh(input_mesh, log_file)

    _remove_floating_junk(min_component_faces, log_file)

    final_tris = _decimate_mesh(target_triangles, log_file)

    _export_glb(output_path, log_file)

    write_log(log_file, "=== SUCCESS ===")
    write_log(log_file, f"Output: {output_path} ({output_path.stat().st_size} bytes)")
    write_log(log_file, f"Final triangles: {final_tris}")

    if final_tris > target_triangles:
        write_log(log_file, f"WARN: final triangle count ({final_tris}) exceeds target ({target_triangles}).")
        write_log(log_file, "Collision mesh may be heavier than expected — verify performance at runtime.")
        write_log(log_file, "Re-run with a lower --target-triangles value if needed.")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    # Blender passes '--' before script args; strip it if present
    if argv and argv[0] == '--':
        argv = argv[1:]

    args = parse_args(argv)

    if args.validate_args:
        # Validation-only mode: test argument parsing without Blender
        scene_dir = Path(args.scene_dir).resolve()
        input_mesh = Path(args.input_mesh or (scene_dir / DEFAULT_INPUT_NAME))
        output_path = Path(args.output or (scene_dir / DEFAULT_OUTPUT_NAME))
        log_file = Path(args.log_file or (scene_dir / DEFAULT_LOG_NAME))

        print(f"scene_dir:       {scene_dir}")
        print(f"input_mesh:      {input_mesh}")
        print(f"output:          {output_path}")
        print(f"target_triangles: {args.target_triangles}")
        print(f"min_component_faces: {args.min_component_faces}")
        print(f"log_file:        {log_file}")

        if args.target_triangles < 100:
            print(f"WARN: target-triangles ({args.target_triangles}) is very low.", file=sys.stderr)
        if args.target_triangles > DEFAULT_TARGET_TRIANGLES:
            print(f"WARN: target-triangles ({args.target_triangles}) exceeds recommended maximum ({DEFAULT_TARGET_TRIANGLES}).", file=sys.stderr)

        return

    # Check if running inside Blender
    try:
        import bpy  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "ERROR: This script must be run inside Blender.\n"
            "Usage: blender --background --python decimate_to_glb.py -- --scene-dir <dir>\n"
        )
        sys.exit(1)

    main_blender(args)


if __name__ == "__main__":
    main()
