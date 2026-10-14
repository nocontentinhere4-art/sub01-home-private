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
SitDown and GetUp) is refused outright: never imported, no override flag exists; its receipt row says
`imported: false, accepted: false, fit_pass: false` with the reason. The importer refuses (RuntimeError, every asset imported in this run deleted again, NO receipt) when
the audit is not the committed fit, a source FBX changed, the owner skeleton is not
/Game/Sub01Hands/FBX/SUB01_OriginalOwner_Skeleton, an imported clip is on another skeleton or at another path, its
length differs from the GLB duration, or its structural root moves. It never writes config, never touches
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
    'GetUpSeated': '1a75ff55161c8ee3b3a88c37446ad790e1fe6c5dd8120a201e687715c9ae369a',
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


def main(u, root: Path | None = None, owner_parents: dict | None = None, repo: Path = REPO) -> dict:
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
    # A receipt exists only after a complete successful run; an older one is withdrawn before anything is replaced.
    if receipt_path.exists():
        receipt_path.unlink()
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    u.SystemLibrary.execute_console_command(world, 'Interchange.FeatureFlags.Import.FBX 0')
    imported, results = [], []

    def refuse(why):
        for p in imported:
            u.EditorAssetLibrary.delete_asset(p)
        raise RuntimeError(why)

    for row in rows:
        role = row['role']
        entry = {'role': role, 'object_path': object_path(role), 'fit_pass': row['fit_pass'], 'fps': row['fps'],
                 'glb': row['glb'], 'glb_sha256': row['glb_sha256'], 'report_sha256': row['report_sha256'],
                 'fbx_sha256': row['sha256'], 'glb_duration_s': row['duration_s'], 'frames': row['frames']}
        if not row['fit_pass']:
            results.append(dict(entry, imported=False, accepted=False,
                                refusal='per-clip seat-pose-fit gates failed; a failed fit is never imported'))
            continue
        task = u.AssetImportTask()
        task.filename, task.destination_path, task.destination_name = str(source / row['file']), DEST, asset_name(role)
        task.automated, task.replace_existing, task.save, task.options = True, True, True, _options(u, skeleton, row['fps'])
        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        imported.extend(task.imported_object_paths)
        clips = [c for c in (u.load_asset(p) for p in task.imported_object_paths) if isinstance(c, u.AnimSequence)]
        if len(clips) != 1 or clips[0].get_editor_property('skeleton') != skeleton:
            refuse(f'{role}: imported sequence differs from the actual owner skeleton')
        clip = clips[0]
        if clip.get_path_name() != object_path(role):
            refuse(f'{role}: imported as {clip.get_path_name()}, expected {object_path(role)}')
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
        results.append(dict(entry, imported=True, accepted=True, duration_s=duration,
                            sample_rate_hz=row['fps'], sampled_rate_measured_hz=rate,
                            same_existing_skeleton=True, skeleton_parity=clip_parity))
    u.EditorAssetLibrary.save_directory(DEST, only_if_is_dirty=False, recursive=True)
    receipt = {'schema': RECEIPT_SCHEMA, 'owner': mesh.get_path_name(), 'skeleton': skeleton.get_path_name(),
               'identity_basis': basis, 'destination': DEST, 'protected_untouched': PROTECTED_TYPING,
               'clips': results,
               'accepted_roles': [r['role'] for r in results if r['accepted']],
               'fit_label': 'trial', 'requires_server_reaudit': True, 'requires_native_collision_audit': True,
               'physical_contact_verified': False, 'native_seat_verified': False, 'runtime_ready': False,
               'readiness_claimed': False}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    u.log(f'SUB01_SEATED_FIT_IMPORTED accepted={",".join(receipt["accepted_roles"])}')
    return receipt


if __name__ == '__main__':
    import unreal
    if len(sys.argv) > 1 and any(a.startswith('--') for a in sys.argv[1:]):
        raise SystemExit('unreal_import_seated_fit_fbx.py takes no options; failed fits are never imported')
    main(unreal)
