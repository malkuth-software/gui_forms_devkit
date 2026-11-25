#!/usr/bin/env python3
"""Restore or build GUI.Forms' Windows own runtime on a developer machine and name its toolchain file.

The local counterpart of CI's .github/actions/windows-own-runtime, step for
step, for a workspace where resolve_gui_forms.py resolve and fetch have run:

    python3 -B harness/harness/own_runtime_local.py [--workspace DIR] [--jobs N]
            [--github-base URL] [--dry-run]

(sh harness/bootstrap.sh own-runtime runs it with a suitable Python.)

1. Reads the resolved GUI.Forms revision from <workspace>/.ci/gui_forms-resolved.json.
2. Checks out that revision of GUI.Forms sparsely (tools/, cmake/, stx.lock)
   at <workspace>/.ci/gui_forms-tools, as CI's action does: a clone with no
   blobs until checkout, or a fetch into an existing one. A checkout with
   uncommitted changes to tracked files is refused.
3. Runs its tools/own_runtime.py build --out <workspace>/.ci/own-runtime.
   fetch has already extracted the build's gui-forms-runtime-windows-x64
   asset there when the build publishes one, and own_runtime.py reuses it
   when its stamp matches; otherwise it builds the runtime (the fallback,
   tens of minutes).
4. Prints the settings own_runtime.py printed (NAME=VALUE, the three its
   toolchain reads) and CMAKE_TOOLCHAIN_FILE=<that revision's
   cmake/llvm22-windows-msvc.cmake>, and records them in
   <workspace>/.ci/windows-own-runtime.json.

The NAME=VALUE lines are what bootstrap.py and prepare_build.py collect from
a prepare command, so naming this in a project's [bootstrap.windows-x64]
prepare puts the settings and the toolchain file (CMake reads
CMAKE_TOOLCHAIN_FILE from the environment) in .ci/local-build-env.*.
devkit_build.py runs it on Windows before configuring.

The runtime is Windows': on another host own_runtime.py would cross-build,
so this refuses unless --allow-cross is given. --github-base replaces
https://github.com (tests).
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any, Callable

HARNESS: Path = Path(__file__).resolve().parent
DEVKIT_ROOT: Path = HARNESS.parent.parent
GITHUB: str = 'https://github.com'
RESOLVED_RECORD: str = '.ci/gui_forms-resolved.json'
TOOLS_DIRECTORY: str = '.ci/gui_forms-tools'
RUNTIME_DIRECTORY: str = '.ci/own-runtime'
RECORD: str = '.ci/windows-own-runtime.json'
# What CI's action checks out (sparse, not cone mode).
SPARSE_PATHS: tuple[str, ...] = ('tools', 'cmake', 'stx.lock')
TOOLCHAIN_FILE: str = 'cmake/llvm22-windows-msvc.cmake'
OWN_RUNTIME_TOOL: str = 'tools/own_runtime.py'
SETTING_LINE: re.Pattern[str] = re.compile(r'([A-Z][A-Z0-9_]*)=(.*)')
REVISION_PATTERN: re.Pattern[str] = re.compile(r'[0-9a-f]{40}')


class OwnRuntimeError(Exception):
    """An expected refusal or failure; the command prints it and exits 1."""


def say(text: str) -> None:
    print(text, flush=True)


def resolved(workspace: Path) -> tuple[str, str]:
    """The resolved build's repository and revision."""
    path: Path = workspace / RESOLVED_RECORD
    if not path.is_file():
        raise OwnRuntimeError('No ' + RESOLVED_RECORD + ' in ' + str(workspace)
                              + '; run resolve_gui_forms.py resolve and fetch first')
    record: Any = json.loads(path.read_text(encoding='utf-8'))
    repository: str = str(record.get('repository', '')) if isinstance(record, dict) else ''
    revision: str = str(record.get('revision', '')) if isinstance(record, dict) else ''
    if repository.count('/') != 1 or REVISION_PATTERN.fullmatch(revision) is None:
        raise OwnRuntimeError(str(path) + ' names no repository (owner/name) and full revision')
    return repository, revision


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        ['git', *arguments], capture_output=True, text=True, check=False)
    if check and completed.returncode != 0:
        raise OwnRuntimeError(shlex.join(['git', *arguments]) + ' failed: ' + completed.stderr.strip())
    return completed


def checkout_commands(directory: Path, url: str, revision: str, cloned: bool) -> list[list[str]]:
    """The git commands that make directory the sparse checkout of revision (cloned: it is a clone already)."""
    place: str = str(directory)
    commands: list[list[str]] = []
    if not cloned:
        commands.append(['clone', '--quiet', '--no-checkout', '--filter=blob:none', url, place])
    commands.append(['-C', place, 'sparse-checkout', 'set', '--no-cone', *SPARSE_PATHS])
    commands.append(['-C', place, 'fetch', '--quiet', '--filter=blob:none', url, revision])
    commands.append(['-C', place, 'checkout', '--quiet', '--detach', revision])
    return commands


def sparse_checkout(workspace: Path, repository: str, revision: str, github: str, dry_run: bool) -> Path:
    """<workspace>/.ci/gui_forms-tools at revision, with only the paths CI's action checks out."""
    directory: Path = workspace / TOOLS_DIRECTORY
    url: str = github.rstrip('/') + '/' + repository + '.git'
    cloned: bool = (directory / '.git').exists()
    if cloned and not dry_run:
        changes: str = git('-C', str(directory), 'status', '--porcelain', '--untracked-files=no').stdout.strip()
        if changes:
            raise OwnRuntimeError(str(directory) + ' has uncommitted changes to tracked files; '
                                  'move them aside:\n' + changes)
        head: str = git('-C', str(directory), 'rev-parse', 'HEAD', check=False).stdout.strip()
        if head == revision:
            say(str(directory) + ' is ' + repository + ' at ' + revision[:12])
            return directory
    elif directory.exists() and any(directory.iterdir()) and not dry_run:
        raise OwnRuntimeError(str(directory) + ' is not empty and is not a git clone; move it aside')
    arguments: list[str]
    for arguments in checkout_commands(directory, url, revision, cloned):
        say(('would run: ' if dry_run else '+ ') + shlex.join(['git', *arguments]))
        if not dry_run:
            git(*arguments)
    return directory


def settings_of(printed: str) -> list[tuple[str, str]]:
    """The NAME=VALUE lines own_runtime.py printed, in order."""
    found: list[tuple[str, str]] = []
    line: str
    for line in printed.splitlines():
        match: re.Match[str] | None = SETTING_LINE.fullmatch(line.strip())
        if match is not None:
            found.append((match.group(1), match.group(2)))
    return found


def run_tool(command: list[str]) -> str:
    """Runs own_runtime.py, passing its output through; returns its standard output."""
    completed: subprocess.CompletedProcess[str] = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.stderr.strip():
        print(completed.stderr.rstrip(), file=sys.stderr, flush=True)
    if completed.returncode != 0:
        raise OwnRuntimeError(shlex.join(command) + ' failed (' + str(completed.returncode) + ')')
    return completed.stdout


def own_runtime(workspace: Path, jobs: int, github: str, dry_run: bool,
                runner: Callable[[list[str]], str] = run_tool) -> list[tuple[str, str]]:
    """Steps 1 to 4 of the module docstring; returns the settings, CMAKE_TOOLCHAIN_FILE last."""
    repository: str
    revision: str
    repository, revision = resolved(workspace)
    tools: Path = sparse_checkout(workspace, repository, revision, github, dry_run)
    toolchain: str = (tools / TOOLCHAIN_FILE).as_posix()
    command: list[str] = [sys.executable, '-B', str(tools / OWN_RUNTIME_TOOL), 'build',
                          '--out', str(workspace / RUNTIME_DIRECTORY), '--jobs', str(jobs)]
    if dry_run:
        say('would run: ' + shlex.join(command))
        return [('CMAKE_TOOLCHAIN_FILE', toolchain)]
    say('+ ' + shlex.join(command))
    settings: list[tuple[str, str]] = [setting for setting in settings_of(runner(command))
                                       if setting[0] != 'CMAKE_TOOLCHAIN_FILE']
    if not settings:
        raise OwnRuntimeError(OWN_RUNTIME_TOOL + ' printed no settings; its toolchain cannot find the runtime')
    if not (tools / TOOLCHAIN_FILE).is_file():
        raise OwnRuntimeError('GUI.Forms ' + revision[:12] + ' has no ' + TOOLCHAIN_FILE)
    settings.append(('CMAKE_TOOLCHAIN_FILE', toolchain))
    record: Path = workspace / RECORD
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({'schema': 1, 'repository': repository, 'revision': revision,
                                  'toolchain': toolchain, 'environment': dict(settings)}, indent=2, sort_keys=True)
                      + '\n', encoding='utf-8')
    return settings


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--workspace', type=Path, default=DEVKIT_ROOT)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--github-base', default=GITHUB, help='the base URL of the repositories (tests)')
    parser.add_argument('--dry-run', action='store_true', help='print the steps; change nothing')
    parser.add_argument('--allow-cross', action='store_true', help='run on a host other than Windows (a cross build)')
    args: argparse.Namespace = parser.parse_args(argv)
    if sys.platform != 'win32' and not args.allow_cross and not args.dry_run:
        print('own_runtime_local: the own runtime is Windows\'; on this host own_runtime.py would cross-build '
              '(--allow-cross)', file=sys.stderr)
        return 1
    try:
        settings: list[tuple[str, str]] = own_runtime(args.workspace.resolve(), args.jobs, args.github_base,
                                                      args.dry_run)
    except OwnRuntimeError as error:
        print('own_runtime_local: ' + str(error), file=sys.stderr)
        return 1
    name: str
    value: str
    for name, value in settings:
        say(name + '=' + value)
    return 0


if __name__ == '__main__':
    sys.exit(main())
