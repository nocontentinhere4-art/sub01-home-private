"""Fix only the observed controller MIC warning without rebuilding its mesh."""
import hashlib
import json
import shutil
import time
from pathlib import Path

from unreal_controller_material_audit import MESH, MATERIAL
from unreal_fix_private_nanite_materials import effective, chain, binding_inventory, path


def run(u=None):
    if u is None:import unreal as u
    project=Path(u.Paths.project_dir());audit=project/'private-audit'
    from unreal_import_reference_dressing import fingerprint
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.',1)[0]!='/Game/Sub01Home/ActualHome':raise RuntimeError('Actual private Editor world required')
    receipt=json.loads((audit/'native-controller-asset.json').read_text())
    if receipt['physical_assembly']['mesh']!=MESH:raise RuntimeError('Exact physical controller receipt required')
    eal=u.EditorAssetLibrary;mel=u.MaterialEditingLibrary
    material=eal.load_asset(MATERIAL);mesh=eal.load_asset(MESH)
    if not isinstance(material,u.MaterialInstanceConstant) or not mesh or path(mesh)!=MESH:raise RuntimeError('Exact controller assets required')
    lineage=chain(u,material)
    expected=[MATERIAL,'/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque.MI_Default_Opaque','/InterchangeAssets/gltf/M_Default.M_Default']
    if [path(m)for m in lineage]!=expected:raise RuntimeError('Actual audited controller parent chain differs')
    if mesh.get_num_sections(0)!=1 or path(mesh.get_material(0))!=MATERIAL:raise RuntimeError('Audited controller binding differs')
    actors=list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    beforeactors=fingerprint(u,actors);bindings=binding_inventory(u);pbr=effective(u,material)
    meshfile=project/'Content'/(MESH.split('.',1)[0][len('/Game/'):]+'.uasset')
    meshsha=hashlib.sha256(meshfile.read_bytes()).hexdigest()
    settings=u.get_editor_subsystem(u.StaticMeshEditorSubsystem).get_nanite_settings(mesh)
    nanite={k:settings.get_editor_property(k)for k in ('enabled','keep_percent_triangles','trim_relative_error','fallback_percent_triangles','fallback_relative_error')}
    backup=project/'Saved/PrivateMaterialBackups'/('controller-'+str(time.time_ns()));backup.mkdir(parents=True)
    file=project/'Content'/(MATERIAL.split('.',1)[0][len('/Game/'):]+'.uasset')
    saved=backup/'controller.uasset';shutil.copy2(file,saved)
    dest='/Game/Sub01Home/NaniteMaterials/Controller/Attempt_'+str(time.time_ns())
    originalparent=lineage[1];changed=False;clones=[]
    try:
        base=eal.duplicate_asset(path(lineage[2]),dest+'/ControllerBase')
        if not base:raise RuntimeError('Private base duplication refused')
        clones.append(base);mel.set_material_usage(base,u.MaterialUsage.MATUSAGE_NANITE)
        if not base.get_editor_property('used_with_nanite'):raise RuntimeError('Private Nanite usage refused')
        mel.recompile_material(base)
        parent=eal.duplicate_asset(path(originalparent),dest+'/ControllerOpaque')
        if not parent:raise RuntimeError('Private opaque ancestor duplication refused')
        clones.append(parent);mel.set_material_instance_parent(parent,base);mel.update_material_instance(parent)
        changed=True;mel.set_material_instance_parent(material,parent);mel.update_material_instance(material)
        if effective(u,material)!=pbr or binding_inventory(u)!=bindings or fingerprint(u,actors)!=beforeactors:raise RuntimeError('PBR or protected actor bindings changed')
        current=u.get_editor_subsystem(u.StaticMeshEditorSubsystem).get_nanite_settings(mesh)
        if {k:current.get_editor_property(k)for k in nanite}!=nanite or hashlib.sha256(meshfile.read_bytes()).hexdigest()!=meshsha:raise RuntimeError('Mesh package or settings changed')
        for obj in clones+[material]:
            if not eal.save_loaded_asset(obj,only_if_is_dirty=False):raise RuntimeError('Scoped material save refused')
        result={'schema':'sub01.controller-private-nanite-material-fix.v1','mesh':MESH,'material':MATERIAL,'before_chain':expected,'after_chain':[path(m)for m in chain(u,material)],'effective_before':pbr,'effective_after':effective(u,material),'owned_ancestors':[path(m)for m in clones],'original_package_backup':str(saved),'original_package_sha256':hashlib.sha256(saved.read_bytes()).hexdigest(),'nanite_settings_unchanged':nanite,'mesh_rebuilt':False,'mesh_package_sha256_unchanged':meshsha,'mesh_geometry_uvs_material_slots_unchanged':True,'all_actor_bindings_unchanged':True,'plugin_assets_modified':False,'game_visual_verified':False,'captured_epoch':time.time()}
        (audit/'controller-private-nanite-material-fix.json').write_text(json.dumps(result,indent=2)+'\n');return result
    except Exception as error:
        if changed:
            mel.set_material_instance_parent(material,originalparent);mel.update_material_instance(material)
            if not eal.save_loaded_asset(material,only_if_is_dirty=False):raise RuntimeError('Controller material rollback save refused')from error
        good=effective(u,material)==pbr and binding_inventory(u)==bindings and fingerprint(u,actors)==beforeactors
        (backup/'failure.json').write_text(json.dumps({'error':str(error),'rollback_verified':good,'quarantined_owned_assets':dest},indent=2)+'\n')
        if not good:raise RuntimeError('Controller material rollback differs')from error
        raise
