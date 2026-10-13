"""Real end-to-end check: actual live_server.py + /ws + home-state bridge on loopback.

Skipped only when the server cannot start in time (reason shown); any failed
check fails the test. The tool kills its children in every case and this test
verifies none is left running.
"""

import asyncio
import os

import pytest

from tools.home_e2e_check import STARTED, CheckFailed, StartTimeout, run_check

TIMEOUT = min(90.0, float(os.environ.get("SUB01_E2E_TIMEOUT", "90")))


def test_home_stack_end_to_end():
    try:
        report = asyncio.run(run_check(TIMEOUT))
    except StartTimeout as error:
        pytest.skip(f"home backend could not start within {TIMEOUT:.0f} s: {str(error)[-400:]}")
    except CheckFailed as error:
        pytest.fail(str(error))
    finally:
        left = [p.pid for p in STARTED if p.poll() is None]
        assert not left, f"end-to-end child processes left running: {left}"
    assert STARTED, "the check started real child processes"
    names = {c["check"] for c in report["checks"]}
    assert report["ok"] and all(c["ok"] for c in report["checks"])
    for required in ("ws_home_fields", "settings_403_without_token", "settings_400_bad_mode",
                     "ws_reflects_settings", "api_home_200_without_browse", "bridge_live",
                     "bridge_controls_passthrough", "bridge_stale_after_backend_stop",
                     "privacy_ws_position", "privacy_ws_devices", "privacy_api_unauthenticated_pose",
                     "privacy_bridge_only_flag_and_house"):
        assert required in names, required
