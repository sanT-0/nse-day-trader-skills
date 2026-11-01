from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tests.helpers import ROOT


class StructureTests(unittest.TestCase):
    def test_repository_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "verify_skills.py")],
                cwd=tmp, capture_output=True, text=True, timeout=120,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("12 skills", result.stdout)

    def test_installer_dry_run_includes_router(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "install.py"),
                 "--destination", tmp, "--dry-run"],
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nse-trader ->", result.stdout)
        self.assertIn("12 skills", result.stdout)

    def test_platform_neutral_dispatcher(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run.py"), "--list"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("scanner", result.stdout)
        self.assertIn("ticket", result.stdout)

    def test_portable_zip_contains_skill_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "package_skills.py"),
                 "--skill", "nse-trader", "--out", tmp],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = Path(tmp) / "nse-trader.zip"
            with zipfile.ZipFile(archive) as package:
                names = set(package.namelist())
            self.assertIn("nse-trader/SKILL.md", names)
            self.assertIn("nse-trader/LICENSE", names)
            self.assertTrue((Path(tmp) / "SHA256SUMS").is_file())


if __name__ == "__main__":
    unittest.main()
