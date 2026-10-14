"""Quarantine only this project's stale discovery caches after verified migration.

Dry-run is the default. This does not repair or validate engine bytes, build the
project, or authorize server startup. Readiness is an extraction attestation.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import uuid


CACHE_PATHS = (
    Path("Intermediate/Build/Linux/x64/Sub01HomeLabEditor/Development/Makefile.bin"),
    Path("Intermediate/Build/SourceFileCache.bin"),
    Path("Intermediate/Build/Linux/Sub01HomeLabEditor/Sub01HomeLabEditor.uhtmanifest"),
)


def validate_readiness(proof, engine_root):
    """Validate the producer's explicit complete-engine attestation, not existence."""
    if not isinstance(proof, dict) or proof.get("schema") != "sub01.unreal-engine-readiness.v1":
        raise ValueError("Expected complete-engine readiness attestation")
    if proof.get("engine_version") != "5.8.3":
        raise ValueError("This recovery is scoped to the actual Unreal 5.8.3 engine")
    if proof.get("engine_root") != str(Path(engine_root).resolve()):
        raise ValueError("Readiness belongs to another engine root")
    for key in ("archive_sha256_verified", "all_selected_members_crc_verified",
                "original_critical_mtimes_restored"):
        if proof.get(key) is not True:
            raise ValueError(f"Engine prerequisite not verified: {key}")
    expected = proof.get("expected_selected_members")
    verified = proof.get("crc_verified_selected_members")
    if type(expected) is not int or expected <= 0 or type(verified) is not int or verified != expected:
        raise ValueError("Partial extraction cannot authorize cache quarantine")
    archive_hash = proof.get("archive_sha256")
    if not isinstance(archive_hash, str) or len(archive_hash) != 64 or any(c not in "0123456789abcdef" for c in archive_hash):
        raise ValueError("Missing verified archive SHA-256 identity")
    return proof


def _safe_cache(project, relative):
    path = project / relative
    # A symlinked Intermediate directory could otherwise reach Engine or Content.
    cursor = project
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"Symlinked project cache refused: {relative}")
    if path.exists() and not path.is_file():
        raise ValueError(f"Non-file project cache refused: {relative}")
    return path


def quarantine(project, *, apply=False, readiness=None, engine_root=None):
    project = Path(project).resolve(strict=True)
    if not (project / "Sub01HomeLab.uproject").is_file():
        raise ValueError("Expected the actual Sub01HomeLab project root")
    paths = [_safe_cache(project, relative) for relative in CACHE_PATHS]
    if apply:
        if engine_root is None:
            raise ValueError("Explicit engine root and verified readiness required")
        validate_readiness(readiness, engine_root)
        # Avoid applying after a failed/stale migration whose engine is absent.
        engine = Path(engine_root).resolve(strict=True)
        if not (engine / "Engine/Build/Build.version").is_file():
            raise ValueError("Attested engine root is absent")
    report = {"mode": "apply" if apply else "dry-run", "project": str(project),
              "runtime_ready": False, "compile_verified": False, "caches": []}
    suffix = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex
    for relative, path in zip(CACHE_PATHS, paths):
        item = {"path": str(relative), "status": "missing"}
        if path.exists():
            item["status"] = "would-quarantine"
            if apply:
                backup = path.with_name(path.name + ".quarantined-" + suffix)
                # Hard-link is exclusive: existing backups cannot be overwritten.
                # Unlink only after preservation succeeds; no deletion on failure.
                os.link(path, backup, follow_symlinks=False)
                try:
                    path.unlink()
                except Exception:
                    # Preserve both names if removal fails. Never delete evidence.
                    raise
                item.update(status="quarantined", backup=str(backup.relative_to(project)))
        report["caches"].append(item)
    report["next_build_flag"] = "-NoUBTMakefiles"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--engine-root", type=Path)
    parser.add_argument("--readiness", type=Path, help="Private extraction attestation JSON; mandatory for apply")
    args = parser.parse_args()
    proof = json.loads(args.readiness.read_text()) if args.readiness else None
    print(json.dumps(quarantine(args.project, apply=args.apply, readiness=proof, engine_root=args.engine_root), indent=2))


if __name__ == "__main__":
    main()
