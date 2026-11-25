"""Tests build_guard.py: a matching build passes, each mismatch stops with its message, the override goes on."""

import contextlib
import dataclasses
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
import unittest
from unittest import mock

import build_guard as guard

REVISION: str = 'ab' * 20
ENVIRONMENT: dict[str, str] = {'CCACHE_COMPILERCHECK': 'content', 'CCACHE_SLOPPINESS': 'pch_defines,time_macros',
                               'LANG': 'C.UTF-8', 'LC_ALL': '', 'LC_CTYPE': '', 'LC_MESSAGES': ''}


class Workspace:
    """A workspace with an unpacked SDK record, a resolved record and a fake compiler."""

    def __init__(self) -> None:
        self.root: Path = Path(tempfile.mkdtemp()).resolve()
        self.compiler: Path = self.root / 'toolchain' / 'clang++'
        self.compiler.parent.mkdir()
        self.compiler.write_bytes(b'the producer clang')
        self.digest: str = hashlib.sha256(b'the producer clang').hexdigest()
        sdk: Path = self.root / guard.SDK_DIRECTORY
        (sdk / 'lib' / 'cmake' / 'GUIForms').mkdir(parents=True)
        self.write(sdk / guard.SDK_RECORD, {'revision': REVISION, 'platform': 'linux-x64',
                                            'producer': {'compiler_version': '22.1.8', 'compiler_sha256': self.digest,
                                                         'environment': ENVIRONMENT}})
        self.write(self.root / guard.RESOLVED_RECORD, {'revision': REVISION})
        self.build: Path = self.root / 'build'
        self.build.mkdir()

    @staticmethod
    def write(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def remove(self) -> None:
        shutil.rmtree(self.root, True)

    def inputs(self, **changes: Any) -> guard.Inputs:
        environment: dict[str, str] = {'CCACHE_BASEDIR': self.root.as_posix(),
                                       'CCACHE_DIR': (self.root / '.ccache').as_posix(), **ENVIRONMENT}
        environment = {name: value for name, value in environment.items() if value != ''}
        inputs: guard.Inputs = guard.Inputs(
            workspace=self.root, platform='linux-x64', build_dir=self.build, cxx_compiler=str(self.compiler),
            launcher='ccache', compile_environment=environment,
            gui_forms_dir=(self.root / guard.SDK_DIRECTORY / 'lib' / 'cmake' / 'GUIForms').as_posix(),
            imported='yes', sources=(), dry_run='objects', threshold=0.9)
        return dataclasses.replace(inputs, **changes)


class GuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace: Workspace = Workspace()
        self.addCleanup(self.workspace.remove)

    def kinds(self, inputs: guard.Inputs) -> list[str]:
        return [finding.kind for finding in guard.check(inputs)]

    def test_a_matching_build_passes(self) -> None:
        self.assertEqual(guard.check(self.workspace.inputs()), [])

    def test_no_sdk_stops(self) -> None:
        (self.workspace.root / guard.SDK_DIRECTORY / guard.SDK_RECORD).unlink()
        findings: list[guard.Finding] = guard.check(self.workspace.inputs())
        self.assertEqual(findings[0].kind, 'sdk')
        self.assertIn('resolve_gui_forms.py', findings[0].fix)

    def test_a_stale_sdk_stops(self) -> None:
        Workspace.write(self.workspace.root / guard.RESOLVED_RECORD, {'revision': 'cd' * 20})
        self.assertIn('sdk', self.kinds(self.workspace.inputs()))

    def test_gui_forms_found_elsewhere_stops(self) -> None:
        self.assertIn('sdk-path', self.kinds(self.workspace.inputs(gui_forms_dir='/opt/gui_forms/lib/cmake/GUIForms')))

    def test_gui_forms_built_from_source_stops(self) -> None:
        self.assertIn('sdk-path', self.kinds(self.workspace.inputs(imported='no')))

    def test_a_gui_forms_source_stops(self) -> None:
        tree: Path = self.workspace.root / 'gui_forms'
        (tree / 'include' / 'gui_forms').mkdir(parents=True)
        (tree / 'src' / 'core').mkdir(parents=True)
        source: Path = tree / 'src' / 'core' / 'window.cpp'
        source.write_text('', encoding='utf-8')
        findings: list[guard.Finding] = guard.check(self.workspace.inputs(sources=(str(source),)))
        self.assertEqual([finding.kind for finding in findings], ['sources'])
        self.assertIn('window.cpp', findings[0].what)

    def test_the_installed_sdk_headers_are_not_sources(self) -> None:
        header: Path = self.workspace.root / guard.SDK_DIRECTORY / 'include' / 'gui_forms' / 'window.hpp'
        header.parent.mkdir(parents=True)
        header.write_text('', encoding='utf-8')
        self.assertEqual(self.kinds(self.workspace.inputs(sources=(str(header),))), [])

    def test_another_compiler_stops(self) -> None:
        other: Path = self.workspace.root / 'toolchain' / 'other-clang++'
        other.write_bytes(b'a different clang')
        findings: list[guard.Finding] = guard.check(self.workspace.inputs(cxx_compiler=str(other)))
        self.assertEqual([finding.kind for finding in findings], ['compiler'])
        self.assertIn('every object misses', findings[0].what)

    def test_the_restored_cache_manifest_wins_over_the_sdk(self) -> None:
        Workspace.write(self.workspace.root / guard.CACHE_MANIFEST,
                        {'compiler_sha256': 'f' * 64, 'compiler_version': '22.1.8', 'environment': ENVIRONMENT})
        self.assertEqual(self.kinds(self.workspace.inputs()), ['compiler'])

    def test_no_launcher_stops(self) -> None:
        self.assertEqual(self.kinds(self.workspace.inputs(launcher='')), ['launcher'])

    def test_another_basedir_stops(self) -> None:
        inputs: guard.Inputs = self.workspace.inputs()
        environment: dict[str, str] = dict(inputs.compile_environment, CCACHE_BASEDIR='/elsewhere')
        self.assertEqual(self.kinds(dataclasses.replace(inputs, compile_environment=environment)), ['ccache'])

    def test_another_compiler_check_stops(self) -> None:
        inputs: guard.Inputs = self.workspace.inputs()
        environment: dict[str, str] = dict(inputs.compile_environment, CCACHE_COMPILERCHECK='mtime')
        findings: list[guard.Finding] = guard.check(dataclasses.replace(inputs, compile_environment=environment))
        self.assertEqual([finding.kind for finding in findings], ['ccache'])
        self.assertIn('CCACHE_COMPILERCHECK', findings[0].what)

    def test_another_locale_stops(self) -> None:
        inputs: guard.Inputs = self.workspace.inputs()
        environment: dict[str, str] = dict(inputs.compile_environment, LANG='de_DE.UTF-8')
        findings: list[guard.Finding] = guard.check(dataclasses.replace(inputs, compile_environment=environment))
        self.assertEqual([finding.kind for finding in findings], ['locale'])
        self.assertIn('LANG=C.UTF-8', findings[0].fix)

    def test_a_locale_sloppy_cache_ignores_the_locale(self) -> None:
        sloppy: dict[str, str] = dict(ENVIRONMENT, CCACHE_SLOPPINESS='pch_defines,time_macros,locale')
        Workspace.write(self.workspace.root / guard.CACHE_MANIFEST,
                        {'compiler_sha256': self.workspace.digest, 'environment': sloppy})
        inputs: guard.Inputs = self.workspace.inputs()
        environment: dict[str, str] = dict(inputs.compile_environment, LANG='de_DE.UTF-8',
                                           CCACHE_SLOPPINESS='pch_defines,time_macros,locale')
        self.assertEqual(self.kinds(dataclasses.replace(inputs, compile_environment=environment)), [])

    def record_objects(self, count: int) -> None:
        header: Path = self.workspace.root / 'views' / 'view.hpp'
        header.parent.mkdir(parents=True, exist_ok=True)
        header.write_text('recorded', encoding='utf-8')
        objects: dict[str, Any] = {}
        number: int
        for number in range(count):
            inputs: list[str] = ['views/view.hpp']
            objects['obj/' + str(number) + '.o'] = {'inputs': inputs,
                                                    'digest': guard.input_digest(self.workspace.root, inputs)}
        Workspace.write(self.workspace.root / guard.DEPS_RECORD, {'schema': 1, 'objects': objects})

    def test_a_projected_hit_rate_above_the_threshold_passes(self) -> None:
        self.record_objects(4)
        self.assertEqual(self.kinds(self.workspace.inputs()), [])

    def test_a_projected_hit_rate_below_the_threshold_stops(self) -> None:
        self.record_objects(4)
        (self.workspace.root / 'views' / 'view.hpp').write_text('changed', encoding='utf-8')
        findings: list[guard.Finding] = guard.check(self.workspace.inputs())
        self.assertEqual([finding.kind for finding in findings], ['hit-rate'])
        self.assertIn('0 of 4', findings[0].what)

    def test_built_objects_are_not_projected(self) -> None:
        self.record_objects(2)
        (self.workspace.root / 'views' / 'view.hpp').write_text('changed', encoding='utf-8')
        (self.workspace.build / 'obj').mkdir()
        (self.workspace.build / 'obj' / '0.o').write_bytes(b'')
        (self.workspace.build / 'obj' / '1.o').write_bytes(b'')
        self.assertEqual(self.kinds(self.workspace.inputs()), [])

    def test_ninja_compiles_are_parsed(self) -> None:
        text: str = ('[1/2] /usr/bin/ccache /usr/bin/clang++ -I../x -o views/CMakeFiles/v.dir/a.cpp.o '
                     '-c /src/views/a.cpp\n[2/2] : && /usr/bin/clang++ -o app a.o\n')
        compiles: list[guard.Compile] = guard.parse_compiles(text, self.workspace.build)
        self.assertEqual(compiles, [guard.Compile('/src/views/a.cpp', 'views/CMakeFiles/v.dir/a.cpp.o')])

    def test_the_deps_record_is_workspace_relative(self) -> None:
        header: Path = self.workspace.root / 'views' / 'v.hpp'
        header.parent.mkdir(parents=True)
        header.write_text('x', encoding='utf-8')
        text: str = 'views/v.o: #deps 2, deps mtime 1 (VALID)\n    ../views/v.hpp\n    /usr/include/stdio.h\n\n'
        record: dict[str, Any] = guard.deps_record(self.workspace.root, self.workspace.build, text)
        self.assertEqual(record['objects']['views/v.o']['inputs'][0], 'views/v.hpp')
        self.assertEqual(record['build_dir'], 'build')

    def test_the_diagnostic_names_the_cause_and_the_override(self) -> None:
        text: str = guard.diagnostic([guard.Finding('locale', 'LANG is x', 'set LANG=C.UTF-8')], False)
        self.assertTrue(text.startswith(guard.HEADLINE))
        self.assertIn('[locale] LANG is x', text)
        self.assertIn('GUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=1', text)


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace: Workspace = Workspace()
        self.addCleanup(self.workspace.remove)

    def run_main(self, arguments: list[str], environment: dict[str, str]) -> tuple[int, str]:
        errors: io.StringIO = io.StringIO()
        with mock.patch.dict(os.environ, environment, clear=True), contextlib.redirect_stderr(errors), \
                contextlib.redirect_stdout(io.StringIO()):
            code: int = guard.main(arguments)
        return code, errors.getvalue()

    def base(self) -> list[str]:
        return ['check', '--workspace', str(self.workspace.root), '--platform', 'linux-x64', '--build-dir',
                str(self.workspace.build), '--cxx-compiler', str(self.workspace.compiler), '--launcher', 'ccache',
                '--dry-run', 'objects', '--compile-env', 'CCACHE_BASEDIR=' + self.workspace.root.as_posix(),
                '--compile-env', 'CCACHE_DIR=' + (self.workspace.root / '.ccache').as_posix(),
                '--compile-env', 'CCACHE_COMPILERCHECK=content',
                '--compile-env', 'CCACHE_SLOPPINESS=pch_defines,time_macros', '--compile-env', 'LANG=C.UTF-8']

    def test_a_matching_build_goes_on(self) -> None:
        self.assertEqual(self.run_main(self.base(), {})[0], 0)

    def test_a_mismatch_stops_the_build(self) -> None:
        code: int
        text: str
        code, text = self.run_main(self.base() + ['--launcher', ''], {})
        self.assertEqual(code, guard.STOP_EXIT)
        self.assertIn(guard.HEADLINE, text)

    def test_the_environment_override_goes_on(self) -> None:
        code: int
        text: str
        code, text = self.run_main(self.base() + ['--launcher', ''], {guard.OVERRIDE_VARIABLE: '1'})
        self.assertEqual(code, 0)
        self.assertIn('expect a full, slow build', text)

    def test_the_flag_override_goes_on(self) -> None:
        self.assertEqual(self.run_main(self.base() + ['--launcher', '', '--allow-full-build'], {})[0], 0)

    def test_environment_prints_the_compile_settings(self) -> None:
        output: io.StringIO = io.StringIO()
        with contextlib.redirect_stdout(output):
            guard.main(['environment', '--workspace', str(self.workspace.root), '--platform', 'linux-x64'])
        lines: list[str] = output.getvalue().splitlines()
        self.assertIn('CCACHE_BASEDIR=' + self.workspace.root.as_posix(), lines)
        self.assertIn('LANG=C.UTF-8', lines)


if __name__ == '__main__':
    unittest.main()
