"""prepare_build.py: GUI.Forms' Windows prepare command, and the environment rewritten with its settings."""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

import prepare_build
import project

PROJECTS: Path = Path(__file__).resolve().parent.parent / 'projects'


class PrepareTests(unittest.TestCase):
    def test_gui_forms_windows_runs_the_own_runtime_and_sets_its_settings(self) -> None:
        product: project.Project = project.load(PROJECTS / 'gui_forms.toml')
        commands: list[list[str]] = []

        def runner(command: list[str]) -> str:
            commands.append(command)
            if 'own_runtime.py' in ' '.join(command):
                return ('own runtime: reused (STXlib abc1234, LLVM 22.1.8)\n'
                        'GUI_FORMS_OWN_RUNTIME_SOURCE=W/.ci/own-runtime/stxlib\n'
                        'GUI_FORMS_OWN_RUNTIME_PREFIX=W/.ci/own-runtime/own-runtime\n'
                        'GUI_FORMS_LIBCXX_PREFIX=W/.ci/own-runtime/libcxx\n')
            return ''
        settings: list[str] = prepare_build.prepare(product, 'windows-x64', runner)
        self.assertEqual(commands[0][0], sys.executable)
        self.assertIn('gui_forms/tools/own_runtime.py', commands[0])
        self.assertEqual(len(settings), 3)
        self.assertEqual(commands[-1][3:6], ['env', '--platform', 'windows-x64'])
        self.assertIn('GUI_FORMS_LIBCXX_PREFIX=W/.ci/own-runtime/libcxx', commands[-1])

    def test_a_platform_without_prepare_does_nothing(self) -> None:
        product: project.Project = project.load(PROJECTS / 'gui_forms.toml')
        commands: list[list[str]] = []
        self.assertEqual(prepare_build.prepare(product, 'linux-x64', lambda command: commands.append(command) or ''),
                         [])
        self.assertEqual(commands, [])


if __name__ == '__main__':
    unittest.main()
