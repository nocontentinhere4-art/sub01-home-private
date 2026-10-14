"""Fake-unreal tests for tools/unreal_import_gaming_grip.py (owner skeleton only, parity gate, receipt, refusals)."""
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import unreal_import_gaming_grip as grip  # noqa: E402
import unreal_controller_play_runtime as controller  # noqa: E402

OWNER_PARENTS = {'mixamorig:Hips': None, 'mixamorig:Spine': 'mixamorig:Hips', 'mixamorig:Head': 'mixamorig:Spine'}
BONES = ['mixamo', 'mixamorig:Hips', 'mixamorig:Spine', 'mixamorig:Head']
PARENTS = {'mixamo': 'None', 'mixamorig:Hips': 'mixamo', 'mixamorig:Spine': 'mixamorig:Hips', 'mixamorig:Head': 'mixamorig:Spine'}


class Props:
    def __init__(self, **values):
        self.values = dict(values)

    def set_editor_property(self, key, value):
        self.values[key] = value

    def get_editor_property(self, key):
        return self.values[key]


def fake_unreal(project, *, typing_skeleton='SK', clip_skeleton='SK', duration=grip.NATIVE_DURATION_S,
                root_moves=False, bones=BONES, parents=PARENTS, path=None, extra_outputs=0, rename_ok=True):
    log = SimpleNamespace(imported=[], deleted=[], saved=[], renamed=[], messages=[])

    class SkeletalMesh(Props):
        def get_path_name(self):
            return grip.OWNER_MESH

    class AnimSequence(Props):
        def __init__(self, p, **v):
            super().__init__(**v)
            self.p = p

        def get_path_name(self):
            return self.p

    class Skeleton:
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return isinstance(other, Skeleton) and other.name == self.name

        def get_path_name(self):
            return '/Game/Sub01Hands/FBX/SUB01_OriginalOwner_Skeleton.SUB01_OriginalOwner_Skeleton'

    owner_sk = Skeleton('SK')
    assets = {grip.OWNER_MESH: SkeletalMesh(skeleton=owner_sk),
              grip.OWNER_TYPING: AnimSequence(grip.OWNER_TYPING, skeleton=Skeleton(typing_skeleton))}

    class Component:
        def set_skeletal_mesh_asset(self, mesh):
            pass

        def get_num_bones(self):
            return len(bones)

        def get_bone_name(self, i):
            return bones[i]

        def get_parent_bone(self, name):
            return parents[name]

    class Tools:
        def import_asset_tasks(self, tasks):
            for task in tasks:
                assert task.destination_path == grip.STAGING_DIR and task.destination_name.startswith(grip.ASSET_NAME + '_')
                assert task.replace_existing is False
                assert task.options.values['skeleton'] == owner_sk and task.options.values['import_mesh'] is False
                out = path or f'{task.destination_path}/{task.destination_name}.{task.destination_name}'
                assets[out] = AnimSequence(out, skeleton=Skeleton(clip_skeleton), sequence_length=duration)
                for i in range(extra_outputs):    # e.g. a side asset the FBX import may create next to the clip
                    side = f'{task.destination_path}/{task.destination_name}_Side{i}.{task.destination_name}_Side{i}'
                    assets[side] = Props()
                task.imported_object_paths = [out]
                log.imported.append(task.filename)

    def package(p):
        return p.split('.', 1)[0]

    def find(p):
        return next((k for k in assets if package(k) == package(p)), None)

    def delete_asset(p):
        log.deleted.append(package(p))
        del assets[find(p)]
        return True

    def rename_asset(src, dst):
        if not rename_ok or find(dst):
            return False
        obj = assets.pop(find(src))
        name = dst.rsplit('/', 1)[1]
        obj.p = f'{dst}.{name}'
        assets[obj.p] = obj
        log.renamed.append((package(src), dst))
        return True

    library = SimpleNamespace(
        does_asset_exist=lambda p: find(p) is not None,
        does_directory_exist=lambda d: any(k.startswith(d + '/') for k in assets),
        list_assets=lambda d, recursive=True, include_folder=False: [k for k in assets if k.startswith(d + '/')],
        delete_asset=delete_asset, rename_asset=rename_asset,
        save_asset=lambda p, only_if_is_dirty=False: log.saved.append(p) or True)

    def poses(clip, names, t, _, mesh):
        x = t if root_moves else 0.0
        return [SimpleNamespace(translation=SimpleNamespace(x=x, y=0, z=0), rotation=SimpleNamespace(x=0, y=0, z=0, w=1),
                                scale3d=SimpleNamespace(x=1, y=1, z=1))]

    u = SimpleNamespace(
        SkeletalMesh=SkeletalMesh, AnimSequence=AnimSequence, load_asset=lambda p: assets.get(p),
        Paths=SimpleNamespace(project_dir=lambda: str(project)),
        Sub01HomeHandsInstance=SimpleNamespace(finish_pending_skin_compilation=lambda: None),
        SkeletalMeshComponent=Component, UnrealEditorSubsystem=object,
        get_editor_subsystem=lambda cls: SimpleNamespace(get_editor_world=lambda: 'world'),
        SystemLibrary=SimpleNamespace(execute_console_command=lambda w, c: log.messages.append(c)),
        FbxImportUI=lambda: Props(anim_sequence_import_data=Props()),
        FBXImportType=SimpleNamespace(FBXIT_ANIMATION='anim'),
        AssetImportTask=lambda: SimpleNamespace(imported_object_paths=[]),
        AssetToolsHelpers=SimpleNamespace(get_asset_tools=lambda: Tools()),
        AnimationLibrary=SimpleNamespace(get_bone_poses_for_time=poses),
        EditorAssetLibrary=library,
        log=log.messages.append)
    u.assets, u.Skeleton = assets, Skeleton
    return u, log


def write_source(project, **override):
    folder = project / grip.SOURCE_DIR
    folder.mkdir(parents=True)
    fbx = folder / 'GamingGrip.fbx'
    fbx.write_bytes(b'fake fbx bytes')
    row = {'role': 'Gaming', 'derived_glb_sha256': grip.DERIVED_GLB_SHA256, 'source_fbx_sha256': controller.GAMING_FBX_SHA256,
           'frames': 152, 'duration_s': grip.NATIVE_DURATION_S, 'file': fbx.name,
           'sha256': hashlib.sha256(fbx.read_bytes()).hexdigest()}
    row.update(override)
    audit = {'schema': grip.AUDIT_SCHEMA, 'bone_names': [f'b{i}' for i in range(65)], 'bone_edits': False, 'fps': 30, 'clips': [row]}
    (folder / grip.AUDIT_FILE).write_text(json.dumps(audit))
    return fbx


def test_constants_match_the_adapter_and_the_committed_derived_clip():
    assert grip.OBJECT_PATH == '/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip'
    assert hashlib.sha256((ROOT / grip.DERIVED_GLB).read_bytes()).hexdigest() == grip.DERIVED_GLB_SHA256
    report = json.loads((ROOT / 'docs/proposed/controller-play/SUB01_GamingGrip_derived.report.json').read_text())
    assert report['output_glb_sha256'] == grip.DERIVED_GLB_SHA256 and report['frames'] == grip.FRAMES


def test_imports_on_owner_skeleton_and_receipt_satisfies_adapter_config(tmp_path):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path)
    receipt = grip.main(u, tmp_path, OWNER_PARENTS)
    assert log.imported and not log.deleted and log.saved == [grip.FINAL_PACKAGE]
    assert len(log.renamed) == 1 and log.renamed[0][1] == grip.FINAL_PACKAGE
    assert log.renamed[0][0].startswith(grip.STAGING_DIR + '/') and receipt['staging_path'] == log.renamed[0][0]
    assert isinstance(u.assets[grip.OBJECT_PATH], u.AnimSequence)
    on_disk = json.loads((tmp_path / grip.RECEIPT_FILE).read_text())
    assert on_disk == json.loads(json.dumps(receipt))
    assert on_disk['runtime_ready'] is False and on_disk['controller_grip_verified'] is False
    row = on_disk['clips'][0]
    assert row['skeleton_parity']['pass'] and row['skeleton_parity']['root_motion_checked']
    # The controller adapter accepts exactly this row once accepted evidence with the same grip sha exists.
    audit = tmp_path / 'private-audit'
    audit.mkdir()
    sofa = '{"sofa": "measured"}'
    (audit / controller.SOFA_REPORT).write_text(sofa)
    (audit / controller.EVIDENCE).write_text(json.dumps({'schema': controller.EVIDENCE_SCHEMA, 'accepted': True,
                                                          'sofa_revision': str(controller.play_id(sofa)),
                                                          'grip_clip_sha256': grip.DERIVED_GLB_SHA256}))
    text, refusals = controller.config_fragment(tmp_path, on_disk)
    assert refusals == {} and text.endswith('+ValidatedHandsPostures=Gaming\n')


def test_without_evidence_the_config_stays_refused(tmp_path):
    write_source(tmp_path)
    u, _ = fake_unreal(tmp_path)
    text, refusals = controller.config_fragment(tmp_path, grip.main(u, tmp_path, OWNER_PARENTS))
    assert text == '' and 'evidence' in refusals


@pytest.mark.parametrize('override, why', [
    ({'derived_glb_sha256': '0' * 64}, 'derived grip GLB'),
    ({'source_fbx_sha256': '0' * 64}, 'Gaming.fbx'),
    ({'frames': 151}, 'frame count'),
    ({'role': 'Idle'}, 'exactly one Gaming'),
    ({'sha256': '0' * 64}, 'changed since conversion'),
])
def test_refuses_wrong_source_before_any_import(tmp_path, override, why):
    write_source(tmp_path, **override)
    u, log = fake_unreal(tmp_path)
    with pytest.raises(RuntimeError, match=why):
        grip.main(u, tmp_path, OWNER_PARENTS)
    assert not log.imported and not (tmp_path / grip.RECEIPT_FILE).exists()


def test_refuses_without_the_existing_owner_skeleton(tmp_path):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path, typing_skeleton='OTHER')
    with pytest.raises(RuntimeError, match='owner USkeleton unavailable'):
        grip.main(u, tmp_path, OWNER_PARENTS)
    assert not log.imported


def test_refuses_on_skeleton_parity_mismatch(tmp_path):
    write_source(tmp_path)
    parents = dict(PARENTS, **{'mixamorig:Head': 'mixamorig:Hips'})
    u, log = fake_unreal(tmp_path, parents=parents)
    with pytest.raises(RuntimeError, match='not the owner skeleton'):
        grip.main(u, tmp_path, OWNER_PARENTS)
    assert not log.imported and not (tmp_path / grip.RECEIPT_FILE).exists()


@pytest.mark.parametrize('kwargs, why', [
    ({'clip_skeleton': 'NEW'}, 'differs from the actual owner skeleton'),
    ({'duration': 4.0}, 'duration'),
    ({'root_moves': True}, 'parity failed'),
    ({'rename_ok': False}, 'Could not move'),
])
def test_refuses_and_deletes_only_its_own_staging_import(tmp_path, kwargs, why):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path, **kwargs)
    with pytest.raises(RuntimeError, match=why):
        grip.main(u, tmp_path, OWNER_PARENTS)
    assert log.deleted and all(p.startswith(grip.STAGING_DIR + '/') for p in log.deleted)
    assert not log.saved and not (tmp_path / grip.RECEIPT_FILE).exists()
    assert grip.OBJECT_PATH not in u.assets and not any(k.startswith(grip.STAGING_DIR + '/') for k in u.assets)


def valid_existing(u, tmp_path, fbx_sha=None):
    """A previously imported real final clip plus its receipt (bytes returned for exact comparison)."""
    u.assets[grip.OBJECT_PATH] = u.AnimSequence(grip.OBJECT_PATH, skeleton=u.Skeleton('SK'),
                                                sequence_length=grip.NATIVE_DURATION_S)
    audit = json.loads((tmp_path / grip.SOURCE_DIR / grip.AUDIT_FILE).read_text())['clips'][0]
    receipt = {'schema': grip.RECEIPT_SCHEMA, 'clips': [{
        'role': 'Gaming', 'object_path': grip.OBJECT_PATH, 'duration_s': grip.NATIVE_DURATION_S,
        'fbx_sha256': fbx_sha or audit['sha256'], 'source_fbx_sha256': audit['source_fbx_sha256'],
        'derived_glb_sha256': audit['derived_glb_sha256']}], 'runtime_ready': False}
    (tmp_path / grip.RECEIPT_FILE).write_text(json.dumps(receipt))
    return (tmp_path / grip.RECEIPT_FILE).read_bytes()


def test_preserves_a_valid_existing_clip_without_any_mutation(tmp_path):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path)
    before = valid_existing(u, tmp_path)
    existing = u.assets[grip.OBJECT_PATH]
    result = grip.main(u, tmp_path, OWNER_PARENTS)
    assert result['preserved_existing'] is True
    assert not log.imported and not log.deleted and not log.renamed and not log.saved
    assert u.assets[grip.OBJECT_PATH] is existing and (tmp_path / grip.RECEIPT_FILE).read_bytes() == before


@pytest.mark.parametrize('setup, why', [
    (lambda u, t: u.assets.__setitem__(grip.OBJECT_PATH, u.AnimSequence(
        grip.OBJECT_PATH, skeleton=u.Skeleton('SK'), sequence_length=grip.NATIVE_DURATION_S)), 'without an import receipt'),
    (lambda u, t: valid_existing(u, t, fbx_sha='0' * 64), 'another source'),
    (lambda u, t: (valid_existing(u, t), u.assets[grip.OBJECT_PATH].set_editor_property('skeleton', u.Skeleton('X'))),
     'not on the owner skeleton'),
    (lambda u, t: (valid_existing(u, t), u.assets[grip.OBJECT_PATH].set_editor_property('sequence_length', 3.0)),
     'duration differs'),
])
def test_refuses_an_unverifiable_existing_clip_without_any_mutation(tmp_path, setup, why):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path)
    setup(u, tmp_path)
    receipt = tmp_path / grip.RECEIPT_FILE
    before = receipt.read_bytes() if receipt.exists() else None
    existing = u.assets[grip.OBJECT_PATH]
    with pytest.raises(RuntimeError, match=why):
        grip.main(u, tmp_path, OWNER_PARENTS)
    assert not log.imported and not log.deleted and not log.renamed and not log.saved
    assert u.assets[grip.OBJECT_PATH] is existing
    assert (receipt.read_bytes() if receipt.exists() else None) == before


def test_failure_after_import_keeps_previous_receipt_and_foreign_assets_intact(tmp_path):
    """The final clip is absent (so a new import runs) while a previous receipt and an unrelated staging asset
    exist; verification fails after the staged import with side outputs. Only this transaction's paths go."""
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path, duration=4.0, extra_outputs=2)
    previous = b'{"schema": "previous receipt kept byte-for-byte"}\n'
    (tmp_path / grip.RECEIPT_FILE).write_bytes(previous)
    foreign = f'{grip.STAGING_DIR}/Other_run.Other_run'
    u.assets[foreign] = u.AnimSequence(foreign, skeleton=u.Skeleton('SK'), sequence_length=1.0)
    keep = {k: v for k, v in u.assets.items()}
    with pytest.raises(RuntimeError, match='duration'):
        grip.main(u, tmp_path, OWNER_PARENTS)
    assert len(log.deleted) == 3 and grip.STAGING_DIR + '/Other_run' not in log.deleted
    assert u.assets == keep and (tmp_path / grip.RECEIPT_FILE).read_bytes() == previous
    assert not log.renamed and not log.saved and not list(tmp_path.glob('*.tmp'))


def test_import_output_outside_staging_is_refused_and_left_untouched(tmp_path):
    write_source(tmp_path)
    stray = '/Game/Sub01Hands/Play/SUB01_GamingGrip2.SUB01_GamingGrip2'
    u, log = fake_unreal(tmp_path, path=stray)
    with pytest.raises(RuntimeError, match='outside its transaction staging path'):
        grip.main(u, tmp_path, OWNER_PARENTS)
    assert stray in u.assets and not log.deleted and not log.renamed and not (tmp_path / grip.RECEIPT_FILE).exists()


def test_default_owner_parents_are_the_65_joint_owner_with_one_root():
    parents = grip.owner_parents_default()
    assert len(parents) == 65 and [n for n, p in parents.items() if p is None] == ['mixamorig:Hips']
