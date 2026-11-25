#!/usr/bin/env python3
"""Tests for build.py: finding the devkit, passing the options on, and the checks' profile."""
from __future__ import annotations
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        directory: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root: Path = Path(directory.name).resolve()

    def devkit(self, name: str) -> Path:
        """A gui_forms_devkit stand-in: <name>/harness/harness/devkit_build.py."""
        checkout: Path = self.root / name
        (checkout / 'harness' / 'harness').mkdir(parents=True)
        (checkout / 'harness' / 'harness' / 'devkit_build.py').write_text('\n', encoding='utf-8')
        return checkout

    def test_a_devkit_checkout_and_a_harness_checkout_are_both_found(self) -> None:
        checkout: Path = self.devkit('gui_forms_devkit')
        self.assertEqual(build.harness_root(checkout), checkout / 'harness')
        self.assertEqual(build.harness_root(checkout / 'harness'), checkout / 'harness')
        self.assertIsNone(build.harness_root(self.root))

    def test_a_named_devkit_wins_and_a_wrong_one_is_refused(self) -> None:
        checkout: Path = self.devkit('named')
        self.assertEqual(build.find_devkit(str(checkout)), checkout / 'harness')
        with mock.patch.dict(os.environ, {'GUI_FORMS_DEVKIT_DIR': str(checkout)}):
            self.assertEqual(build.find_devkit(''), checkout / 'harness')
        with self.assertRaisesRegex(build.DevkitError, 'holds no devkit harness'):
            build.find_devkit(str(self.root))

    def test_devkit_is_taken_out_and_everything_else_goes_to_devkit_build(self) -> None:
        self.assertEqual(build.split_devkit(['--devkit', '/d', '--jobs', '8']), ('/d', ['--jobs', '8']))
        self.assertEqual(build.split_devkit(['--devkit=/d', '--resolve']), ('/d', ['--resolve']))
        root: Path = self.devkit('kit') / 'harness'
        command: list[str] = build.command_for(root, ['--configure-only'])
        self.assertEqual(command[2:], [str(root / 'harness' / 'devkit_build.py'), '--app', str(build.HERE),
                                       '--configure-only'])

    def test_the_checks_run_at_the_pinned_profile_unless_named(self) -> None:
        root: Path = self.devkit('kit') / 'harness'
        command: list[str] = build.command_for(root, ['check'])
        self.assertEqual(command[2:5], [str(root / 'harness' / 'run_checks.py'), '--profile', 'consumer'])
        self.assertIn(str(build.HERE / 'src'), command)
        strict: list[str] = build.command_for(root, ['check', '--profile', 'strict'])
        self.assertEqual(strict[4], 'strict')


if __name__ == '__main__':
    unittest.main()
