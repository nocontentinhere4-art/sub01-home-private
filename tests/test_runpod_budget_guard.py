import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("budget_guard",Path(__file__).resolve().parents[1]/"scripts/runpod-budget-guard.py")
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)

class BudgetGuardTest(unittest.TestCase):
    def run_guard(self, pod=None, state=None, stop=None):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/"private").mkdir();(root/"logs").mkdir()
            (root/"private/control.json").write_text(json.dumps({"api_key":"test-only","pod_id":pod or guard.POD}))
            (root/"logs/budget-20261013-deadline").write_text("1")
            responses=[{"pod":state or {"id":guard.POD,"name":"sub01-unreal-preview-migration","desiredStatus":"RUNNING"}}]
            responses.extend(stop or [{"podStop":{"id":guard.POD,"desiredStatus":"EXITED"}}])
            with patch.object(guard,"ROOT",root),patch.object(guard,"api",side_effect=responses) as api,patch.object(guard.time,"sleep"),patch.object(guard.sys,"argv",["guard"]),patch.dict(guard.os.environ,{"RUNPOD_POD_ID":guard.POD}):
                try:guard.main()
                finally:self.calls=api.call_args_list
    def test_expired_deadline_stops_only_bound_pod(self):
        self.run_guard()
        self.assertEqual(len(self.calls),2)
        self.assertIn('podStop',self.calls[-1].args[1])
        self.assertIn(guard.POD,self.calls[-1].args[1])
    def test_other_pod_is_rejected_without_api_call(self):
        with self.assertRaisesRegex(RuntimeError,"Unauthorized pod"):self.run_guard(pod="other-brain-pod")
        self.assertEqual(self.calls,[])
    def test_wrong_identity_never_stops(self):
        with self.assertRaisesRegex(RuntimeError,"Unexpected pod identity"):
            self.run_guard(state={"id":guard.POD,"name":"other-brain","desiredStatus":"RUNNING"})
        self.assertEqual(len(self.calls),1)
    def test_transient_stop_error_retries(self):
        self.run_guard(stop=[TimeoutError(),{"podStop":{"id":guard.POD,"desiredStatus":"EXITED"}}])
        self.assertEqual(len(self.calls),3)

if __name__=="__main__":unittest.main()
