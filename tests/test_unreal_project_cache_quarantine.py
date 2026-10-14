import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("cache_quarantine", Path(__file__).resolve().parents[1] / "tools/quarantine_unreal_project_cache.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProjectCacheRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "Sub01HomeLab.uproject").write_text("actual project sentinel")
        self.engine = self.root / "UE"
        (self.engine / "Engine/Build").mkdir(parents=True)
        (self.engine / "Engine/Build/Build.version").write_text("official engine sentinel")
        self.proof = dict(schema="sub01.unreal-engine-readiness.v1", engine_version="5.8.3",
                          engine_root=str(self.engine.resolve()), archive_sha256="a" * 64,
                          archive_sha256_verified=True, all_selected_members_crc_verified=True,
                          original_critical_mtimes_restored=True, expected_selected_members=294043,
                          crc_verified_selected_members=294043)
        for relative in module.CACHE_PATHS:
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"stale discovery " + bytes(str(relative), "utf8"))
        for relative in ("Content/map.uasset", "Config/DefaultEngine.ini", "Binaries/native.so",
                         "Intermediate/Build/keep-other-target.bin"):
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"must remain exact")

    def tree(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_default_dry_run_mutates_nothing(self):
        before = self.tree()
        report = module.quarantine(self.project)
        self.assertEqual(self.tree(), before)
        self.assertEqual([x["status"] for x in report["caches"]], ["would-quarantine"] * 3)

    def test_apply_preserves_exact_bytes_and_only_three_caches(self):
        before = self.tree()
        report = module.quarantine(self.project, apply=True, readiness=self.proof, engine_root=self.engine)
        for item in report["caches"]:
            original = self.project / item["path"]
            self.assertFalse(original.exists())
            backup = self.project / item["backup"]
            self.assertEqual(backup.read_bytes(), before[str(original.relative_to(self.root))])
        for name, data in before.items():
            if name not in {"project/" + str(p) for p in module.CACHE_PATHS}:
                self.assertEqual((self.root / name).read_bytes(), data)
        self.assertFalse(report["runtime_ready"])
        self.assertFalse(report["compile_verified"])
        repeated = module.quarantine(self.project, apply=True, readiness=self.proof, engine_root=self.engine)
        self.assertEqual([x["status"] for x in repeated["caches"]], ["missing"] * 3)

    def test_partial_or_other_engine_readiness_refused_before_mutation(self):
        for changes in ({"crc_verified_selected_members": 1}, {"all_selected_members_crc_verified": False},
                        {"archive_sha256_verified": 1}, {"original_critical_mtimes_restored": False},
                        {"engine_root": str(self.root / "other")}, {"expected_selected_members": True},
                        {"archive_sha256": "unknown"}):
            with self.subTest(changes=changes):
                before = self.tree()
                with self.assertRaises(ValueError):
                    module.quarantine(self.project, apply=True, readiness=self.proof | changes, engine_root=self.engine)
                self.assertEqual(self.tree(), before)
        with self.assertRaises(ValueError):
            module.quarantine(self.project, apply=True)

    def test_symlink_into_engine_refused_and_engine_untouched(self):
        path = self.project / module.CACHE_PATHS[0]
        path.unlink()
        path.symlink_to(self.engine / "Engine/Build/Build.version")
        with self.assertRaises(ValueError):
            module.quarantine(self.project, apply=True, readiness=self.proof, engine_root=self.engine)
        self.assertEqual((self.engine / "Engine/Build/Build.version").read_text(), "official engine sentinel")

    def test_nonfile_refused_before_first_move(self):
        path = self.project / module.CACHE_PATHS[2]
        path.unlink()
        path.mkdir()
        first = self.project / module.CACHE_PATHS[0]
        with self.assertRaises(ValueError):
            module.quarantine(self.project, apply=True, readiness=self.proof, engine_root=self.engine)
        self.assertTrue(first.is_file())

    def test_parent_symlink_cannot_reach_outside_project(self):
        parent = self.project / "Intermediate/Build/Linux"
        saved = parent.with_name("Linux-original")
        parent.rename(saved)
        parent.symlink_to(saved, target_is_directory=True)
        with self.assertRaises(ValueError):
            module.quarantine(self.project)
        self.assertTrue((saved / "x64/Sub01HomeLabEditor/Development/Makefile.bin").is_file())

    def test_backup_failure_never_unlinks_original(self):
        before = self.tree()
        with patch.object(module.os, "link", side_effect=FileExistsError("backup exists")):
            with self.assertRaises(FileExistsError):
                module.quarantine(self.project, apply=True, readiness=self.proof, engine_root=self.engine)
        self.assertEqual(self.tree(), before)


if __name__ == "__main__":
    unittest.main()
