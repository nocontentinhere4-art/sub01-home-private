import importlib.util
import json
import stat
import types
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location('private_editor_launcher', Path(__file__).parents[1] / 'tools/launch_private_persistent_editor.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

class VerifiedEditorWindowTests(unittest.TestCase):
    def check_window(self, **changes):
        window = dict(pod=launcher.POD, deadline_epoch=1792117175,
                      total_cap=100, minimum_balance_reserve=10, initial_actual_balance=91.67,
                      stop_guards_authenticated=True, root_guard_authenticated=True,
                      root_guard_pid=145, external_guard_pid=24619, second_external_guard_pid=24622)
        window.update(changes)
        guard = Mock()
        guard.parent.lstat.return_value = types.SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o755)
        metadata = types.SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o644, st_nlink=1)
        with patch.object(launcher.os, 'open', return_value=8), patch.object(launcher.os, 'fstat', return_value=metadata), patch.object(launcher.os, 'read', return_value=json.dumps(window).encode()), patch.object(launcher.os, 'close'), patch.object(launcher.os, 'kill'), patch.object(launcher.time, 'time', return_value=1792032000):
            return launcher.verified_window(guard)

    def test_current_continuous_window_is_read_dynamically(self):
        self.assertEqual(self.check_window(deadline_epoch=1792117100)['deadline_epoch'], 1792117100)

    def test_retired_pod_cannot_launch(self):
        with self.assertRaises(AssertionError):
            self.check_window(pod='kjsxms1gk4rmv6')

    def test_expired_or_extended_window_cannot_launch(self):
        for deadline in (1792031000, 1792117176):
            with self.subTest(deadline=deadline), self.assertRaises(AssertionError):
                self.check_window(deadline_epoch=deadline)

    def test_reserve_and_guard_authentication_are_required(self):
        for change in ({'minimum_balance_reserve': 0}, {'stop_guards_authenticated': False}, {'root_guard_authenticated': False}, {'second_external_guard_pid': 0}):
            with self.subTest(change=change), self.assertRaises(AssertionError):
                self.check_window(**change)

if __name__ == '__main__':
    unittest.main()
