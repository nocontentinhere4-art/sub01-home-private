"""Install the real house's licensed static Tokyo panorama into the current UE map.

GPU editor only, AFTER collision setup. Copy existing residential-4096.webp as
SourceAssets/TokyoResidential.png (lossless format conversion), together with
its existing tokyo-residential/manifest.json attribution. No generated imagery.
Never changes the HDR SkyLight or other actors. Not a 3D/live Tokyo world.
"""
import hashlib
import json
from pathlib import Path
import unreal as u

ROOT = Path(u.Paths.project_dir()).resolve()
SOURCE = ROOT / 'SourceAssets/TokyoResidential.png'
DESTINATION = '/Game/Sub01Home/Environment'
LABEL = 'SUB01_ActualHistoricalTokyoBackground'
TAG = 'SUB01VisualBackground'
if not SOURCE.is_file():
    raise RuntimeError('Actual licensed Tokyo panorama PNG must be copied, no substitute')
actors = u.get_editor_subsystem(u.EditorActorSubsystem)
level = u.get_editor_subsystem(u.LevelEditorSubsystem)
task = u.AssetImportTask()
task.filename = str(SOURCE)
task.destination_path = DESTINATION
task.automated = True
task.save = True
task.replace_existing = True
u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
texture = next((u.load_asset(path) for path in task.imported_object_paths
                if isinstance(u.load_asset(path), u.Texture2D)), None)
if texture is None:
    raise RuntimeError('Official PNG importer failed to create panorama Texture2D')
texture.set_editor_property('srgb', True)
material_path = DESTINATION + '/M_Sub01ActualTokyoBackground'
material = u.load_asset(material_path)
if material is None:
    material = u.AssetToolsHelpers.get_asset_tools().create_asset(
        'M_Sub01ActualTokyoBackground', DESTINATION, u.Material, u.MaterialFactoryNew())
if not isinstance(material, u.Material):
    raise RuntimeError('Owned exterior material path contains a different asset type')
material.set_editor_property('two_sided', True)
material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_UNLIT)
u.MaterialEditingLibrary.delete_all_material_expressions(material)
sample = u.MaterialEditingLibrary.create_material_expression(
    material, u.MaterialExpressionTextureSample, -250, 0)
sample.set_editor_property('texture', texture)
sample.set_editor_property('sampler_type', u.MaterialSamplerType.SAMPLERTYPE_COLOR)
if not u.MaterialEditingLibrary.connect_material_property(
        sample, 'RGB', u.MaterialProperty.MP_EMISSIVE_COLOR):
    raise RuntimeError('Actual photo RGB could not connect to unlit exterior material')
u.MaterialEditingLibrary.recompile_material(material)

# Exact owned label only: do not delete user furniture, lights or other skies.
for actor in list(actors.get_all_level_actors()):
    if actor.get_actor_label() == LABEL:
        actors.destroy_actor(actor)
sphere = u.load_asset('/Engine/BasicShapes/Sphere.Sphere')
if not isinstance(sphere, u.StaticMesh):
    raise RuntimeError('Actual Engine BasicShapes sphere is unavailable')
actor = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector(0, 0, 165))
actor.set_actor_label(LABEL)
actor.set_editor_property('tags', [u.Name(TAG)])
component = actor.get_component_by_class(u.StaticMeshComponent)
component.set_static_mesh(sphere)
component.set_material(0, material)
component.set_collision_profile_name('NoCollision')
component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
actor.set_actor_enable_collision(False)
component.set_editor_property('cast_shadow', False)
component.set_editor_property('affect_dynamic_indirect_lighting', False)
component.set_editor_property('affect_distance_field_lighting', False)
component.set_editor_property('visible_in_ray_tracing', False)
# Engine sphere has 50 cm radius. Verify the real mesh instead of assuming it.
box = sphere.get_bounding_box()
native_radius = max(abs(box.min.x), abs(box.max.x), abs(box.min.y), abs(box.max.y))
if not 1 < native_radius < 1000:
    raise RuntimeError('Unexpected Engine sphere size')
radius_cm = 200000.0  # 2 km; comfortably inside UE perspective far range.
actor.set_actor_scale3d(u.Vector(*([radius_cm / native_radius] * 3)))
actor.set_actor_rotation(u.Rotator(0, -90, 0), False)
u.EditorAssetLibrary.save_loaded_asset(texture)
u.EditorAssetLibrary.save_loaded_asset(material)
if not level.save_current_level():
    raise RuntimeError('Actual map exterior could not save')
report = {'actor': actor.get_path_name(), 'tag': TAG, 'radius_m': radius_cm / 100,
          'source': str(SOURCE), 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
          'material': material_path, 'collision': False, 'casts_shadows': False,
          'changes_hdr_lighting': False, 'scope': 'Historical static licensed Tokyo photograph on background sphere; not reconstructed 3D city, live Tokyo, device UI or gameplay.'}
(ROOT / 'unreal-home-exterior.json').write_text(json.dumps(report, indent=2) + '\n')
u.log('SUB01_ACTUAL_HISTORICAL_TOKYO_BACKGROUND ' + json.dumps(report))
