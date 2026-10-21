"""Create the bounded, native-Blender visual repair for Chainlink #153."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[4]
ROUND = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROUND / "source"
GENERATED_DIR = ROUND / "generated"
BLEND_PATH = ROUND / "column_corner_repair.blend"
GLB_PATH = GENERATED_DIR / "column_corner_repair.glb"
FLOOR_Y = -1.2709904909
COLUMN_CENTER_XZ = (-0.44746488, 0.32348078)
COLUMN_WIDTH_X = 1.8587826
COLUMN_WIDTH_Z = 2.3700817
COLUMN_HEIGHT = 2.4
SURFACE_OFFSET = 0.018


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bevy_to_blender(point: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = point
    return x, -z, y


def make_material(name: str, color: tuple[float, float, float], texture: Path | None = None):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.0)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    shader = nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = 1.0
    if "Emission Color" in shader.inputs:
        shader.inputs["Emission Color"].default_value = (*color, 1.0)
        shader.inputs["Emission Strength"].default_value = 1.0
    if texture is not None:
        image = bpy.data.images.load(str(texture), check_existing=True)
        image.pack()
        texture_node = nodes.new("ShaderNodeTexImage")
        texture_node.image = image
        texture_node.interpolation = "Closest"
        material.node_tree.links.new(texture_node.outputs["Color"], shader.inputs["Base Color"])
        if "Emission Color" in shader.inputs:
            material.node_tree.links.new(
                texture_node.outputs["Color"], shader.inputs["Emission Color"]
            )
    return material


def make_face(name: str, corners: list[tuple[float, float, float]], material, uv=None) -> None:
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata([bevy_to_blender(point) for point in corners], [], [(0, 1, 2, 3)])
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="SourceUV")
    coordinates = uv or [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    for loop_index, coordinate in enumerate(coordinates):
        uv_layer.data[loop_index].uv = coordinate
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)


def column_faces(bounds: tuple[float, float, float, float, float, float], materials) -> None:
    x0, x1, y0, y1, z0, z1 = bounds
    faces = [
        ("column_flat_face_north", [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], materials["flat"]),
        ("column_source_face_east", [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], materials["column"]),
        ("column_flat_face_south", [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)], materials["flat"]),
        ("column_flat_face_west", [(x0, y0, z1), (x0, y1, z1), (x0, y1, z0), (x0, y0, z0)], materials["flat"]),
        ("column_flat_cap_top", [(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)], materials["flat"]),
        ("column_flat_cap_bottom", [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], materials["flat"]),
    ]
    for name, corners, material in faces:
        make_face(name, corners, material)


def adjoining_corner(bounds, material) -> None:
    _, x1, y0, y1, z0, _ = bounds
    wall_x = x1 + 0.01
    wall_end_z = z0 - 0.85
    return_x = wall_x + 0.12
    make_face(
        "authored_wall_texture_return",
        [(wall_x, y0, wall_end_z), (wall_x, y1, wall_end_z),
         (wall_x, y1, z0), (wall_x, y0, z0)],
        material,
    )
    make_face(
        "authored_corner_right_angle_endcap",
        [(wall_x, y0, wall_end_z), (return_x, y0, wall_end_z),
         (return_x, y1, wall_end_z), (wall_x, y1, wall_end_z)],
        material,
    )


def add_review_camera() -> None:
    camera = bpy.data.objects.new("review_camera_frame_0152_anchor", bpy.data.cameras.new("ReviewCamera"))
    bpy.context.scene.collection.objects.link(camera)
    camera.location = bevy_to_blender((2.920978333, -0.084976566, 3.703507945))
    target = Vector(bevy_to_blender((COLUMN_CENTER_XZ[0], FLOOR_Y + COLUMN_HEIGHT * 0.5, COLUMN_CENTER_XZ[1])))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 38.0
    bpy.context.scene.camera = camera


def create_materials(crop_paths):
    return {
        "column": make_material("source_frame_0152_column_face", (0.73, 0.68, 0.47), crop_paths["column_face"]),
        "wall": make_material("source_frame_0152_wallpaper", (0.72, 0.70, 0.48), crop_paths["wallpaper_panel"]),
        "flat": make_material("authored_psx_flat_fill", (0.75, 0.70, 0.53)),
    }


def column_bounds() -> tuple[float, float, float, float, float, float]:
    half_x = COLUMN_WIDTH_X * 0.5 + SURFACE_OFFSET
    half_z = COLUMN_WIDTH_Z * 0.5 + SURFACE_OFFSET
    return (
        COLUMN_CENTER_XZ[0] - half_x,
        COLUMN_CENTER_XZ[0] + half_x,
        FLOOR_Y - SURFACE_OFFSET,
        FLOOR_Y + COLUMN_HEIGHT + SURFACE_OFFSET,
        COLUMN_CENTER_XZ[1] - half_z,
        COLUMN_CENTER_XZ[1] + half_z,
    )


def export_assets() -> None:
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.select_set(True)
    mesh_objects = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
    if not mesh_objects:
        raise SystemExit("no visual meshes are selected for GLB export")
    bpy.context.view_layer.objects.active = mesh_objects[0]
    bpy.ops.export_scene.gltf(
        filepath=str(GLB_PATH),
        export_format="GLB",
        export_yup=True,
        export_apply=True,
        export_materials="EXPORT",
        use_selection=True,
    )


def write_authoring_manifest(source: dict) -> None:
    report = {
        "schema_version": 1,
        "issue": 153,
        "tool": "Blender 5.2.2 LTS",
        "tool_license": "Blender GPL-3.0-or-later; no third-party add-on used",
        "authoring_method": "native editable quad meshes, UV maps, and Principled materials",
        "visual_only": True,
        "calibration": {"registration_accepted": False, "scale_calibrated": False},
        "coordinate_convention": "Bevy world (x,y,z) maps to Blender (x,-z,y); GLB Y-up export returns it to Bevy coordinates",
        "authored_proposal": "one source-textured east-facing column face and a narrow wallpaper L-return; not inferred architecture",
        "blender_project_path": BLEND_PATH.relative_to(ROOT).as_posix(),
        "blender_project_sha256": sha256(BLEND_PATH),
        "visual_glb_path": GLB_PATH.relative_to(ROOT).as_posix(),
        "visual_glb_sha256": sha256(GLB_PATH),
        "source_crops": source["crops"],
        "export_settings": {
            "format": "GLB 2.0",
            "export_yup": True,
            "apply_modifiers": True,
            "selected_objects_only": True,
            "collision_exported": False,
        },
    }
    (GENERATED_DIR / "authoring_manifest.json").write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    source = json.loads((SOURCE_DIR / "crop_manifest.json").read_text())
    crop_paths = {record["id"]: ROOT / record["output_path"] for record in source["crops"]}
    if any(not path.is_file() for path in crop_paths.values()):
        raise SystemExit("run extract_source_crops.py before building the Blender repair")
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    materials = create_materials(crop_paths)
    bounds = column_bounds()
    column_faces(bounds, materials)
    adjoining_corner(bounds, materials["wall"])
    add_review_camera()
    export_assets()
    write_authoring_manifest(source)


if __name__ == "__main__":
    main()
