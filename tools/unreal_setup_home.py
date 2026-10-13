"""Actual UE editor setup after import: verified coordinates, collision and first-person map.

Execute on the GPU server only. Native runtime module must be compiled first.
Backend interactions are explicitly unconnected markers until real wiring exists.
"""
import json
import re
import sys
from pathlib import Path
import unreal as u
sys.path.insert(0,str(Path(__file__).parent))
from unreal_home_coordinates import infer_import_transform,convert_position

ROOT=Path(u.Paths.project_dir()).resolve()
level=u.get_editor_subsystem(u.LevelEditorSubsystem)
actors=u.get_editor_subsystem(u.EditorActorSubsystem)
if not level.load_level('/Game/Sub01Home/ActualHome'):
    raise RuntimeError('Actual imported home map is missing')
raw=(ROOT/'SourceAssets/full-home.glb').read_bytes()
doc=json.loads(raw[20:20+int.from_bytes(raw[12:16],'little')])
identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
parents={child:index for index,node in enumerate(doc['nodes'])for child in node.get('children',[])}
def multiply(a,b):return[sum(a[k*4+row]*b[col*4+k]for k in range(4))for col in range(4)for row in range(4)]
def local(node):
    if 'matrix'in node:return node['matrix']
    x,y,z,w=node.get('rotation',[0,0,0,1]);sx,sy,sz=node.get('scale',[1,1,1]);tx,ty,tz=node.get('translation',[0,0,0])
    return[(1-2*(y*y+z*z))*sx,2*(x*y+z*w)*sx,2*(x*z-y*w)*sx,0,
            2*(x*y-z*w)*sy,(1-2*(x*x+z*z))*sy,2*(y*z+x*w)*sy,0,
            2*(x*z+y*w)*sz,2*(y*z-x*w)*sz,(1-2*(x*x+y*y))*sz,0,tx,ty,tz,1]
world={}
def transform(index):
    if index not in world:world[index]=multiply(transform(parents[index])if index in parents else identity,local(doc['nodes'][index]))
    return world[index]
canonical=lambda name:re.sub('[^a-z0-9]','',name.lower())
source_pivots={canonical(node['name']):transform(i)[12:15]for i,node in enumerate(doc['nodes'])if node.get('name')and'mesh'in node}
components=[];pairs=[];matched=set()
for actor in actors.get_all_level_actors():
    for component in actor.get_components_by_class(u.StaticMeshComponent):
        if not component.get_editor_property('static_mesh'):continue
        components.append(component)
        for name in [component.get_name(),actor.get_actor_label()]:
            key=canonical(name)
            if key in source_pivots and key not in matched:
                loc=component.get_world_location();pairs.append((source_pivots[key],(loc.x,loc.y,loc.z)));matched.add(key);break
try:
    coordinates=infer_import_transform(pairs)
except ValueError as error:
    (ROOT/'coordinate-audit-failed.json').write_text(json.dumps({'error':str(error),'matched_pivots':len(pairs),'component_names':[c.get_name()for c in components[:80]],'actor_labels':[a.get_actor_label()for a in actors.get_all_level_actors()[:80]]},indent=2))
    raise
meshes=set();collision=[]
for component in components:
    mesh=component.get_editor_property('static_mesh')
    if mesh not in meshes:
        body=mesh.get_editor_property('body_setup')
        if body is None:raise RuntimeError('Imported real mesh has no BodySetup: '+mesh.get_path_name())
        body.set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        meshes.add(mesh)
    component.set_collision_profile_name('BlockAll')
    component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    component.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
    collision.append(component.get_name())
    name=(component.get_name()+' '+component.get_owner().get_actor_label()).lower()
    role=next((role for role,fragments in [('Desk',('office-desk','office_desk')),('Kitchen',('kitchen-cabinet','kitchen_cabinet')),('Bed',('queen-bed','queen_bed','bedframe')),('TV',('television',))]if any(fragment in name for fragment in fragments)),None)
    if role:
        tags=list(component.get_editor_property('component_tags'));tags.append(u.Name('SUB01Device:'+role));component.set_editor_property('component_tags',tags)
pos=lambda v:u.Vector(*convert_position(v,coordinates))
start=actors.spawn_actor_from_class(u.PlayerStart,pos((2,.94,3.1)),u.MathLibrary.find_look_at_rotation(pos((2,.94,3.1)),pos((2,.94,-2.8))))
start.set_actor_label('SUB01_GroundFloor_FirstPerson_Start')
game_mode=u.load_class(None,'/Script/Sub01HomeLab.Sub01HomeGameMode')
if not game_mode:raise RuntimeError('Native walking Character/GameMode is not compiled; refusing to substitute a flying spectator')
u.EditorLevelLibrary.get_editor_world().get_world_settings().set_editor_property('default_game_mode',game_mode)
camera=actors.spawn_actor_from_class(u.CineCameraActor,pos((2,1.65,3.1)),u.MathLibrary.find_look_at_rotation(pos((2,1.65,3.1)),pos((2,1.3,-2.8))))
camera.set_actor_label('SUB01_Real_FirstPerson_Render_Camera')
cc=camera.get_cine_camera_component();cc.set_editor_property('current_focal_length',24)
focus=cc.get_editor_property('focus_settings');focus.set_editor_property('focus_method',u.CameraFocusMethod.DISABLE);cc.set_editor_property('focus_settings',focus)
# No synthetic window fill cards. A real source HDR illuminates Lumen and
# reflections; original glTF practical lights retain their imported values.
hdr=ROOT/'SourceAssets/room-light.hdr'
if not hdr.is_file():raise RuntimeError('Real room-light HDR must accompany setup; no invented ambient fallback')
task=u.AssetImportTask();task.filename=str(hdr);task.destination_path='/Game/Sub01Home/Environment';task.automated=True;task.save=True;task.replace_existing=True
u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
cubes=[u.load_asset(path)for path in task.imported_object_paths];cube=next((asset for asset in cubes if isinstance(asset,u.TextureCube)),None)
if not cube:raise RuntimeError('Official HDR importer did not produce a real TextureCube')
sky=actors.spawn_actor_from_class(u.SkyLight,u.Vector(0,0,0));sky.set_actor_label('SUB01_ActualHDR_Sky')
sk=sky.get_component_by_class(u.SkyLightComponent);sk.set_editor_property('source_type',u.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP);sk.set_editor_property('cubemap',cube);sk.set_editor_property('source_cubemap_angle',-90);sk.set_intensity(.4225)
light_rows=[]
for actor in actors.get_all_level_actors():
    for light in actor.get_components_by_class(u.LightComponent):
        light_rows.append({'actor':actor.get_actor_label(),'class':light.get_class().get_name(),'intensity':light.get_editor_property('intensity')})
u.EditorAssetLibrary.save_directory('/Game/Sub01Home',only_if_is_dirty=False,recursive=True)
if not level.save_current_level():raise RuntimeError('First-person actual home map failed to save')
(ROOT/'unreal-home-setup.json').write_text(json.dumps({'coordinates':coordinates,'collision_components':len(collision),'collision_unique_meshes':len(meshes),'spawn_source_m':[2,.94,3.1],'eye_height_cm':165,'standing_capsule_height_cm':182,'camera':camera.get_path_name(),'lighting':light_rows,'backend_interactions':'Explicitly not connected. Native E reports this; no simulated device action.','scope':'Actual Unreal scene setup; native controls/collision still require server PIE acceptance and first real renders.'},indent=2))
u.log('SUB01_REAL_FIRSTPERSON_HOME_SETUP_READY')
