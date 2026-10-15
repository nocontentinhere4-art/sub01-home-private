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
    property_name = None
    for candidate in ('send_unattended_bug_reports', 'bSendUnattendedBugReports'):
        try:
            before = bool(default.get_editor_property(candidate))
            property_name = candidate
            break
        except Exception:
            continue
    if property_name is None:
        raise RuntimeError('Actual source-defined crash privacy property is unavailable')
    # set_editor_property notifies the verified PostEditChangeProperty delegate.
    default.set_editor_property(property_name, False)
    if default.get_editor_property(property_name):
        raise RuntimeError('Actual crash privacy CDO refused the owned setting')
    marker = str(time.time_ns())
    begin = 'SUB01_PRIVATE_CRASH_RELOAD_BEGIN_'+marker
    end = 'SUB01_PRIVATE_CRASH_RELOAD_END_'+marker
    u.log(begin)
    # Actual UE5.8 KismetSystemLibrary.cpp falls back to GEngine->Exec with no PC.
    # GetIni reads GConfig and prints final cached values after static layers.
    u.SystemLibrary.execute_console_command(world, COMMAND)
    u.SystemLibrary.execute_console_command(world, 'GetIni EditorSettings:/Script/UnrealEd.CrashReportsPrivacySettings bSendUnattendedBugReports')
    u.log(end)
    after = bool(default.get_editor_property(property_name))
    if after or not disk_disabled():
        raise RuntimeError('Actual reloaded crash privacy setting is not disabled')
    report = {'schema': 'sub01.private-editor-crash-policy.v1', 'editor_pid': os.getpid(),
              'applied_epoch': time.time(), 'class': cls.get_path_name(),
              'property_name': property_name,
              'previous_send_unattended_bug_reports': before,
              'current_send_unattended_bug_reports': after,
              'disk_explicitly_disabled': True, 'fixed_reload_command': COMMAND,
              'cache_reload_requested': True, 'cache_reload_execution_verified': False,
              'cached_getini_readback_requested': True, 'log_begin_marker': begin,
              'log_end_marker': end, 'crash_triggered_for_test': False,
              'scene_mutations': 0, 'native_game_accepted': False}
    path = Path(u.Paths.project_dir())/'private-audit/private-editor-crash-policy.json'
    path.write_text(json.dumps(report, indent=2)+'\n')
    return report
