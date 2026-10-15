"""One fixed warm-Editor R5→measured lower-fit kitchen replacement transaction.

No actor/asset deletion, arbitrary namespace adoption, level load, provider or
runtime action. The exact previous152 parts are reversibly hidden/de-collided
and their40 old runtime tags retired, then the existing strict importer proves
all152 new parts/PBR before saving. Originals are exposed only inside this
transaction. Failure restores every original fingerprint and quarantines imports.
"""
import copy
import hashlib
import json
import shutil
from pathlib import Path
import time

ROOT=Path('/workspace/sub01-home-private/kitchen-lowerfit-source-20261015/output')
PREVIOUS=Path('/workspace/sub01-private-kitchen-3eb5419-20261015/proof-output-r2/uid1001/native-kitchen-import.json')
PREVIOUS_SHA='88be2838c81e79d40a5595ad5588f392b0a98f7208cd420d77a2778f2cf3c3c0'
OLD_EXPORT='c5b8f73361d819efced9ab1f7f567f6c9adb284126eebb7de3b03db33229eec5'
NEW_EXPORT='accd954c120a60f4eb68bd869fe2f1b578517880d71b82e673af5834c32fb79d'
NEW_PROOF_SHA='11acf200b869a6a6100c7b341ca1fe01c90ecace139d009f77e797f40ded63fd'
OLD_PREFIX='/Game/Sub01Home/RealKitchen/V_c5b8f73361d8_R5/'
OLD_ACTOR_PREFIX='/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.SUB01_RealKitchen_687d9c6d9bda_'


def validate_previous(raw):
    if hashlib.sha256(raw).hexdigest()!=PREVIOUS_SHA:raise ValueError('Exact authenticated saved R5 receipt required')
    row=json.loads(raw);parts=row.get('parts',[])
    if row.get('schema')!='sub01.real-kitchen-native-import.v1' or row.get('export_sha256')!=OLD_EXPORT or len(parts)!=152 or len({p.get('component')for p in parts})!=152 or len({p.get('part')for p in parts})!=152:raise ValueError('Exact complete R5 152-part receipt required')
    for p in parts:
        if not p.get('component','').startswith(OLD_ACTOR_PREFIX) or not p.get('mesh','').startswith(OLD_PREFIX) or p.get('surface_parity',{}).get('all_native_triangles_matched')is not True:raise ValueError('Exact proved R5 part namespace/surface required')
    if sorted(p['moving_hinge']for p in parts if p.get('moving_hinge')is not None)!=[i for i in range(8)for _ in range(5)]:raise ValueError('Exact40 previous moving parts required')
    return row


def retained_paths(receipt):
    rows=receipt.get('retained_sink_full_source_restore',[])
    if len(rows)!=1 or rows[0].get('node')!=164 or rows[0].get('source_triangles')!=2700 or rows[0].get('native_full_triangles')!=2700 or rows[0].get('owned_mesh')!='/Game/Sub01Home/RealKitchen/V_9556495fa816_RetainedSink164/Mesh.Mesh':raise ValueError('Exact already-proved retained source2700-triangle sink required')
    return {164:rows[0]['owned_mesh']}


def guard():
    from unreal_editor_task_queue import guard_valid
    p=Path('/run/sub01-home-private/runtime-window.json')
    if not guard_valid(p, now=time.time()+60):raise RuntimeError('Live trusted private budget window required')
    private=Path('/home/unreal/.sub01-private')
    if any((private/name).exists()for name in('native-viewer-capture-enabled','native-viewer-input-enabled')):raise RuntimeError('Both human viewer grants must be revoked before Editor replacement')
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            args=(proc/'cmdline').read_bytes().split(b'\0');state=(proc/'stat').read_text().rsplit(')',1)[1].split()[0]
            if state!='Z' and args and args[0]==b'/workspace/sub01-private-recovered-engine/Engine/Binaries/Linux/UnrealEditor-Cmd' and b'-game'in args:raise RuntimeError('Owned Game must be absent; Editor only')
        except OSError:pass


def resolve_parts(u, actors, receipt):
    from unreal_import_real_kitchen import surface,close
    found={c.get_path_name():(a,c)for a in actors for c in a.get_components_by_class(u.StaticMeshComponent)}
    rows=[];tags=[]
    for expected in receipt['parts']:
        pair=found.get(expected['component'])
        if pair is None:raise RuntimeError('Exact current R5 component missing')
        actor,c=pair;mesh=c.get_editor_property('static_mesh')
        if len(actor.get_components_by_class(u.StaticMeshComponent))!=1 or not mesh or mesh.get_path_name()!=expected['mesh'] or bool(actor.get_editor_property('hidden')) or not c.get_editor_property('visible') or c.get_collision_enabled()!=u.CollisionEnabled.QUERY_AND_PHYSICS:raise RuntimeError('Current saved R5 component binding/visibility/collision differs')
        points,count=surface(u,c);bounds=[[f(p[k]for p in points)for k in range(3)]for f in(min,max)]
        if count!=expected['triangles'] or not all(close(a,b,.02)for a,b in zip(bounds,expected['bounds_cm'])):raise RuntimeError('Current saved R5 closed geometry differs')
        actual=[str(t)for t in c.get_editor_property('component_tags')if str(t).startswith('SUB01Kitchen:')]
        wanted=[] if expected['moving_hinge']is None else [f"SUB01Kitchen:{OLD_EXPORT}:D{expected['moving_hinge']}:{expected['part'].rsplit('__',1)[-1]}"]
        if actual!=wanted:raise RuntimeError('Exact current R5 moving-tag identity differs')
        tags+=actual;rows.append((actor,c))
    all_tags=[str(t)for a in actors for c in a.get_components_by_class(u.StaticMeshComponent)for t in c.get_editor_property('component_tags')if str(t).startswith('SUB01Kitchen:')]
    if len(tags)!=40 or sorted(tags)!=sorted(all_tags):raise RuntimeError('Unexpected old/new kitchen duplicate runtime tags')
    return rows


def capture_states(u, actors):
    return [(a,a.get_actor_transform(),a.get_actor_label(),bool(a.get_editor_property('hidden')),
             [(c,c.get_world_transform(),c.get_editor_property('static_mesh'),list(c.get_materials()),list(c.get_editor_property('component_tags')),bool(c.get_editor_property('visible')),c.get_collision_enabled(),c.get_collision_profile_name(),c.get_editor_property('mobility'))for c in a.get_components_by_class(u.StaticMeshComponent)])for a in actors]


def restore_states(states):
    # Existing parent hierarchy is unchanged; every actual world transform is restored.
    def depth(actor):
        seen=set()
        while actor.get_attach_parent_actor():
            actor=actor.get_attach_parent_actor()
            if actor.get_path_name() in seen:raise RuntimeError('Attachment cycle in protected kitchen rollback')
            seen.add(actor.get_path_name())
        return len(seen)
    for a,world,label,hidden,components in sorted(states,key=lambda row:depth(row[0])):a.set_actor_transform(world,False,False)
    for a,world,label,hidden,components in states:
        a.set_actor_label(label);a.set_actor_hidden_in_game(hidden)
        for c,transform,mesh,materials,tags,visible,collision,profile,mobility in components:
            c.set_static_mesh(mesh);c.set_world_transform(transform,False,False);c.set_editor_property('component_tags',tags);c.set_visibility(visible);c.set_collision_profile_name(profile);c.set_collision_enabled(collision);c.set_mobility(mobility)
            for slot,material in enumerate(materials):c.set_material(slot,material)


def retired_snapshot_expected(u,before,parts):
    expected=copy.deepcopy(before)
    for a,c in parts:
        row=expected[a.get_path_name()];row['hidden']=True
        target=next(x for x in row['components']if x['path']==c.get_path_name());target['collision']=str(u.CollisionEnabled.NO_COLLISION);target['profile']='Custom';target['tags']=[t for t in target['tags']if not t.startswith('SUB01Kitchen:')]
    return expected


def run():
    import unreal as u
    import unreal_import_real_kitchen as importer
    from prepare_real_kitchen_native_bundle import validate_manifest
    guard();previous=validate_previous(PREVIOUS.read_bytes());owned_sink=retained_paths(previous)
    raw=(ROOT/'native-kitchen.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=NEW_PROOF_SHA:raise RuntimeError('Exact actual lower-fit source proof required')
    proof=validate_manifest(json.loads(raw))
    if proof['export_sha256']!=NEW_EXPORT or hashlib.sha256((ROOT/'native-kitchen.glb').read_bytes()).hexdigest()!=NEW_EXPORT:raise RuntimeError('Exact new lower-fit152-part GLB required')
    project=Path(u.Paths.project_dir());world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.',1)[0]!=importer.LEVEL:raise RuntimeError('Existing sole Editor must have ActualHome loaded')
    eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());parts=resolve_parts(u,actors,previous)
    originals=[]
    for index in (63,178):
        found=[a for a in actors if a.get_name()=='full-home_node_'+str(index)]
        if len(found)!=1:raise RuntimeError('Exact preserved source original missing')
        a=found[0];cs=a.get_components_by_class(u.StaticMeshComponent)
        if len(cs)!=1 or not a.get_editor_property('hidden') or cs[0].get_collision_enabled()!=u.CollisionEnabled.NO_COLLISION:raise RuntimeError('Preserved originals must remain retired in saved map')
        originals.append((a,cs[0]))
    # Recheck the already-proved owned sink before any temporary original exposure.
    importer.verify_retained_native(u,actors,project/'SourceAssets/full-home.glb',owned_paths=owned_sink)
    before=importer.snapshot(u,actors);expected=retired_snapshot_expected(u,before,parts);states=capture_states(u,actors);map_path=project/'Content/Sub01Home/ActualHome.umap';map_sha=hashlib.sha256(map_path.read_bytes()).hexdigest()
    guard()
    backup=project/'Saved/PrivateMapBackups'/('kitchen-closed-fit-original-'+str(time.time_ns()))
    backup.mkdir(parents=True)
    shutil.copy2(map_path,backup/'ActualHome.umap')
    for directory in ('__ExternalActors__','__ExternalObjects__'):
        folder=project/'Content'/directory/'Sub01Home/ActualHome'
        if folder.exists():shutil.copytree(folder,backup/directory)
    try:
        for actor,c in parts:
            actor.set_actor_hidden_in_game(True);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);c.set_editor_property('component_tags',[t for t in c.get_editor_property('component_tags')if not str(t).startswith('SUB01Kitchen:')])
        for actor,c in originals:actor.set_actor_hidden_in_game(False);c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
        result=importer.run(ROOT,dry_run=False,u=u,retained_owned_paths=owned_sink,import_revision=7)
        # The inner importer retires these source objects, but toggling collision
        # can change Unreal's collision profile. Exposure is temporary: restore
        # their exact captured state rather than guessing only hidden/collision.
        original_paths={a.get_path_name()for a,c in originals}
        restore_states([row for row in states if row[0].get_path_name()in original_paths])
        after=importer.snapshot(u,actors)
        if after!=expected:
            differences={path:{'expected':expected.get(path),'actual':after.get(path)}for path in set(expected)|set(after)if expected.get(path)!=after.get(path)}
            (ROOT/'native-kitchen-protected-differences.json').write_text(json.dumps(differences,indent=2))
            raise RuntimeError('Replacement changed protected originals or retired R5 transforms/materials; inspect native-kitchen-protected-differences.json')
        actual=[str(t)for a in eas.get_all_level_actors()for c in a.get_components_by_class(u.StaticMeshComponent)for t in c.get_editor_property('component_tags')if str(t).startswith('SUB01Kitchen:')]
        if len(actual)!=40 or any(not t.startswith('SUB01Kitchen:'+NEW_EXPORT+':')for t in actual):raise RuntimeError('Exactly40 new runtime tags required; old tags must remain retired')
        # Carry the already-proved full-source sink identity into this receipt;
        # no clone/replacement was needed during this second kitchen import.
        result['retained_sink_full_source_restore']=copy.deepcopy(previous['retained_sink_full_source_restore'])
        guard()
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Final exact kitchen replacement save failed')
        result['replacement']={'schema':'sub01.exact-R5-lower-fit-replacement.v1','previous_receipt_sha256':PREVIOUS_SHA,'previous_export_sha256':OLD_EXPORT,'retired_preserved_components':[c.get_path_name()for a,c in parts],'retired_count':152,'old_assets_deleted':False,'original_map_backup':str(backup),'preserved_actor_transforms_and_materials':True,'originals_exposed_only_within_transaction':True,'native_runtime_rebind_required':True};result['native_visual_verified']=False;result['native_hinge_motion_verified']=False;result['interactions_enabled']=False
        pending=ROOT/'native-kitchen-replacement.pending.json';pending.write_text(json.dumps(result,indent=2));pending.replace(ROOT/'native-kitchen-import.json')
        return result
    except Exception:
        restore_states(states);importer.detach_failed_import(u,eas,before)
        if importer.snapshot(u,actors)!=before:raise RuntimeError('Exact R5 replacement rollback failed; preserve existing map backups')
        imported=ROOT/'native-kitchen-import.json'
        if imported.exists() and json.loads(imported.read_text()).get('export_sha256')==NEW_EXPORT:
            imported.replace(ROOT/'native-kitchen-import.postcheck-failed.json')
        # Only persist a proven rollback if the inner importer actually changed disk.
        if hashlib.sha256(map_path.read_bytes()).hexdigest()!=map_sha and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Known-original rollback save failed')
        raise


def preflight_retirement():
    """Exercise only reversible visibility/tag/collision retirement, no import/save.

    This identifies Unreal side effects of the precise152 old parts and original
    two source actors before another costly import. All captured state is restored
    and independently compared, even if the diagnostic finds a mismatch.
    """
    import unreal as u
    import unreal_import_real_kitchen as importer
    guard();previous=validate_previous(PREVIOUS.read_bytes())
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.',1)[0]!=importer.LEVEL:
        raise RuntimeError('ActualHome must already be loaded')
    eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors())
    parts=resolve_parts(u,actors,previous);states=capture_states(u,actors)
    originals=[]
    for index in (63,178):
        found=[a for a in actors if a.get_name()=='full-home_node_'+str(index)]
        if len(found)!=1:raise RuntimeError('Exact preserved source original missing')
        cs=found[0].get_components_by_class(u.StaticMeshComponent)
        if len(cs)!=1 or not found[0].get_editor_property('hidden') or cs[0].get_collision_enabled()!=u.CollisionEnabled.NO_COLLISION:
            raise RuntimeError('Original source actors must remain retired')
        originals.append((found[0],cs[0]))
    before=importer.snapshot(u,actors);expected=retired_snapshot_expected(u,before,parts)
    map_path=Path(u.Paths.project_dir())/'Content/Sub01Home/ActualHome.umap';map_sha=hashlib.sha256(map_path.read_bytes()).hexdigest()
    result={'schema':'sub01.exact-R5-retirement-preflight.v1','imported':False,'saved':False,'native_accepted':False}
    try:
        guard()
        for actor,c in parts:
            actor.set_actor_hidden_in_game(True);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
            c.set_editor_property('component_tags',[t for t in c.get_editor_property('component_tags')if not str(t).startswith('SUB01Kitchen:')])
        for actor,c in originals:
            actor.set_actor_hidden_in_game(False);c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
        for actor,c in originals:
            actor.set_actor_hidden_in_game(True);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        after=importer.snapshot(u,actors)
        result['differences']={p:{'expected':expected.get(p),'actual':after.get(p)}for p in set(expected)|set(after)if expected.get(p)!=after.get(p)}
        result['retirement_matches_expected']=not result['differences']
    finally:
        restore_states(states)
        if importer.snapshot(u,actors)!=before:raise RuntimeError('Exact diagnostic state rollback failed; do not save')
        if hashlib.sha256(map_path.read_bytes()).hexdigest()!=map_sha:raise RuntimeError('Diagnostic unexpectedly changed disk map')
    result['original_state_restored_exactly']=True
    (ROOT/'native-kitchen-retirement-preflight.json').write_text(json.dumps(result,indent=2))
    return result
