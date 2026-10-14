"""Seated-fit clips -> native seat chain: role mapping, 60 Hz, fit-verdict refusal, fake-unreal import, adapter binding."""
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import unreal_import_seated_fit_fbx as fit  # noqa: E402
import unreal_seat_transition_runtime as seat  # noqa: E402

OWNER_PARENTS = {'mixamorig:Hips': None, 'mixamorig:Spine': 'mixamorig:Hips', 'mixamorig:Head': 'mixamorig:Spine'}
BONES = ['mixamo', 'mixamorig:Hips', 'mixamorig:Spine', 'mixamorig:Head']
PARENTS = {'mixamo': 'None', 'mixamorig:Hips': 'mixamo', 'mixamorig:Spine': 'mixamorig:Hips', 'mixamorig:Head': 'mixamorig:Spine'}
PLAN = {r['role']: r for r in fit.plan_clips()}


class Props:
    def __init__(self, **values):
        self.values = dict(values)

    def set_editor_property(self, key, value):
        self.values[key] = value

    def get_editor_property(self, key):
        return self.values[key]


def fake_unreal(project, *, clip_skeleton='SK', durations=None, wrong_path_for=None, extra_for=None, root_moves=False,
                skeleton_path=fit.OWNER_SKELETON, frames_per_s=None, rename_fails_for=None, existing=()):
    """A fake editor with a real asset table: import, list, exists, rename, delete and load all act on `assets`."""
    log = SimpleNamespace(imported=[], deleted=[], saved=[], renamed=[], options={})

    class SkeletalMesh(Props):
        def get_path_name(self):
            return fit.grip.OWNER_MESH

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
            return skeleton_path

    owner_sk = Skeleton('SK')
    assets = {fit.grip.OWNER_MESH: SkeletalMesh(skeleton=owner_sk),
              fit.grip.OWNER_TYPING: AnimSequence(fit.grip.OWNER_TYPING, skeleton=owner_sk)}
    for role in existing:
        assets[fit.object_path(role)] = AnimSequence(fit.object_path(role), skeleton=owner_sk,
                                                     sequence_length=PLAN[role]['duration_s'], role=role, original=True)

    def obj(package):
        return f'{package}.{package.rsplit("/", 1)[1]}'

    class Tools:
        def import_asset_tasks(self, tasks):
            for task in tasks:
                assert task.destination_path == fit.DEST + '/_Staging' and task.replace_existing is False
                assert task.options.values['skeleton'] == owner_sk and task.options.values['import_mesh'] is False
                role = task.destination_name.rsplit('_', 1)[0]
                package = f'{task.destination_path}/{task.destination_name}' + ('X' if role == wrong_path_for else '')
                assert obj(package) not in assets, 'import must never replace'
                duration = (durations or {}).get(role, PLAN[role]['duration_s'])
                assets[obj(package)] = AnimSequence(obj(package), skeleton=Skeleton(clip_skeleton), sequence_length=duration, role=role)
                task.imported_object_paths = [obj(package)]
                if role == extra_for:
                    assets[obj(package + '_Extra')] = AnimSequence(obj(package + '_Extra'), skeleton=owner_sk)
                log.imported.append(role)
                log.options[role] = task.options.values['anim_sequence_import_data'].values

    def poses(clip, names, t, _, mesh):
        x = t if root_moves else 0.0
        return [SimpleNamespace(translation=SimpleNamespace(x=x, y=0, z=0), rotation=SimpleNamespace(x=0, y=0, z=0, w=1),
                                scale3d=SimpleNamespace(x=1, y=1, z=1))]

    def exists(path):
        return any(k.split('.', 1)[0] == path.split('.', 1)[0] for k in assets)

    def rename(src, dst):
        role = src.rsplit('/', 1)[1].rsplit('_', 1)[0]
        if role == rename_fails_for or exists(dst) or not exists(src):
            return False
        clip = assets.pop(obj(src))
        clip.p = obj(dst)
        assets[obj(dst)] = clip
        log.renamed.append((src, dst))
        return True

    def delete(path):
        assert path.split('.', 1)[0].startswith(fit.DEST + '/_Staging/'), f'deleted a non-staging path {path}'
        for k in [k for k in assets if k.split('.', 1)[0] == path.split('.', 1)[0]]:
            del assets[k]
        log.deleted.append(path)

    library = SimpleNamespace(get_bone_poses_for_time=poses)
    if frames_per_s is not None:
        library.get_num_frames = lambda clip: round(frames_per_s(clip.values['role']) * clip.values['sequence_length'])
    u = SimpleNamespace(
        SkeletalMesh=SkeletalMesh, AnimSequence=AnimSequence, load_asset=lambda p: assets.get(p),
        Paths=SimpleNamespace(project_dir=lambda: str(project)),
        Sub01HomeHandsInstance=SimpleNamespace(finish_pending_skin_compilation=lambda: None),
        SkeletalMeshComponent=Component, UnrealEditorSubsystem=object,
        get_editor_subsystem=lambda cls: SimpleNamespace(get_editor_world=lambda: 'world'),
        SystemLibrary=SimpleNamespace(execute_console_command=lambda w, c: None),
        FbxImportUI=lambda: Props(anim_sequence_import_data=Props()),
        FBXImportType=SimpleNamespace(FBXIT_ANIMATION='anim'),
        AssetImportTask=lambda: SimpleNamespace(imported_object_paths=[]),
        AssetToolsHelpers=SimpleNamespace(get_asset_tools=lambda: Tools()),
        AnimationLibrary=library,
        EditorAssetLibrary=SimpleNamespace(
            save_directory=lambda d, **k: log.saved.append(d), delete_asset=delete, does_asset_exist=exists,
            rename_asset=rename,
            list_assets=lambda d, recursive=True, include_folder=False: [k for k in assets if k.startswith(d + '/')]),
        log=lambda m: None)
    log.assets = assets
    return u, log


class Component:
    def set_skeletal_mesh_asset(self, mesh):
        pass

    def get_num_bones(self):
        return len(BONES)

    def get_bone_name(self, i):
        return BONES[i]

    def get_parent_bone(self, name):
        return PARENTS[name]


def write_source(project, mutate=None):
    folder = project / fit.SOURCE_DIR
    folder.mkdir(parents=True)
    rows = []
    for role, row in PLAN.items():
        fbx = folder / f'{role}.fbx'
        fbx.write_bytes(f'fake fbx {role}'.encode())
        rows.append({'role': role, 'source_action': row['source_action'], 'glb': row['glb'], 'glb_sha256': row['glb_sha256'],
                     'report': row['report'], 'fit_pass': row['fit_pass'], 'fps': row['fps'], 'frames': row['frames'],
                     'duration_s': row['duration_s'], 'file': fbx.name, 'sha256': hashlib.sha256(fbx.read_bytes()).hexdigest()})
    audit = {'schema': fit.AUDIT_SCHEMA, 'bone_names': [f'b{i}' for i in range(65)], 'bone_edits': False, 'clips': rows}
    if mutate:
        mutate(audit)
    (folder / fit.AUDIT_FILE).write_text(json.dumps(audit))


# ------------------------------------------------------------------ role mapping, paths, 60 Hz, verdicts
def test_role_mapping_paths_and_rates():
    assert set(fit.ROLES) == {'DeskTypingSeated', 'SeatedIdle', 'SitDownSeated', 'SitToTypeSeated', 'TypeToSitSeated', 'GetUpSeated'}
    for role in fit.ROLES:
        assert fit.object_path(role) == f'/Game/Sub01Hands/Seating/SUB01_{role}.SUB01_{role}'
        assert fit.object_path(role) != fit.PROTECTED_TYPING and not fit.object_path(role).startswith('/Game/Sub01Hands/FBX/')
    assert fit.OWNER_SKELETON == '/Game/Sub01Hands/FBX/SUB01_OriginalOwner_Skeleton.SUB01_OriginalOwner_Skeleton'
    assert {r: p['fps'] for r, p in PLAN.items()} == {'DeskTypingSeated': 60, 'SeatedIdle': 30, 'SitDownSeated': 30,
                                                       'SitToTypeSeated': 30, 'TypeToSitSeated': 30, 'GetUpSeated': 30}
    assert PLAN['DeskTypingSeated']['frames'] == 989 and PLAN['DeskTypingSeated']['duration_s'] == pytest.approx(16.4667, abs=1e-3)
    # Seated-fit names never collide with root's captured seating roles.
    assert not set(fit.ROLES) & set(seat.SEAT_ROLE_ASSETS.values())


def test_fit_verdicts_are_the_committed_reports():
    verdicts = {r: p['fit_pass'] for r, p in PLAN.items()}
    assert verdicts == {'DeskTypingSeated': True, 'SeatedIdle': True, 'SitDownSeated': False, 'SitToTypeSeated': True,
                        'TypeToSitSeated': True, 'GetUpSeated': True}


def _copy_fit(tmp_path):
    repo = tmp_path / 'repo'
    (repo / fit.FIT_DIR).mkdir(parents=True)
    for f in (ROOT / fit.FIT_DIR).iterdir():
        (repo / fit.FIT_DIR / f.name).write_bytes(f.read_bytes())
    return repo


def test_plan_refuses_a_changed_glb_or_a_disagreeing_verdict(tmp_path):
    repo = _copy_fit(tmp_path)
    report = repo / fit.FIT_DIR / 'SUB01_SitDown_seated.report.json'
    data = json.loads(report.read_text())
    data['all_gates_pass'] = True                          # the per-clip verdict cannot be flipped on its own
    report.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match='verdicts disagree'):
        fit.plan_clips(repo)
    repo2 = _copy_fit(tmp_path / 'b')
    glb = repo2 / fit.FIT_DIR / 'SUB01_SeatedIdle.glb'
    glb.write_bytes(glb.read_bytes() + b' ')
    with pytest.raises(RuntimeError, match='not the committed fit GLB'):
        fit.plan_clips(repo2)


# ------------------------------------------------------------------ importer (fake unreal)
PASSING = ['DeskTypingSeated', 'SeatedIdle', 'SitToTypeSeated', 'TypeToSitSeated', 'GetUpSeated']


def final_paths(log):
    return {k for k in log.assets if k.startswith(fit.DEST + '/') and '/_Staging/' not in k}


def test_imports_only_passing_fits_via_staging_with_60hz_typing(tmp_path):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path)
    receipt = fit.main(u, tmp_path, OWNER_PARENTS, txid='t1')
    assert sorted(log.imported) == sorted(PASSING) and not log.deleted and log.saved == [fit.DEST]
    assert sorted(log.renamed) == sorted((f'{fit.DEST}/_Staging/{r}_t1', f'{fit.DEST}/SUB01_{r}') for r in PASSING)
    assert final_paths(log) == {fit.object_path(r) for r in PASSING}
    assert not [k for k in log.assets if '/_Staging/' in k]
    assert log.options['DeskTypingSeated'] == {'use_default_sample_rate': False, 'custom_sample_rate': 60}
    assert log.options['SeatedIdle'] == {'use_default_sample_rate': True}
    on_disk = json.loads((tmp_path / 'private-audit/unreal-seated-fit-import.json').read_text())
    assert on_disk == json.loads(json.dumps(receipt))
    assert on_disk['schema'] == seat.SEATED_FIT_RECEIPT_SCHEMA and on_disk['skeleton'] == fit.OWNER_SKELETON
    assert on_disk['runtime_ready'] is False and on_disk['readiness_claimed'] is False and on_disk['native_seat_verified'] is False
    rows = {r['role']: r for r in on_disk['clips']}
    assert sorted(on_disk['accepted_roles']) == sorted(PASSING)
    for role in ('SitDownSeated',):
        assert rows[role]['imported'] is False and rows[role]['accepted'] is False and rows[role]['fit_pass'] is False
        assert 'never imported' in rows[role]['refusal']
    typing = rows['DeskTypingSeated']
    assert typing['object_path'] == '/Game/Sub01Hands/Seating/SUB01_DeskTypingSeated.SUB01_DeskTypingSeated'
    assert typing['sample_rate_hz'] == 60 and typing['accepted'] and typing['same_existing_skeleton']
    assert typing['preserved_existing'] is False


def test_no_override_exists_for_failed_fits(tmp_path):
    import inspect
    source = (ROOT / 'tools/unreal_import_seated_fit_fbx.py').read_text() + (ROOT / 'tools/export_unreal_seated_fit_fbx.py').read_text()
    assert 'allow' not in source.lower()
    assert set(inspect.signature(fit.main).parameters) == {'u', 'root', 'owner_parents', 'repo', 'txid'}
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path)
    with pytest.raises(TypeError):
        fit.main(u, tmp_path, OWNER_PARENTS, allow_failed_fit=True)
    assert not log.imported


def test_seated_durations_keep_the_transition_timing():
    header = seat.HEADER_FILE.read_text()

    def constant(name):
        return float(header.split(f'static constexpr double {name}=', 1)[1].split(';', 1)[0])
    assert PLAN['SitDownSeated']['duration_s'] == pytest.approx(constant('SitDownSeconds'), abs=1e-4)
    assert PLAN['GetUpSeated']['duration_s'] == pytest.approx(constant('GetUpSeconds'), abs=1e-4)
    assert PLAN['SitToTypeSeated']['duration_s'] == pytest.approx(constant('SitToTypeSeconds'), abs=1e-4)


def test_measured_rate_is_checked_when_the_editor_exposes_it(tmp_path):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path, frames_per_s=lambda role: 30)        # typing resampled to 30 Hz
    with pytest.raises(RuntimeError, match='DeskTypingSeated: sampled at 30.00 Hz, expected 60 Hz'):
        fit.main(u, tmp_path, OWNER_PARENTS)
    assert log.deleted and not final_paths(log) and not (tmp_path / fit.RECEIPT_FILE).exists()
    u, _ = fake_unreal(tmp_path, frames_per_s=lambda role: PLAN[role]['fps'])
    assert fit.main(u, tmp_path, OWNER_PARENTS)['clips'][0]['sampled_rate_measured_hz'] == pytest.approx(60, abs=1)


@pytest.mark.parametrize('kwargs, why', [
    ({'clip_skeleton': 'NEW'}, 'differs from the actual owner skeleton'),
    ({'durations': {'SeatedIdle': 4.5}}, 'SeatedIdle: length'),
    ({'root_moves': True}, 'parity failed'),
    ({'wrong_path_for': 'SitToTypeSeated'}, 'SitToTypeSeated: import created'),
    ({'extra_for': 'SeatedIdle'}, 'SeatedIdle: import created'),
])
def test_failure_after_staged_import_deletes_only_staging_and_keeps_existing_asset_and_receipt(tmp_path, kwargs, why):
    write_source(tmp_path)
    # A valid earlier run: SeatedIdle exists at its final path with a matching receipt.
    first, first_log = fake_unreal(tmp_path)
    fit.main(first, tmp_path, OWNER_PARENTS, txid='old')
    receipt_bytes = (tmp_path / fit.RECEIPT_FILE).read_bytes()
    # The failing role must be one that is staged again, so the preserved one is another role.
    keep = 'DeskTypingSeated' if 'SeatedIdle' in (kwargs.get('durations') or {}) or kwargs.get('extra_for') else 'SeatedIdle'
    assert fit.object_path(keep) in first_log.assets
    # A later run where only `keep` exists and the others must be staged again.
    u, log = fake_unreal(tmp_path, existing=[keep], **kwargs)
    original = log.assets[fit.object_path(keep)]
    with pytest.raises(RuntimeError, match=why):
        fit.main(u, tmp_path, OWNER_PARENTS, txid='new')
    assert (tmp_path / fit.RECEIPT_FILE).read_bytes() == receipt_bytes             # receipt untouched
    assert log.assets[fit.object_path(keep)] is original and original.values.get('original')   # existing asset kept
    assert final_paths(log) == {fit.object_path(keep)} and not log.renamed
    assert log.deleted and all(d.startswith(fit.DEST + '/_Staging/') and '_new' in d for d in log.deleted)
    assert not [k for k in log.assets if '/_Staging/' in k]                          # this run's staging is cleaned up


def test_rename_failure_never_deletes_a_final_path(tmp_path):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path, rename_fails_for='SitToTypeSeated')
    with pytest.raises(RuntimeError, match='rename'):
        fit.main(u, tmp_path, OWNER_PARENTS, txid='r')
    assert not (tmp_path / fit.RECEIPT_FILE).exists()
    assert all('/_Staging/' in d for d in log.deleted)
    assert not [k for k in log.assets if '/_Staging/' in k]


def test_existing_asset_without_matching_receipt_is_refused_with_zero_mutations(tmp_path):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path, existing=['SeatedIdle'])
    before = dict(log.assets)
    with pytest.raises(RuntimeError, match='already exists without a matching import receipt'):
        fit.main(u, tmp_path, OWNER_PARENTS)
    assert log.assets == before and not log.imported and not log.deleted and not log.renamed and not log.saved
    assert not (tmp_path / fit.RECEIPT_FILE).exists()
    # A receipt for another FBX does not match either.
    (tmp_path / fit.RECEIPT_FILE).parent.mkdir(parents=True, exist_ok=True)
    stale = {'schema': fit.RECEIPT_SCHEMA, 'skeleton': fit.OWNER_SKELETON, 'clips': [
        {'role': 'SeatedIdle', 'object_path': fit.object_path('SeatedIdle'), 'fbx_sha256': '0' * 64,
         'glb_sha256': PLAN['SeatedIdle']['glb_sha256'], 'fps': 30, 'imported': True, 'accepted': True,
         'fit_pass': True, 'same_existing_skeleton': True}]}
    (tmp_path / fit.RECEIPT_FILE).write_text(json.dumps(stale))
    stale_bytes = (tmp_path / fit.RECEIPT_FILE).read_bytes()
    with pytest.raises(RuntimeError, match='without a matching import receipt'):
        fit.main(u, tmp_path, OWNER_PARENTS)
    assert log.assets == before and not log.imported and (tmp_path / fit.RECEIPT_FILE).read_bytes() == stale_bytes


def test_rerun_preserves_matching_existing_assets(tmp_path):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path)
    fit.main(u, tmp_path, OWNER_PARENTS, txid='a')
    receipt_bytes = (tmp_path / fit.RECEIPT_FILE).read_bytes()
    u2, log2 = fake_unreal(tmp_path, existing=PASSING)
    assert fit.main(u2, tmp_path, OWNER_PARENTS, txid='b') == json.loads(receipt_bytes)
    assert not log2.imported and not log2.renamed and not log2.deleted
    assert (tmp_path / fit.RECEIPT_FILE).read_bytes() == receipt_bytes
    # Only SeatedIdle exists: it is preserved, the rest staged and renamed, receipt rewritten.
    (tmp_path / fit.RECEIPT_FILE).write_bytes(receipt_bytes)
    u3, log3 = fake_unreal(tmp_path, existing=['SeatedIdle'])
    receipt = fit.main(u3, tmp_path, OWNER_PARENTS, txid='c')
    rows = {r['role']: r for r in receipt['clips']}
    assert rows['SeatedIdle']['preserved_existing'] is True and rows['DeskTypingSeated']['preserved_existing'] is False
    assert sorted(log3.imported) == sorted(set(PASSING) - {'SeatedIdle'})


def test_existing_asset_on_another_skeleton_is_refused_without_change(tmp_path):
    write_source(tmp_path)
    u, _ = fake_unreal(tmp_path)
    fit.main(u, tmp_path, OWNER_PARENTS, txid='a')
    receipt_bytes = (tmp_path / fit.RECEIPT_FILE).read_bytes()
    u2, log2 = fake_unreal(tmp_path, existing=['SeatedIdle'])
    log2.assets[fit.object_path('SeatedIdle')].values['sequence_length'] = 9.0
    before = dict(log2.assets)
    with pytest.raises(RuntimeError, match='differs from its receipt'):
        fit.main(u2, tmp_path, OWNER_PARENTS)
    assert log2.assets == before and not log2.imported and (tmp_path / fit.RECEIPT_FILE).read_bytes() == receipt_bytes


def test_refuses_another_owner_skeleton_before_any_import(tmp_path):
    write_source(tmp_path)
    u, log = fake_unreal(tmp_path, skeleton_path='/Game/Other/SK.SK')
    with pytest.raises(RuntimeError, match='expected /Game/Sub01Hands/FBX/SUB01_OriginalOwner_Skeleton'):
        fit.main(u, tmp_path, OWNER_PARENTS)
    assert not log.imported and not (tmp_path / fit.RECEIPT_FILE).exists()


@pytest.mark.parametrize('mutate, why', [
    (lambda a: a['clips'][2].update(fit_pass=True), 'fit_pass differs'),            # a failed fit relabelled as passing
    (lambda a: a['clips'][0].update(fps=30), 'fps differs'),
    (lambda a: a['clips'].pop(), 'exactly the six'),
    (lambda a: a['clips'][1].update(sha256='0' * 64), 'source FBX changed'),
    (lambda a: a.update(bone_edits=True), '65-joint owner'),
])
def test_refuses_a_wrong_audit_before_any_import(tmp_path, mutate, why):
    write_source(tmp_path, mutate)
    u, log = fake_unreal(tmp_path)
    with pytest.raises(RuntimeError, match=why):
        fit.main(u, tmp_path, OWNER_PARENTS)
    assert not log.imported and not (tmp_path / fit.RECEIPT_FILE).exists()


# ------------------------------------------------------------------ adapter binding (receipt -> slots)
def _receipt(tmp_path):
    write_source(tmp_path)
    u, _ = fake_unreal(tmp_path)
    return fit.main(u, tmp_path, OWNER_PARENTS)


def test_adapter_binds_seated_slots_only_from_an_accepted_receipt_and_config(tmp_path):
    receipt = _receipt(tmp_path)
    bound = seat.seated_fit_bindings(receipt, validated={'SeatedIdle', 'DeskTypingSeated'})
    assert bound['Sitting'] == {'bound': True, 'role': 'SeatedIdle', 'object_path': fit.object_path('SeatedIdle')}
    assert bound['DeskTyping'] == {'bound': True, 'role': 'DeskTypingSeated', 'object_path': fit.object_path('DeskTypingSeated')}
    # Without config validation, without a receipt, or with a non-accepted row: existing behaviour.
    assert not any(v['bound'] for v in seat.seated_fit_bindings(receipt, validated=()).values())
    assert not any(v['bound'] for v in seat.seated_fit_bindings(None, validated={'SeatedIdle', 'DeskTypingSeated'}).values())
    failed = json.loads(json.dumps(receipt))
    for row in failed['clips']:
        if row['role'] == 'SeatedIdle':
            row['accepted'] = False
    assert seat.seated_fit_bindings(failed, {'SeatedIdle'})['Sitting']['refusal'] == 'fit gates failed or row not accepted'
    other = dict(receipt, skeleton='/Game/Other/SK.SK')
    assert not seat.seated_fit_bindings(other, {'SeatedIdle'})['Sitting']['bound']


def test_failed_fits_never_fill_a_slot(tmp_path):
    receipt = _receipt(tmp_path)
    everything = set(seat.SEATED_FIT_SLOTS)
    bound = seat.seated_fit_bindings(receipt, everything)
    assert bound['StandToSit']['bound'] is False                       # SitDown seated still fails its fit
    assert bound['Sitting']['bound'] and bound['SitToType']['bound'] and bound['DeskTyping']['bound']
    assert bound['SitToStand']['bound']                                # GetUp seated passes since the seam need floor
    # Even a hand-edited receipt row that claims the import cannot pass a failed fit.
    forged = json.loads(json.dumps(receipt))
    for row in forged['clips']:
        if row['role'] == 'SitDownSeated':
            row.update(imported=True, accepted=True, same_existing_skeleton=True)
    assert seat.seated_fit_bindings(forged, everything)['StandToSit']['bound'] is False


def test_installed_native_binding_mirrors_the_python_gate():
    sources = {'header': '#include "Sub01HomeLab.generated.h"\n void Forward(float Value);\n',
               'cpp': ' BeginLiveHome();\n UpdateNativeFeedback();\n if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus(\n '
                      + seat.SEAT_RATE_ANCHOR,
               'hands_header': ' protected:\n', 'hands_cpp': ' float Progress=1;\n  Current.SetPlayRate(Hands->TargetRate);\n  Blend.Evaluate_AnyThread(Output);\n'}
    cpp = seat.install(sources)['cpp']
    load = cpp.split('void ASub01HomeCharacter::LoadSeatTransition(){', 1)[1].split(' // Chair:', 1)[0]
    assert '@@' not in cpp
    typing = load.index('if(UAnimSequence* Typing=HandsClips.FindRef(TEXT("DeskTyping")))')
    fits = load.index('const FSeatFitSlot FitSlots[]={{TEXT("SitDownSeated"),TEXT("StandToSit"),SeatRoleStandToSit},'
                      '{TEXT("SeatedIdle"),TEXT("Sitting"),SeatRoleSitting},{TEXT("SitToTypeSeated"),TEXT("SitToType"),SeatRoleSitToType},'
                      '{TEXT("DeskTypingSeated"),TEXT("DeskTyping"),SeatRoleDeskTyping},{TEXT("GetUpSeated"),TEXT("SitToStand"),SeatRoleSitToStand}};')
    assert typing < fits                                   # the seated clip overrides, only after the existing binding
    assert 'TEXT("private-audit/unreal-seated-fit-import.json")' in load and 'FitSchema==TEXT("sub01.unreal-seated-fit-import.v1")' in load
    assert 'FitSkeleton==Mesh->GetSkeleton()->GetPathName()' in load
    for gate in ('TEXT("accepted"),A)&&A', 'TEXT("fit_pass"),P)&&P', 'TEXT("same_existing_skeleton"),Same)&&Same', 'Object==Path',
                 'ValidatedHandsPostures.Contains(FName(S.Role))', 'Clip->GetSkeleton()==Mesh->GetSkeleton()'):
        assert gate in load
    assert 'TEXT("%s/SUB01_%s.SUB01_%s"),TEXT("/Game/Sub01Hands/Seating"),S.Role,S.Role' in load
    # Seat verification, typing profile and the receipts are untouched by the binding.
    assert load.count('NativeSeatVerified') == 0 and 'ContactSequence' not in load
