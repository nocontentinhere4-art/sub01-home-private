from pathlib import Path
import pytest
from tools.launch_private_persistent_editor import verified_private_crash_preference


def test_actual_base_layer_must_explicitly_disable_reports(tmp_path):
    path = tmp_path / 'Engine/Config/BaseEditorSettings.ini'
    path.parent.mkdir(parents=True)
    for value in ('True', 'False'):
        path.write_text('[/Script/UnrealEd.CrashReportsPrivacySettings]\nbSendUnattendedBugReports='+value+'\n')
        if value == 'True':
            with pytest.raises(AssertionError):
                verified_private_crash_preference(tmp_path)
        else:
            assert verified_private_crash_preference(tmp_path) == path


def test_missing_active_preference_refuses_even_if_other_file_false(tmp_path):
    (tmp_path / 'EditorSettings.ini').write_text('[/Script/UnrealEd.CrashReportsPrivacySettings]\nbSendUnattendedBugReports=False\n')
    with pytest.raises(AssertionError):
        verified_private_crash_preference(tmp_path)
