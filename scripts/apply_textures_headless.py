import os

import bpy

WORKSPACE = '/home/user/backrooms-workspace'
BLEND = WORKSPACE + '/backrooms_infinite/assets/scenes/source/corridor_corner_box.blend'
TEX = WORKSPACE + '/backrooms_infinite/assets/textures'
OUT = WORKSPACE + '/backrooms_infinite/assets/scenes/corridor_corner.glb'
LOG = WORKSPACE + '/backrooms_infinite/assets/scenes/source/apply_textures.log'

MATERIAL_MAP = {
    'Floor': 'corner_floor.png',
    'Ceiling': 'corner_ceiling.png',
    'Wall_North': 'corner_front.png',
    'Wall_South': 'corner_front.png',
    'Wall_West': 'corner_side.png',
}


def append_log(handle, line):
    handle.write(line + '\n')
    handle.flush()


def fail(handle, message, code=1):
    append_log(handle, message)
    raise SystemExit(code)


def build_material_for_texture(material_name, texture_path):
    material = bpy.data.materials.new(name=material_name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    texture_node = nodes.new(type='ShaderNodeTexImage')
    bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')
    output_node = nodes.new(type='ShaderNodeOutputMaterial')

    texture_node.image = bpy.data.images.load(texture_path, check_existing=True)

    links.new(texture_node.outputs['Color'], bsdf_node.inputs['Base Color'])
    links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

    return material


def main():
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, 'w', encoding='utf-8') as log_handle:
        append_log(log_handle, 'START')

        if not os.path.exists(BLEND):
            fail(log_handle, f'FATAL: Missing blend file: {BLEND}')

        bpy.ops.wm.open_mainfile(filepath=BLEND)

        for object_name, texture_name in MATERIAL_MAP.items():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                fail(log_handle, f'ERROR: Missing object: {object_name}')

            texture_path = os.path.join(TEX, texture_name)
            if not os.path.exists(texture_path):
                fail(log_handle, f'ERROR: Missing texture: {texture_path}')

            material = build_material_for_texture(f'Mat_{object_name}', texture_path)

            if obj.data.materials:
                obj.data.materials[0] = material
            else:
                obj.data.materials.append(material)

            append_log(log_handle, f'OK: {object_name} -> {texture_name}')

        bpy.ops.export_scene.gltf(
            filepath=OUT,
            export_format='GLB',
            export_yup=True,
            export_texcoords=True,
            export_normals=True,
            export_materials='EXPORT',
            export_image_format='AUTO',
        )

        if not os.path.exists(OUT):
            fail(log_handle, f'FATAL: Export missing output: {OUT}')

        glb_size = os.path.getsize(OUT)
        append_log(log_handle, f'GLB size: {glb_size} bytes')
        if glb_size < 500000:
            fail(log_handle, f'FATAL: GLB size below threshold: {glb_size} bytes')

        append_log(log_handle, 'PASS')


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, 'a', encoding='utf-8') as log_handle:
            append_log(log_handle, f'FATAL: {exc}')
        raise
