#!/usr/bin/env python3
"""Tests for own_runtime_local.py: the resolved revision, the sparse checkout's steps, the settings and the record."""
from __future__ import annotations
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import own_runtime_local  # noqa: E402

GIT_ENVIRONMENT: dict[str, str] = {'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
                                   'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.invalid',
                                   'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}


def git(directory: Path, *arguments: str) -> str:
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        ['git', '-C', str(directory), *arguments], capture_output=True, text=True, check=True)
    return completed.stdout.strip()


class OwnRuntimeLocalTests(unittest.TestCase):
    def setUp(self) -> None:
        environment: mock._patch_dict = mock.patch.dict(os.environ, GIT_ENVIRONMENT)
        environment.start()
        self.addCleanup(environment.stop)
        directory: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root: Path = Path(directory.name).resolve()
        self.workspace: Path = self.root / 'workspace'
        self.workspace.mkdir()

    def write_resolved(self, revision: str) -> None:
        record: Path = self.workspace / own_runtime_local.RESOLVED_RECORD
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({'repository': 'owner/gui_forms', 'revision': revision}), encoding='utf-8')

    def gui_forms_at_tools(self) -> str:
        """A GUI.Forms stand-in with the toolchain file, cloned at .ci/gui_forms-tools; returns its revision."""
        source: Path = self.root / 'gui_forms'
        (source / 'cmake').mkdir(parents=True)
        (source / 'tools').mkdir()
        (source / own_runtime_local.TOOLCHAIN_FILE).write_text('# toolchain\n', encoding='utf-8')
        (source / own_runtime_local.OWN_RUNTIME_TOOL).write_text('# tool\n', encoding='utf-8')
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(source)], check=True)
        git(source, 'add', '.')
        git(source, 'commit', '-q', '-m', 'tools')
        subprocess.run(['git', 'clone', '-q', str(source), str(self.workspace / own_runtime_local.TOOLS_DIRECTORY)],
                       check=True)
        return git(source, 'rev-parse', 'HEAD')

    def test_a_workspace_without_a_resolved_build_is_refused(self) -> None:
        with self.assertRaisesRegex(own_runtime_local.OwnRuntimeError, 'run resolve_gui_forms.py resolve and fetch'):
            own_runtime_local.resolved(self.workspace)
        self.write_resolved('abc')
        with self.assertRaisesRegex(own_runtime_local.OwnRuntimeError, 'full revision'):
            own_runtime_local.resolved(self.workspace)

    def test_the_checkout_is_sparse_like_ci_and_fetches_the_revision(self) -> None:
        revision: str = 'a' * 40
        place: Path = self.workspace / own_runtime_local.TOOLS_DIRECTORY
        commands: list[list[str]] = own_runtime_local.checkout_commands(place, 'https://example/o/g.git', revision,
                                                                         cloned=False)
        self.assertEqual(commands[0], ['clone', '--quiet', '--no-checkout', '--filter=blob:none',
                                       'https://example/o/g.git', str(place)])
        self.assertEqual(commands[1][-4:], ['--no-cone', 'tools', 'cmake', 'stx.lock'])
        self.assertEqual(commands[-1], ['-C', str(place), 'checkout', '--quiet', '--detach', revision])
        again: list[list[str]] = own_runtime_local.checkout_commands(place, 'u', revision, cloned=True)
        self.assertEqual(len(again), 3)
        self.assertNotIn('clone', again[0])

    def test_the_settings_and_the_toolchain_file_are_printed_and_recorded(self) -> None:
        revision: str = self.gui_forms_at_tools()
        self.write_resolved(revision)
        ran: list[list[str]] = []

        def runner(command: list[str]) -> str:
            ran.append(command)
            return ('own runtime: reused (STXlib 1234567, LLVM 22.1.8)\n'
                    'GUI_FORMS_OWN_RUNTIME_PREFIX=C:/w/.ci/own-runtime/own-runtime\n'
                    'GUI_FORMS_LIBCXX_PREFIX=C:/w/.ci/own-runtime/libcxx\n'
                    'GUI_FORMS_STXLIB_SOURCE=C:/w/.ci/own-runtime/stxlib\n')

        output: io.StringIO = io.StringIO()
        with contextlib.redirect_stdout(output):
            settings: list[tuple[str, str]] = own_runtime_local.own_runtime(self.workspace, 2, 'unused', False, runner)
        self.assertEqual(ran[0][2:], [str(self.workspace / own_runtime_local.TOOLS_DIRECTORY / 'tools'
                                          / 'own_runtime.py'), 'build', '--out',
                                      str(self.workspace / own_runtime_local.RUNTIME_DIRECTORY), '--jobs', '2'])
        toolchain: str = (self.workspace / own_runtime_local.TOOLS_DIRECTORY / own_runtime_local.TOOLCHAIN_FILE).as_posix()
        self.assertEqual([name for name, _ in settings], ['GUI_FORMS_OWN_RUNTIME_PREFIX', 'GUI_FORMS_LIBCXX_PREFIX',
                                                          'GUI_FORMS_STXLIB_SOURCE', 'CMAKE_TOOLCHAIN_FILE'])
        self.assertEqual(settings[-1], ('CMAKE_TOOLCHAIN_FILE', toolchain))
        record: dict[str, object] = json.loads((self.workspace / own_runtime_local.RECORD).read_text(encoding='utf-8'))
        self.assertEqual((record['revision'], record['toolchain']), (revision, toolchain))
        # A checkout already at the revision is not fetched again.
        self.assertIn('is owner/gui_forms at ' + revision[:12], output.getvalue())

    def test_a_tool_that_prints_no_settings_stops(self) -> None:
        self.write_resolved(self.gui_forms_at_tools())
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(own_runtime_local.OwnRuntimeError, 'printed no settings'):
                own_runtime_local.own_runtime(self.workspace, 2, 'unused', False, lambda command: 'nothing\n')

    def test_a_changed_checkout_is_refused(self) -> None:
        self.write_resolved(self.gui_forms_at_tools())
        tools: Path = self.workspace / own_runtime_local.TOOLS_DIRECTORY
        (tools / own_runtime_local.OWN_RUNTIME_TOOL).write_text('# edited\n', encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(own_runtime_local.OwnRuntimeError, 'uncommitted changes'):
                own_runtime_local.own_runtime(self.workspace, 2, 'unused', False, lambda command: '')

    def test_another_host_needs_allow_cross(self) -> None:
        if sys.platform == 'win32':
            self.skipTest('the refusal is for hosts other than Windows')
        errors: io.StringIO = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(own_runtime_local.main(['--workspace', str(self.workspace)]), 1)
        self.assertIn('--allow-cross', errors.getvalue())


if __name__ == '__main__':
    unittest.main()
