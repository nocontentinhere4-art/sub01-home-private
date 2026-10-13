"""Run inside the real Unreal Editor: import the complete current home with transforms.

Official Interchange synchronous scene import is used, not a flattened manual
mesh placement. Separate source furniture assets remain in the authoring library
and are never spawned over furniture already present in the full house.
"""
import hashlib
import json
from pathlib import Path
import unreal as u

ROOT = Path(u.Paths.project_dir()).resolve()
manifest = json.loads((ROOT / 'home-inputs.json').read_text())
for entry in manifest['assets']:
    if hashlib.sha256((ROOT / entry['file']).read_bytes()).hexdigest() != entry['sha256']:
        raise RuntimeError('Unreal source changed: ' + entry['file'])
level = u.get_editor_subsystem(u.LevelEditorSubsystem)
actors = u.get_editor_subsystem(u.EditorActorSubsystem)
if not level.new_level('/Game/Sub01Home/ActualHome'):
    raise RuntimeError('Cannot create isolated actual-home level')
manager = u.InterchangeManager.get_interchange_manager_scripted()
params = u.ImportAssetParameters()
params.set_editor_property('is_automated', True)
source = manager.create_source_data(str(ROOT / manifest['assets'][0]['file']))
if not manager.can_translate_source_data(source, True):
    raise RuntimeError('Official glTF scene translator is unavailable in this engine build')
if not manager.import_scene('/Game/Sub01Home/ImportedScene', source, params):
    raise RuntimeError('Actual full-home scene import failed')
mesh_components = []
light_components = []
for actor in actors.get_all_level_actors():
    for component in actor.get_components_by_class(u.StaticMeshComponent):
        if component.get_editor_property('static_mesh'):
            mesh_components.append(component)
    for component in actor.get_components_by_class(u.LightComponent):
        light_components.append(component)
if not mesh_components:
    raise RuntimeError('Scene import returned no real placed mesh components')
library = []
for entry in manifest['assets'][1:]:
    data = manager.create_source_data(str(ROOT / entry['file']))
    destination = '/Game/Sub01Home/AuthoringLibrary/' + Path(entry['file']).stem.replace('-', '_')
    imported = manager.import_asset(destination, data, params)
    if not imported:
        raise RuntimeError('Furniture authoring import failed: ' + entry['file'])
    objects = (u.EditorAssetLibrary.list_assets(destination, recursive=True, include_folder=False)
               if isinstance(imported, bool) else [item.get_path_name() for item in imported])
    if not objects:
        raise RuntimeError('Furniture imported no saved assets: ' + entry['file'])
    library.append({'source': entry['file'], 'objects': list(objects)})
# Save a real editor map. Camera/brain/control/streaming integration must be
# verified subsequently in Unreal; do not declare a static imported map alive.
u.EditorAssetLibrary.save_directory('/Game/Sub01Home', only_if_is_dirty=False, recursive=True)
if not level.save_current_level():
    raise RuntimeError('Imported actual-home level did not save')
report = {'engine': u.SystemLibrary.get_engine_version(), 'source_sha256': manifest['assets'][0]['sha256'],
          'level': '/Game/Sub01Home/ActualHome', 'placed_mesh_components': len(mesh_components),
          'placed_light_components': len(light_components), 'authoring_library': library,
          'scope': 'Real Unreal scene import and saved map, preserving imported scene transforms. Not yet validated rendering, physical collision, dynamic furniture or live brain/devices.'}
(ROOT / 'unreal-home-import.json').write_text(json.dumps(report, indent=2) + '\n')
u.log('SUB01_ACTUAL_HOME_IMPORTED ' + json.dumps(report))
