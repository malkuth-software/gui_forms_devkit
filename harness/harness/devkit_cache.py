#!/usr/bin/env python3
"""The devkit's own compiler cache and the cache proof.

    python3 -B harness/harness/devkit_cache.py pack --workspace W --platform P --build-dir B
            --revision SHA --compiler PATH
    python3 -B harness/harness/devkit_cache.py restore --workspace W --platform P [--repository R] [--tag TAG]
    python3 -B harness/harness/devkit_cache.py expect --workspace W --row ROW
    python3 -B harness/harness/devkit_cache.py prove --workspace W --platform P --row ROW --stats FILE
            [--gui-forms LABEL]

pack
    After a lockstep build: records each object's inputs (build_guard.py
    record, .ci/devkit-deps.json), writes cache-manifest.json (the compiler's
    SHA-256, the ccache settings and locale of the compile, and the GUI.Forms
    build it was made against, from .ci/gui_forms-resolved.json), and packs
    .ccache/, the dependency record and the manifest into
    gui-forms-devkit-cache-<platform>.tar.gz at the workspace root, the name
    projects/gui_forms_devkit.toml gives publish_cache.py. It also writes the
    identity publish_cache.py checks (.ci/inputs.json: platform, revision).

restore
    Extracts the newest devkit cache into the workspace: the newest
    `gf-<GUI.Forms sha>` pre-release of the repository carrying this
    platform's asset (or --tag's), checked against the digest GitHub lists.
    No published cache yet is not an error: the first lockstep run fills it.

expect
    Before a cache-proof build, after the SDK of the row is unpacked: the
    expected hits, computed and not guessed. An object whose recorded inputs
    (the restored .ci/devkit-deps.json) are byte identical in this workspace
    must hit; .ci/cache-proof-expected-<row>.json holds the count.

prove
    After the build, with `ccache --print-stats` in --stats: the row's hits
    (direct and preprocessed) against its expectation. Rows and their pass
    conditions (DEVKIT_DESIGN.md section 2):

        current, previous   at least 99% of the expected hits
        stable, floor       recorded; a warning below a 50% hit rate
        gui-forms-current   GUI.Forms built at R from its own published
                            cache: at least a 98% hit rate
        gui-forms-previous  the same from R-1's cache: recorded

    Each row is appended to .ci/cache-proof-<platform>.json (the job's
    artifact) and, under Actions, to the job summary. Exit 1 when a row
    fails.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from typing import Any, Callable

import build_guard
import resolve_gui_forms as resolver

CACHE_ASSET: str = 'gui-forms-devkit-cache-{platform}.tar.gz'
DEVKIT_TAG_PREFIX: str = 'gf-'
DEVKIT_REPOSITORY: str = 'malkuth-software/gui_forms_devkit'
INPUTS_RECORD: str = '.ci/inputs.json'
RESTORED_RECORD: str = '.ci/devkit-cache-restored.json'
EXPECTED_RECORD: str = '.ci/cache-proof-expected-{row}.json'
PROOF_RECORD: str = '.ci/cache-proof-{platform}.json'
CACHE_DIRECTORY: str = '.ccache'


@dataclass(frozen=True)
class Rule:
    # 'expected': hits against the computed expectation; 'rate': hits against all compilations.
    basis: str
    # The least share that passes; 0 records only.
    required: float
    # Below this share the row warns (0: never).
    warn_below: float


RULES: dict[str, Rule] = {
    'current': Rule('expected', 0.99, 0.0),
    'previous': Rule('expected', 0.99, 0.0),
    'stable': Rule('rate', 0.0, 0.5),
    'floor': Rule('rate', 0.0, 0.5),
    'gui-forms-current': Rule('rate', 0.98, 0.0),
    'gui-forms-previous': Rule('rate', 0.0, 0.0),
}


def recorded_environment(environment: dict[str, str]) -> dict[str, str | None]:
    """The compile settings a consumer must match (None: unset), as cache-manifest.json records them."""
    values: dict[str, str | None] = {}
    name: str
    for name in build_guard.CCACHE_VARIABLES + build_guard.LOCALE_VARIABLES:
        values[name] = environment.get(name) or None
    return values


def cache_manifest(workspace: Path, platform: str, revision: str, compiler: Path,
                   environment: dict[str, str]) -> dict[str, Any]:
    resolved: dict[str, Any] = build_guard.read_json(workspace / resolver.RESOLVED_RECORD)
    producer: Any = resolved.get('manifest', {}).get('platforms', {}).get(platform, {})
    manifest: dict[str, Any] = {
        'schema': 1, 'product': 'gui_forms_devkit', 'platform': platform, 'revision': revision,
        'compiler_sha256': build_guard.file_digest(compiler.resolve()),
        'compiler_version': str(producer.get('compiler_version', '')) if isinstance(producer, dict) else '',
        'environment': recorded_environment(environment),
        'gui_forms': {key: resolved.get(key, '') for key in ('tag', 'revision', 'version')}}
    return manifest


def pack(workspace: Path, platform: str, build_dir: Path, revision: str, compiler: Path, deps_text: str,
         environment: dict[str, str]) -> Path:
    """Writes the dependency record, the manifest and the identity; returns the cache archive."""
    record: dict[str, Any] = build_guard.deps_record(workspace, build_dir, deps_text)
    deps: Path = workspace / build_guard.DEPS_RECORD
    deps.parent.mkdir(parents=True, exist_ok=True)
    deps.write_text(json.dumps(record, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    manifest: dict[str, Any] = cache_manifest(workspace, platform, revision, compiler, environment)
    (workspace / build_guard.CACHE_MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n',
                                                         encoding='utf-8')
    (workspace / INPUTS_RECORD).write_text(json.dumps({'platform': platform, 'revision': revision}) + '\n',
                                           encoding='utf-8')
    archive: Path = workspace / CACHE_ASSET.format(platform=platform)
    payload: tarfile.TarFile
    with tarfile.open(archive, 'w:gz') as payload:
        name: str
        for name in (CACHE_DIRECTORY, build_guard.DEPS_RECORD, build_guard.CACHE_MANIFEST):
            if (workspace / name).exists():
                payload.add(workspace / name, arcname=name)
    print('Packed ' + str(len(record['objects'])) + ' recorded objects and ' + CACHE_DIRECTORY + ' into '
          + str(archive), flush=True)
    return archive


def newest_cache(releases: list[dict[str, Any]], platform: str, tag: str) -> tuple[str, dict[str, Any]] | None:
    """(tag, asset) of the newest devkit pre-release carrying the platform's cache, or of `tag` when named."""
    wanted: str = CACHE_ASSET.format(platform=platform)
    found: list[tuple[str, str, dict[str, Any]]] = []
    release: dict[str, Any]
    for release in releases:
        name: str = str(release.get('tag_name', ''))
        if tag and name != tag:
            continue
        if not tag and (not name.startswith(DEVKIT_TAG_PREFIX) or not release.get('prerelease')):
            continue
        asset: dict[str, Any]
        for asset in release.get('assets', []):
            if asset.get('name') == wanted:
                found.append((str(release.get('published_at', '')), name, asset))
    if not found:
        return None
    found.sort(key=lambda entry: entry[0], reverse=True)
    return found[0][1], found[0][2]


def restore(workspace: Path, platform: str, repository: str, tag: str,
            releases: Callable[[str], list[dict[str, Any]]] = resolver.list_releases,
            downloader: Callable[[str, str, str, Path], Path] = resolver.download_asset) -> bool:
    """Extracts the newest devkit cache; False when none is published."""
    chosen: tuple[str, dict[str, Any]] | None = newest_cache(releases(repository), platform, tag)
    if chosen is None:
        print('No published devkit cache for ' + platform + (' in ' + tag if tag else '') + '; the build fills one',
              flush=True)
        return False
    release_tag: str
    asset: dict[str, Any]
    release_tag, asset = chosen
    archive: Path = downloader(repository, release_tag, str(asset['name']), workspace / resolver.DOWNLOAD_DIRECTORY)
    expected: str = resolver.asset_digest(asset)
    digest: str = resolver.file_digest(archive)
    if expected and digest != expected:
        raise resolver.ResolveError(str(asset['name']) + ' of ' + release_tag + ' does not match its listed SHA-256')
    resolver.extract_into(archive, workspace)
    marker: Path = workspace / RESTORED_RECORD
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({'tag': release_tag, 'asset': asset['name'], 'sha256': digest}) + '\n',
                      encoding='utf-8')
    print('Restored ' + str(asset['name']) + ' of ' + release_tag, flush=True)
    return True


def expect(workspace: Path, row: str) -> dict[str, Any]:
    record: dict[str, Any] = build_guard.read_json(workspace / build_guard.DEPS_RECORD)
    objects: list[str] = list(record.get('objects', {}))
    hits: int
    known: int
    misses: list[str]
    hits, known, misses = build_guard.projected_hits(workspace, record, objects)
    expectation: dict[str, Any] = {'row': row, 'expected': hits, 'recorded': known, 'will_miss': misses}
    path: Path = workspace / EXPECTED_RECORD.format(row=row)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(expectation, indent=2) + '\n', encoding='utf-8')
    print('cache proof ' + row + ': ' + str(hits) + ' of ' + str(known) + ' recorded objects must hit', flush=True)
    return expectation


def stats_counters(text: str) -> dict[str, int]:
    """`ccache --print-stats` lines (name TAB value) as counters."""
    counters: dict[str, int] = {}
    line: str
    for line in text.splitlines():
        fields: list[str] = line.split('\t')
        if len(fields) == 2 and fields[1].strip().isdigit():
            counters[fields[0].strip()] = int(fields[1])
    return counters


def judge(row: str, counters: dict[str, int], expected: int) -> dict[str, Any]:
    """The row's verdict: 'pass', 'warn' or 'fail', with the numbers it rests on."""
    rule: Rule = RULES[row]
    hits: int = counters.get('direct_cache_hit', 0) + counters.get('preprocessed_cache_hit', 0)
    compilations: int = hits + counters.get('cache_miss', 0)
    rate: float = hits / compilations if compilations else 1.0
    verdict: str = 'pass'
    reason: str = ''
    if rule.basis == 'expected':
        needed: int = math.ceil(rule.required * expected)
        if hits < needed:
            verdict = 'fail'
            reason = (str(hits) + ' hits, ' + str(needed) + ' needed (' + str(round(rule.required * 100)) + '% of '
                      + str(expected) + ' expected)')
    elif rule.required and rate < rule.required:
        verdict = 'fail'
        reason = 'hit rate ' + format(rate, '.1%') + ' below ' + format(rule.required, '.0%')
    if verdict == 'pass' and rule.warn_below and rate < rule.warn_below:
        verdict = 'warn'
        reason = 'hit rate ' + format(rate, '.1%') + ' below ' + format(rule.warn_below, '.0%')
    misses: dict[str, int] = {name: value for name, value in counters.items()
                              if value and (name.startswith('cache_miss') or name in (
                                  'compiler_check_failed', 'could_not_use_precompiled_header',
                                  'could_not_use_modules', 'unsupported_compiler_option',
                                  'preprocessor_error', 'compile_failed'))}
    result: dict[str, Any] = {'row': row, 'verdict': verdict, 'reason': reason, 'hits': hits,
                              'compilations': compilations, 'expected': expected, 'hit_rate': round(rate, 4),
                              'misses': misses}
    return result


def prove(workspace: Path, platform: str, row: str, stats_text: str, gui_forms: str) -> dict[str, Any]:
    expectation: dict[str, Any] = build_guard.read_json(workspace / EXPECTED_RECORD.format(row=row))
    result: dict[str, Any] = judge(row, stats_counters(stats_text), int(expectation.get('expected', 0)))
    result['gui_forms'] = gui_forms
    result['will_miss'] = expectation.get('will_miss', [])
    path: Path = workspace / PROOF_RECORD.format(platform=platform)
    proof: dict[str, Any] = build_guard.read_json(path) or {'schema': 1, 'platform': platform, 'rows': []}
    proof['rows'] = [entry for entry in proof.get('rows', []) if entry.get('row') != row] + [result]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    line: str = ('| ' + platform + ' | ' + row + ' | ' + gui_forms + ' | ' + str(result['hits']) + ' / '
                 + str(result['compilations']) + ' | ' + str(result['expected']) + ' | ' + result['verdict']
                 + (' (' + result['reason'] + ')' if result['reason'] else '') + ' |')
    print('cache proof: ' + line, flush=True)
    summary: str = os.environ.get('GITHUB_STEP_SUMMARY', '')
    if summary:
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write(line + '\n')
    return result


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(dest='command',
                                                                                          required=True)
    packing: argparse.ArgumentParser = commands.add_parser('pack')
    packing.add_argument('--workspace', type=Path, required=True)
    packing.add_argument('--platform', choices=resolver.PLATFORMS, required=True)
    packing.add_argument('--build-dir', type=Path, required=True)
    packing.add_argument('--revision', required=True)
    packing.add_argument('--compiler', type=Path, required=True)
    restoring: argparse.ArgumentParser = commands.add_parser('restore')
    restoring.add_argument('--workspace', type=Path, required=True)
    restoring.add_argument('--platform', choices=resolver.PLATFORMS, required=True)
    restoring.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', DEVKIT_REPOSITORY))
    restoring.add_argument('--tag', default='')
    expecting: argparse.ArgumentParser = commands.add_parser('expect')
    expecting.add_argument('--workspace', type=Path, required=True)
    expecting.add_argument('--row', choices=sorted(RULES), required=True)
    proving: argparse.ArgumentParser = commands.add_parser('prove')
    proving.add_argument('--workspace', type=Path, required=True)
    proving.add_argument('--platform', choices=resolver.PLATFORMS, required=True)
    proving.add_argument('--row', choices=sorted(RULES), required=True)
    proving.add_argument('--stats', type=Path, required=True)
    proving.add_argument('--gui-forms', default='')
    arguments: argparse.Namespace = parser.parse_args(argv)
    workspace: Path = arguments.workspace.resolve()
    try:
        if arguments.command == 'pack':
            completed: subprocess.CompletedProcess[str] = subprocess.run(
                ['ninja', '-C', str(arguments.build_dir), '-t', 'deps'], capture_output=True, text=True, check=False)
            if completed.returncode != 0:
                print('devkit_cache: ninja -t deps failed: ' + completed.stderr.strip(), file=sys.stderr)
                return 1
            compiler: Path = arguments.compiler
            # MSYS2's command -v names clang++ without its .exe.
            if not compiler.is_file() and Path(str(compiler) + '.exe').is_file():
                compiler = Path(str(compiler) + '.exe')
            pack(workspace, arguments.platform, arguments.build_dir, arguments.revision, compiler,
                 completed.stdout, dict(os.environ))
        elif arguments.command == 'restore':
            restore(workspace, arguments.platform, arguments.repository, arguments.tag)
        elif arguments.command == 'expect':
            expect(workspace, arguments.row)
        else:
            result: dict[str, Any] = prove(workspace, arguments.platform, arguments.row,
                                           arguments.stats.read_text(encoding='utf-8'), arguments.gui_forms)
            return 1 if result['verdict'] == 'fail' else 0
    except resolver.ResolveError as error:
        print('devkit_cache: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
