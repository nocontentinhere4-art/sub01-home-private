import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('handoff',Path(__file__).parents[1]/'tools/private_playable_handoff.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_read_exact_constants_without_executing_policy():
 text="PROJECT='/private/home.uproject'\nNATIVE_PID=123\nNATIVE_START_TICKS=456\nraise RuntimeError('must never execute')\n"
 assert m.consumer_policy_constants(text)=={'PROJECT':'/private/home.uproject','NATIVE_PID':123,'NATIVE_START_TICKS':456}
@pytest.mark.parametrize('text',["PROJECT='/x'\nNATIVE_PID=123\nNATIVE_START_TICKS=456\nNATIVE_PID=124", "PROJECT='/x'\nNATIVE_PID=True\nNATIVE_START_TICKS=456", "PROJECT=discover_project()\nNATIVE_PID=123\nNATIVE_START_TICKS=456"])
def test_duplicate_computed_or_boolean_consumer_pins_are_not_proof(text):
 with pytest.raises((AssertionError,ValueError)):m.consumer_policy_constants(text)
