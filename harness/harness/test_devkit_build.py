#!/usr/bin/env python3
"""Tests for devkit_build.py: the steps per platform, the toolchain file, the guard wiring and the refusals."""
from __future__ import annotations
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import devkit_build  # noqa: E402


class DevkitBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        directory: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.app: Path = Path(directory.name).resolve() / 'paint_box'
        self.app.mkdir()
        for name in (devkit_build.DEVKIT_FILE, devkit_build.PROJECT_FILE, 'CMakeLists.txt'):
            (self.app / name).write_text('\n', encoding='utf-8')

    def options(self, platform: str, **values: object) -> devkit_build.Options:
        options: devkit_build.Options = devkit_build.Options(app=self.app, project=self.app / 'harness.toml',
                                                             platform=platform, **values)
        return options

    def whats(self, steps: list[devkit_build.Step]) -> list[str]:
        return [step.what for step in steps]

    def test_a_first_build_resolves_then_fetches_and_restores_the_runtime(self) -> None:
        steps: list[devkit_build.Step] = devkit_build.preparation(self.options('macos-arm64'))
        self.assertEqual(self.whats(steps), ['resolving GUI.Forms', 'fetching the SDK',
                                             'verifying or building the C++ runtime'])
        self.assertEqual(steps[0].command[3:], ['resolve', '--devkit', str(self.app / 'devkit.toml'),
                                                '--workspace', str(self.app)])
        self.assertEqual(steps[1].command[3:], ['fetch', '--platform', 'macos-arm64', '--workspace', str(self.app)])

    def test_a_resolved_build_stays_on_its_gui_forms_until_asked(self) -> None:
        record: Path = self.app / devkit_build.RESOLVED_RECORD
        record.parent.mkdir()
        record.write_text('{}', encoding='utf-8')
        self.assertEqual(self.whats(devkit_build.preparation(self.options('linux-x64')))[0], 'fetching the SDK')
        floor: list[devkit_build.Step] = devkit_build.preparation(self.options('linux-x64', floor=True))
        self.assertEqual(floor[0].command[-1], '--floor')
        exact: list[devkit_build.Step] = devkit_build.preparation(self.options('linux-x64', revision='abc'))
        self.assertEqual(exact[0].command[-2:], ['--revision', 'abc'])

    def test_windows_restores_the_toolchain_and_the_own_runtime_whose_toolchain_file_it_uses(self) -> None:
        steps: list[devkit_build.Step] = devkit_build.preparation(self.options('windows-x64', jobs=8))
        self.assertEqual(self.whats(steps)[-2:], ['restoring the Windows toolchain',
                                                  'restoring or building the own runtime'])
        self.assertTrue(steps[-1].settings)
        self.assertEqual(Path(steps[-1].command[2]).name, 'own_runtime_local.py')
        self.assertEqual(steps[-1].command[-2:], ['--jobs', '8'])
        settings: list[tuple[str, str]] = devkit_build.settings_of(
            'own runtime: reused\nGUI_FORMS_LIBCXX_PREFIX=C:/r/libcxx\nCMAKE_TOOLCHAIN_FILE=C:/t/llvm22-windows-msvc.cmake\n')
        self.assertEqual(devkit_build.toolchain_file(settings), 'C:/t/llvm22-windows-msvc.cmake')
        environment: devkit_build.Step = devkit_build.environment_step(self.options('windows-x64'), settings)
        self.assertEqual(environment.command[3:], ['env', '--platform', 'windows-x64',
                                                   '--set', 'GUI_FORMS_LIBCXX_PREFIX=C:/r/libcxx',
                                                   '--set', 'CMAKE_TOOLCHAIN_FILE=C:/t/llvm22-windows-msvc.cmake'])

    def test_a_consumer_configures_with_llvm22_and_the_guard_of_this_harness(self) -> None:
        steps: list[devkit_build.Step] = devkit_build.build_steps(self.options('linux-x64'), [], display=False)
        self.assertEqual(self.whats(steps), ['configuring', 'building', 'testing'])
        configure: list[str] = steps[0].command
        self.assertIn('-DCMAKE_TOOLCHAIN_FILE=' + devkit_build.TOOLCHAIN.as_posix(), configure)
        self.assertIn('-DGUI_FORMS_DEVKIT_HARNESS_ROOT=' + devkit_build.HARNESS_ROOT.as_posix(), configure)
        self.assertNotIn('-DGUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=ON', configure)
        self.assertEqual(configure[configure.index('-B') + 1], str(self.app / '.build' / 'native-linux-x64'))
        # Linux without a display runs the tests under xvfb-run.
        self.assertEqual(steps[2].command[:3], ['xvfb-run', '-a', 'ctest'])
        shown: list[devkit_build.Step] = devkit_build.build_steps(self.options('linux-x64'), [], display=True)
        self.assertEqual(shown[2].command[0], 'ctest')

    def test_configure_only_and_the_override_and_the_devkit_itself(self) -> None:
        steps: list[devkit_build.Step] = devkit_build.build_steps(
            self.options('macos-arm64', configure_only=True, allow_full_build=True), [], display=True)
        self.assertEqual(self.whats(steps), ['configuring'])
        self.assertIn('-DGUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=ON', steps[0].command)
        devkit: devkit_build.Options = devkit_build.Options(app=devkit_build.HARNESS_ROOT.parent,
                                                            project=Path('p.toml'), platform='linux-x64', tests=False)
        own: list[devkit_build.Step] = devkit_build.build_steps(devkit, [], display=True)
        self.assertEqual(self.whats(own), ['configuring', 'building'])
        self.assertFalse([argument for argument in own[0].command if 'GUI_FORMS_DEVKIT_HARNESS_ROOT' in argument])

    def test_the_devkit_cache_is_restored_only_when_asked(self) -> None:
        asked: list[devkit_build.Step] = devkit_build.preparation(self.options('linux-x64', restore_devkit_cache=True))
        self.assertEqual(asked[-1].what, "restoring the devkit's cache")
        self.assertNotIn("restoring the devkit's cache", self.whats(devkit_build.preparation(self.options('linux-x64'))))

    def test_a_dry_run_prints_every_step(self) -> None:
        output: io.StringIO = io.StringIO()
        with contextlib.redirect_stdout(output):
            status: int = devkit_build.main(['--app', str(self.app), '--platform', 'windows-x64', '--dry-run'])
        self.assertEqual(status, 0)
        lines: list[str] = [line for line in output.getvalue().splitlines() if line.startswith('would run: ')]
        self.assertEqual(len(lines), 8, output.getvalue())
        # resolve, fetch, toolchain, own runtime, env, configure, build, test.
        self.assertIn(' env --platform windows-x64', lines[4])
        self.assertIn('CMAKE_TOOLCHAIN_FILE=', lines[4])
        self.assertTrue(lines[5].startswith('would run: cmake -S'))
        self.assertIn('llvm22-windows-msvc.cmake', lines[5])
        self.assertFalse((self.app / '.ci').exists())

    def test_an_app_without_its_pin_or_project_is_refused(self) -> None:
        (self.app / devkit_build.DEVKIT_FILE).unlink()
        errors: io.StringIO = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(devkit_build.main(['--app', str(self.app), '--dry-run']), 1)
        self.assertIn('has no devkit.toml', errors.getvalue())
        (self.app / devkit_build.DEVKIT_FILE).write_text('\n', encoding='utf-8')
        (self.app / devkit_build.PROJECT_FILE).unlink()
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(devkit_build.main(['--app', str(self.app), '--dry-run']), 1)
        self.assertIn('No project file', errors.getvalue())


if __name__ == '__main__':
    unittest.main()
