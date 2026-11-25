"""Tests run_checks.py: the profile choice and that each profile runs its checks."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import run_checks

HERE: Path = Path(__file__).resolve().parent


class ProfileTests(unittest.TestCase):
    def test_the_default_is_consumer(self) -> None:
        self.assertEqual(run_checks.chosen_profile(None, {}), 'consumer')

    def test_the_environment_opts_in(self) -> None:
        self.assertEqual(run_checks.chosen_profile(None, {run_checks.PROFILE_VARIABLE: 'strict'}), 'strict')

    def test_the_argument_wins_over_the_environment(self) -> None:
        self.assertEqual(run_checks.chosen_profile('consumer', {run_checks.PROFILE_VARIABLE: 'strict'}), 'consumer')

    def test_an_unknown_profile_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            run_checks.chosen_profile(None, {run_checks.PROFILE_VARIABLE: 'house'})

    def test_consumer_leaves_out_the_house_checks(self) -> None:
        labels: list[str] = [check.label for check in run_checks.PROFILES['consumer']]
        self.assertEqual(labels, ['retained mode'])

    def test_strict_adds_house_style_and_lifetime_rules(self) -> None:
        labels: list[str] = [check.label for check in run_checks.PROFILES['strict']]
        self.assertEqual(labels, ['retained mode', 'house style', 'lifetime rules'])

    def test_every_profile_names_scripts_that_exist(self) -> None:
        for checks in run_checks.PROFILES.values():
            for check in checks:
                self.assertTrue((HERE / check.script).is_file(), check.script)


class RunTests(unittest.TestCase):
    def run_profile(self, profile: str, source: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path: Path = Path(directory) / 'empty.cpp'
            path.write_text(source, encoding='utf-8')
            environment: dict[str, str] = dict(os.environ)
            environment.pop(run_checks.PROFILE_VARIABLE, None)
            return subprocess.run([sys.executable, '-B', str(HERE / 'run_checks.py'), '--profile', profile, str(path)],
                                  capture_output=True, text=True, check=False, env=environment)

    def test_consumer_runs_only_the_retained_check(self) -> None:
        completed: subprocess.CompletedProcess[str] = self.run_profile('consumer', '// nothing\n')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('== retained mode (consumer)', completed.stdout)
        self.assertNotIn('== house style', completed.stdout)

    def test_strict_runs_all_three(self) -> None:
        completed: subprocess.CompletedProcess[str] = self.run_profile('strict', '// nothing\n')
        self.assertIn('== retained mode (strict)', completed.stdout)
        self.assertIn('== house style (strict)', completed.stdout)
        self.assertIn('== lifetime rules (strict)', completed.stdout)


if __name__ == '__main__':
    unittest.main()
