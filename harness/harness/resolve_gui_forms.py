#!/usr/bin/env python3
"""Resolve the devkit's GUI.Forms pin to one green build and unpack its SDK at the fixed path.

devkit.toml pins GUI.Forms by major with a floor ([gui_forms] major,
minimum, channel, platforms). This turns that into one revision:

    python3 -B harness/harness/resolve_gui_forms.py resolve [--devkit FILE] [--workspace DIR]
            [--channel main|stable] [--revision SHA | --floor] [--dry-run]
    python3 -B harness/harness/resolve_gui_forms.py fetch --platform P [--workspace DIR] [--dry-run]

resolve
    Lists the repository's releases and takes the first candidate:

    - channel main: `build-<full sha>` pre-releases, newest published first;
      channel stable: `v<major>.*` releases, highest version first;
    - a candidate carries `gui-forms-sdk-<platform>.tar.gz` and
      `gui-forms-cache-<platform>.tar.gz` for every platform devkit.toml
      names (a platform publishes only when its native job passed, so all
      present means green) and `gui-forms-sdk-manifest.json`;
    - its SDK manifest's version has the pinned major and is at least
      `minimum`;
    - each platform's recorded compiler is the LLVM this harness's toolchain
      pins (windows_toolchain.json's "llvm": every platform builds with the
      same LLVM release).

    --revision SHA takes that commit's build exactly (the lockstep and the
    cache proof); --floor takes the newest build whose version is exactly
    `minimum` (the pull-request floor row). The result is written to
    <workspace>/.ci/gui_forms-resolved.json: the repository, tag, commit,
    version, the SDK manifest, and each platform's asset names and SHA-256.
    Every devkit artifact copies it into its own manifest, so a devkit build
    always says which GUI.Forms it was built on.

fetch
    Restores the resolved build's C++ runtime for the platform when it
    publishes one (gui-forms-runtime-<platform>.tar.gz, extracted into the
    workspace as restore_local.py extracts it; `restore_local.py runtime`
    then verifies it, and builds a runtime only when none verifies), and
    downloads the resolved build's SDK for one platform, checks it against
    the SHA-256 the record holds, and unpacks it at
    <workspace>/.sdk/gui-forms-sdk/, whatever the revision. ccache keys
    include include paths, so a per-revision path would make every devkit
    object miss on every advance; at a fixed path an object misses only when
    a header it reads changed. The revision lives in
    .sdk/gui-forms-sdk/devkit-sdk.json (the build guard reads it), not in
    the path. An SDK already unpacked from the same archive is kept.

The SDK manifest asset (published by GUI.Forms beside the SDK archives):

    {"schema": 1, "version": "1.0.4", "revision": "<40 hex>",
     "platforms": {"<platform>": {"compiler_version": "22.1.8",
                                  "compiler_sha256": "<hex>",
                                  "environment": {"CCACHE_COMPILERCHECK": ..., "LANG": ...},
                                  "sdk_version": "<macOS SDK, macOS only>"}}}

Each platform's record is the producer's cache-manifest.json fields of the
same names, so a consumer can match its compiler and environment before it
builds. Every GitHub call goes through gh when installed and the public
endpoints otherwise; tests replace `list_releases`, `read_json_asset` and
`download_asset`.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
from typing import Any, BinaryIO, Callable

HARNESS: Path = Path(__file__).resolve().parent
DEVKIT_ROOT: Path = HARNESS.parent.parent
DEVKIT_FILE: Path = DEVKIT_ROOT / 'devkit.toml'
TOOLCHAIN_SPEC: Path = HARNESS / 'windows_toolchain.json'
RESOLVED_RECORD: str = '.ci/gui_forms-resolved.json'
SDK_DIRECTORY: str = '.sdk/gui-forms-sdk'
SDK_RECORD: str = 'devkit-sdk.json'
DOWNLOAD_DIRECTORY: str = '.sdk/downloads'
RUNTIME_RECORD: str = '.ci/gui_forms-runtime.json'
SDK_ASSET: str = 'gui-forms-sdk-{platform}.tar.gz'
CACHE_ASSET: str = 'gui-forms-cache-{platform}.tar.gz'
MANIFEST_ASSET: str = 'gui-forms-sdk-manifest.json'
# Optional: the C++ runtime the build linked (macOS and Linux), restored so a
# consumer need not build it (restore_local.py runtime verifies it, and builds
# one only when none verifies).
RUNTIME_ASSET: str = 'gui-forms-runtime-{platform}.tar.gz'
CHANNELS: tuple[str, ...] = ('main', 'stable')
PLATFORMS: tuple[str, ...] = ('linux-x64', 'linux-arm64', 'macos-arm64', 'windows-x64')
RELEASES_PER_PAGE: int = 100
RELEASE_PAGES: int = 3
GITHUB_API: str = 'https://api.github.com/'
GITHUB_DOWNLOADS: str = 'https://github.com/'
BUILD_TAG: re.Pattern[str] = re.compile(r'build-([0-9a-f]{40})')
VERSION_TEXT: re.Pattern[str] = re.compile(r'v?([0-9]+)\.([0-9]+)\.([0-9]+)')

Version = tuple[int, int, int]


class ResolveError(Exception):
    """An expected refusal; the command prints it and exits 1."""


@dataclass(frozen=True)
class Pin:
    repository: str
    major: int
    minimum: Version
    channel: str
    platforms: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    tag: str
    revision: str
    published: str
    assets: dict[str, dict[str, Any]]


def parse_version(text: str) -> Version | None:
    """(major, minor, patch) of a version or tag such as 1.0.4 or v1.0.4; None when it is not one."""
    match: re.Match[str] | None = VERSION_TEXT.fullmatch(text.strip())
    if match is None:
        return None
    version: Version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return version


def version_text(version: Version) -> str:
    return '.'.join(str(part) for part in version)


def load_pin(path: Path) -> Pin:
    """devkit.toml's [gui_forms] table; raises ResolveError when it is malformed."""
    stream: BinaryIO
    with path.open('rb') as stream:
        document: dict[str, Any] = tomllib.load(stream)
    table: Any = document.get('gui_forms')
    if not isinstance(table, dict):
        raise ResolveError(str(path) + ' has no [gui_forms] table')
    minimum: Version | None = parse_version(str(table.get('minimum', '')))
    major: Any = table.get('major')
    if not isinstance(major, int) or minimum is None or minimum[0] != major:
        raise ResolveError(str(path) + ': [gui_forms] needs an integer major and a minimum x.y.z within it')
    channel: str = str(table.get('channel', 'main'))
    if channel not in CHANNELS:
        raise ResolveError(str(path) + ': channel must be main or stable, not ' + channel)
    platforms: tuple[str, ...] = tuple(str(name) for name in table.get('platforms', PLATFORMS))
    unknown: list[str] = sorted(set(platforms) - set(PLATFORMS))
    if unknown or not platforms:
        raise ResolveError(str(path) + ': unknown or no platforms: ' + ', '.join(unknown))
    repository: str = str(table.get('repository', ''))
    if repository.count('/') != 1:
        raise ResolveError(str(path) + ': repository must be owner/name')
    pin: Pin = Pin(repository, major, minimum, channel, platforms)
    return pin


def harness_llvm() -> str:
    """The LLVM release this harness's toolchain pins (windows_toolchain.json "llvm")."""
    spec: dict[str, Any] = json.loads(TOOLCHAIN_SPEC.read_text(encoding='utf-8'))
    llvm: str = str(spec.get('llvm', ''))
    return llvm


def github_request(url: str) -> urllib.request.Request:
    request: urllib.request.Request = urllib.request.Request(url, headers={'User-Agent': 'gui-forms-devkit-resolve'})
    token: str = os.environ.get('GH_TOKEN', '') or os.environ.get('GITHUB_TOKEN', '')
    if token:
        request.add_header('Authorization', 'Bearer ' + token)
    return request


def gh_json(path: str) -> Any:
    """GET a GitHub API path through gh, or from the public API without it."""
    if shutil.which('gh') is None:
        try:
            with urllib.request.urlopen(github_request(GITHUB_API + path), timeout=60) as response:
                value: Any = json.loads(response.read().decode('utf-8'))
        except OSError as error:
            raise ResolveError('GET ' + GITHUB_API + path + ' failed: ' + str(error)) from error
        return value
    completed: subprocess.CompletedProcess[str] = subprocess.run(['gh', 'api', path], capture_output=True,
                                                                 text=True, check=False)
    if completed.returncode != 0:
        raise ResolveError('gh api ' + path + ' failed: ' + completed.stderr.strip())
    listed: Any = json.loads(completed.stdout)
    return listed


def list_releases(repository: str) -> list[dict[str, Any]]:
    """The newest releases of repository, up to RELEASE_PAGES pages."""
    releases: list[dict[str, Any]] = []
    page: int
    for page in range(1, RELEASE_PAGES + 1):
        listed: list[dict[str, Any]] = gh_json('repos/' + repository + '/releases?per_page=' + str(RELEASES_PER_PAGE)
                                               + '&page=' + str(page))
        releases.extend(listed)
        if len(listed) < RELEASES_PER_PAGE:
            break
    return releases


def download_asset(repository: str, tag: str, name: str, directory: Path) -> Path:
    """Downloads one release asset into directory; returns its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path: Path = directory / name
    if shutil.which('gh') is None:
        url: str = GITHUB_DOWNLOADS + repository + '/releases/download/' + tag + '/' + name
        try:
            stream: BinaryIO
            with urllib.request.urlopen(github_request(url), timeout=600) as response, path.open('wb') as stream:
                shutil.copyfileobj(response, stream)
        except OSError as error:
            raise ResolveError('downloading ' + url + ' failed: ' + str(error)) from error
        return path
    subprocess.run(['gh', 'release', 'download', tag, '--repo', repository, '--pattern', name, '--dir',
                    str(directory), '--clobber'], check=True)
    return path


def read_json_asset(repository: str, tag: str, name: str, directory: Path) -> dict[str, Any]:
    """A small JSON release asset, downloaded and parsed."""
    path: Path = download_asset(repository, tag, name, directory)
    value: Any = json.loads(path.read_text(encoding='utf-8'))
    record: dict[str, Any] = value if isinstance(value, dict) else {}
    return record


def required_assets(platforms: tuple[str, ...]) -> list[str]:
    names: list[str] = [MANIFEST_ASSET]
    platform: str
    for platform in platforms:
        names.append(SDK_ASSET.format(platform=platform))
        names.append(CACHE_ASSET.format(platform=platform))
    return names


def candidates(releases: list[dict[str, Any]], pin: Pin, channel: str) -> list[Candidate]:
    """The releases of the channel that carry every required asset, in the order they are tried."""
    wanted: list[str] = required_assets(pin.platforms)
    found: list[Candidate] = []
    release: dict[str, Any]
    for release in releases:
        tag: str = str(release.get('tag_name', ''))
        build: re.Match[str] | None = BUILD_TAG.fullmatch(tag)
        if channel == 'main':
            if build is None or not release.get('prerelease'):
                continue
            revision: str = build.group(1)
        else:
            tagged: Version | None = parse_version(tag)
            if build is not None or release.get('prerelease') or tagged is None or tagged[0] != pin.major:
                continue
            revision = str(release.get('target_commitish', ''))
        assets: dict[str, dict[str, Any]] = {str(asset.get('name', '')): asset for asset in release.get('assets', [])}
        if any(name not in assets for name in wanted):
            continue
        found.append(Candidate(tag, revision, str(release.get('published_at', '')), assets))
    if channel == 'main':
        found.sort(key=lambda candidate: candidate.published, reverse=True)
    else:
        found.sort(key=lambda candidate: parse_version(candidate.tag) or (0, 0, 0), reverse=True)
    return found


def refusal(manifest: dict[str, Any], pin: Pin, llvm: str, exact: Version | None) -> str:
    """Why this SDK manifest does not satisfy the pin; empty when it does."""
    version: Version | None = parse_version(str(manifest.get('version', '')))
    if version is None:
        return 'its SDK manifest names no version'
    if version[0] != pin.major:
        return 'version ' + version_text(version) + ' is outside major ' + str(pin.major)
    if version < pin.minimum:
        return 'version ' + version_text(version) + ' is below the floor ' + version_text(pin.minimum)
    if exact is not None and version != exact:
        return 'version ' + version_text(version) + ' is not the floor ' + version_text(exact)
    records: Any = manifest.get('platforms')
    platform: str
    for platform in pin.platforms:
        record: Any = records.get(platform) if isinstance(records, dict) else None
        if not isinstance(record, dict):
            return 'its SDK manifest has no record for ' + platform
        compiler: str = str(record.get('compiler_version', ''))
        if compiler != llvm:
            return platform + ' was built with LLVM ' + (compiler or '(unrecorded)') + ', this harness pins ' + llvm
    return ''


def asset_digest(asset: dict[str, Any]) -> str:
    digest: str = str(asset.get('digest', ''))
    return digest[len('sha256:'):] if digest.startswith('sha256:') else ''


def resolved_record(pin: Pin, channel: str, candidate: Candidate, manifest: dict[str, Any]) -> dict[str, Any]:
    assets: dict[str, dict[str, dict[str, str]]] = {}
    platform: str
    for platform in pin.platforms:
        entry: dict[str, dict[str, str]] = {}
        kind: str
        pattern: str
        for kind, pattern in (('sdk', SDK_ASSET), ('cache', CACHE_ASSET)):
            name: str = pattern.format(platform=platform)
            entry[kind] = {'name': name, 'sha256': asset_digest(candidate.assets[name])}
        runtime: str = RUNTIME_ASSET.format(platform=platform)
        if runtime in candidate.assets:
            entry['runtime'] = {'name': runtime, 'sha256': asset_digest(candidate.assets[runtime])}
        assets[platform] = entry
    revision: str = str(manifest.get('revision', '')) or candidate.revision
    record: dict[str, Any] = {'schema': 1, 'repository': pin.repository, 'channel': channel, 'tag': candidate.tag,
                              'revision': revision, 'version': str(manifest.get('version', '')),
                              'major': pin.major, 'minimum': version_text(pin.minimum), 'manifest': manifest,
                              'assets': assets}
    return record


def resolve(pin: Pin, workspace: Path, channel: str, revision: str = '', floor: bool = False,
            releases: Callable[[str], list[dict[str, Any]]] = list_releases,
            manifest_reader: Callable[[str, str, str, Path], dict[str, Any]] = read_json_asset) -> dict[str, Any]:
    """The record of the first candidate satisfying the pin; raises ResolveError naming why each was refused."""
    llvm: str = harness_llvm()
    exact: Version | None = pin.minimum if floor else None
    listed: list[Candidate] = candidates(releases(pin.repository), pin, channel)
    if revision:
        listed = [candidate for candidate in listed if candidate.revision.startswith(revision.lower())]
    refusals: list[str] = []
    candidate: Candidate
    for candidate in listed:
        manifest: dict[str, Any] = manifest_reader(pin.repository, candidate.tag, MANIFEST_ASSET,
                                                   workspace / DOWNLOAD_DIRECTORY / candidate.tag)
        why: str = refusal(manifest, pin, llvm, exact)
        if not why:
            return resolved_record(pin, channel, candidate, manifest)
        refusals.append(candidate.tag + ': ' + why)
    wanted: str = ('revision ' + revision if revision else 'the floor ' + version_text(pin.minimum) if floor
                   else 'major ' + str(pin.major) + ' at least ' + version_text(pin.minimum))
    detail: str = ('; '.join(refusals[:5]) if refusals else 'no ' + channel + ' release carries every platform\'s '
                   'SDK and cache (' + ', '.join(pin.platforms) + ') and ' + MANIFEST_ASSET)
    raise ResolveError('No green GUI.Forms build for ' + wanted + ' in ' + pin.repository + ': ' + detail)


def write_resolved(workspace: Path, record: dict[str, Any]) -> Path:
    path: Path = workspace / RESOLVED_RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return path


def read_resolved(workspace: Path) -> dict[str, Any]:
    path: Path = workspace / RESOLVED_RECORD
    if not path.is_file():
        raise ResolveError('No ' + RESOLVED_RECORD + ' in ' + str(workspace) + '; run resolve first')
    value: Any = json.loads(path.read_text(encoding='utf-8'))
    record: dict[str, Any] = value if isinstance(value, dict) else {}
    return record


def file_digest(path: Path) -> str:
    stream: BinaryIO
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def common_top(names: list[PurePosixPath]) -> str:
    """The one top directory every member lies under, or "" (members then unpack as they are)."""
    tops: set[str] = {name.parts[0] for name in names if name.parts}
    if len(tops) != 1:
        return ''
    top: str = next(iter(tops))
    nested: bool = all(len(name.parts) > 1 or name.parts == (top,) for name in names)
    return top if nested else ''


def unpack_sdk(archive: Path, destination: Path) -> None:
    """Unpacks an SDK archive at destination, replacing what was there; a single top directory is stripped.

    Members must be relative and stay inside. The archive is unpacked beside
    destination first, so a failed unpack leaves the previous SDK in place.
    """
    staging: Path = destination.with_name(destination.name + '.new')
    previous: Path = destination.with_name(destination.name + '.old')
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(previous, ignore_errors=True)
    payload: tarfile.TarFile
    with tarfile.open(archive, 'r:*') as payload:
        members: list[tarfile.TarInfo] = payload.getmembers()
        names: list[PurePosixPath] = [PurePosixPath(member.name) for member in members]
        name: PurePosixPath
        for name in names:
            if not name.parts or name.is_absolute() or '..' in name.parts:
                raise ResolveError('Unexpected SDK archive member: ' + str(name))
        top: str = common_top(names)
        member: tarfile.TarInfo
        for member in members:
            if top:
                parts: tuple[str, ...] = PurePosixPath(member.name).parts[1:]
                if not parts:
                    continue
                member.name = PurePosixPath(*parts).as_posix()
            payload.extract(member, staging, filter='data')
    if destination.exists():
        destination.rename(previous)
    staging.rename(destination)
    shutil.rmtree(previous, ignore_errors=True)


def extract_into(archive: Path, workspace: Path) -> None:
    """Extracts an archive into the workspace; members must be relative and stay inside."""
    payload: tarfile.TarFile
    with tarfile.open(archive, 'r:*') as payload:
        member: tarfile.TarInfo
        for member in payload.getmembers():
            name: PurePosixPath = PurePosixPath(member.name)
            if not name.parts or name.is_absolute() or '..' in name.parts:
                raise ResolveError('Unexpected runtime archive member: ' + member.name)
        payload.extractall(workspace, filter='data')


def fetch_runtime(workspace: Path, record: dict[str, Any], runtime: dict[str, str], dry_run: bool,
                  downloader: Callable[[str, str, str, Path], Path]) -> None:
    """Restores the build's runtime asset into the workspace, once per asset."""
    marker: Path = workspace / RUNTIME_RECORD
    if marker.is_file() and json.loads(marker.read_text(encoding='utf-8')).get('sha256') == runtime['sha256'] \
            and runtime['sha256']:
        return
    if dry_run:
        print('would restore ' + runtime['name'] + ' of ' + str(record.get('tag')) + ' into ' + str(workspace),
              flush=True)
        return
    archive: Path = downloader(str(record['repository']), str(record['tag']), runtime['name'],
                               workspace / DOWNLOAD_DIRECTORY)
    digest: str = file_digest(archive)
    if runtime['sha256'] and digest != runtime['sha256']:
        raise ResolveError(runtime['name'] + ' of ' + str(record['tag']) + ' does not match its recorded SHA-256')
    extract_into(archive, workspace)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({'tag': record['tag'], 'asset': runtime['name'], 'sha256': digest}) + '\n',
                      encoding='utf-8')
    print('Restored ' + runtime['name'] + ' of ' + str(record['tag']) + '; restore_local.py runtime verifies it',
          flush=True)


def fetch(workspace: Path, platform: str, dry_run: bool = False,
          downloader: Callable[[str, str, str, Path], Path] = download_asset) -> Path:
    """Restores the resolved build's runtime when it has one and unpacks its SDK for platform at the fixed path;
    returns that path."""
    record: dict[str, Any] = read_resolved(workspace)
    assets: Any = record.get('assets', {}).get(platform)
    if not isinstance(assets, dict):
        raise ResolveError('The resolved build ' + str(record.get('tag')) + ' has no SDK for ' + platform)
    if isinstance(assets.get('runtime'), dict):
        fetch_runtime(workspace, record, assets['runtime'], dry_run, downloader)
    sdk: dict[str, str] = assets['sdk']
    destination: Path = workspace / SDK_DIRECTORY
    marker: Path = destination / SDK_RECORD
    if marker.is_file():
        present: dict[str, Any] = json.loads(marker.read_text(encoding='utf-8'))
        if present.get('sha256') == sdk['sha256'] and present.get('platform') == platform and sdk['sha256']:
            print('The SDK of ' + str(record.get('tag')) + ' is already at ' + str(destination), flush=True)
            return destination
    if dry_run:
        print('would download ' + sdk['name'] + ' of ' + str(record.get('tag')) + ' and unpack it at '
              + str(destination), flush=True)
        return destination
    archive: Path = downloader(str(record['repository']), str(record['tag']), sdk['name'],
                               workspace / DOWNLOAD_DIRECTORY)
    digest: str = file_digest(archive)
    if sdk['sha256'] and digest != sdk['sha256']:
        raise ResolveError(sdk['name'] + ' of ' + str(record['tag']) + ' does not match its recorded SHA-256')
    unpack_sdk(archive, destination)
    platform_record: Any = record.get('manifest', {}).get('platforms', {}).get(platform, {})
    written: dict[str, Any] = {'schema': 1, 'repository': record['repository'], 'tag': record['tag'],
                               'revision': record['revision'], 'version': record['version'], 'platform': platform,
                               'asset': sdk['name'], 'sha256': digest, 'producer': platform_record}
    marker.write_text(json.dumps(written, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print('Unpacked GUI.Forms ' + str(record['version']) + ' (' + str(record['revision'])[:12] + ') for ' + platform
          + ' at ' + str(destination), flush=True)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(dest='command',
                                                                                          required=True)
    resolving: argparse.ArgumentParser = commands.add_parser('resolve')
    resolving.add_argument('--devkit', type=Path, default=DEVKIT_FILE)
    resolving.add_argument('--workspace', type=Path, default=DEVKIT_ROOT)
    resolving.add_argument('--channel', choices=CHANNELS, default=None)
    exact: argparse._MutuallyExclusiveGroup = resolving.add_mutually_exclusive_group()
    exact.add_argument('--revision', default='')
    exact.add_argument('--floor', action='store_true')
    resolving.add_argument('--dry-run', action='store_true')
    fetching: argparse.ArgumentParser = commands.add_parser('fetch')
    fetching.add_argument('--workspace', type=Path, default=DEVKIT_ROOT)
    fetching.add_argument('--platform', choices=PLATFORMS, required=True)
    fetching.add_argument('--dry-run', action='store_true')
    arguments: argparse.Namespace = parser.parse_args(argv)
    try:
        if arguments.command == 'resolve':
            pin: Pin = load_pin(arguments.devkit)
            channel: str = arguments.channel or pin.channel
            record: dict[str, Any] = resolve(pin, arguments.workspace.resolve(), channel, arguments.revision,
                                             arguments.floor)
            print('GUI.Forms ' + record['version'] + ' at ' + record['revision'][:12] + ' (' + record['tag'] + ')',
                  flush=True)
            if not arguments.dry_run:
                print('Wrote ' + str(write_resolved(arguments.workspace.resolve(), record)), flush=True)
        else:
            fetch(arguments.workspace.resolve(), arguments.platform, arguments.dry_run)
    except ResolveError as error:
        print('resolve_gui_forms: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
