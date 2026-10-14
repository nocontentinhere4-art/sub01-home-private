"""SERVER ONLY (root): import the seat-pose-fit clips (docs/proposed/seat-pose-fit/) onto the EXISTING verified owner
USkeleton as /Game/Sub01Hands/Seating/SUB01_<Role>, next to (never over) root's captured seating clips.

    UnrealEditor-Cmd <project>/Sub01HomeLab.uproject \
        -ExecutePythonScript="<repo>/tools/unreal_import_seated_fit_fbx.py" -unattended

Owned wrapper: root's tools/unreal_import_seating_fbx.py (four captured roles, 30 fps) is left untouched; owner
resolution and skeleton parity reuse tools/unreal_import_gaming_grip.py and tools/native_life_skeleton_parity.py.
Reads <project>/SourceAssets/SeatedFitFBX/seated-fit-fbx-audit.json and the FBX files it names
(tools/export_unreal_seated_fit_fbx.py), and re-reads the committed per-clip fit reports in this repo.

Roles (role -> committed GLB, export rate):
    DeskTypingSeated <- SUB01_DeskTyping_seated.glb   60 fps export, 60 Hz custom sample rate on import
    SeatedIdle       <- SUB01_SeatedIdle.glb          30 fps (default sample rate)
    SitDownSeated    <- SUB01_SitDown_seated.glb      30 fps
    SitToTypeSeated  <- SUB01_SitToType_seated.glb    30 fps
    TypeToSitSeated  <- SUB01_TypeToSit_seated.glb    30 fps
    GetUpSeated      <- SUB01_GetUp_seated.glb        30 fps

Only a clip whose per-clip report has `all_gates_pass: true` is imported (and then ACCEPTED). A failing clip (today
SitDown) is refused outright: never imported, no override flag exists; its receipt row says
`imported: false, accepted: false, fit_pass: false` with the reason. The importer refuses (RuntimeError, only this run's staging assets deleted, receipt untouched) when
the audit is not the committed fit, a source FBX changed, the owner skeleton is not
/Game/Sub01Hands/FBX/SUB01_OriginalOwner_Skeleton, a staged clip is on another skeleton or at another path, its
length differs from the GLB duration, or its structural root moves. It never replaces or deletes an existing asset:
an existing final path is kept only when the existing receipt matches it (`preserved_existing`), else it refuses with
no change; new clips are imported into this run's unique staging paths (/Game/Sub01Hands/Seating/_Staging/<Role>_<txid>,
replace_existing=False), verified there, then renamed onto final paths that must not exist. On failure only this
run's staging assets are deleted and the receipt is left untouched. It never writes config, never touches
/Game/Sub01Hands/FBX (SUB01_DeskTyping stays the renderer's), and claims no seat, contact or readiness.
Receipt: <project>/private-audit/unreal-seated-fit-import.json (sub01.unreal-seated-fit-import.v1), which the seat
adapter (tools/unreal_seat_transition_runtime.py) and tools/install_default_game_ini.py read.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import native_life_skeleton_parity as parity  # noqa: E402
import unreal_import_gaming_grip as grip  # noqa: E402  (owner resolution, duration tolerance; no unreal at import)
import unreal_seat_transition_runtime as seat  # noqa: E402

FIT_DIR = 'docs/proposed/seat-pose-fit'
SUMMARY_REPORT = f'{FIT_DIR}/seat-pose-fit.report.json'
DEST = seat.SEAT_CLIP_DIR                                   # /Game/Sub01Hands/Seating
PROTECTED_TYPING = seat.TYPING_CLIP                         # /Game/Sub01Hands/FBX/SUB01_DeskTyping, never written
OWNER_SKELETON = seat.OWNER_SKELETON
SOURCE_DIR = 'SourceAssets/SeatedFitFBX'
AUDIT_FILE = 'seated-fit-fbx-audit.json'
AUDIT_SCHEMA = 'sub01.seated-fit-fbx-audit.v1'
RECEIPT_FILE = seat.SEATED_FIT_RECEIPT
RECEIPT_SCHEMA = seat.SEATED_FIT_RECEIPT_SCHEMA
DURATION_TOLERANCE_S = grip.DURATION_TOLERANCE_S            # 2/30 s, the existing importers' tolerance

# role -> (GLB basename = merged action name, key in seat-pose-fit.report.json `clips`, export fps)
ROLES = {
    'DeskTypingSeated': ('SUB01_DeskTyping_seated', 'DeskTyping_seated', 60),
    'SeatedIdle': ('SUB01_SeatedIdle', 'SeatedIdle', 30),
    'SitDownSeated': ('SUB01_SitDown_seated', 'SitDown', 30),
    'SitToTypeSeated': ('SUB01_SitToType_seated', 'SitToType', 30),
    'TypeToSitSeated': ('SUB01_TypeToSit_seated', 'TypeToSit', 30),
    'GetUpSeated': ('SUB01_GetUp_seated', 'GetUp', 30),
}
# The committed fit GLBs, byte for byte (also stated by each per-clip report and the summary report).
GLB_SHA256 = {
    'DeskTypingSeated': '97fd8489fa19d71192c74eae47d69a1045a723a7692fbaa59cfa73f9c3ef75b9',
    'SeatedIdle': '57ba5e1be7a392b3889c8a875f993d39a808fee87f12a4e25d6f70a62b47a156',
    'SitDownSeated': '2c6d5da111b3af04e59719e55375b13c304a93ba755524a18865e6653cb41a6a',
    'SitToTypeSeated': 'ed46fd3e667089b8f10780dc377c0c86239122256557a34b41e5f751eebd6d21',
    'TypeToSitSeated': 'd25496c64288de5f1574956bac7099d60b7e8a8e3345f4e821883fcf13422452',
    'GetUpSeated': '6105564f22e712e19ed18bfbeea5b185518f8f67d60b76b2c59f5a041a8331d0',
}


def asset_name(role: str) -> str:
    return f'SUB01_{role}'


def object_path(role: str) -> str:
    return seat.seated_fit_object_path(role)


def glb_path(role: str, repo: Path = REPO) -> Path:
    return Path(repo) / FIT_DIR / f'{ROLES[role][0]}.glb'


def report_path(role: str, repo: Path = REPO) -> Path:
    return Path(repo) / FIT_DIR / f'{ROLES[role][0]}.report.json'


def glb_animation(raw: bytes, name: str) -> dict:
    """Key count, first/last key time and measured key rate of the named glTF animation (pure Python)."""
    magic, _, _ = struct.unpack_from('<4sII', raw, 0)
    if magic != b'glTF':
        raise RuntimeError('Not a binary glTF')
    doc = json.loads(raw[20:20 + int.from_bytes(raw[12:16], 'little')])
    animations = [a for a in doc.get('animations', []) if a.get('name') == name]
    if len(animations) != 1:
        raise RuntimeError(f'Expected exactly one animation {name!r}')
    inputs = [doc['accessors'][s['input']] for s in animations[0]['samplers']]
    count = max(i['count'] for i in inputs)
    start, end = min(i['min'][0] for i in inputs), max(i['max'][0] for i in inputs)
    duration = end - start
    return {'keys': count, 'start_s': start, 'duration_s': duration,
            'rate_hz': (count - 1) / duration if duration > 0 else 0.0}


def plan_clips(repo: Path = REPO) -> list:
    """Every role, checked against the committed fit: GLB bytes, per-clip report, summary verdict, labels, key rate.

    Pure Python (runs anywhere, also inside Blender and UE). `fit_pass` is the per-clip report's verdict, which must
    agree with the summary report; nothing here decides acceptance on its own.
    """
    repo = Path(repo)
    summary = json.loads((repo / SUMMARY_REPORT).read_text())
    if summary.get('verified') is not False or summary.get('cushion_is_proxy') is not False:
        raise RuntimeError('Summary fit report is not the trial on the actual native cushion')
    rows = []
    for role, (stem, key, fps) in ROLES.items():
        raw = glb_path(role, repo).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != GLB_SHA256[role]:
            raise RuntimeError(f'{stem}.glb is not the committed fit GLB')
        report_bytes = report_path(role, repo).read_bytes()
        report = json.loads(report_bytes)
        summary_row = summary.get('clips', {}).get(key, {})
        if report.get('sha256') != digest or summary_row.get('sha256') != digest:
            raise RuntimeError(f'{role}: fit reports describe another GLB')
        verdict = report.get('all_gates_pass')
        if not isinstance(verdict, bool) or summary_row.get('all_gates_pass') is not verdict \
                or summary.get('trial_gates_pass', {}).get(key) is not verdict:
            raise RuntimeError(f'{role}: per-clip and summary fit verdicts disagree')
        if report.get('labels', {}).get('verified') is not False:
            raise RuntimeError(f'{role}: fit report must stay labelled unverified')
        anim = glb_animation(raw, stem)
        if anim['keys'] != report.get('key_count') or abs(anim['duration_s'] - float(report.get('duration_s', -1))) > 1e-3:
            raise RuntimeError(f'{role}: GLB keys/duration differ from its report')
        if abs(anim['rate_hz'] - fps) > 0.01:
            raise RuntimeError(f'{role}: GLB keys at {anim["rate_hz"]:.3f} Hz, expected {fps} Hz')
        rows.append({'role': role, 'source_action': stem, 'report_key': key, 'fps': fps,
                     'glb': f'{FIT_DIR}/{stem}.glb', 'glb_sha256': digest,
                     'report': f'{FIT_DIR}/{stem}.report.json',
                     'report_sha256': hashlib.sha256(report_bytes).hexdigest(),
                     'fit_pass': verdict, 'frames': anim['keys'], 'duration_s': anim['duration_s']})
    return rows


def check_audit(audit: dict, repo: Path = REPO) -> list:
    """The conversion audit must describe exactly the committed fit clips on the unchanged 65-joint owner."""
    if audit.get('schema') != AUDIT_SCHEMA:
        raise RuntimeError('Not a seated-fit FBX conversion audit')
    if len(audit.get('bone_names', [])) != 65 or audit.get('bone_edits') is not False:
        raise RuntimeError('Conversion source is not the verified unchanged 65-joint owner')
    expected = {r['role']: r for r in plan_clips(repo)}
    clips = audit.get('clips', [])
    if sorted(r.get('role') for r in clips) != sorted(expected):
        raise RuntimeError('Expected exactly the six seated-fit roles; nothing is substituted')
    for row in clips:
        want = expected[row['role']]
        for field in ('glb_sha256', 'fps', 'frames', 'fit_pass', 'source_action'):
            if row.get(field) != want[field]:
                raise RuntimeError(f'{row["role"]}: audit {field} differs from the committed fit')
        if abs(float(row.get('duration_s', -1)) - want['duration_s']) > 1e-3:
            raise RuntimeError(f'{row["role"]}: audit duration differs from the GLB')
    return [dict(row, report_sha256=expected[row['role']]['report_sha256']) for row in clips]


def _options(u, skeleton, fps: int):
    options = u.FbxImportUI()
    for key, value in (('automated_import_should_detect_type', False), ('import_as_skeletal', True), ('import_mesh', False),
                       ('import_animations', True), ('import_materials', False), ('import_textures', False),
                       ('mesh_type_to_import', u.FBXImportType.FBXIT_ANIMATION), ('skeleton', skeleton)):
        options.set_editor_property(key, value)
    data = options.get_editor_property('anim_sequence_import_data')
    if fps == 30:
        data.set_editor_property('use_default_sample_rate', True)
    else:
        data.set_editor_property('use_default_sample_rate', False)
        data.set_editor_property('custom_sample_rate', fps)
    return options


def _sampled_rate(u, clip, duration):
    """Measured key rate of the imported sequence when the editor exposes its frame count, else None."""
    library = getattr(u, 'AnimationLibrary', None)
    frames = getattr(library, 'get_num_frames', None)
    if frames is None or duration <= 0:
        return None
    return float(frames(clip)) / duration


def package_path(object_path_: str) -> str:
    return object_path_.split('.', 1)[0]


def _matching_receipt_row(receipt, row) -> dict | None:
    """The existing receipt's row for exactly this source, skeleton and path (an accepted, imported fit), or None."""
    if not isinstance(receipt, dict) or receipt.get('schema') != RECEIPT_SCHEMA or receipt.get('skeleton') != OWNER_SKELETON:
        return None
    for old in receipt.get('clips', []):
        if (isinstance(old, dict) and old.get('role') == row['role'] and old.get('object_path') == object_path(row['role'])
                and old.get('fbx_sha256') == row['sha256'] and old.get('glb_sha256') == row['glb_sha256']
                and old.get('fps') == row['fps'] and old.get('imported') is True and old.get('accepted') is True
                and old.get('fit_pass') is True and old.get('same_existing_skeleton') is True):
            return old
    return None


def main(u, root: Path | None = None, owner_parents: dict | None = None, repo: Path = REPO, txid: str | None = None) -> dict:
    """Never replaces or deletes an existing asset at a final path, and never touches the receipt on failure.

    1. every final path that already exists must match the existing receipt (same FBX/GLB sha256, skeleton, path,
       rate) and the live asset (owner skeleton, length): it is kept as `preserved_existing`; otherwise refuse with
       zero mutations;
    2. missing roles are imported into unique staging paths of this run (replace_existing=False);
    3. each staged asset is verified (skeleton, path, length, sample rate, structural root);
    4. only when all pass are they renamed onto their final paths (which must not exist); then the receipt is written.
    On any failure only the staging assets this run created (folder-list diff) are deleted.
    """
    import uuid
    root = Path(root or u.Paths.project_dir()).resolve()
    receipt_path = root / RECEIPT_FILE
    source = root / SOURCE_DIR
    rows = check_audit(json.loads((source / AUDIT_FILE).read_text()), repo)
    for row in rows:
        if hashlib.sha256((source / row['file']).read_bytes()).hexdigest() != row['sha256']:
            raise RuntimeError(f'{row["role"]}: source FBX changed since conversion')
        if object_path(row['role']) == PROTECTED_TYPING or not object_path(row['role']).startswith(DEST + '/'):
            raise RuntimeError('Seated-fit destination would overwrite a protected asset')
    mesh, skeleton, basis = grip.resolve_owner(u, root)
    if skeleton.get_path_name() != OWNER_SKELETON:
        raise RuntimeError(f'Owner skeleton is {skeleton.get_path_name()}, expected {OWNER_SKELETON}')
    u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
    probe = u.SkeletalMeshComponent()
    probe.set_skeletal_mesh_asset(mesh)
    ue_names = [str(probe.get_bone_name(i)) for i in range(probe.get_num_bones())]
    ue_parents = {n: (None if str(probe.get_parent_bone(n)) in ('None', '') else str(probe.get_parent_bone(n))) for n in ue_names}
    owner = parity.map_owner_parents_to_ue(owner_parents or grip.owner_parents_default(), ue_names)
    skeleton_parity = parity.structural_root_parity(ue_names, ue_parents, owner, structure_only=True)
    if not skeleton_parity['pass']:
        raise RuntimeError('UE skeleton is not the owner skeleton: ' + '; '.join(skeleton_parity['failures']))
    assets = u.EditorAssetLibrary
    old_receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else None

    # Phase 1 (read only): existing final assets are preserved only against a matching receipt and live checks.
    results, todo = {}, []
    for row in rows:
        role = row['role']
        entry = {'role': role, 'object_path': object_path(role), 'fit_pass': row['fit_pass'], 'fps': row['fps'],
                 'glb': row['glb'], 'glb_sha256': row['glb_sha256'], 'report_sha256': row['report_sha256'],
                 'fbx_sha256': row['sha256'], 'glb_duration_s': row['duration_s'], 'frames': row['frames']}
        if not row['fit_pass']:
            results[role] = dict(entry, imported=False, accepted=False,
                                 refusal='per-clip seat-pose-fit gates failed; a failed fit is never imported')
            continue
        if not assets.does_asset_exist(package_path(object_path(role))):
            todo.append((row, entry))
            continue
        old = _matching_receipt_row(old_receipt, row)
        live = u.load_asset(object_path(role))
        if old is None:
            raise RuntimeError(f'{role}: {object_path(role)} already exists without a matching import receipt; '
                               'nothing replaced, nothing changed')
        if (not isinstance(live, u.AnimSequence) or live.get_editor_property('skeleton') != skeleton
                or abs(live.get_editor_property('sequence_length') - row['duration_s']) > DURATION_TOLERANCE_S):
            raise RuntimeError(f'{role}: existing {object_path(role)} differs from its receipt (skeleton or length); '
                               'nothing replaced, nothing changed')
        results[role] = dict(old, preserved_existing=True)
    if not todo:
        if old_receipt is None:
            raise RuntimeError('Nothing to import and no receipt')
        return old_receipt

    # Phase 2: stage every missing role under this run's unique names; verify; then rename all.
    txid = txid or uuid.uuid4().hex[:12]
    staging = f'{DEST}/_Staging'
    listed = lambda: {package_path(str(p)) for p in assets.list_assets(staging, recursive=True, include_folder=False)}
    created, staged = set(), []

    def refuse(why):
        for path in sorted(created):              # only paths this transaction created (staged or renamed-to finals)
            if assets.does_asset_exist(path):
                assets.delete_asset(path)
        raise RuntimeError(why)

    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    u.SystemLibrary.execute_console_command(world, 'Interchange.FeatureFlags.Import.FBX 0')
    for row, entry in todo:
        role = row['role']
        name = f'{role}_{txid}'
        staged_package = f'{staging}/{name}'
        if assets.does_asset_exist(staged_package):
            refuse(f'{role}: staging path {staged_package} already exists')
        before = listed()
        task = u.AssetImportTask()
        task.filename, task.destination_path, task.destination_name = str(source / row['file']), staging, name
        task.automated, task.replace_existing, task.save, task.options = True, False, False, _options(u, skeleton, row['fps'])
        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        new = listed() - before
        created |= new
        foreign = {package_path(str(p)) for p in task.imported_object_paths} - new
        if foreign:
            refuse(f'{role}: import reported paths outside this run\'s staging: {sorted(foreign)}')
        if new != {staged_package}:
            refuse(f'{role}: import created {sorted(new)}, expected only {staged_package}')
        clip = u.load_asset(f'{staged_package}.{name}')
        if not isinstance(clip, u.AnimSequence) or clip.get_editor_property('skeleton') != skeleton:
            refuse(f'{role}: imported sequence differs from the actual owner skeleton')
        if clip.get_path_name() != f'{staged_package}.{name}':
            refuse(f'{role}: staged as {clip.get_path_name()}, expected {staged_package}.{name}')
        duration = clip.get_editor_property('sequence_length')
        if abs(duration - row['duration_s']) > DURATION_TOLERANCE_S:
            refuse(f'{role}: length {duration:.4f} s differs from the GLB {row["duration_s"]:.4f} s')
        rate = _sampled_rate(u, clip, duration)
        if rate is not None and abs(rate - row['fps']) > 1:
            refuse(f'{role}: sampled at {rate:.2f} Hz, expected {row["fps"]} Hz')
        samples = []
        if skeleton_parity['structural_root']:
            for t in parity.sample_times(duration):
                pose = u.AnimationLibrary.get_bone_poses_for_time(clip, [skeleton_parity['structural_root']], t, False, mesh)[0]
                loc, rot, scale = pose.translation, pose.rotation, pose.scale3d
                samples.append((t, (loc.x, loc.y, loc.z), (rot.x, rot.y, rot.z, rot.w), (scale.x, scale.y, scale.z)))
        clip_parity = parity.structural_root_parity(ue_names, ue_parents, owner, samples)
        if not clip_parity['pass']:
            refuse(f'{role}: owner skeleton parity failed: ' + '; '.join(clip_parity['failures']))
        staged.append((role, staged_package, dict(entry, imported=True, accepted=True, preserved_existing=False,
                                                  duration_s=duration, sample_rate_hz=row['fps'], sampled_rate_measured_hz=rate,
                                                  same_existing_skeleton=True, skeleton_parity=clip_parity)))
    for role, staged_package, _ in staged:
        if assets.does_asset_exist(package_path(object_path(role))):
            refuse(f'{role}: final path {object_path(role)} appeared during the import; nothing replaced')
    for role, staged_package, result in staged:
        if not assets.rename_asset(staged_package, package_path(object_path(role))):
            refuse(f'{role}: rename {staged_package} -> {object_path(role)} failed')
        created.discard(staged_package)
        created.add(package_path(object_path(role)))   # was absent before this run, so owned by this transaction
        moved = u.load_asset(object_path(role))
        if not isinstance(moved, u.AnimSequence) or moved.get_editor_property('skeleton') != skeleton:
            refuse(f'{role}: renamed asset is not the verified staged sequence')
        results[role] = result
    for role, _, _ in staged:
        if not assets.save_asset(package_path(object_path(role)), only_if_is_dirty=False):
            refuse(f'{role}: could not save {object_path(role)}; this run\'s clips removed, earlier receipt untouched')
    receipt = {'schema': RECEIPT_SCHEMA, 'owner': mesh.get_path_name(), 'skeleton': skeleton.get_path_name(),
               'identity_basis': basis, 'destination': DEST, 'protected_untouched': PROTECTED_TYPING, 'txid': txid,
               'clips': [results[r['role']] for r in rows],
               'accepted_roles': [r['role'] for r in rows if results[r['role']]['accepted']],
               'fit_label': 'trial', 'requires_server_reaudit': True, 'requires_native_collision_audit': True,
               'physical_contact_verified': False, 'native_seat_verified': False, 'runtime_ready': False,
               'readiness_claimed': False}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temp = receipt_path.with_name(receipt_path.name + f'.{txid}.tmp')
    temp.write_text(json.dumps(receipt, indent=2) + '\n')
    temp.replace(receipt_path)
    u.log(f'SUB01_SEATED_FIT_IMPORTED accepted={",".join(receipt["accepted_roles"])} txid={txid}')
    return receipt


if __name__ == '__main__':
    import unreal
    if len(sys.argv) > 1 and any(a.startswith('--') for a in sys.argv[1:]):
        raise SystemExit('unreal_import_seated_fit_fbx.py takes no options; failed fits are never imported')
    main(unreal)
