"""Tests resolve_gui_forms.py: the pin, the candidate rules, the fixed SDK path."""

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
from typing import Any
import unittest

import resolve_gui_forms as resolver

LLVM: str = resolver.harness_llvm()
PLATFORMS: tuple[str, ...] = ('linux-x64', 'macos-arm64')


def sha(number: int) -> str:
    return format(number, 'x').ljust(40, 'a')


def pin(minimum: tuple[int, int, int] = (1, 0, 3)) -> resolver.Pin:
    return resolver.Pin('owner/gui_forms', 1, minimum, 'main', PLATFORMS)


def asset(name: str) -> dict[str, Any]:
    return {'name': name, 'digest': 'sha256:' + hashlib.sha256(name.encode()).hexdigest()}


def release(tag: str, published: str, prerelease: bool = True, platforms: tuple[str, ...] = PLATFORMS,
            manifest: bool = True) -> dict[str, Any]:
    names: list[str] = [resolver.MANIFEST_ASSET] if manifest else []
    for platform in platforms:
        names += [resolver.SDK_ASSET.format(platform=platform), resolver.CACHE_ASSET.format(platform=platform)]
    return {'tag_name': tag, 'prerelease': prerelease, 'published_at': published, 'target_commitish': sha(99),
            'assets': [asset(name) for name in names]}


def sdk_manifest(version: str, compiler: str = LLVM, platforms: tuple[str, ...] = PLATFORMS) -> dict[str, Any]:
    return {'schema': 1, 'version': version,
            'platforms': {platform: {'compiler_version': compiler, 'compiler_sha256': 'c' * 64,
                                     'environment': {'CCACHE_COMPILERCHECK': 'content'}} for platform in platforms}}


class Fixture:
    def __init__(self, releases: list[dict[str, Any]], manifests: dict[str, dict[str, Any]]) -> None:
        self.releases: list[dict[str, Any]] = releases
        self.manifests: dict[str, dict[str, Any]] = manifests
        self.read: list[str] = []

    def list(self, repository: str) -> list[dict[str, Any]]:
        return self.releases

    def manifest(self, repository: str, tag: str, name: str, directory: Path) -> dict[str, Any]:
        self.read.append(tag)
        return self.manifests[tag]


class PinTests(unittest.TestCase):
    def write(self, text: str) -> Path:
        directory: Path = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(directory, True))
        path: Path = directory / 'devkit.toml'
        path.write_text(text, encoding='utf-8')
        return path

    def test_the_repository_file_loads(self) -> None:
        loaded: resolver.Pin = resolver.load_pin(resolver.DEVKIT_FILE)
        self.assertEqual(loaded.major, 1)
        self.assertEqual(loaded.minimum[0], 1)

    def test_a_floor_outside_the_major_is_refused(self) -> None:
        path: Path = self.write('[gui_forms]\nrepository = "a/b"\nmajor = 1\nminimum = "2.0.0"\n')
        with self.assertRaises(resolver.ResolveError):
            resolver.load_pin(path)

    def test_an_unknown_channel_is_refused(self) -> None:
        path: Path = self.write('[gui_forms]\nrepository = "a/b"\nmajor = 1\nminimum = "1.0.0"\nchannel = "x"\n')
        with self.assertRaises(resolver.ResolveError):
            resolver.load_pin(path)


class ResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace: Path = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(self.workspace, True))

    def run_resolve(self, fixture: Fixture, **options: Any) -> dict[str, Any]:
        record: dict[str, Any] = resolver.resolve(options.pop('the_pin', pin()), self.workspace,
                                                  options.pop('channel', 'main'), releases=fixture.list,
                                                  manifest_reader=fixture.manifest, **options)
        return record

    def test_the_newest_green_build_in_range_wins(self) -> None:
        fixture: Fixture = Fixture(
            [release('build-' + sha(1), '2026-11-20T00:00:00Z'), release('build-' + sha(2), '2026-11-22T00:00:00Z')],
            {'build-' + sha(1): sdk_manifest('1.0.3'), 'build-' + sha(2): sdk_manifest('1.0.4')})
        record: dict[str, Any] = self.run_resolve(fixture)
        self.assertEqual(record['revision'], sha(2))
        self.assertEqual(record['version'], '1.0.4')
        self.assertEqual(record['assets']['macos-arm64']['sdk']['name'], 'gui-forms-sdk-macos-arm64.tar.gz')
        self.assertEqual(len(record['assets']['linux-x64']['cache']['sha256']), 64)

    def test_a_build_missing_a_platform_is_not_green(self) -> None:
        fixture: Fixture = Fixture(
            [release('build-' + sha(1), '2026-11-20T00:00:00Z'),
             release('build-' + sha(2), '2026-11-22T00:00:00Z', platforms=('linux-x64',))],
            {'build-' + sha(1): sdk_manifest('1.0.3')})
        self.assertEqual(self.run_resolve(fixture)['revision'], sha(1))
        self.assertNotIn('build-' + sha(2), fixture.read)

    def test_a_build_without_the_sdk_manifest_is_skipped(self) -> None:
        fixture: Fixture = Fixture([release('build-' + sha(2), '2026-11-22T00:00:00Z', manifest=False)], {})
        with self.assertRaises(resolver.ResolveError):
            self.run_resolve(fixture)

    def test_below_the_floor_or_another_major_is_refused(self) -> None:
        fixture: Fixture = Fixture(
            [release('build-' + sha(1), '2026-11-20T00:00:00Z'), release('build-' + sha(2), '2026-11-22T00:00:00Z')],
            {'build-' + sha(1): sdk_manifest('1.0.2'), 'build-' + sha(2): sdk_manifest('2.0.0')})
        with self.assertRaises(resolver.ResolveError) as raised:
            self.run_resolve(fixture)
        self.assertIn('below the floor', str(raised.exception))
        self.assertIn('outside major', str(raised.exception))

    def test_another_compiler_is_refused(self) -> None:
        fixture: Fixture = Fixture([release('build-' + sha(1), '2026-11-20T00:00:00Z')],
                                   {'build-' + sha(1): sdk_manifest('1.0.3', compiler='21.1.0')})
        with self.assertRaises(resolver.ResolveError) as raised:
            self.run_resolve(fixture)
        self.assertIn('LLVM 21.1.0', str(raised.exception))

    def test_revision_takes_one_build_exactly(self) -> None:
        fixture: Fixture = Fixture(
            [release('build-' + sha(1), '2026-11-20T00:00:00Z'), release('build-' + sha(2), '2026-11-22T00:00:00Z')],
            {'build-' + sha(1): sdk_manifest('1.0.3'), 'build-' + sha(2): sdk_manifest('1.0.4')})
        self.assertEqual(self.run_resolve(fixture, revision=sha(1)[:12])['revision'], sha(1))

    def test_floor_takes_the_floor_version(self) -> None:
        fixture: Fixture = Fixture(
            [release('build-' + sha(1), '2026-11-20T00:00:00Z'), release('build-' + sha(2), '2026-11-22T00:00:00Z')],
            {'build-' + sha(1): sdk_manifest('1.0.3'), 'build-' + sha(2): sdk_manifest('1.0.4')})
        self.assertEqual(self.run_resolve(fixture, floor=True)['version'], '1.0.3')

    def test_stable_takes_the_highest_release_of_the_major(self) -> None:
        fixture: Fixture = Fixture(
            [release('v1.0.3', '2026-11-20T00:00:00Z', prerelease=False),
             release('v1.0.10', '2026-11-19T00:00:00Z', prerelease=False),
             release('v2.0.0', '2026-11-23T00:00:00Z', prerelease=False),
             release('build-' + sha(2), '2026-11-22T00:00:00Z')],
            {'v1.0.3': sdk_manifest('1.0.3'), 'v1.0.10': sdk_manifest('1.0.10')})
        self.assertEqual(self.run_resolve(fixture, channel='stable')['tag'], 'v1.0.10')

    def test_the_record_is_written_under_ci(self) -> None:
        fixture: Fixture = Fixture([release('build-' + sha(1), '2026-11-20T00:00:00Z')],
                                   {'build-' + sha(1): sdk_manifest('1.0.3')})
        path: Path = resolver.write_resolved(self.workspace, self.run_resolve(fixture))
        self.assertEqual(path, self.workspace / '.ci' / 'gui_forms-resolved.json')
        self.assertEqual(resolver.read_resolved(self.workspace)['version'], '1.0.3')


def sdk_archive(directory: Path, name: str, top: str, marker: str) -> Path:
    path: Path = directory / name
    with tarfile.open(path, 'w:gz') as archive:
        data: bytes = marker.encode()
        info: tarfile.TarInfo = tarfile.TarInfo(top + '/lib/cmake/GUIForms/GUIFormsConfig.cmake')
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return path


class FetchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace: Path = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(self.workspace, True))
        self.archives: Path = self.workspace / 'archives'
        self.archives.mkdir()

    def record(self, revision: str, archive: Path) -> None:
        digest: str = hashlib.sha256(archive.read_bytes()).hexdigest()
        resolver.write_resolved(self.workspace, {
            'repository': 'owner/gui_forms', 'tag': 'build-' + revision, 'revision': revision, 'version': '1.0.4',
            'manifest': sdk_manifest('1.0.4'),
            'assets': {'macos-arm64': {'sdk': {'name': archive.name, 'sha256': digest},
                                       'cache': {'name': 'c', 'sha256': ''}}}})

    def downloader(self, archive: Path) -> Any:
        def download(repository: str, tag: str, name: str, directory: Path) -> Path:
            return archive
        return download

    def test_every_revision_unpacks_at_the_same_path(self) -> None:
        first: Path = sdk_archive(self.archives, 'first.tar.gz', 'gui-forms-sdk-1.0.4', 'one')
        self.record(sha(1), first)
        path: Path = resolver.fetch(self.workspace, 'macos-arm64', downloader=self.downloader(first))
        self.assertEqual(path, self.workspace / '.sdk' / 'gui-forms-sdk')
        config: Path = path / 'lib/cmake/GUIForms/GUIFormsConfig.cmake'
        self.assertEqual(config.read_text(), 'one')
        second: Path = sdk_archive(self.archives, 'second.tar.gz', 'gui-forms-sdk-1.0.5', 'two')
        self.record(sha(2), second)
        self.assertEqual(resolver.fetch(self.workspace, 'macos-arm64', downloader=self.downloader(second)), path)
        self.assertEqual(config.read_text(), 'two')
        written: dict[str, Any] = json.loads((path / resolver.SDK_RECORD).read_text())
        self.assertEqual(written['revision'], sha(2))
        self.assertEqual(written['producer']['compiler_sha256'], 'c' * 64)

    def test_a_wrong_digest_leaves_the_previous_sdk(self) -> None:
        first: Path = sdk_archive(self.archives, 'first.tar.gz', 'top', 'one')
        self.record(sha(1), first)
        resolver.fetch(self.workspace, 'macos-arm64', downloader=self.downloader(first))
        second: Path = sdk_archive(self.archives, 'second.tar.gz', 'top', 'two')
        self.record(sha(2), second)
        other: Path = sdk_archive(self.archives, 'other.tar.gz', 'top', 'tampered')
        with self.assertRaises(resolver.ResolveError):
            resolver.fetch(self.workspace, 'macos-arm64', downloader=self.downloader(other))
        config: Path = self.workspace / '.sdk/gui-forms-sdk/lib/cmake/GUIForms/GUIFormsConfig.cmake'
        self.assertEqual(config.read_text(), 'one')

    def test_the_runtime_asset_is_restored_into_the_workspace(self) -> None:
        sdk: Path = sdk_archive(self.archives, 'sdk.tar.gz', 'top', 'one')
        runtime: Path = self.archives / 'gui-forms-runtime-macos-arm64.tar.gz'
        with tarfile.open(runtime, 'w:gz') as archive:
            data: bytes = b'{}'
            info: tarfile.TarInfo = tarfile.TarInfo('.build/toolchain/llvm-22.1.8-macos14/runtime-manifest.json')
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        self.record(sha(1), sdk)
        record: dict[str, Any] = resolver.read_resolved(self.workspace)
        record['assets']['macos-arm64']['runtime'] = {'name': runtime.name,
                                                      'sha256': hashlib.sha256(runtime.read_bytes()).hexdigest()}
        resolver.write_resolved(self.workspace, record)

        def download(repository: str, tag: str, name: str, directory: Path) -> Path:
            return runtime if name == runtime.name else sdk
        resolver.fetch(self.workspace, 'macos-arm64', downloader=download)
        self.assertTrue((self.workspace / '.build/toolchain/llvm-22.1.8-macos14/runtime-manifest.json').is_file())
        self.assertTrue((self.workspace / resolver.RUNTIME_RECORD).is_file())

    def test_a_runtime_asset_is_recorded_when_published(self) -> None:
        listed: dict[str, Any] = release('build-' + sha(1), '2026-11-20T00:00:00Z')
        listed['assets'].append(asset('gui-forms-runtime-linux-x64.tar.gz'))
        candidate: resolver.Candidate = resolver.candidates([listed], pin(), 'main')[0]
        record: dict[str, Any] = resolver.resolved_record(pin(), 'main', candidate, sdk_manifest('1.0.3'))
        self.assertEqual(record['assets']['linux-x64']['runtime']['name'], 'gui-forms-runtime-linux-x64.tar.gz')
        self.assertNotIn('runtime', record['assets']['macos-arm64'])

    def test_an_escaping_member_is_refused(self) -> None:
        path: Path = self.archives / 'bad.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            info: tarfile.TarInfo = tarfile.TarInfo('../outside')
            archive.addfile(info, io.BytesIO(b''))
        with self.assertRaises(resolver.ResolveError):
            resolver.unpack_sdk(path, self.workspace / 'sdk')


if __name__ == '__main__':
    unittest.main()
