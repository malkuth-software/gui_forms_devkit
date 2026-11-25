#!/usr/bin/env python3
"""Build and test {{title}} against the prebuilt GUI.Forms SDK; nothing of GUI.Forms is compiled here.

    python3 build.py [--devkit DIR] [--configure-only] [--no-tests] [--jobs N]
                     [--resolve | --floor | --revision SHA] [--allow-full-build] [--dry-run]
    python3 build.py check [--devkit DIR] [--profile consumer|strict]

The devkit's harness does the work: build runs its
harness/harness/devkit_build.py for this directory, which resolves
devkit.toml's GUI.Forms pin (major and floor) to one green build, unpacks
its SDK at .sdk/gui-forms-sdk, restores the C++ runtime (the own runtime
on Windows), writes .ci/local-build-env.*, and configures, builds and
tests with CMake and Ninja. CMakeLists.txt includes the devkit's
DevkitBuildGuard.cmake, which stops a configure that would compile
GUI.Forms from source or miss the SDK. Every option after the command
goes to devkit_build.py.

check runs the devkit's static checks (run_checks.py: house style,
lifetime rules, retained mode) over src, tests and reference at the
profile devkit.toml's [checks] names: "consumer" unless the app opts into
"strict".

The devkit is found at --devkit DIR, else $GUI_FORMS_DEVKIT_DIR, else the
harness this directory sits in (the devkit's example app), else
../template_harness (the in-house sibling layout), else .devkit/: the
devkit at the commit harness.lock pins, which new-app clones there and this
script checks out at the pin when it is missing or elsewhere.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tomllib

HERE: Path = Path(__file__).resolve().parent
DEVKIT_CLONE: Path = HERE / '.devkit'
LOCK: Path = HERE / 'harness.lock'
GITHUB: str = 'https://github.com'
CHECKED_PATHS: tuple[str, ...] = ('src', 'tests', 'reference')


class DevkitError(Exception):
    """An expected failure; the script prints it and exits 1."""


def harness_root(directory: Path) -> Path | None:
    """The harness root (the directory holding harness/devkit_build.py) of a devkit checkout or a harness checkout."""
    candidate: Path
    for candidate in (directory / 'harness', directory):
        if (candidate / 'harness' / 'devkit_build.py').is_file():
            return candidate
    return None


def git(*arguments: str) -> subprocess.CompletedProcess[str]:
    completed: subprocess.CompletedProcess[str] = subprocess.run(['git', *arguments], capture_output=True, text=True,
                                                                 check=False)
    return completed


def pinned() -> tuple[str, str]:
    """harness.lock's repository and commit."""
    if not LOCK.is_file():
        raise DevkitError('No harness.lock in ' + str(HERE) + ' to check the devkit out from')
    table: object = tomllib.loads(LOCK.read_text(encoding='utf-8')).get('harness')
    if not isinstance(table, dict) or not table.get('repository') or not table.get('commit'):
        raise DevkitError(str(LOCK) + ' needs [harness] repository and commit')
    return str(table['repository']), str(table['commit'])


def check_out_devkit() -> None:
    """.devkit/ at the pinned commit: cloned when missing, moved when clean and elsewhere."""
    repository: str
    commit: str
    repository, commit = pinned()
    url: str = os.environ.get('GUI_FORMS_DEVKIT_GITHUB', GITHUB).rstrip('/') + '/' + repository + '.git'
    if not (DEVKIT_CLONE / '.git').exists():
        print('Cloning ' + url + ' into ' + str(DEVKIT_CLONE), flush=True)
        if git('clone', '--quiet', '--no-checkout', url, str(DEVKIT_CLONE)).returncode != 0:
            raise DevkitError('cloning ' + url + ' failed; give --devkit DIR or set GUI_FORMS_DEVKIT_DIR')
    place: str = str(DEVKIT_CLONE)
    if git('-C', place, 'rev-parse', 'HEAD').stdout.strip() == commit:
        return
    if git('-C', place, 'status', '--porcelain', '--untracked-files=no').stdout.strip():
        raise DevkitError(place + ' has uncommitted changes and is not at the pinned ' + commit[:12])
    if git('-C', place, 'cat-file', '-t', commit).stdout.strip() != 'commit':
        git('-C', place, 'fetch', '--quiet', url, commit)
    if git('-C', place, 'checkout', '--quiet', '--detach', commit).returncode != 0:
        raise DevkitError(repository + ' has no commit ' + commit + ' (harness.lock)')


def find_devkit(named: str) -> Path:
    """The harness root of the devkit this build uses (the module docstring's order)."""
    chosen: str = named or os.environ.get('GUI_FORMS_DEVKIT_DIR', '')
    root: Path | None
    if chosen:
        root = harness_root(Path(chosen).resolve())
        if root is None:
            raise DevkitError(chosen + ' holds no devkit harness (harness/harness/devkit_build.py)')
        return root
    candidate: Path
    for candidate in (HERE.parent, HERE.parent / 'template_harness'):
        root = harness_root(candidate)
        if root is not None:
            return root
    if LOCK.is_file():
        check_out_devkit()
        root = harness_root(DEVKIT_CLONE)
        if root is not None:
            return root
    raise DevkitError('No devkit harness found: give --devkit DIR (a gui_forms_devkit checkout)')


def split_devkit(arguments: list[str]) -> tuple[str, list[str]]:
    """The --devkit value and the other arguments."""
    rest: list[str] = []
    named: str = ''
    index: int = 0
    while index < len(arguments):
        argument: str = arguments[index]
        if argument == '--devkit' and index + 1 < len(arguments):
            named = arguments[index + 1]
            index += 2
            continue
        if argument.startswith('--devkit='):
            named = argument.partition('=')[2]
        else:
            rest.append(argument)
        index += 1
    return named, rest


def checks_profile(arguments: list[str]) -> str:
    if '--profile' in arguments:
        return arguments[arguments.index('--profile') + 1]
    devkit_file: Path = HERE / 'devkit.toml'
    table: object = tomllib.loads(devkit_file.read_text(encoding='utf-8')).get('checks', {})
    profile: str = str(table.get('profile', 'consumer')) if isinstance(table, dict) else 'consumer'
    return profile


def command_for(root: Path, arguments: list[str]) -> list[str]:
    """The devkit command these arguments ask for."""
    if arguments[:1] == ['check']:
        paths: list[str] = [str(HERE / name) for name in CHECKED_PATHS if (HERE / name).is_dir()]
        return [sys.executable, '-B', str(root / 'harness' / 'run_checks.py'), '--profile',
                checks_profile(arguments[1:]), *paths]
    command: list[str] = [sys.executable, '-B', str(root / 'harness' / 'devkit_build.py'), '--app', str(HERE),
                          *arguments]
    return command


def main(argv: list[str] | None = None) -> int:
    named: str
    rest: list[str]
    named, rest = split_devkit(list(sys.argv[1:] if argv is None else argv))
    try:
        root: Path = find_devkit(named)
    except DevkitError as error:
        print('build: ' + str(error), file=sys.stderr)
        return 1
    completed: subprocess.CompletedProcess[bytes] = subprocess.run(command_for(root, rest), check=False)
    return completed.returncode


if __name__ == '__main__':
    sys.exit(main())
