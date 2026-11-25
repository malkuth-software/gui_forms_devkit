"""The devkit's own cache: pack, restore, and the cache proof's expectation and verdicts."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
from typing import Any
import unittest
from unittest import mock

import build_guard
import devkit_cache as cache
import project

HARNESS: Path = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Workspace:
    """A workspace with one source, one header and a build directory whose deps name them."""

    def __init__(self) -> None:
        self.root: Path = Path(tempfile.mkdtemp())
        (self.root / 'views').mkdir()
        (self.root / 'views' / 'a.cpp').write_text('int a;\n', encoding='utf-8')
        (self.root / 'views' / 'b.cpp').write_text('int b;\n', encoding='utf-8')
        (self.root / '.sdk/gui-forms-sdk/include').mkdir(parents=True)
        (self.root / '.sdk/gui-forms-sdk/include/h.hpp').write_text('// 1\n', encoding='utf-8')
        (self.root / '.ccache').mkdir()
        (self.root / '.ccache' / 'entry').write_bytes(b'object')
        self.build: Path = self.root / 'build'
        self.build.mkdir()
        self.compiler: Path = self.root / 'clang++'
        self.compiler.write_bytes(b'compiler')
        resolved: dict[str, Any] = {'tag': 'build-' + 'a' * 40, 'revision': 'a' * 40, 'version': '1.0.4',
                                    'manifest': {'platforms': {'linux-x64': {'compiler_version': '22.1.8'}}}}
        (self.root / '.ci').mkdir()
        (self.root / '.ci/gui_forms-resolved.json').write_text(json.dumps(resolved), encoding='utf-8')

    def deps(self) -> str:
        return ('views/a.o: #deps 2, deps mtime 1 (VALID)\n    ../views/a.cpp\n    ../.sdk/gui-forms-sdk/include/h.hpp\n'
                '\nviews/b.o: #deps 1, deps mtime 1 (VALID)\n    ../views/b.cpp\n')

    def pack(self) -> Path:
        environment: dict[str, str] = {'CCACHE_COMPILERCHECK': 'content', 'LANG': 'C.UTF-8'}
        archive: Path = cache.pack(self.root, 'linux-x64', self.build, 'b' * 40, self.compiler, self.deps(),
                                   environment)
        return archive


class PackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace: Workspace = Workspace()
        self.addCleanup(shutil.rmtree, self.workspace.root, True)

    def test_the_archive_holds_the_cache_the_record_and_the_manifest(self) -> None:
        archive: Path = self.workspace.pack()
        self.assertEqual(archive.name, 'gui-forms-devkit-cache-linux-x64.tar.gz')
        with tarfile.open(archive) as payload:
            names: list[str] = payload.getnames()
        self.assertIn('.ccache/entry', names)
        self.assertIn(build_guard.DEPS_RECORD, names)
        self.assertIn(build_guard.CACHE_MANIFEST, names)

    def test_the_manifest_records_compiler_environment_and_gui_forms(self) -> None:
        self.workspace.pack()
        manifest: dict[str, Any] = json.loads((self.workspace.root / 'cache-manifest.json').read_text())
        self.assertEqual(manifest['compiler_sha256'], digest(self.workspace.compiler))
        self.assertEqual(manifest['compiler_version'], '22.1.8')
        self.assertEqual(manifest['environment']['CCACHE_COMPILERCHECK'], 'content')
        self.assertIsNone(manifest['environment']['LC_ALL'])
        self.assertEqual(manifest['gui_forms']['version'], '1.0.4')
        identity: dict[str, Any] = json.loads((self.workspace.root / cache.INPUTS_RECORD).read_text())
        self.assertEqual(identity, {'platform': 'linux-x64', 'revision': 'b' * 40})

    def test_the_build_guard_reads_the_packed_environment(self) -> None:
        self.workspace.pack()
        expected: dict[str, str] = build_guard.expected_environment(self.workspace.root)
        self.assertEqual(expected['CCACHE_COMPILERCHECK'], 'content')
        self.assertEqual(expected['LANG'], 'C.UTF-8')

    def test_the_project_file_names_the_same_asset(self) -> None:
        devkit: project.Project = project.load(HARNESS.parent / 'projects' / 'gui_forms_devkit.toml')
        self.assertEqual(devkit.cache_asset('macos-arm64'), cache.CACHE_ASSET.format(platform='macos-arm64'))


class ExpectationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace: Workspace = Workspace()
        self.addCleanup(shutil.rmtree, self.workspace.root, True)
        self.workspace.pack()

    def test_unchanged_inputs_must_all_hit(self) -> None:
        self.assertEqual(cache.expect(self.workspace.root, 'current')['expected'], 2)

    def test_a_changed_sdk_header_takes_its_objects_out(self) -> None:
        (self.workspace.root / '.sdk/gui-forms-sdk/include/h.hpp').write_text('// 2\n', encoding='utf-8')
        expectation: dict[str, Any] = cache.expect(self.workspace.root, 'previous')
        self.assertEqual(expectation['expected'], 1)
        self.assertEqual(expectation['will_miss'], ['views/a.o'])


def stats(direct: int, preprocessed: int, missed: int) -> str:
    return ('direct_cache_hit\t' + str(direct) + '\npreprocessed_cache_hit\t' + str(preprocessed)
            + '\ncache_miss\t' + str(missed) + '\n')


class VerdictTests(unittest.TestCase):
    def counters(self, direct: int, preprocessed: int, missed: int) -> dict[str, int]:
        return cache.stats_counters(stats(direct, preprocessed, missed))

    def test_current_passes_at_ninety_nine_percent_of_expected(self) -> None:
        self.assertEqual(cache.judge('current', self.counters(90, 9, 50), 100)['verdict'], 'pass')
        self.assertEqual(cache.judge('current', self.counters(90, 8, 50), 100)['verdict'], 'fail')

    def test_previous_has_the_same_bar(self) -> None:
        self.assertEqual(cache.judge('previous', self.counters(0, 0, 10), 1)['verdict'], 'fail')
        self.assertEqual(cache.judge('previous', self.counters(0, 0, 10), 0)['verdict'], 'pass')

    def test_stable_records_and_warns_below_half(self) -> None:
        self.assertEqual(cache.judge('stable', self.counters(1, 0, 9), 0)['verdict'], 'warn')
        self.assertEqual(cache.judge('stable', self.counters(6, 0, 4), 0)['verdict'], 'pass')

    def test_gui_forms_own_cache_needs_ninety_eight_percent(self) -> None:
        self.assertEqual(cache.judge('gui-forms-current', self.counters(98, 0, 2), 0)['verdict'], 'pass')
        self.assertEqual(cache.judge('gui-forms-current', self.counters(97, 0, 3), 0)['verdict'], 'fail')
        self.assertEqual(cache.judge('gui-forms-previous', self.counters(0, 0, 3), 0)['verdict'], 'pass')

    def test_prove_appends_the_row_and_fails_through_main(self) -> None:
        root: Path = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        (root / '.ci').mkdir()
        (root / '.ci/cache-proof-expected-current.json').write_text(json.dumps({'expected': 10}), encoding='utf-8')
        stats_file: Path = root / 'stats.txt'
        stats_file.write_text(stats(5, 0, 5), encoding='utf-8')
        with mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}):
            code: int = cache.main(['prove', '--workspace', str(root), '--platform', 'linux-x64', '--row', 'current',
                                    '--stats', str(stats_file), '--gui-forms', 'R'])
        self.assertEqual(code, 1)
        proof: dict[str, Any] = json.loads((root / '.ci/cache-proof-linux-x64.json').read_text())
        self.assertEqual([row['row'] for row in proof['rows']], ['current'])
        self.assertEqual(proof['rows'][0]['hits'], 5)


class RestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace: Workspace = Workspace()
        self.addCleanup(shutil.rmtree, self.workspace.root, True)
        self.archive: Path = self.workspace.pack()
        self.target: Path = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.target, True)

    def release(self, tag: str, published: str, sha256: str = '') -> dict[str, Any]:
        asset: dict[str, Any] = {'name': self.archive.name, 'digest': 'sha256:' + (sha256 or digest(self.archive))}
        return {'tag_name': tag, 'prerelease': True, 'published_at': published, 'assets': [asset]}

    def test_the_newest_devkit_release_is_extracted(self) -> None:
        releases: list[dict[str, Any]] = [self.release('gf-' + '1' * 40, '2026-11-20T00:00:00Z'),
                                          self.release('gf-' + '2' * 40, '2026-11-22T00:00:00Z'),
                                          self.release('build-' + '3' * 40, '2026-11-23T00:00:00Z')]
        taken: list[str] = []

        def download(repository: str, tag: str, name: str, directory: Path) -> Path:
            taken.append(tag)
            return self.archive
        self.assertTrue(cache.restore(self.target, 'linux-x64', 'owner/devkit', '', lambda _: releases, download))
        self.assertEqual(taken, ['gf-' + '2' * 40])
        self.assertTrue((self.target / '.ccache/entry').is_file())
        self.assertTrue((self.target / build_guard.DEPS_RECORD).is_file())

    def test_no_published_cache_is_not_an_error(self) -> None:
        self.assertFalse(cache.restore(self.target, 'linux-x64', 'owner/devkit', '', lambda _: [],
                                       lambda *_: self.archive))

    def test_a_wrong_digest_is_refused(self) -> None:
        releases: list[dict[str, Any]] = [self.release('gf-' + '1' * 40, '2026-11-20T00:00:00Z', 'f' * 64)]
        with self.assertRaises(cache.resolver.ResolveError):
            cache.restore(self.target, 'linux-x64', 'owner/devkit', '', lambda _: releases, lambda *_: self.archive)


if __name__ == '__main__':
    unittest.main()
