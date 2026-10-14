"""Add a finite supported private entry courtyard to the existing native map.

Run in the sole real editor while gameplay is stopped. The exact existing
landing and panorama must be measured first. No original actor is changed.
This is a small physical courtyard, not a reconstructed Tokyo street.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unreal_import_reference_dressing import fingerprint

LEVEL = '/Game/Sub01Home/ActualHome'
PREFIX = 'SUB01_PrivateEntry_'
SOURCE_SHA = '9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'


def world_bounds(u, component):
    lo, hi = component.get_local_bounds()
    t = component.get_world_transform()
    points = [t.transform_location(u.Vector(x, y, z))
              for x in (lo.x, hi.x) for y in (lo.y, hi.y)
              for z in (lo.z, hi.z)]
    return {'min': [min(getattr(p, k) for p in points) for k in ('x', 'y', 'z')],
            'max': [max(getattr(p, k) for p in points) for k in ('x', 'y', 'z')]}


def matches_landing(b):
    expected = {'min': [75, 400, 2.5], 'max': [325, 580, 2.5]}
    return all(abs(b[key][i] - expected[key][i]) < .02
               for key in expected for i in range(3))


def run():
    import unreal as u

    root = Path(u.Paths.project_dir())
    source = root / 'SourceAssets/full-home.glb'
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA:
        raise RuntimeError('Actual home source changed; remeasure before extending')
    level = u.get_editor_subsystem(u.LevelEditorSubsystem)
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    if not level or not actors or not level.load_level(LEVEL):
        raise RuntimeError('A real initialized editor and existing map are required')
    original = list(actors.get_all_level_actors())
    if any(a.get_actor_label().startswith(PREFIX) for a in original):
        raise RuntimeError('Private courtyard already exists; do not duplicate it')
    before = fingerprint(u, original)
    backgrounds = [a for a in original
                   if a.get_actor_label() == 'SUB01_ActualHistoricalTokyoBackground']
    if len(backgrounds) != 1:
        raise RuntimeError('Actual existing panorama is missing or ambiguous')
    background = backgrounds[0]
    bg_meshes = background.get_components_by_class(u.StaticMeshComponent)
    if len(bg_meshes) != 1 or bg_meshes[0].get_collision_enabled() != u.CollisionEnabled.NO_COLLISION:
        raise RuntimeError('Existing panorama collision differs from the measured scene')
    landing = []
    for actor in original:
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            if component.get_editor_property('static_mesh'):
                bounds = world_bounds(u, component)
                if matches_landing(bounds):
                    landing.append((actor, component, bounds))
    if len(landing) != 1:
        raise RuntimeError('Exact original supported landing is missing or ambiguous')
    actor, component, measured = landing[0]
    material = component.get_material(0)
    if not material or component.get_collision_enabled() == u.CollisionEnabled.NO_COLLISION:
        raise RuntimeError('Actual landing material and physical collision are required')
    cube = u.load_asset('/Engine/BasicShapes/Cube.Cube')
    if not isinstance(cube, u.StaticMesh):
        raise RuntimeError('Actual engine cube mesh unavailable')
    cube_box = cube.get_bounding_box()
    base = [getattr(cube_box.max, k) - getattr(cube_box.min, k) for k in ('x', 'y', 'z')]
    if any(v <= 0 for v in base) or any(abs(getattr(cube_box.min, k) + getattr(cube_box.max, k)) > .001 for k in ('x', 'y', 'z')):
        raise RuntimeError('Actual cube dimensions/origin differ; no assumed substitute')
    # Join the existing finish at 580 cm. Canonical outside target (200,725)
    # stays within the finite courtyard; three 110 cm walls bound its edges.
    rows = [('Support', [200, 725, 0], [250, 290, 5]),
            ('LeftWall', [77.5, 725, 57.5], [5, 290, 110]),
            ('RightWall', [322.5, 725, 57.5], [5, 290, 110]),
            ('FarWall', [200, 867.5, 57.5], [250, 5, 110])]
    created = []
    for name, center, dimensions in rows:
        added = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector(*center))
        added.set_actor_label(PREFIX + name)
        added.set_editor_property('tags', [u.Name('SUB01PrivateEntry')])
        mesh = added.get_component_by_class(u.StaticMeshComponent)
        mesh.set_static_mesh(cube)
        mesh.set_material(0, material)
        mesh.set_collision_profile_name('BlockAll')
        mesh.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
        added.set_actor_enable_collision(True)
        added.set_actor_scale3d(u.Vector(*[dimensions[i] / base[i] for i in range(3)]))
        actual = world_bounds(u, mesh)
        expected = {'min': [center[i] - dimensions[i] / 2 for i in range(3)],
                    'max': [center[i] + dimensions[i] / 2 for i in range(3)]}
        if any(abs(actual[key][i] - expected[key][i]) > .001
               for key in expected for i in range(3)):
            raise RuntimeError('Actual new support dimensions differ; existing map not saved')
        created.append({'actor': added.get_path_name(), 'label': added.get_actor_label(),
                        'bounds_cm': actual, 'collision': str(mesh.get_collision_enabled()),
                        'material': material.get_path_name()})
    if fingerprint(u, original) != before:
        raise RuntimeError('An original actor changed; existing map not saved')
    if not level.save_current_level():
        raise RuntimeError('Physical private courtyard could not save')
    report = {'schema': 'sub01.private-entry-extension.v1',
              'source_sha256': SOURCE_SHA, 'original_actors_unchanged': len(original),
              'landing': {'actor': actor.get_path_name(), 'component': component.get_path_name(), 'bounds_cm': measured},
              'background': {'actor': background.get_path_name(), 'bounds_cm': world_bounds(u, bg_meshes[0]), 'collision': False},
              'created': created, 'canonical_outside_floor_cm': [200, 725, 2.5],
              'real_walk_verified': False, 'scope': 'Finite enclosed entry courtyard, not a navigable Tokyo city'}
    (root / 'private-entry-extension.json').write_text(json.dumps(report, indent=2) + '\n')
    u.log('SUB01_PRIVATE_ENTRY_SAVED ' + json.dumps({'created': len(created), 'originals': len(original)}))
    return report


if __name__ == '__main__':
    try:
        run()
    finally:
        import unreal
        unreal.SystemLibrary.quit_editor()
