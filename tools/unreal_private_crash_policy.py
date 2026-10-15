"""Apply only the verified private unattended crash-report policy in the warm Editor."""
import configparser
import json
import os
import time
from pathlib import Path

SETTINGS = Path('/home/unreal/.config/Epic/UnrealEngine/5.8/Saved/Config/LinuxEditor/EditorSettings.ini')
SECTION = '/Script/UnrealEd.CrashReportsPrivacySettings'
COMMAND = 'RELOADCONFIG CrashReportsPrivacySettings'


def disk_disabled():
    config = configparser.ConfigParser(strict=False, interpolation=None)
    config.read(SETTINGS)
    return config.getboolean(SECTION, 'bSendUnattendedBugReports', fallback=True) is False


def run(u=None):
    if u is None:
        import unreal as u
    if not disk_disabled():
        raise RuntimeError('Verified current EditorSettings must explicitly disable unattended reports first')
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.', 1)[0] != '/Game/Sub01Home/ActualHome':
        raise RuntimeError('Actual warm private Editor world required')
    cls = u.load_class(None, '/Script/UnrealEd.CrashReportsPrivacySettings')
    if not cls:
        raise RuntimeError('Actual reflected crash privacy class unavailable')
    default = u.get_default_object(cls)
    before = bool(default.get_editor_property('send_unattended_bug_reports'))
    # set_editor_property notifies the verified PostEditChangeProperty delegate.
    default.set_editor_property('send_unattended_bug_reports', False)
    if default.get_editor_property('send_unattended_bug_reports'):
        raise RuntimeError('Actual crash privacy CDO refused the owned setting')
    # Do not mistake a void Blueprint command request for actual Editor Exec.
    # Record the installed reflected APIs before choosing a proven execution path.
    apis = {}
    for name in ('EditorLevelLibrary', 'LevelEditorSubsystem', 'UnrealEditorSubsystem'):
        cls_api = getattr(u, name, None)
        apis[name] = {n: str(getattr(cls_api, n).__doc__)[:1800]
                     for n in dir(cls_api) if 'console' in n.lower() or 'exec' in n.lower()}
    after = bool(default.get_editor_property('send_unattended_bug_reports'))
    if after or not disk_disabled():
        raise RuntimeError('Actual reloaded crash privacy setting is not disabled')
    report = {'schema': 'sub01.private-editor-crash-policy.v1', 'editor_pid': os.getpid(),
              'applied_epoch': time.time(), 'class': cls.get_path_name(),
              'previous_send_unattended_bug_reports': before,
              'current_send_unattended_bug_reports': after,
              'disk_explicitly_disabled': True, 'fixed_reload_command': COMMAND,
              'cache_reload_requested': False, 'cache_reload_execution_verified': False,
              'reflected_editor_command_apis': apis, 'crash_triggered_for_test': False,
              'scene_mutations': 0, 'native_game_accepted': False}
    path = Path(u.Paths.project_dir())/'private-audit/private-editor-crash-policy.json'
    path.write_text(json.dumps(report, indent=2)+'\n')
    return report
