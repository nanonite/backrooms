import bpy
import os

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

ROOM_W = 6.0
ROOM_D = 6.0
ROOM_H = 3.0
WALL_T = 0.2
DOOR_W = 1.2
DOOR_H = 2.2

def make_box(name, location, dimensions, color):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    mat = bpy.data.materials.new(name=name + "_mat")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs[0].default_value = color
    if len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat
    return obj

# Floor: at Z=-WALL_T/2, spans whole room
make_box("Floor", (0, 0, -WALL_T/2), (ROOM_W, ROOM_D, WALL_T), (0.35, 0.35, 0.35, 1.0))

hw = ROOM_W / 2  # half width
hd = ROOM_D / 2  # half depth
hh = ROOM_H / 2  # half height

# North wall: at -Y edge
make_box("Wall_North", (0, -hd + WALL_T/2, hh), (ROOM_W, WALL_T, ROOM_H), (0.82, 0.35, 0.22, 1.0))

# South wall: at +Y edge
make_box("Wall_South", (0, hd - WALL_T/2, hh), (ROOM_W, WALL_T, ROOM_H), (0.22, 0.62, 0.35, 1.0))

# East wall: at +X edge
make_box("Wall_East", (hw - WALL_T/2, 0, hh), (WALL_T, ROOM_D, ROOM_H), (0.30, 0.35, 0.78, 1.0))

# West wall (-X edge) with doorway — three pieces: left, right, top

left_depth = hd - DOOR_W/2
left_y = -DOOR_W/2 - left_depth/2
make_box("Wall_West_Left", (-hw + WALL_T/2, left_y, hh), (WALL_T, left_depth, ROOM_H), (0.72, 0.68, 0.25, 1.0))

right_depth = hd - DOOR_W/2
right_y = DOOR_W/2 + right_depth/2
make_box("Wall_West_Right", (-hw + WALL_T/2, right_y, hh), (WALL_T, right_depth, ROOM_H), (0.72, 0.68, 0.25, 1.0))

top_height = ROOM_H - DOOR_H
top_z = DOOR_H + top_height/2
make_box("Wall_West_Top", (-hw + WALL_T/2, 0, top_z), (WALL_T, DOOR_W, top_height), (0.72, 0.68, 0.25, 1.0))

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

output_dir = os.path.dirname(bpy.data.filepath) or os.getcwd()
output_path = os.path.abspath(os.path.join(output_dir, "test_room.glb"))
bpy.ops.export_scene.gltf(
    filepath=output_path,
    export_format='GLB',
    export_apply=False,
    export_texcoords=True,
    export_normals=True,
    export_materials='EXPORT',
    use_selection=False,
)
print(f"Exported to: {output_path}")
