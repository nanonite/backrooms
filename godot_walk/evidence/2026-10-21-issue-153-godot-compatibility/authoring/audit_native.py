"""Record installed-tool and native-pipeline provenance without addon source reuse."""
import hashlib
import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1]
PROJECT = Path(__file__).resolve().parents[3]
WORKSPACE = PROJECT.parent
ADDON = Path('/home/goya/.config/blender/5.0/scripts/addons/PSX tools')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    prior = json.loads((PROJECT / 'evidence/2026-10-21-issue-151-column-box/verification.json').read_text())
    protected = []
    for entry in prior['protected_hashes']:
        path = WORKSPACE / entry['path']
        actual = digest(path)
        protected.append({'path': entry['path'], 'sha256': actual,
                          'matches_prior': actual == entry['sha256']})
    native = ['scripts/psx/psx_post_effect.gd',
              'scripts/psx/shaders/psx_post.glsl',
              'scripts/hunyuan_psx_column_box.gd',
              'scripts/hunyuan_psx_round1.gd',
              'scripts/hunyuan_psx_round3.gd']
    report = {'issue': 153, 'active_runtime': 'Godot', 'bevy_status': 'deferred',
              'addon_version': '1.6.1', 'addon_install_directory': str(ADDON),
              'addon_license': str(ADDON / 'LICENSE.txt'),
              'addon_sha256': {path.name: digest(path) for path in ADDON.iterdir()
                               if path.is_file()},
              'native_sha256': {name: digest(PROJECT / name) for name in native},
              'protected_hashes': protected, 'registration_accepted': False,
              'scale_calibrated': False,
              'blender_smoke': {'exit_code': 139, 'operation': 'psx_texture_bake',
                                'assets_exported': False,
                                'limitation': 'Background popup_menu crash; not an interactive compatibility verdict'},
              'godot_column_regression': 'PASS',
              'readiness': {'first_room_column': 'operator_accepted',
                            'first_room_whole_psx_review': 'pending',
                            'second_independent_godot_room': 'pending',
                            'both_rooms_psx_review': 'pending',
                            'connector_validation': 'pending'}}
    (OUTPUT / 'provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    if not all(entry['matches_prior'] for entry in protected):
        raise RuntimeError('Protected fixture mismatch; inspect provenance.json')
    print(f'Protected hashes verified: {len(protected)}')


main()
