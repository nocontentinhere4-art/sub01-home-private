"""Stage an actual private home scene for the official Unreal Editor on the GPU server.

Only file copies/hashes occur here; this never launches an engine or a paid pod.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ['haven-sofa/sofa.glb', 'coffee-table-original/coffee-table.glb',
          'kitchen-cabinet-original/cabinet.glb', 'office-desk-original/desk.glb',
          'office-shelves-original/shelves.glb', 'cc0-queen-bed/queen-bed.glb',
          'cc0-porta-espresso/porta-espresso.glb']

def stage(source, expected_sha, output):
    source, output = Path(source), Path(output)
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != expected_sha:
        raise ValueError('Actual exported scene SHA does not match reviewed input')
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'SourceAssets'
    target.mkdir(exist_ok=True)
    shutil.copy2(source, target / 'full-home.glb')
    entries = [{'role': 'full_scene', 'file': 'SourceAssets/full-home.glb', 'sha256': actual}]
    for asset in ASSETS:
        original = ROOT / 'web/house/assets' / asset
        name = asset.replace('/', '-')
        shutil.copy2(original, target / name)
        entries.append({'role': 'authoring_library_only', 'file': 'SourceAssets/' + name, 'sha256': hashlib.sha256(original.read_bytes()).hexdigest()})
    (output / 'Config').mkdir(exist_ok=True)
    (output / 'Content/Python').mkdir(parents=True, exist_ok=True)
    (output / 'Sub01HomeLab.uproject').write_text(json.dumps({'FileVersion': 3, 'EngineAssociation': '5.8',
        'Description': 'Private actual SUB-01 home authoring; scene import is not a live brain/device integration',
        'Plugins': [{'Name': name, 'Enabled': True} for name in ['PythonScriptPlugin', 'EditorScriptingUtilities', 'Interchange', 'MovieRenderPipeline']]}, indent=2) + '\n')
    (output / 'Config/DefaultEngine.ini').write_text('''[/Script/Engine.RendererSettings]
r.DynamicGlobalIlluminationMethod=1
r.ReflectionMethod=1
r.GenerateMeshDistanceFields=True
r.Shadow.Virtual.Enable=1

[/Script/EngineSettings.GameMapsSettings]
EditorStartupMap=/Game/Sub01Home/ActualHome
GameDefaultMap=/Game/Sub01Home/ActualHome
''')
    shutil.copy2(ROOT / 'tools/unreal_import_home.py', output / 'Content/Python/import_home.py')
    manifest = {'engine_version': '5.8.3', 'private_only': True, 'assets': entries,
                'scope': 'Full imported source scene, plus non-spawned furniture authoring library. No public endpoint, brain/device emulator or game behavior is silently replaced.'}
    (output / 'home-inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    result = stage(args.source, args.source_sha, args.output)
    print(json.dumps({'staged': str(args.output), 'assets': len(result['assets']), 'source_sha256': result['assets'][0]['sha256']}))
