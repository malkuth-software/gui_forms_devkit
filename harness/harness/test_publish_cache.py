"""Concurrent platforms may create one release, but cannot replace its bytes."""
from __future__ import annotations
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

import harness_testing
import publish_cache


class PublicationCommands:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.creation_race: bool = False
        self.existing_asset: bool = False
        self.existing_bytes: bytes = b'archive'
        self.views: int = 0

    def run(self, command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        result: int = 0
        action: str = command[2]
        if action == 'view':
            self.views += 1
            if self.views == 1:
                result = 1
        if action == 'create' and self.creation_race:
            result = 1
        if action == 'upload' and self.existing_asset:
            result = 1
        if action == 'download':
            destination: Path = Path(command[command.index('--dir') + 1])
            name: str = command[command.index('--pattern') + 1]
            (destination / name).write_bytes(self.existing_bytes)
        if options.get('check') and result != 0:
            raise subprocess.CalledProcessError(result, command)
        return subprocess.CompletedProcess(command, result, '', '')


class PublicationTests(unittest.TestCase):
    def publish(self, fixture: PublicationCommands, revision: str = 'revision', tag: str = '') -> None:
        reference: dict[str, Any] = {'object': {'type': 'commit', 'sha': revision}}
        with tempfile.TemporaryDirectory() as directory:
            archive: Path = Path(directory) / 'gui-forms-cache-linux-x64.tar.gz'
            archive.write_bytes(b'archive')
            with patch.object(publish_cache.subprocess, 'run', side_effect=fixture.run), \
                 patch.object(publish_cache, 'api', return_value=reference):
                publish_cache.publish('owner/repo', 'revision', archive, tag)

    def test_first_platform_creates_and_publishes_without_other_archives(self) -> None:
        fixture: PublicationCommands = PublicationCommands()
        self.publish(fixture)
        self.assertEqual(fixture.calls[-1][2], 'upload')
        self.assertNotIn('--clobber', fixture.calls[-1])

    def test_other_platform_winning_release_creation_is_accepted(self) -> None:
        fixture: PublicationCommands = PublicationCommands()
        fixture.creation_race = True
        self.publish(fixture)
        self.assertEqual(fixture.views, 2)

    def test_a_named_tag_is_created_on_the_tested_commit(self) -> None:
        fixture: PublicationCommands = PublicationCommands()
        self.publish(fixture, tag='gf-' + 'a' * 40)
        created: list[str] = next(call for call in fixture.calls if call[2] == 'create')
        self.assertEqual(created[3], 'gf-' + 'a' * 40)
        self.assertEqual(created[created.index('--target') + 1], 'revision')
        self.assertEqual(fixture.calls[-1][3], 'gf-' + 'a' * 40)

    def test_wrong_source_tag_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, 'tested source commit'):
            self.publish(PublicationCommands(), 'wrong')

    def test_rerun_accepts_equal_bytes_but_refuses_changed_asset(self) -> None:
        fixture: PublicationCommands = PublicationCommands()
        fixture.existing_asset = True
        self.publish(fixture)
        fixture = PublicationCommands()
        fixture.existing_asset = True
        fixture.existing_bytes = b'different'
        with self.assertRaisesRegex(ValueError, 'different bytes'):
            self.publish(fixture)


class MainTests(unittest.TestCase):
    def test_the_devkit_publishes_cache_and_packages_into_its_tag_without_a_toolchain(self) -> None:
        import json
        import os
        import project
        devkit: project.Project = project.load(Path(__file__).resolve().parent.parent / 'projects'
                                               / 'gui_forms_devkit.toml')
        published: list[tuple[str, str, str]] = []
        with tempfile.TemporaryDirectory() as directory:
            inputs: Path = Path(directory) / 'inputs.json'
            inputs.write_text(json.dumps({'platform': 'windows-x64', 'revision': 'c' * 40}))
            arguments: list[str] = ['publish_cache.py', '--platform', 'windows-x64', '--tag', 'gf-' + 'a' * 40,
                                    '--inputs', str(inputs), '--asset', 'dist/a.zip', '--no-toolchain']
            with patch("sys.argv", arguments), \
                 patch.dict(os.environ, {'GITHUB_SHA': 'c' * 40, 'GITHUB_REPOSITORY': 'owner/devkit'}), \
                 patch.object(publish_cache.project, 'current', return_value=devkit), \
                 patch.object(publish_cache.windows_toolchain, 'publication_files',
                              side_effect=AssertionError('no toolchain')), \
                 patch.object(publish_cache, 'publish',
                              side_effect=lambda repository, revision, archive, tag: published.append(
                                  (archive.as_posix(), revision, tag))):
                publish_cache.main()
        self.assertEqual(published, [('gui-forms-devkit-cache-windows-x64.tar.gz', 'c' * 40, 'gf-' + 'a' * 40),
                                     ('dist/a.zip', 'c' * 40, 'gf-' + 'a' * 40)])


if __name__ == '__main__':
    unittest.main()
