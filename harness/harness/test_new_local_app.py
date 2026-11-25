#!/usr/bin/env python3
"""Tests for new_local_app.py: an outsider's app, rendered locally with the devkit pinned and nothing pushed."""
from __future__ import annotations
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
from typing import Any
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import new_app  # noqa: E402
import new_local_app  # noqa: E402
import project  # noqa: E402

GIT_ENVIRONMENT: dict[str, str] = {
    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
    'GIT_AUTHOR_NAME': 'fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
    'GIT_COMMITTER_NAME': 'fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
IN_DEVKIT: bool = (new_local_app.DEVKIT_ROOT / '.git').exists()


def git(directory: Path, *arguments: str) -> str:
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        ['git', '-C', str(directory), *arguments], capture_output=True, text=True, check=True)
    return completed.stdout.strip()


@unittest.skipUnless(IN_DEVKIT, 'new-app pins the devkit checkout it runs from')
class NewLocalAppTests(unittest.TestCase):
    def setUp(self) -> None:
        environment: mock._patch_dict = mock.patch.dict(os.environ, GIT_ENVIRONMENT)
        environment.start()
        self.addCleanup(environment.stop)
        directory: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root: Path = Path(directory.name).resolve()

    def run_new_app(self, *arguments: str) -> tuple[int, str, str]:
        output: io.StringIO = io.StringIO()
        errors: io.StringIO = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status: int = new_local_app.main(list(arguments))
        return status, output.getvalue(), errors.getvalue()

    def test_an_app_is_rendered_pinned_committed_and_never_given_a_remote(self) -> None:
        app: Path = self.root / 'apps' / 'paint_box'
        status: int
        output: str
        errors: str
        status, output, errors = self.run_new_app('paint_box', str(app), '--title', 'Paint Box')
        self.assertEqual(status, 0, errors)
        expected: str
        for expected in ('build.py', 'test_build.py', 'devkit.toml', 'harness.toml', 'harness.lock', 'CMakeLists.txt',
                         'README.md', 'AGENTS.md', 'CLAUDE.md', '.gitignore', 'src/main.cpp', 'tests/greeter_tests.cpp',
                         'tests/interaction_tests.cpp', 'reference/link_page.cpp'):
            self.assertTrue((app / expected).is_file(), expected)
        # No in-house configuration, and no LICENSE unless asked.
        for absent in ('.claude', '.sushi', '.github', 'LICENSE'):
            self.assertFalse((app / absent).exists(), absent)
        commit: str = git(new_local_app.DEVKIT_ROOT, 'rev-parse', 'HEAD')
        lock: dict[str, Any] = tomllib.loads((app / 'harness.lock').read_text(encoding='utf-8'))
        self.assertEqual(lock['harness'], {'repository': project.load(new_local_app.DEVKIT_PROJECT).repository,
                                           'commit': commit})
        pin: dict[str, Any] = tomllib.loads((app / 'devkit.toml').read_text(encoding='utf-8'))
        self.assertEqual((str(pin['gui_forms']['major']), pin['gui_forms']['minimum']), new_app.gui_forms_pin())
        self.assertEqual(pin['checks']['profile'], 'consumer')
        product: project.Project = project.load(app / 'harness.toml')
        self.assertEqual((product.name, product.repository, product.source_dir), ('paint_box', 'local/paint_box', '.'))
        self.assertIsNone(product.bootstrap.notes_repository)
        self.assertIn('gui_forms_devkit_build_guard()', (app / 'CMakeLists.txt').read_text(encoding='utf-8'))
        readme: str = (app / 'README.md').read_text(encoding='utf-8')
        self.assertIn('# Paint Box', readme)
        self.assertNotIn('template_harness', readme)
        # The devkit sits at the pin inside the app, ignored; the app is committed on main with no remote.
        self.assertEqual(git(app / '.devkit', 'rev-parse', 'HEAD'), commit)
        self.assertEqual(git(app, 'branch', '--show-current'), 'main')
        self.assertEqual(git(app, 'remote'), '')
        self.assertEqual(git(app, 'status', '--porcelain'), '')
        self.assertNotIn('.devkit', git(app, 'ls-files'))
        path: Path
        for path in app.rglob('*'):
            if path.is_file() and '.devkit' not in path.relative_to(app).parts and '.git' not in path.parts:
                self.assertFalse(new_app.leftover_placeholders(path.read_text(encoding='utf-8')), str(path))
        self.assertIn('nothing pushed', output)

    def test_strict_and_a_license_are_opt_in(self) -> None:
        app: Path = self.root / 'strict_box'
        status: int
        errors: str
        status, _, errors = self.run_new_app('strict_box', str(app), '--strict', '--license', 'mit', '--licensor',
                                             'Test Holder', '--no-devkit-clone')
        self.assertEqual(status, 0, errors)
        pin: dict[str, Any] = tomllib.loads((app / 'devkit.toml').read_text(encoding='utf-8'))
        self.assertEqual(pin['checks']['profile'], 'strict')
        self.assertIn('Test Holder', (app / 'LICENSE').read_text(encoding='utf-8'))
        self.assertFalse((app / '.devkit').exists())

    def test_the_rendered_build_script_tests_pass(self) -> None:
        app: Path = self.root / 'paint_box'
        self.assertEqual(self.run_new_app('paint_box', str(app), '--no-devkit-clone')[0], 0)
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(app), '-p', 'test_*.py'],
            capture_output=True, text=True, check=False, timeout=120)
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])

    def test_a_dry_run_writes_nothing_and_a_used_directory_is_refused(self) -> None:
        app: Path = self.root / 'paint_box'
        status: int
        output: str
        errors: str
        status, output, errors = self.run_new_app('paint_box', str(app), '--dry-run')
        self.assertEqual(status, 0, errors)
        self.assertIn('would write devkit.toml', output)
        self.assertNotIn('would write .sushi', output)
        self.assertFalse(app.exists())
        app.mkdir()
        (app / 'mine.txt').write_text('mine\n', encoding='utf-8')
        status, output, errors = self.run_new_app('paint_box', str(app))
        self.assertEqual(status, 1)
        self.assertIn('exists and is not an empty directory', errors)
        status, output, errors = self.run_new_app('gui_thing', str(self.root / 'other'))
        self.assertEqual(status, 1)
        self.assertIn('may not start with gui', errors)


if __name__ == '__main__':
    unittest.main()
