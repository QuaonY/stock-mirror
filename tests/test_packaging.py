import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.package_skill import ROOT, build_archive, collect_package_files


class PackagingTests(unittest.TestCase):
    def test_allowlist_includes_skill_files_but_excludes_runtime_state(self):
        names = {
            path.relative_to(ROOT).as_posix() for path in collect_package_files(ROOT)
        }
        self.assertIn("SKILL.md", names)
        self.assertIn("LICENSE", names)
        self.assertIn("assets/icon.jpg", names)
        self.assertIn("scripts/run_pipeline.py", names)
        self.assertIn("state/account_state.example.json", names)
        self.assertNotIn("scripts/package_skill.py", names)
        self.assertNotIn(".gitignore", names)
        self.assertNotIn("DEVELOPMENT_PLAN.md", names)
        self.assertNotIn("RELEASE_CHECKLIST.md", names)
        self.assertNotIn("state/account_state.json", names)
        self.assertNotIn("state/trade-ledger.csv", names)
        self.assertFalse(any(name.startswith(("state/audit/", "state/pipeline/")) for name in names))
        self.assertFalse(any(name.startswith("tests/") for name in names))
        self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))

    def test_archive_contains_only_allowlisted_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "StockMirror.zip"
            expected = set(build_archive(output, ROOT))
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(expected, set(archive.namelist()))
                self.assertNotIn("state/account_state.json", archive.namelist())
                self.assertNotIn("state/trade-ledger.csv", archive.namelist())


if __name__ == "__main__":
    unittest.main()
