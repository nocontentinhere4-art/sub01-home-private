"""Restore only the independently authenticated saved ActualHome in the warm Editor."""
import hashlib
import json
import os
import time
from pathlib import Path

MAP = '/Game/Sub01Home/ActualHome'
EXPECTED_SAVED_SHA = '461b78b1c419ec5587f9f28c9b30e960172a91be9848edc7322ad1c96a9c7c23'


def run(u=None):
    if u is None:
        import unreal as u
    from unreal_import_reference_dressing import fingerprint
    project = Path(u.Paths.project_dir())
    path = project/'Content/Sub01Home/ActualHome.umap'
    before_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if before_sha != EXPECTED_SAVED_SHA:
        raise RuntimeError('Actual saved accepted kitchen/home bytes changed; recovery refused')
    safety = json.loads((project/'private-audit/office44-saved-map-preservation.json').read_text())
    if not safety['matches_pre_office'] or safety['sha256'] != before_sha:
        raise RuntimeError('Independent accepted pre-office map preservation receipt absent')
    current = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not current or current.get_path_name().split('.', 1)[0] != MAP:
        raise RuntimeError('Actual private home Editor world required')
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    before = fingerprint(u, actors.get_all_level_actors())
    output = project/'private-audit'
    (output/'office44-before-saved-recovery-fingerprint.json').write_text(json.dumps(before, indent=2)+'\n')
    # This known Editor API discards only the unsaved failed office activation.
    # It does not replace assets, restart the Editor, or alter the preserved map.
    restored = u.EditorLoadingAndSavingUtils.load_map(MAP)
    if not restored:
        raise RuntimeError('Actual saved home reload refused')
    after = fingerprint(u, actors.get_all_level_actors())
    if hashlib.sha256(path.read_bytes()).hexdigest() != before_sha:
        raise RuntimeError('Saved home unexpectedly changed during read-only reload')
    changes = {key: {'before_recovery': before.get(key), 'saved_baseline': after.get(key)}
               for key in sorted(set(before)|set(after)) if before.get(key) != after.get(key)}
    (output/'office44-after-saved-recovery-fingerprint.json').write_text(json.dumps(after, indent=2)+'\n')
    (output/'office44-rollback-versus-saved-differences.json').write_text(json.dumps(changes, indent=2)+'\n')
    report = {'schema': 'sub01.saved-home-warm-recovery.v1', 'epoch': time.time(),
              'editor_pid': os.getpid(), 'saved_sha256': before_sha,
              'same_editor': True, 'map_saved': False, 'assets_deleted': False,
              'actors_before': len(before), 'actors_after': len(after),
              'rollback_fingerprint_difference_count': len(changes),
              'changed_actor_paths': list(changes), 'native_game_accepted': False}
    (output/'office44-saved-home-warm-recovery.json').write_text(json.dumps(report, indent=2)+'\n')
    return report
