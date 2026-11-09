"""The integration launcher must not repurpose or remove an existing cluster."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_isolated_postgres as launcher


class IsolatedPostgresLauncherTests(unittest.TestCase):
    def test_existing_directory_is_refused_before_postgres_commands(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(launcher, "DATA", Path(directory)), \
             patch.object(launcher, "SOCKET", Path(directory) / "missing"), \
             patch.object(launcher.os, "getuid", return_value=1000), \
             patch.object(launcher, "postgres_bin") as binaries, \
             patch.object(launcher.shutil, "rmtree") as remove:
            with self.assertRaisesRegex(RuntimeError, "Refusing existing"):
                launcher.run()
            binaries.assert_not_called()
            remove.assert_not_called()

    def test_existing_opt_in_only_runs_suite_and_never_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "PG_VERSION").write_text("18")
            (root / "socket").touch()
            with patch.object(launcher, "DATA", root), \
                 patch.object(launcher, "SOCKET", root / "socket"), \
                 patch.object(launcher, "run_suite", return_value=7) as suite, \
                 patch.object(launcher, "postgres_bin") as binaries, \
                 patch.object(launcher.shutil, "rmtree") as remove:
                self.assertEqual(launcher.run(existing=True), 7)
                suite.assert_called_once_with()
                binaries.assert_not_called()
                remove.assert_not_called()

    def test_environment_does_not_inherit_application_credentials(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://live", "OPENAI_API_KEY": "real-key",
                                     "GOOGLE_APPLICATION_CREDENTIALS": "/secret.json",
                                     "EXA_API_KEY": "real-exa", "AWS_PROFILE": "personal"}):
            environment = launcher.test_environment()
        self.assertIn("host=/tmp&port=55439", environment["DATABASE_URL"])
        self.assertEqual(environment["OPENAI_API_KEY"], "ci-placeholder")
        for key in ("GOOGLE_APPLICATION_CREDENTIALS", "EXA_API_KEY", "AWS_PROFILE"):
            self.assertNotIn(key, environment)

    def test_expected_suite_skip_is_a_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "skipped_suite.py").write_text(
                "import unittest\nclass Tests(unittest.TestCase):\n"
                " @unittest.skip('unavailable')\n def test_required(self): pass\n")
            environment = {**os.environ, "PYTHONPATH": directory}
            result = subprocess.run([sys.executable, "-c", launcher.RUNNER, "skipped_suite"],
                                    env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Required integration tests were skipped", result.stderr)

    def test_empty_expected_suite_is_a_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "empty_suite.py").write_text("")
            result = subprocess.run([sys.executable, "-c", launcher.RUNNER, "empty_suite"],
                                    env={**os.environ, "PYTHONPATH": directory}, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("contains no tests", result.stderr)


if __name__ == "__main__":
    unittest.main()
