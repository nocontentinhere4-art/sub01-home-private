"""Build and verify the consolidated home.js integration patch (never edits home.js).

The repository's web/house/home.js is owned by Codex and may carry local work.
This tool copies it to a temporary directory, applies each proposed hunk to the
COPY with exact, unique anchors, and writes the result as a repo-relative
`git diff` to docs/proposed/home-js-integration.patch.

    python tools/build_home_js_integration_patch.py            # write the patch
    python tools/build_home_js_integration_patch.py --check    # patch up to date?
    python tools/build_home_js_integration_patch.py --verify   # apply + node checks
                                                               # in a temp copy

--verify copies the repository files (assets symlinked) into a temporary
directory, runs `git apply --check` and `node --check`, then runs the node
checks that read home.js on the unpatched and the patched copy and reports any
check whose result changed. The real working tree is never touched.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME_JS = "web/house/home.js"
PATCH = ROOT / "docs/proposed/home-js-integration.patch"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from home_js_integration_edits import EDITS  # noqa: E402


def apply_edits(text):
    applied = []
    original = text
    for hid, title, source, anchor, replacement in EDITS:
        count = text.count(anchor)
        if count != 1 or original.count(anchor) != 1:
            raise SystemExit(f"{hid} ({title}): anchor found {count} times; home.js has moved on")
        start = original.index(anchor)   # line numbers refer to the unpatched home.js
        line = original.count("\n", 0, start) + 1
        text = text.replace(anchor, replacement, 1)
        applied.append({"id": hid, "title": title, "source": source,
                        "original_lines": [line, line + anchor.count("\n") - 1]})
    return text, applied


def build_patch(home_text=None):
    original = home_text if home_text is not None else (ROOT / HOME_JS).read_text()
    patched, applied = apply_edits(original)
    with tempfile.TemporaryDirectory(prefix="home-js-patch-") as tmp:
        a, b = Path(tmp, "a.js"), Path(tmp, "b.js")
        a.write_text(original)
        b.write_text(patched)
        diff = subprocess.run(["git", "diff", "--no-index", "--no-color", "-U3", str(a), str(b)],
                              capture_output=True, text=True)
    if diff.returncode not in (0, 1):
        raise SystemExit(diff.stderr)
    lines = diff.stdout.splitlines(keepends=True)
    body = [line for line in lines if not line.startswith(("diff --git", "index ", "--- ", "+++ "))]
    header = [f"diff --git a/{HOME_JS} b/{HOME_JS}\n", f"--- a/{HOME_JS}\n", f"+++ b/{HOME_JS}\n"]
    return "".join(header + body), patched, applied


def run(cmd, cwd, timeout=120, env=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, (r.stdout + r.stderr)[-20000:]
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def summary(output):
    """The first error/assertion line of a failed check (for the report)."""
    for line in output.splitlines():
        if any(word in line for word in ("Error", "assert", "FAIL", "Missing")):
            return line.strip()[:240]
    return output.strip().splitlines()[-1][:240] if output.strip() else ""


PY_TESTS = ("tests/test_assemble_home_blender.py", "tests/test_home_asset_audit.py",
            "tests/test_home_bath_fixtures.py", "tests/test_home_bath_light_door.py",
            "tests/test_home_daytime_fixture.py", "tests/test_home_world.py")


def pytest_failures(dest, env):
    code, out = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *PY_TESTS],
                    dest, timeout=600, env=env)
    full = out
    return code, sorted({line.split(" ")[1] for line in full.splitlines() if line.startswith("FAILED ")})


def node_checks():
    found = []
    for path in sorted((ROOT / "tests/js").iterdir()):
        if path.suffix not in (".mjs", ".js", ".cjs"):
            continue
        text = path.read_text(errors="replace")
        if "home.js" in text or path.name in ("house_interactions_check.mjs", "house_controls_panel_check.mjs",
                                              "replaced_primitives_check.mjs", "furnishing_detail_check.mjs",
                                              "bath_fixture_materials_check.mjs"):
            found.append(path.relative_to(ROOT).as_posix())
    return found


def temp_copy(dest):
    files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.splitlines()
    for rel in files:
        if rel.startswith("web/house/assets/") or rel.startswith("out/"):
            continue
        src = ROOT / rel
        if not src.is_file():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    (dest / "web/house/assets").symlink_to(ROOT / "web/house/assets")
    # Node resolution for bare 'three' imports, from the vendored build only.
    three = dest / "node_modules/three"
    (three / "build").mkdir(parents=True)
    (three / "addons").mkdir()
    vendor = ROOT / "web/house/vendor"
    for name in ("three.module.js", "three.core.js"):
        shutil.copy2(vendor / name, three / "build" / name)
    addons = {"loaders/GLTFLoader.js": "GLTFLoader.js", "loaders/HDRLoader.js": "HDRLoader.js",
              "exporters/GLTFExporter.js": "GLTFExporter.js", "environments/RoomEnvironment.js": "RoomEnvironment.js",
              "utils/BufferGeometryUtils.js": "BufferGeometryUtils.js", "geometries/RoundedBoxGeometry.js": "RoundedBoxGeometry.js"}
    for name in set(addons.values()):
        shutil.copy2(vendor / name, three / "addons" / name)
    (three / "package.json").write_text(json.dumps({
        "name": "three", "type": "module",
        "exports": {".": "./build/three.module.js", **{f"./addons/{k}": f"./addons/{v}" for k, v in addons.items()}}}))


def verify(patch_text):
    report = {"apply_check_repo": None, "node_check": None, "checks": {}}
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as f:
        f.write(patch_text)
        patch_file = f.name
    try:
        code, out = run(["git", "apply", "--check", patch_file], ROOT)
        report["apply_check_repo"] = {"ok": code == 0, "output": out.strip()}
        with tempfile.TemporaryDirectory(prefix="home-js-verify-") as tmp:
            dest = Path(tmp)
            temp_copy(dest)
            env = {**os.environ, "SUB01_TEST_PYTHON": sys.executable}
            checks = node_checks()
            baseline = {c: run(["node", c], dest, env=env) for c in checks}
            py_before = pytest_failures(dest, env)
            code, out = run(["git", "apply", patch_file], dest)
            if code:
                raise SystemExit("patch does not apply to the temp copy: " + out)
            code, out = run(["node", "--check", HOME_JS], dest)
            report["node_check"] = {"ok": code == 0, "output": out.strip()}
            for c in checks:
                after = run(["node", c], dest, env=env)
                report["checks"][c] = {"baseline": baseline[c][0] == 0, "patched": after[0] == 0,
                                       **({"patched_error": summary(after[1])} if after[0] else {}),
                                       **({"baseline_error": summary(baseline[c][1])} if baseline[c][0] else {})}
            py_after = pytest_failures(dest, env)
            report["python"] = {"files": list(PY_TESTS), "failed_before": py_before[1], "failed_after": py_after[1],
                                "new_failures": sorted(set(py_after[1]) - set(py_before[1]))}
    finally:
        os.unlink(patch_file)
    report["regressions"] = [c for c, r in report["checks"].items() if r["baseline"] and not r["patched"]]
    # Expected, documented in docs/proposed/README.md (H6 removes the audited boxes).
    expected = {"tests/test_home_asset_audit.py::test_balcony_boxes_measured_against_actual_chair"}
    report["python"]["unexpected_new_failures"] = sorted(set(report["python"]["new_failures"]) - expected)
    report["ok"] = bool(report["apply_check_repo"]["ok"] and report["node_check"]["ok"] and not report["regressions"]
                        and not report["python"]["unexpected_new_failures"])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if the committed patch is stale")
    parser.add_argument("--verify", action="store_true", help="apply in a temp copy and run node checks")
    args = parser.parse_args(argv)
    patch_text, _, applied = build_patch()
    if args.check:
        same = PATCH.is_file() and PATCH.read_text() == patch_text
        print(json.dumps({"up_to_date": same}))
        return 0 if same else 1
    if args.verify:
        report = verify(PATCH.read_text() if PATCH.is_file() else patch_text)
        print(json.dumps(report, indent=1))
        return 0 if report["ok"] else 1
    PATCH.parent.mkdir(parents=True, exist_ok=True)
    PATCH.write_text(patch_text)
    print(json.dumps({"written": PATCH.relative_to(ROOT).as_posix(), "hunks": applied}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
