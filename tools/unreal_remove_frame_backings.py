"""Remove ONLY two generated backing boxes from shared darkwood batch165.

Exact retained600 triangles are imported first and bound to the unchanged
original Material5. Never hide the shared original without its proven remainder.
"""
import copy
import hashlib
import itertools
import json
import math
import shutil
import struct
import time
import uuid
from pathlib import Path
from prepare_frame_backing_remainder import read,elements,SOURCE_SHA
from unreal_import_reference_dressing import fingerprint
from unreal_component_collision_state import capture,restore

ROOT=Path('/workspace/sub01-home-private/frame-backing-removal-source')
SHA='62f2fb15e063b381ee627ee1acb7b9ac57bc34c7014bc44a74bc15940eabd0fb'
MATERIAL='/Game/Sub01Home/ImportedScene/full-home/Materials/Material_5.Material_5'
LABEL='SUB01_FrameBackingRemainder_165_600'


def native_triangles(u,c):
    result=[];mesh=c.get_editor_property('static_mesh');world=c.get_world_transform()
    for i in range(mesh.get_num_sections(0)):
        vertices,indices,*_=u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,0,i)
        points=[world.transform_location(v)for v in vertices]
        for k in range(0,len(indices),3):result.append([[float(getattr(points[j],a))for a in ('x','y','z')]for j in indices[k:k+3]])
    return result


def same_triangles(expected,actual,tolerance=.001,deadline_monotonic=None):
    """Nearest complete triangle, including all positive source faces; no pruning."""
    import time
    def check_deadline():
        if deadline_monotonic is not None and time.monotonic()>=deadline_monotonic:raise TimeoutError('Complete triangle proof exceeded explicit budget; no partial acceptance')
    if deadline_monotonic is not None and not math.isfinite(deadline_monotonic):raise ValueError('Finite absolute proof deadline required')
    check_deadline()
    if len(expected)!=len(actual):return False
    if not math.isfinite(tolerance)or tolerance<=0:raise ValueError('Positive finite triangle tolerance required')
    # Complete corner agreement within tolerance implies centroid agreement
    # within that same tolerance (triangle inequality). Two-tolerance cells
    # therefore retain every possible match in the same 27 adjacent buckets,
    # while avoiding quadratic scans for dense submillimeter furniture meshes.
    cell=2*tolerance
    def key(t):return tuple(math.floor(sum(p[a]for p in t)/(3*cell))for a in range(3))
    buckets={}
    for i,t in enumerate(actual):
        if i%256==0:check_deadline()
        buckets.setdefault(key(t),set()).add(i)
    for triangle_index,triangle in enumerate(expected):
        if triangle_index%128==0:check_deadline()
        center=key(triangle);choices=[]
        for offset in itertools.product((-1,0,1),repeat=3):
            bucket=buckets.get(tuple(a+b for a,b in zip(center,offset)),set())
            for candidate_index,i in enumerate(bucket):
                if candidate_index%128==0:check_deadline()
                error=min(max(math.dist(a,b)for a,b in zip(triangle,order))for order in itertools.permutations(actual[i]))
                if error<=tolerance:choices.append((error,i,bucket))
        if not choices:return False
        _,i,bucket=min(choices,key=lambda row:(row[0],row[1]));bucket.remove(i)
    return True


def run():
    import unreal as u
    project=Path(u.Paths.project_dir());source=ROOT/'remainder.glb';raw=source.read_bytes();proof=json.loads(source.with_suffix('.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=SHA or proof.get('source_sha256')!=SOURCE_SHA or proof.get('output_sha256')!=SHA or proof.get('preserved_triangles')!=list(range(600,1200)) or not proof.get('exact_retained_corner_attribute_bytes'):raise RuntimeError('Exact two-backing-only byte preservation proof required')
    if hashlib.sha256((project/'SourceAssets/full-home.glb').read_bytes()).hexdigest()!=SOURCE_SHA:raise RuntimeError('Original955 source changed')
    eas=u.get_editor_subsystem(u.EditorActorSubsystem);original=list(eas.get_all_level_actors());before=fingerprint(u,original)
    matches=[a for a in original if a.get_name()=='full-home_node_165']
    if len(matches)!=1:raise RuntimeError('Exact shared source165 actor required')
    old=matches[0];components=old.get_components_by_class(u.StaticMeshComponent)
    if len(components)!=1:raise RuntimeError('Shared source165 component identity differs')
    c=components[0];mesh=c.get_editor_property('static_mesh');material=c.get_material(0)
    if c.get_name()!='StaticMeshComponent0' or not mesh or mesh.get_path_name()!='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_124.Mesh_124' or c.get_num_materials()!=1 or not material or material.get_path_name()!=MATERIAL:raise RuntimeError('Exact source165 Mesh124/Material5 binding required')
    if any(a.get_actor_label()==LABEL for a in original):raise RuntimeError('Owned remainder already present; do not duplicate')
    hidden={a.get_path_name():bool(a.get_editor_property('hidden'))for a in original}
    if hidden[old.get_path_name()] or not c.get_editor_property('visible'):raise RuntimeError('Unexpected pre-hidden shared source165; no assumptions')
    collision=capture(u,c)
    backup=project/'Saved/PrivateMapBackups'/('frame-backings-'+str(time.time_ns()));backup.mkdir(parents=True)
    shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
    for name in ('__ExternalActors__','__ExternalObjects__'):
        directory=project/'Content'/name/'Sub01Home/ActualHome'
        if directory.exists():shutil.copytree(directory,backup/name)
    dest='/Game/Sub01Home/FrameBackingRemoval/V_'+SHA[:12]+'/Attempt_'+uuid.uuid4().hex
    new=None;component=None
    try:
        task=u.AssetImportTask();task.filename=str(source);task.destination_path=dest;task.automated=True;task.replace_existing=False;task.save=False
        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        meshes=[m for m in (u.EditorAssetLibrary.load_asset(p)for p in u.EditorAssetLibrary.list_assets(dest,recursive=True,include_folder=False))if isinstance(m,u.StaticMesh)]
        if len(meshes)!=1 or not meshes[0].get_path_name().startswith(dest+'/'):raise RuntimeError('Expected one owned darkwood remainder mesh')
        replacement=meshes[0];sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);settings=sub.get_nanite_settings(replacement)
        for key,value in (('enabled',False),('keep_percent_triangles',1.),('trim_relative_error',0.),('fallback_percent_triangles',1.),('fallback_relative_error',0.)):settings.set_editor_property(key,value)
        sub.set_nanite_settings(replacement,settings,True)
        body=replacement.get_editor_property('body_setup');body.set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        if not u.EditorAssetLibrary.save_loaded_asset(replacement,only_if_is_dirty=False):raise RuntimeError('Owned remainder mesh save failed')
        new=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));component=new.get_components_by_class(u.StaticMeshComponent)[0]
        component.set_static_mesh(replacement);component.set_material(0,material);new.set_actor_transform(c.get_world_transform(),False,True);new.set_actor_hidden_in_game(True)
        restore(u,component,collision,force_response_copy=True)
        doc,blob=read(raw);p=doc['meshes'][0]['primitives'][0];points,fmt=elements(doc,blob,p['attributes']['POSITION']);points=[struct.unpack(fmt,v)for v in points];indices,fmt=elements(doc,blob,p['indices']);indices=[struct.unpack(fmt,v)[0]for v in indices]
        expected=[[[points[j][0]*100,points[j][2]*100,points[j][1]*100]for j in indices[i:i+3]]for i in range(0,len(indices),3)]
        actual=native_triangles(u,component)
        if not same_triangles(expected,actual):raise RuntimeError('Actual remainder600 world triangles differ source; shared165 stays visible')
        if fingerprint(u,original)!=before or hidden!={a.get_path_name():bool(a.get_editor_property('hidden'))for a in original}:raise RuntimeError('Import changed protected originals before activation')
        old.set_actor_hidden_in_game(True);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        new.set_actor_label(LABEL);new.set_actor_hidden_in_game(False)
        allowed=copy.deepcopy(before);allowed[old.get_path_name()]['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION)
        if fingerprint(u,original)!=allowed or component.get_material(0)!=material or len(actual)!=600:raise RuntimeError('Retirement changed protected originals/material binding')
        after_hidden=dict(hidden);after_hidden[old.get_path_name()]=True
        if after_hidden!={a.get_path_name():bool(a.get_editor_property('hidden'))for a in original}:raise RuntimeError('Retirement hid an unrelated actor')
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Exact two-backing retirement map save failed')
        result={'schema':'sub01.generated-frame-backings-retired.v1','source_proof':proof,'original_shared_actor':old.get_path_name(),
                'remainder_actor':new.get_path_name(),'remainder_mesh':replacement.get_path_name(),'preserved_native_triangles':600,
                'original_material':MATERIAL,'removed_only_source_triangles':list(range(600)),'protected_original_fingerprints_equal':True,
                'backup':str(backup),'original_state_before':before[old.get_path_name()],'original_hidden_before':hidden[old.get_path_name()],
                'original_component_visible_before':True,'native_visual_verified':False}
        audit=project/'private-audit';audit.mkdir(exist_ok=True);(audit/'frame-backings-retired.json').write_text(json.dumps(result,indent=2)+'\n')
        return result
    except Exception:
        if component:component.set_static_mesh(None)
        if new:eas.destroy_actor(new)
        if bool(old.get_editor_property('hidden'))!=hidden[old.get_path_name()]:old.set_actor_hidden_in_game(hidden[old.get_path_name()])
        restore(u,c,collision)
        if fingerprint(u,original)!=before:raise RuntimeError('Frame retirement rollback differs; saved map backup retained')
        u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
        raise
