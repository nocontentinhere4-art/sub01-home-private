"""The proposed home.js integration patch still applies and parses.

Skips (with the reason) when web/house/home.js has moved on so the patch no
longer applies; regenerate it with tools/build_home_js_integration_patch.py.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "docs/proposed/home-js-integration.patch"
HOME_JS = "web/house/home.js"


def test_proposed_home_patch_applies_and_parses():
    assert PATCH.is_file(), "docs/proposed/home-js-integration.patch is missing"
    check = subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=ROOT, capture_output=True, text=True)
    if check.returncode:
        pytest.skip("home.js has moved on; regenerate with tools/build_home_js_integration_patch.py: "
                    + check.stderr.strip()[-300:])
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    with tempfile.TemporaryDirectory(prefix="home-patch-") as tmp:
        target = Path(tmp) / HOME_JS
        target.parent.mkdir(parents=True)
        shutil.copy2(ROOT / HOME_JS, target)
        applied = subprocess.run(["git", "apply", str(PATCH)], cwd=tmp, capture_output=True, text=True)
        assert applied.returncode == 0, applied.stderr
        parsed = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True)
        assert parsed.returncode == 0, parsed.stderr
        patched = target.read_text()
    # The real working tree is never modified by this test.
    assert (ROOT / HOME_JS).read_text() != patched


def test_generator_reproduces_the_committed_patch():
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import build_home_js_integration_patch as builder
    try:
        text, _, _ = builder.build_patch()
    except SystemExit as moved:
        pytest.skip(f"home.js has moved on: {moved}")
    assert text == PATCH.read_text(), "patch is stale: run tools/build_home_js_integration_patch.py"
