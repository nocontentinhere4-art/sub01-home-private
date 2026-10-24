"""Fetch pinned guest ROM/kernel assets from official upstream; never mount host files in the VM.

    python computer/bootstrap.py            # verify / download into computer/ (the bundled location)
    python computer/bootstrap.py DEST       # ... into DEST (the server uses <data-dir>/computer-assets)
    python computer/bootstrap.py --status   # say what is installed, download nothing (exit 1 when incomplete)

The three `.bin` files (SeaBIOS, VGA BIOS, the Buildroot Linux kernel image) are gitignored: a fresh clone has none
of them. The server fetches them itself on start into <data-dir>/computer-assets when the network allows (about 5.3 MB
from copy.sh); without network, run this once from a machine that has it, or copy the three files into computer/.
"""

import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GUEST = [
    a
    for a in json.loads((ROOT / "manifest.json").read_text())
    if a["file"].endswith(".bin")
]
RUN_HINT = "run `python computer/bootstrap.py` once (downloads the pinned v86 BIOS and Buildroot Linux image)"


def valid(file, asset):
    return (
        file.is_file()
        and file.stat().st_size == asset["bytes"]
        and hashlib.sha256(file.read_bytes()).hexdigest() == asset["sha256"]
    )


def status(destination=None):
    """What is installed, without touching the network: {"installed": bool, "source": "bundled" | "cache" | None,
    "missing": [file, ...]} (the missing files of the better of the two locations)."""
    locations = [("bundled", ROOT)] + ([("cache", Path(destination))] if destination else [])
    best = None
    for name, folder in locations:
        missing = [a["file"] for a in GUEST if not valid(folder / a["file"], a)]
        if not missing:
            return {"installed": True, "source": name, "missing": [], "path": str(folder)}
        if best is None or len(missing) < len(best["missing"]):
            best = {"installed": False, "source": None, "missing": missing, "path": str(folder)}
    return best


def describe(st):
    """One honest line for logs and the house page from status() (the fix is RUN_HINT, kept apart)."""
    if st["installed"]:
        return f"Linux guest installed ({st['source']} assets in {st['path']})"
    n = len(st["missing"])
    return f"Linux guest not installed: {n} of {len(GUEST)} pinned files missing ({', '.join(st['missing'])})"


def ensure(destination, prefer_bundled=True):
    destination = Path(destination)
    if prefer_bundled and all(valid(ROOT / a["file"], a) for a in GUEST):
        return ROOT
    destination.mkdir(parents=True, exist_ok=True)
    for a in GUEST:
        file = destination / a["file"]
        if valid(file, a):
            continue
        request = urllib.request.Request(
            a["source"], headers={"User-Agent": "SUB01-Home/1.0"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(a["bytes"] + 1)
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            # A plain reason (no network, DNS, a proxy refusing): the server shows it instead of a generic failure.
            reason = getattr(error, "reason", None) or error
            raise RuntimeError(f"Could not download {a['file']} from {a['source']}: {str(reason)[:120]}") from error
        if len(data) != a["bytes"] or hashlib.sha256(data).hexdigest() != a["sha256"]:
            raise RuntimeError(
                "Upstream guest asset differs from pinned version: " + a["file"]
            )
        temporary = file.with_suffix(".download")
        temporary.write_bytes(data)
        temporary.replace(file)
    return destination


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if "--status" in sys.argv[1:]:
        st = status(args[0] if args else None)
        print(describe(st) if st["installed"] else describe(st) + "; " + RUN_HINT)
        sys.exit(0 if st["installed"] else 1)
    where = ensure(args[0] if args else ROOT)
    print(f"Pinned Linux guest and BIOS assets verified in {where}")
