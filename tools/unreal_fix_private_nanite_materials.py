"""Fix the 70 actual Game18241 missing-Nanite material warnings in the Editor.

Plugin material ancestors are duplicated into the private project, never edited.
The only original mutations are project MIC parent links and direct project
UMaterial usage flags. No component binding, texture or PBR parameter is edited.
Run dry_run first; renderer owns the next saved Editor batch and Game handoff.
"""
import hashlib
import json
import shutil
import time
from pathlib import Path

PROJECT = Path('/workspace/sub01-private-recovered-project/Sub01HomeLab')
MANIFEST_NAME='actual-game-nanite-material-warnings-20261015.json'
MANIFEST = Path(__file__).with_name(MANIFEST_NAME)
if not MANIFEST.exists():MANIFEST=Path(__file__).resolve().parents[1]/'docs/proposed'/MANIFEST_NAME
WARNING_SHA='cb35254e3a15c419c89b18deaae4aed5031df4784da2c31ce1a690da2be26e91'
DEST = '/Game/Sub01Home/NaniteMaterials/Game18241'


def path(obj):
    return obj.get_path_name() if obj else None


def private(name):
    return name.startswith('/Game/Sub01Home/')


def effective(u, material):
    """Use public editor getters; include inherited, not just overridden, values."""
    mel=u.MaterialEditingLibrary
    instance=isinstance(material,u.MaterialInstanceConstant)
    prefix='get_material_instance_' if instance else 'get_material_default_'
    out={}
    for kind in ('scalar','vector','texture'):
        rows={}
        getter=getattr(mel,prefix+kind+'_parameter_value')
        for name in getattr(mel,'get_'+kind+'_parameter_names')(material):
            value=getter(material,name)
            if kind=='vector':value=[value.r,value.g,value.b,value.a]
            elif kind=='texture':value=path(value)
            rows[str(name)]=value
        out[kind]=rows
    return out


def chain(u, material):
    rows=[];seen=set()
    while material:
        name=path(material)
        if name in seen:raise RuntimeError('Material parent cycle '+name)
        seen.add(name);rows.append(material)
        if isinstance(material,u.Material) and not isinstance(material,u.MaterialInstanceConstant):return rows
        if not isinstance(material,u.MaterialInstanceConstant):raise RuntimeError('Unexpected material type '+name)
        material=material.get_editor_property('parent')
    raise RuntimeError('Material chain has no base UMaterial')


def binding_inventory(u):
    eas=u.get_editor_subsystem(u.EditorActorSubsystem)
    rows={}
    for actor in eas.get_all_level_actors():
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            rows[path(component)]=[path(m) for m in component.get_materials()]
    return rows


def run(dry_run=True,u=None):
    if u is None:import unreal as u
    # The fixed reviewed manifest is deployed beside this tool by the renderer.
    raw=MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=WARNING_SHA:raise RuntimeError('Actual Game warning manifest hash differs')
    manifest=json.loads(raw)
    names=manifest['material_paths']
    if manifest['native_pid']!=18241 or manifest['native_start_ticks']!=973298943 or len(names)!=70 or len(set(names))!=70 or not all(private(n) for n in names):
        raise RuntimeError('Exact actual Game warning inventory required')
    mel=u.MaterialEditingLibrary;eal=u.EditorAssetLibrary
    usage=u.MaterialUsage.MATUSAGE_NANITE
    targets=[];edges={};direct={};external={}
    for name in names:
        material=eal.load_asset(name)
        if not material or path(material)!=name:raise RuntimeError('Exact warning material absent '+name)
        lineage=chain(u,material);targets.append(material)
        base=lineage[-1]
        if private(path(base)):direct[path(base)]=base
        for child,parent in zip(lineage,lineage[1:]):
            if private(path(child)) and not private(path(parent)):edges[path(child)]=(child,parent)
        for member in lineage:
            if not private(path(member)):
                if not path(member).startswith('/InterchangeAssets/'):
                    raise RuntimeError('Unreviewed external ancestor '+path(member))
                external[path(member)]=member
    before={path(m):effective(u,m) for m in targets}
    bindings=binding_inventory(u)
    report={'schema':'sub01.private-nanite-material-fix.v1','warning_sha256':hashlib.sha256(raw).hexdigest(),
            'dry_run':dry_run,'targets':names,'effective_before':before,
            'project_parent_edges':{n:path(p) for n,(_,p) in edges.items()},
            'target_parents_before':{path(m):path(m.get_editor_property('parent')) for m in targets if isinstance(m,u.MaterialInstanceConstant)},
            'private_direct_bases':sorted(direct),'external_ancestors':sorted(external),
            'game_visual_verified':False}
    if dry_run:return report
    backup=PROJECT/'Saved/PrivateMaterialBackups'/('nanite-'+str(time.time_ns()))
    backup.mkdir(parents=True)
    originals={n:o for n,(o,_) in edges.items()};originals.update(direct)
    files={}
    for name in originals:
        source=PROJECT/'Content'/(name.split('.',1)[0][len('/Game/'):]+'.uasset')
        if not source.is_file():raise RuntimeError('Original package byte backup unavailable '+str(source))
        relative=source.relative_to(PROJECT/'Content');saved=backup/relative;saved.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,saved);files[name]={'file':str(saved),'sha256':hashlib.sha256(saved.read_bytes()).hexdigest()}
    (backup/'before.json').write_text(json.dumps(dict(report,asset_backups=files),indent=2)+'\n')
    clones={};changed_edges=[];flags={n:bool(m.get_editor_property('used_with_nanite')) for n,m in direct.items()}
    destination=DEST+'/Attempt_'+str(time.time_ns())
    def clone(original):
        name=path(original)
        if name in clones:return clones[name]
        parent=original.get_editor_property('parent') if isinstance(original,u.MaterialInstanceConstant) else None
        replacement_parent=clone(parent) if parent else None
        assetname='NM_'+hashlib.sha256(name.encode()).hexdigest()[:16]+'_'+original.get_name()
        duplicate=eal.duplicate_asset(name,destination+'/'+assetname)
        if not duplicate:raise RuntimeError('Private material duplication failed '+name)
        clones[name]=duplicate
        if parent:mel.set_material_instance_parent(duplicate,replacement_parent)
        else:
            mel.set_material_usage(duplicate,usage)
            if not bool(duplicate.get_editor_property('used_with_nanite')):raise RuntimeError('Private Nanite usage refused')
            mel.recompile_material(duplicate)
        return duplicate
    try:
        # Prepare the complete owned shader chains before changing originals.
        for _,parent in edges.values():clone(parent)
        for name,material in direct.items():
            mel.set_material_usage(material,usage)
            if not material.get_editor_property('used_with_nanite'):raise RuntimeError('Direct private Nanite usage refused '+name)
            mel.recompile_material(material)
        for child,parent in edges.values():
            changed_edges.append((child,parent))
            mel.set_material_instance_parent(child,clones[path(parent)])
            mel.update_material_instance(child)
        after={path(m):effective(u,m) for m in targets}
        if before!=after or bindings!=binding_inventory(u):raise RuntimeError('Effective PBR or component binding changed')
        for material in targets:
            if not chain(u,material)[-1].get_editor_property('used_with_nanite'):raise RuntimeError('Effective base still lacks Nanite usage '+path(material))
        for material in list(clones.values())+list(originals.values()):
            if not eal.save_loaded_asset(material,only_if_is_dirty=False):raise RuntimeError('Material package save failed '+path(material))
        report.update(dry_run=False,effective_after=after,owned_ancestors={n:path(m) for n,m in clones.items()},
                      asset_backups=files,backup=str(backup),component_bindings_unchanged=True,pbr_parameters_unchanged=True,
                      target_parents_after={path(m):path(m.get_editor_property('parent')) for m in targets if isinstance(m,u.MaterialInstanceConstant)},
                      fixture_parent_config_review_required=True,shader_completion_and_game_recapture_required=True)
        (backup/'success.json').write_text(json.dumps(report,indent=2)+'\n')
        audit=PROJECT/'private-audit';audit.mkdir(exist_ok=True)
        (audit/'nanite-material-usage-fix.json').write_text(json.dumps(report,indent=2)+'\n')
        return report
    except Exception as error:
        for child,parent in reversed(changed_edges):
            mel.set_material_instance_parent(child,parent);mel.update_material_instance(child)
        for name,value in flags.items():
            direct[name].set_editor_property('used_with_nanite',value);mel.recompile_material(direct[name])
        rollback={path(m):effective(u,m) for m in targets}==before and bindings==binding_inventory(u)
        for material in originals.values():eal.save_loaded_asset(material,only_if_is_dirty=False)
        (backup/'failure.json').write_text(json.dumps({'error':str(error),'rollback_pbr_and_bindings_equal':rollback,
                                                    'quarantined_owned_assets':destination},indent=2)+'\n')
        raise
