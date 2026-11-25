#!/usr/bin/env python3
"""The build guard: a consumer never ends up rebuilding GUI.Forms.

A devkit consumer builds its own code against the prebuilt GUI.Forms SDK
(resolve_gui_forms.py fetch) and, when one is published, a restored compiler
cache. Before a build this checks that it will use both as expected, and
stops it with a diagnostic, written for an agent as much as for a person,
when it will not:

    devkit build guard: likely misconfiguration preventing efficient incremental building.

Each finding names what does not match and how to fix it. The build goes on
only with an explicit override: GUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=1 in the
environment, `--allow-full-build`, or the CMake option of the same name.

    python3 -B harness/harness/build_guard.py check --workspace W --platform P [--build-dir B]
            [--cxx-compiler PATH] [--launcher ccache] [--compile-env NAME=VALUE ...]
            [--gui-forms-dir DIR] [--imported yes|no] [--sources-file F]
            [--dry-run ninja|objects|none] [--threshold 0.9] [--allow-full-build]
    python3 -B harness/harness/build_guard.py environment --workspace W --platform P
    python3 -B harness/harness/build_guard.py record --workspace W --build-dir B

check (exit 0: go on; 3: stopped)
    sdk          the prebuilt SDK is at <workspace>/.sdk/gui-forms-sdk with its
                 devkit-sdk.json, and is the revision .ci/gui_forms-resolved.json
                 names;
    sdk-path     CMake found GUIForms inside that SDK (--gui-forms-dir), as
                 imported targets (--imported), not built from a source tree;
    sources      no source the build compiles lies in a GUI.Forms source tree
                 (a directory holding include/gui_forms/ beside src/core/):
                 the configured targets' sources (--sources-file) and, with
                 --dry-run ninja, every compile `ninja -n -v` would run;
    compiler     the C++ compiler is byte for byte the one that filled the
                 restored cache (cache-manifest.json compiler_sha256), else
                 the one that built the SDK (devkit-sdk.json), when ccache
                 checks compilers by content;
    launcher     the compiler launcher is ccache;
    ccache       CCACHE_BASEDIR is the workspace and CCACHE_DIR its .ccache,
                 CCACHE_COMPILERCHECK and CCACHE_SLOPPINESS are the recorded
                 ones (the compile's environment: the process's, with
                 --compile-env on top, which is what the CMake launcher sets);
    locale       LANG, LC_ALL, LC_CTYPE and LC_MESSAGES are the recorded ones,
                 unless the sloppiness holds "locale";
    runtime      (a warning, never a stop) on macOS and Linux, a C++ runtime is
                 restored under .build/toolchain/: without one, restore_local.py
                 runtime builds it (minutes, once per workspace);
    hit-rate     with a dependency record (<workspace>/.ci/devkit-deps.json,
                 published inside the cache archive by `record`), the share
                 of the objects to compile whose recorded inputs are byte
                 identical here, so must hit, is at least --threshold. The
                 objects to compile are what `ninja -n -v` would compile
                 (--dry-run ninja, from scripts) or the recorded objects
                 missing from the build directory (--dry-run objects, the
                 CMake pre-build step, which cannot run ninja inside ninja).
                 Objects the record does not know (the consumer's own code)
                 are not counted.

environment
    Prints NAME=VALUE lines: the ccache settings and locale the compile must
    have for the restored cache (or the SDK's producer) to hit. The CMake
    module puts them in the compiler launcher, so an IDE build has them
    whatever the IDE's environment.

record
    Writes <workspace>/.ci/devkit-deps.json from `ninja -t deps` of a
    finished build: each object's inputs (workspace-relative when inside the
    workspace) and the digest of their contents. The cache publication
    archives it beside cache-manifest.json.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any, BinaryIO

HARNESS: Path = Path(__file__).resolve().parent
OVERRIDE_VARIABLE: str = 'GUI_FORMS_DEVKIT_ALLOW_FULL_BUILD'
STOP_EXIT: int = 3
HEADLINE: str = 'devkit build guard: likely misconfiguration preventing efficient incremental building.'
SDK_DIRECTORY: str = '.sdk/gui-forms-sdk'
SDK_RECORD: str = 'devkit-sdk.json'
RESOLVED_RECORD: str = '.ci/gui_forms-resolved.json'
CACHE_MANIFEST: str = 'cache-manifest.json'
DEPS_RECORD: str = '.ci/devkit-deps.json'
# Where restore_local.py keeps the C++ runtime (build_environment.RUNTIME_DIRECTORY).
RUNTIME_DIRECTORY: str = '.build/toolchain'
RUNTIME_MANIFEST: str = 'runtime-manifest.json'
UNVERIFIED_SUFFIX: str = '.unverified'
LOCALE_VARIABLES: tuple[str, ...] = ('LANG', 'LC_ALL', 'LC_CTYPE', 'LC_MESSAGES')
CCACHE_VARIABLES: tuple[str, ...] = ('CCACHE_COMPILERCHECK', 'CCACHE_SLOPPINESS')
DEFAULT_THRESHOLD: float = 0.9
DRY_RUNS: tuple[str, ...] = ('ninja', 'objects', 'none')
# How many examples a finding lists.
EXAMPLES: int = 5
COMPILE_SOURCE: re.Pattern[str] = re.compile(r'(?:^|\s)-c\s+("[^"]+"|\S+)')
COMPILE_OUTPUT: re.Pattern[str] = re.compile(r'(?:^|\s)-o\s+("[^"]+"|\S+)')
MSVC_OUTPUT: re.Pattern[str] = re.compile(r'(?:^|\s)/Fo("[^"]+"|\S+)')


@dataclass(frozen=True)
class Finding:
    kind: str
    what: str
    fix: str
    # False for a warning: reported, and the build goes on.
    stops: bool = True


@dataclass(frozen=True)
class Compile:
    source: str
    output: str


@dataclass(frozen=True)
class Inputs:
    """What check reads; the CMake module and the scripts fill it."""
    workspace: Path
    platform: str
    build_dir: Path | None
    cxx_compiler: str
    launcher: str
    compile_environment: dict[str, str]
    gui_forms_dir: str
    imported: str
    sources: tuple[str, ...]
    dry_run: str
    threshold: float


def file_digest(path: Path) -> str:
    stream: BinaryIO
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value: Any = json.loads(path.read_text(encoding='utf-8'))
    record: dict[str, Any] = value if isinstance(value, dict) else {}
    return record


def same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def inside(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def expected_record(workspace: Path) -> tuple[dict[str, Any], str]:
    """The record the compile must match and where it came from: the restored cache's manifest, else the SDK's
    producer record, else empty."""
    manifest: dict[str, Any] = read_json(workspace / CACHE_MANIFEST)
    if manifest:
        return manifest, 'the restored cache (' + CACHE_MANIFEST + ')'
    producer: Any = read_json(workspace / SDK_DIRECTORY / SDK_RECORD).get('producer')
    if isinstance(producer, dict) and producer:
        return producer, 'the SDK\'s producer (' + SDK_DIRECTORY + '/' + SDK_RECORD + ')'
    return {}, ''


def expected_environment(workspace: Path) -> dict[str, str]:
    """The ccache settings and locale the compile must have ("" for one to leave unset), with CCACHE_BASEDIR and
    CCACHE_DIR for this workspace."""
    record: dict[str, Any]
    record, _ = expected_record(workspace)
    recorded: Any = record.get('environment')
    values: dict[str, str] = {'CCACHE_BASEDIR': workspace.resolve().as_posix(),
                              'CCACHE_DIR': (workspace.resolve() / '.ccache').as_posix()}
    if not isinstance(recorded, dict):
        values['CCACHE_COMPILERCHECK'] = 'content'
        return values
    name: str
    for name in CCACHE_VARIABLES + LOCALE_VARIABLES:
        value: Any = recorded.get(name)
        values[name] = '' if value is None else str(value)
    return values


def is_gui_forms_source(path: Path) -> bool:
    """Whether path lies in a GUI.Forms source tree: an ancestor holds include/gui_forms/ and src/core/ (an
    installed SDK has the first, never the second)."""
    ancestor: Path
    for ancestor in path.parents:
        if (ancestor / 'include' / 'gui_forms').is_dir() and (ancestor / 'src' / 'core').is_dir():
            return True
    return False


def check_sdk(workspace: Path) -> list[Finding]:
    findings: list[Finding] = []
    sdk: Path = workspace / SDK_DIRECTORY
    record: dict[str, Any] = read_json(sdk / SDK_RECORD)
    fetch: str = ('python3 -B harness/harness/resolve_gui_forms.py resolve && '
                  'python3 -B harness/harness/resolve_gui_forms.py fetch --platform <platform>')
    if not record:
        findings.append(Finding('sdk', 'no prebuilt GUI.Forms SDK at ' + sdk.as_posix() + ' (no ' + SDK_RECORD + ')',
                                'unpack the resolved SDK there: ' + fetch))
        return findings
    resolved: dict[str, Any] = read_json(workspace / RESOLVED_RECORD)
    if resolved and resolved.get('revision') != record.get('revision'):
        findings.append(Finding('sdk', 'the SDK at ' + sdk.as_posix() + ' is GUI.Forms '
                                + str(record.get('revision', ''))[:12] + ', but ' + RESOLVED_RECORD + ' names '
                                + str(resolved.get('revision', ''))[:12],
                                'fetch the resolved SDK again: python3 -B harness/harness/resolve_gui_forms.py '
                                'fetch --platform ' + str(record.get('platform', '<platform>'))))
    return findings


def check_sdk_path(inputs: Inputs) -> list[Finding]:
    findings: list[Finding] = []
    sdk: Path = inputs.workspace / SDK_DIRECTORY
    if inputs.gui_forms_dir and not inside(Path(inputs.gui_forms_dir), sdk):
        findings.append(Finding('sdk-path', 'CMake found GUIForms at ' + inputs.gui_forms_dir + ', not in the devkit\'s '
                                'SDK ' + sdk.as_posix(),
                                'remove the GUIForms_DIR or CMAKE_PREFIX_PATH entry that points elsewhere (or clear '
                                'the CMake cache) so the SDK at ' + sdk.as_posix() + ' is found'))
    if inputs.imported == 'no':
        findings.append(Finding('sdk-path', 'the GUIForms targets are built from source in this build '
                                '(add_subdirectory or FetchContent of GUI.Forms), so every GUI.Forms source compiles',
                                'link the prebuilt SDK instead: find_package(GUIForms CONFIG) with the SDK at '
                                + sdk.as_posix() + ' on CMAKE_PREFIX_PATH'))
    return findings


def check_sources(sources: list[str], origin: str) -> list[Finding]:
    found: list[str] = [source for source in sources if is_gui_forms_source(Path(source))]
    if not found:
        return []
    finding: Finding = Finding('sources', origin + ' compiles ' + str(len(found)) + ' GUI.Forms source(s), e.g. '
                               + ', '.join(found[:EXAMPLES]),
                               'build against the prebuilt SDK, not a GUI.Forms checkout: drop the source tree '
                               'from the build (add_subdirectory, FetchContent, or source files listed by path)')
    return [finding]


def check_compiler(inputs: Inputs, record: dict[str, Any], origin: str) -> list[Finding]:
    expected: str = str(record.get('compiler_sha256', ''))
    check: str = inputs.compile_environment.get('CCACHE_COMPILERCHECK', 'content') or 'content'
    if not expected or not inputs.cxx_compiler or check != 'content':
        return []
    compiler: Path = Path(inputs.cxx_compiler)
    if not compiler.is_file():
        return [Finding('compiler', 'the C++ compiler ' + inputs.cxx_compiler + ' does not exist',
                        'configure with the toolchain bootstrap restored (CMAKE_CXX_COMPILER)')]
    found: str = file_digest(compiler.resolve())
    if found == expected:
        return []
    finding: Finding = Finding('compiler', 'the C++ compiler ' + inputs.cxx_compiler + ' (sha256 ' + found[:12]
                               + ') is not the clang ' + str(record.get('compiler_version', '')) + ' of ' + origin
                               + ' (sha256 ' + expected[:12] + '): ccache compares compilers by content, so every '
                               'object misses',
                               'use the restored toolchain: run bootstrap.sh (or restore_local.py toolchain), then '
                               'configure a fresh build directory with its clang as CMAKE_CXX_COMPILER')
    return [finding]


def check_environment(inputs: Inputs, expected: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    actual: dict[str, str] = inputs.compile_environment
    if Path(inputs.launcher).name.split('.')[0] != 'ccache':
        findings.append(Finding('launcher', 'the compiler launcher is ' + (inputs.launcher or 'not set')
                                + ', so the restored cache is never consulted',
                                'set CMAKE_CXX_COMPILER_LAUNCHER (and C, OBJCXX) to ccache; the devkit\'s CMake does '
                                'it when ccache is on PATH'))
    basedir: str = actual.get('CCACHE_BASEDIR', '')
    if not basedir or not same_path(Path(basedir), inputs.workspace):
        findings.append(Finding('ccache', 'CCACHE_BASEDIR is ' + (basedir or 'unset') + ', not the workspace '
                                + inputs.workspace.as_posix() + ': absolute paths enter every key and nothing hits',
                                'set CCACHE_BASEDIR=' + inputs.workspace.as_posix()
                                + ' (. .ci/local-build-env.sh, or the devkit CMake launcher)'))
    directory: str = actual.get('CCACHE_DIR', '')
    if not directory or not same_path(Path(directory), inputs.workspace / '.ccache'):
        findings.append(Finding('ccache', 'CCACHE_DIR is ' + (directory or 'unset') + ', not the restored cache '
                                + (inputs.workspace / '.ccache').as_posix(),
                                'set CCACHE_DIR=' + (inputs.workspace / '.ccache').as_posix()))
    name: str
    for name in CCACHE_VARIABLES:
        if name in expected and actual.get(name, '') != expected[name]:
            findings.append(Finding('ccache', name + ' is ' + (actual.get(name) or 'unset') + ', the cache was filled '
                                    'with ' + (expected[name] or 'it unset'),
                                    'set ' + name + '=' + expected[name] if expected[name] else 'unset ' + name))
    if 'locale' in expected.get('CCACHE_SLOPPINESS', '').split(','):
        return findings
    for name in LOCALE_VARIABLES:
        if name in expected and actual.get(name, '') != expected[name]:
            findings.append(Finding('locale', name + ' is ' + (actual.get(name) or 'unset') + ', the cache was filled '
                                    'with ' + (expected[name] or 'it unset') + ': ccache hashes the locale into every key',
                                    ('set ' + name + '=' + expected[name]) if expected[name] else 'unset ' + name))
    return findings


def check_runtime(workspace: Path, platform: str) -> list[Finding]:
    """A warning when macOS or Linux has no restored C++ runtime: building one is slow, not wrong."""
    if platform == 'windows-x64':
        return []
    directory: Path = workspace / RUNTIME_DIRECTORY
    found: list[Path] = [] if not directory.is_dir() else [
        manifest.parent for manifest in directory.glob('*/' + RUNTIME_MANIFEST)
        if not manifest.parent.name.endswith(UNVERIFIED_SUFFIX)]
    if found:
        return []
    finding: Finding = Finding('runtime', 'no restored C++ runtime under ' + directory.as_posix() + ': it will be '
                               'built from source, which takes minutes once per workspace',
                               'python3 -B harness/harness/resolve_gui_forms.py fetch --platform ' + platform
                               + ' restores the build\'s gui-forms-runtime asset when it publishes one; '
                               'restore_local.py runtime verifies it', stops=False)
    return [finding]


def unquote(text: str) -> str:
    return text[1:-1] if len(text) >= 2 and text[0] == text[-1] == '"' else text


def ninja_compiles(build_dir: Path) -> list[Compile]:
    """The compiles `ninja -n -v` would run in build_dir."""
    completed: subprocess.CompletedProcess[str] = subprocess.run(['ninja', '-C', str(build_dir), '-n', '-v'],
                                                                 capture_output=True, text=True, check=False)
    return parse_compiles(completed.stdout, build_dir)


def parse_compiles(text: str, build_dir: Path) -> list[Compile]:
    compiles: list[Compile] = []
    line: str
    for line in text.splitlines():
        source: re.Match[str] | None = COMPILE_SOURCE.search(line)
        output: re.Match[str] | None = COMPILE_OUTPUT.search(line) or MSVC_OUTPUT.search(line)
        if source is None or output is None:
            continue
        source_path: Path = Path(unquote(source.group(1)))
        if not source_path.is_absolute():
            source_path = build_dir / source_path
        compiles.append(Compile(source_path.as_posix(), unquote(output.group(1))))
    return compiles


def input_digest(workspace: Path, inputs: list[str]) -> str:
    """The digest of the inputs' contents, in order; a missing input counts as missing."""
    digest = hashlib.sha256()
    name: str
    for name in inputs:
        path: Path = Path(name) if Path(name).is_absolute() else workspace / name
        digest.update(name.encode('utf-8') + b'\0')
        digest.update((file_digest(path) if path.is_file() else 'missing').encode('ascii') + b'\n')
    return digest.hexdigest()


def projected_hits(workspace: Path, record: dict[str, Any], objects: list[str]) -> tuple[int, int, list[str]]:
    """(objects that must hit, objects the record knows, examples that will miss) among objects."""
    known: dict[str, Any] = record.get('objects', {})
    hits: int = 0
    counted: int = 0
    misses: list[str] = []
    name: str
    for name in objects:
        entry: Any = known.get(name)
        if not isinstance(entry, dict):
            continue
        counted += 1
        if input_digest(workspace, list(entry.get('inputs', []))) == entry.get('digest'):
            hits += 1
        elif len(misses) < EXAMPLES:
            misses.append(name)
    return hits, counted, misses


def objects_to_compile(inputs: Inputs, record: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(objects, their sources) the build would compile, by the dry run chosen."""
    if inputs.build_dir is None or inputs.dry_run == 'none':
        return [], []
    if inputs.dry_run == 'ninja':
        if not (inputs.build_dir / 'build.ninja').is_file():
            return [], []
        compiles: list[Compile] = ninja_compiles(inputs.build_dir)
        return [compile.output for compile in compiles], [compile.source for compile in compiles]
    missing: list[str] = [name for name in record.get('objects', {}) if not (inputs.build_dir / name).exists()]
    return missing, []


def check_hit_rate(inputs: Inputs, objects: list[str], record: dict[str, Any]) -> list[Finding]:
    if not record or not objects:
        return []
    hits: int
    counted: int
    misses: list[str]
    hits, counted, misses = projected_hits(inputs.workspace, record, objects)
    if counted == 0:
        return []
    rate: float = hits / counted
    if rate >= inputs.threshold:
        return []
    finding: Finding = Finding('hit-rate', 'only ' + str(hits) + ' of ' + str(counted) + ' cached objects to compile '
                               '(' + format(rate * 100.0, '.0f') + '%, below ' + format(inputs.threshold * 100.0, '.0f')
                               + '%) have the inputs the cache recorded; e.g. ' + ', '.join(misses),
                               'their headers differ from the cache\'s build: fetch the SDK revision the cache was '
                               'built on (' + DEPS_RECORD + ' and ' + CACHE_MANIFEST + ' name it), or restore the '
                               'cache of this SDK revision; a moved workspace or SDK path also shows here')
    return [finding]


def check(inputs: Inputs) -> list[Finding]:
    """Every finding for this build; empty when it will use the SDK and the cache as expected."""
    findings: list[Finding] = check_sdk(inputs.workspace)
    findings += check_sdk_path(inputs)
    findings += check_sources(list(inputs.sources), 'a configured target')
    record: dict[str, Any]
    origin: str
    record, origin = expected_record(inputs.workspace)
    findings += check_compiler(inputs, record, origin)
    findings += check_environment(inputs, expected_environment(inputs.workspace))
    deps: dict[str, Any] = read_json(inputs.workspace / DEPS_RECORD)
    objects: list[str]
    sources: list[str]
    objects, sources = objects_to_compile(inputs, deps)
    findings += check_sources(sources, 'the dry run')
    findings += check_hit_rate(inputs, objects, deps)
    findings += check_runtime(inputs.workspace, inputs.platform)
    return findings


def warning_text(findings: list[Finding]) -> str:
    lines: list[str] = []
    finding: Finding
    for finding in findings:
        lines.append('devkit build guard: warning: [' + finding.kind + '] ' + finding.what)
        lines.append('      fix: ' + finding.fix)
    return '\n'.join(lines)


def diagnostic(findings: list[Finding], overridden: bool) -> str:
    lines: list[str] = [HEADLINE,
                        'This build would not use the prebuilt GUI.Forms SDK and the restored compiler cache as '
                        'expected, so it would compile far more than it should:']
    finding: Finding
    for finding in findings:
        lines.append('  [' + finding.kind + '] ' + finding.what)
        lines.append('      fix: ' + finding.fix)
    if overridden:
        lines.append('Going on because ' + OVERRIDE_VARIABLE + ' is set: expect a full, slow build.')
    else:
        lines.append('The build stopped. Fix the above, or to build anyway (a full, slow build) set '
                     + OVERRIDE_VARIABLE + '=1, pass --allow-full-build, or configure with -D'
                     + OVERRIDE_VARIABLE + '=ON.')
    return '\n'.join(lines)


def overridden(flag: bool, environment: dict[str, str]) -> bool:
    value: str = environment.get(OVERRIDE_VARIABLE, '').strip().lower()
    return flag or value in ('1', 'on', 'yes', 'true')


def parse_assignment(text: str) -> tuple[str, str]:
    name: str
    value: str
    name, separator, value = text.partition('=')
    if not separator or not name:
        raise argparse.ArgumentTypeError('expected NAME=VALUE, got ' + text)
    return name, value


def deps_record(workspace: Path, build_dir: Path, text: str) -> dict[str, Any]:
    """The dependency record from `ninja -t deps` output."""
    objects: dict[str, Any] = {}
    current: str = ''
    inputs: list[str] = []
    resolved_workspace: Path = workspace.resolve()

    def flush() -> None:
        if current:
            objects[current] = {'inputs': inputs[:], 'digest': input_digest(workspace, inputs)}

    line: str
    for line in text.splitlines():
        if line and not line[0].isspace():
            flush()
            current = line.split(': #deps', 1)[0].strip()
            inputs = []
        elif line.strip():
            path: Path = Path(line.strip())
            absolute: Path = path if path.is_absolute() else (build_dir / path)
            absolute = absolute.resolve()
            inputs.append(absolute.relative_to(resolved_workspace).as_posix() if inside(absolute, resolved_workspace)
                          else absolute.as_posix())
    flush()
    record: dict[str, Any] = {'schema': 1, 'build_dir': build_dir.resolve().relative_to(resolved_workspace).as_posix()
                              if inside(build_dir, resolved_workspace) else build_dir.resolve().as_posix(),
                              'objects': objects}
    return record


def read_sources(path: str) -> tuple[str, ...]:
    if not path:
        return ()
    listing: Path = Path(path)
    if not listing.is_file():
        return ()
    sources: tuple[str, ...] = tuple(line.strip() for line in listing.read_text(encoding='utf-8').splitlines()
                                     if line.strip())
    return sources


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(dest='command',
                                                                                          required=True)
    checking: argparse.ArgumentParser = commands.add_parser('check')
    checking.add_argument('--workspace', type=Path, required=True)
    checking.add_argument('--platform', required=True)
    checking.add_argument('--build-dir', type=Path, default=None)
    checking.add_argument('--cxx-compiler', default='')
    checking.add_argument('--launcher', default=None)
    checking.add_argument('--compile-env', type=parse_assignment, action='append', default=[])
    checking.add_argument('--gui-forms-dir', default='')
    checking.add_argument('--imported', choices=('yes', 'no', ''), default='')
    checking.add_argument('--sources-file', default='')
    checking.add_argument('--dry-run', choices=DRY_RUNS, default='ninja')
    checking.add_argument('--threshold', type=float, default=DEFAULT_THRESHOLD)
    checking.add_argument('--allow-full-build', action='store_true')
    environment: argparse.ArgumentParser = commands.add_parser('environment')
    environment.add_argument('--workspace', type=Path, required=True)
    environment.add_argument('--platform', required=True)
    recording: argparse.ArgumentParser = commands.add_parser('record')
    recording.add_argument('--workspace', type=Path, required=True)
    recording.add_argument('--build-dir', type=Path, required=True)
    arguments: argparse.Namespace = parser.parse_args(argv)
    workspace: Path = arguments.workspace.resolve()
    if arguments.command == 'environment':
        name: str
        value: str
        for name, value in sorted(expected_environment(workspace).items()):
            print(name + '=' + value)
        return 0
    if arguments.command == 'record':
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            ['ninja', '-C', str(arguments.build_dir), '-t', 'deps'], capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            print('build_guard: ninja -t deps failed: ' + completed.stderr.strip(), file=sys.stderr)
            return 1
        path: Path = workspace / DEPS_RECORD
        path.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = deps_record(workspace, arguments.build_dir, completed.stdout)
        path.write_text(json.dumps(record, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        print('Recorded the inputs of ' + str(len(record['objects'])) + ' objects in ' + str(path))
        return 0
    compile_environment: dict[str, str] = dict(os.environ)
    compile_environment.update(dict(arguments.compile_env))
    launcher: str = (arguments.launcher if arguments.launcher is not None
                     else os.environ.get('CMAKE_CXX_COMPILER_LAUNCHER', ''))
    inputs: Inputs = Inputs(workspace, arguments.platform, arguments.build_dir, arguments.cxx_compiler,
                            shlex.split(launcher)[-1] if launcher else '', compile_environment,
                            arguments.gui_forms_dir, arguments.imported, read_sources(arguments.sources_file),
                            arguments.dry_run, arguments.threshold)
    found: list[Finding] = check(inputs)
    warnings: list[Finding] = [finding for finding in found if not finding.stops]
    findings: list[Finding] = [finding for finding in found if finding.stops]
    if warnings:
        print(warning_text(warnings), file=sys.stderr)
    if not findings:
        print('devkit build guard: the build uses the prebuilt SDK and the restored cache as expected')
        return 0
    allowed: bool = overridden(arguments.allow_full_build, dict(os.environ))
    print(diagnostic(findings, allowed), file=sys.stderr)
    return 0 if allowed else STOP_EXIT


if __name__ == '__main__':
    sys.exit(main())
