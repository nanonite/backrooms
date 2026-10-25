"""Exercise installed public Blender operators; never copy addon implementation."""
import hashlib
import json
from pathlib import Path
import sys

import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parents[1]
ADDON = Path('/home/goya/.config/blender/5.0/scripts/addons/PSX tools')
SOURCE = ROOT / 'assets/psx_extension/textures/column_face_frame_0152.png'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_fixture():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add(size=2)
    fixture = bpy.context.object
    fixture.name = 'IsolatedSourceTexturedBox'
    fixture.scale = (0.36, 0.75, 1.2)
    material = bpy.data.materials.new('CopiedSourceFace')
    material.use_nodes = True
    image = material.node_tree.nodes.new('ShaderNodeTexImage')
    image.image = bpy.data.images.load(str(SOURCE))
    image.interpolation = 'Closest'
    material.node_tree.links.new(image.outputs['Color'],
                                material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
    fixture.data.materials.append(material)
    return fixture


def operator_call(name, results):
    try:
        result = getattr(bpy.ops.object, name)()
        results[name] = {'result': sorted(result)}
    except Exception as error:
        results[name] = {'error': str(error)}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'blender': bpy.app.version_string, 'addon_version': '1.6.1',
              'profile': bpy.utils.user_resource('CONFIG'),
              'enabled_before': list(bpy.context.preferences.addons.keys()),
              'registration_accepted': False, 'scale_calibrated': False,
              'source_sha256_before': digest(SOURCE), 'operations': {}}
    sys.path.insert(0, str(ADDON.parent))
    addon_utils.enable(ADDON.name, default_set=False, persistent=False)
    fixture = prepare_fixture()
    settings = {}
    for name in ['psx_texture_size', 'psx_palette_size', 'psx_dither_method']:
        prop = bpy.context.scene.bl_rna.properties.get(name)
        settings[name] = {'value': str(getattr(bpy.context.scene, name)),
                          'choices': [item.identifier for item in prop.enum_items]
                          if prop.type == 'ENUM' else []}
    report['settings'] = settings
    operator_call('psx_triangulate', report['operations'])
    operator_call('psx_texture_bake', report['operations'])
    operator_call('psx_texture_dither', report['operations'])
    report['mesh'] = {'vertices': len(fixture.data.vertices),
                      'polygons': len(fixture.data.polygons),
                      'uv_layers': len(fixture.data.uv_layers)}
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / 'fixture.blend'))
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT / 'fixture.glb'),
                              export_format='GLB', use_selection=True,
                              export_apply=True)
    report['source_sha256_after'] = digest(SOURCE)
    report['addon_files'] = {path.name: digest(path) for path in ADDON.iterdir()
                             if path.is_file()}
    (OUTPUT / 'blender_report.json').write_text(json.dumps(report, indent=2) + '\n')


main()
