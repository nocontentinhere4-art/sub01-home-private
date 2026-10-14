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
                root_moves=False, bones=BONES, parents=PARENTS, path=grip.OBJECT_PATH):
    log = SimpleNamespace(imported=[], deleted=[], saved=[], messages=[])

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
                assert task.destination_path == grip.DEST and task.destination_name == grip.ASSET_NAME
                assert task.options.values['skeleton'] == owner_sk and task.options.values['import_mesh'] is False
                assets[path] = AnimSequence(path, skeleton=Skeleton(clip_skeleton), sequence_length=duration)
                task.imported_object_paths = [path]
                log.imported.append(task.filename)

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
        EditorAssetLibrary=SimpleNamespace(save_directory=lambda d, **k: log.saved.append(d),
                                           delete_asset=lambda p: log.deleted.append(p)),
        log=log.messages.append)
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
    assert log.imported and not log.deleted and log.saved == [grip.DEST]
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
    ({'path': '/Game/Sub01Hands/Play/SUB01_GamingGrip2.SUB01_GamingGrip2'}, 'expected'),
])
def test_refuses_and_deletes_a_bad_import(tmp_path, kwargs, why):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path, **kwargs)
    with pytest.raises(RuntimeError, match=why):
        grip.main(u, tmp_path, OWNER_PARENTS)
    assert log.deleted and not log.saved and not (tmp_path / grip.RECEIPT_FILE).exists()


def test_default_owner_parents_are_the_65_joint_owner_with_one_root():
    parents = grip.owner_parents_default()
    assert len(parents) == 65 and [n for n, p in parents.items() if p is None] == ['mixamorig:Hips']
