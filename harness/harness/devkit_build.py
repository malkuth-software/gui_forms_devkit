#!/usr/bin/env python3
"""Build and test a devkit consumer against the prebuilt GUI.Forms SDK, compiling none of GUI.Forms.

One command for an app made by new-app (its build.py runs this), the
example app, and the devkit itself:

    python3 -B <devkit>/harness/harness/devkit_build.py [--app DIR] [--project FILE] [--platform P]
            [--resolve] [--floor | --revision SHA] [--restore-devkit-cache]
            [--configure-only] [--no-tests] [--jobs N] [--build-dir DIR]
            [--allow-full-build] [--dry-run]

DIR (default: the current directory) is the app's checkout and its
workspace: it holds devkit.toml (the GUI.Forms pin: major and floor) and
receives .ci/, .sdk/, .build/ and .ccache/, which its .gitignore lists. The
project file is --project, else DIR/harness.toml. In order:

1. resolve: resolve_gui_forms.py resolve --devkit DIR/devkit.toml, when
   DIR has no .ci/gui_forms-resolved.json yet or --resolve, --floor or
   --revision asks for a new one (a build stays on its resolved GUI.Forms
   until asked to move);
2. fetch: the resolved SDK at DIR/.sdk/gui-forms-sdk (the fixed path the
   build guard checks), and the build's runtime asset when it has one;
3. the toolchain and the C++ runtime: on Windows the published CLANG64
   toolchain (restore_local.py toolchain) and the own runtime
   (own_runtime_local.py: restored from the runtime asset, else built),
   whose toolchain file the configure uses; on macOS and Linux the runtime
   under .build/toolchain/ (restore_local.py runtime: verified when
   restored, else built), with harness/cmake/llvm22.cmake;
4. with --restore-devkit-cache, the devkit's newest compiler cache
   (devkit_cache.py restore; the devkit's own smoke build);
5. the build environment (restore_local.py env, with the Windows settings
   and CMAKE_TOOLCHAIN_FILE), written to .ci/local-build-env.* and applied
   to the steps below, so a later shell can `. .ci/local-build-env.sh`;
6. configure: cmake -G Ninja into --build-dir (default
   DIR/.build/native-<platform>) with that toolchain file and, for a
   consumer, -DGUI_FORMS_DEVKIT_HARNESS_ROOT naming this harness, whose
   harness/cmake/DevkitBuildGuard.cmake the consumer's CMakeLists.txt
   includes: the build guard stops a configure that would build GUI.Forms
   from source or miss the SDK (--allow-full-build overrides it);
7. build, then ctest (under xvfb-run on Linux without a display), unless
   --configure-only or --no-tests.

--dry-run prints every step and changes nothing.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import platform as host_platform
import shlex
import shutil
import subprocess
import sys

import build_environment

HARNESS: Path = Path(__file__).resolve().parent
# The harness root: the directory holding harness/ (the devkit's harness/ directory).
HARNESS_ROOT: Path = HARNESS.parent
PLATFORMS: tuple[str, ...] = ('windows-x64', 'linux-x64', 'linux-arm64', 'macos-arm64')
DEVKIT_FILE: str = 'devkit.toml'
PROJECT_FILE: str = 'harness.toml'
RESOLVED_RECORD: str = '.ci/gui_forms-resolved.json'
BUILD_ENVIRONMENT_RECORD: str = build_environment.BUILD_ENVIRONMENT_RECORD
TOOLCHAIN: Path = HARNESS / 'cmake' / 'llvm22.cmake'
# The three locations own_runtime.py prints. GUI.Forms' Windows toolchain
# reads them as cache settings (only GUI_FORMS_LIBCXX_PREFIX also from the
# environment), so the configure passes each with -D, beside
# GUI_FORMS_MSVC_RUNTIME=OWN, as GUI.Forms' tools/toolkit_configure.py does.
OWN_RUNTIME_SETTINGS: tuple[str, ...] = ('GUI_FORMS_OWN_RUNTIME_SOURCE', 'GUI_FORMS_OWN_RUNTIME_PREFIX',
                                         'GUI_FORMS_LIBCXX_PREFIX')


class BuildError(Exception):
    """An expected failure; the command prints it and exits 1."""


@dataclass(frozen=True)
class Options:
    app: Path
    project: Path
    platform: str
    resolve: bool = False
    floor: bool = False
    revision: str = ''
    restore_devkit_cache: bool = False
    configure_only: bool = False
    tests: bool = True
    jobs: int = 4
    build_dir: Path | None = None
    allow_full_build: bool = False
    dry_run: bool = False


@dataclass
class Step:
    """One command of the build; settings: it prints NAME=VALUE lines the environment takes."""
    what: str
    command: list[str]
    settings: bool = False


def host_platform_name() -> str:
    machine: str = host_platform.machine().lower()
    if sys.platform == 'win32':
        return 'windows-x64'
    if sys.platform == 'darwin':
        return 'macos-arm64'
    return 'linux-arm64' if machine in ('arm64', 'aarch64') else 'linux-x64'


def tool(name: str) -> list[str]:
    command: list[str] = [sys.executable, '-B', str(HARNESS / name)]
    return command


def build_dir(options: Options) -> Path:
    directory: Path = options.build_dir if options.build_dir is not None else (
        options.app / '.build' / ('native-' + options.platform))
    return directory


def is_devkit(options: Options) -> bool:
    """Whether DIR is this devkit's own checkout (its CMakeLists.txt includes the guard directly)."""
    result: bool = options.app.resolve() == HARNESS_ROOT.parent
    return result


def preparation(options: Options) -> list[Step]:
    """Steps 1 to 4: what runs before the build environment is written."""
    steps: list[Step] = []
    workspace: str = str(options.app)
    if options.resolve or options.floor or options.revision or not (options.app / RESOLVED_RECORD).is_file():
        resolve: list[str] = tool('resolve_gui_forms.py') + ['resolve', '--devkit', str(options.app / DEVKIT_FILE),
                                                              '--workspace', workspace]
        if options.floor:
            resolve.append('--floor')
        if options.revision:
            resolve.extend(['--revision', options.revision])
        steps.append(Step('resolving GUI.Forms', resolve))
    steps.append(Step('fetching the SDK', tool('resolve_gui_forms.py') + ['fetch', '--platform', options.platform,
                                                                          '--workspace', workspace]))
    if options.platform == 'windows-x64':
        steps.append(Step('restoring the Windows toolchain',
                          tool('restore_local.py') + ['toolchain', '--platform', options.platform]))
        steps.append(Step('restoring or building the own runtime',
                          tool('own_runtime_local.py') + ['--workspace', workspace, '--jobs', str(options.jobs)],
                          settings=True))
    else:
        steps.append(Step('verifying or building the C++ runtime',
                          tool('restore_local.py') + ['runtime', '--platform', options.platform]))
    if options.restore_devkit_cache:
        steps.append(Step("restoring the devkit's cache",
                          tool('devkit_cache.py') + ['restore', '--workspace', workspace, '--platform',
                                                     options.platform]))
    return steps


def toolchain_file(settings: list[tuple[str, str]]) -> str:
    """The toolchain the configure uses: the own runtime's on Windows (CMAKE_TOOLCHAIN_FILE), else llvm22.cmake."""
    named: list[str] = [value for name, value in settings if name == 'CMAKE_TOOLCHAIN_FILE']
    result: str = named[-1] if named else TOOLCHAIN.as_posix()
    return result


def own_runtime_options(options: Options, settings: list[tuple[str, str]]) -> list[str]:
    """Windows: the toolchain's own-runtime mode and its three locations, as -D options; nothing elsewhere.

    Without GUI_FORMS_MSVC_RUNTIME=OWN the toolchain takes its Microsoft mode
    (-D_DLL, --dependent-lib=msvcrt, /DEFAULTLIB:msvcprt.lib) while linking
    the own runtime's libc++, and every executable fails on duplicate
    std::exception and std::bad_alloc symbols.
    """
    if options.platform != 'windows-x64':
        return []
    result: list[str] = ['-DGUI_FORMS_MSVC_RUNTIME=OWN']
    name: str
    value: str
    for name, value in settings:
        if name in OWN_RUNTIME_SETTINGS:
            result.append('-D' + name + '=' + value)
    return result


def environment_step(options: Options, settings: list[tuple[str, str]]) -> Step:
    """Step 5: restore_local.py env with every setting and the toolchain file."""
    command: list[str] = tool('restore_local.py') + ['env', '--platform', options.platform]
    name: str
    value: str
    for name, value in settings:
        if name != 'CMAKE_TOOLCHAIN_FILE':
            command.extend(['--set', name + '=' + value])
    command.extend(['--set', 'CMAKE_TOOLCHAIN_FILE=' + toolchain_file(settings)])
    step: Step = Step('writing the build environment', command)
    return step


def build_steps(options: Options, settings: list[tuple[str, str]], display: bool) -> list[Step]:
    """Steps 6 and 7: configure, build and test (display: Linux has one, or xvfb-run is not needed)."""
    tree: str = str(build_dir(options))
    configure: list[str] = ['cmake', '-S', str(options.app), '-B', tree, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                            '-DCMAKE_TOOLCHAIN_FILE=' + toolchain_file(settings), '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']
    configure.extend(own_runtime_options(options, settings))
    if not is_devkit(options):
        configure.append('-DGUI_FORMS_DEVKIT_HARNESS_ROOT=' + HARNESS_ROOT.as_posix())
    if options.allow_full_build:
        configure.append('-DGUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=ON')
    steps: list[Step] = [Step('configuring', configure)]
    if options.configure_only:
        return steps
    steps.append(Step('building', ['cmake', '--build', tree, '--parallel', str(options.jobs)]))
    if options.tests:
        test: list[str] = ['ctest', '--test-dir', tree, '--output-on-failure', '--timeout', '300']
        if options.platform.startswith('linux') and not display:
            test = ['xvfb-run', '-a'] + test
        steps.append(Step('testing', test))
    return steps


def step_environment(options: Options) -> dict[str, str]:
    """The tools' environment: the project and workspace, then the build environment once written."""
    environment: dict[str, str] = dict(os.environ)
    environment['HARNESS_PROJECT'] = str(options.project)
    environment['HARNESS_WORKSPACE'] = str(options.app)
    record: Path = options.app / BUILD_ENVIRONMENT_RECORD
    if record.is_file():
        environment = build_environment.apply_build_environment(record, environment)
    return environment


def run(options: Options, step: Step) -> str:
    """Runs one step, printing it; returns its output when it prints settings (it is passed through)."""
    print(('would run: ' if options.dry_run else '+ ') + shlex.join(step.command), flush=True)
    if options.dry_run:
        return ''
    if not step.settings:
        completed: subprocess.CompletedProcess[str] = subprocess.run(step.command, env=step_environment(options),
                                                                     check=False)
        if completed.returncode != 0:
            raise BuildError(step.what + ' failed (' + str(completed.returncode) + ')')
        return ''
    captured: subprocess.CompletedProcess[str] = subprocess.run(step.command, env=step_environment(options),
                                                                capture_output=True, text=True, check=False)
    if captured.stdout.strip():
        print(captured.stdout.rstrip(), flush=True)
    if captured.stderr.strip():
        print(captured.stderr.rstrip(), file=sys.stderr, flush=True)
    if captured.returncode != 0:
        raise BuildError(step.what + ' failed (' + str(captured.returncode) + ')')
    return captured.stdout


def settings_of(printed: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    line: str
    for line in printed.splitlines():
        name: str
        separator: str
        value: str
        name, separator, value = line.strip().partition('=')
        if separator and name and name.replace('_', '').isalnum() and name.upper() == name and name[0].isalpha():
            found.append((name, value))
    return found


def check_inputs(options: Options) -> None:
    if not (options.app / DEVKIT_FILE).is_file():
        raise BuildError(str(options.app) + ' has no ' + DEVKIT_FILE + ' (the GUI.Forms pin: [gui_forms] major and '
                         'minimum); new-app writes one')
    if not options.project.is_file():
        raise BuildError('No project file ' + str(options.project) + ' (give --project, or put ' + PROJECT_FILE
                         + ' in ' + str(options.app) + ')')
    if not (options.app / 'CMakeLists.txt').is_file():
        raise BuildError(str(options.app) + ' has no CMakeLists.txt')


def build(options: Options) -> None:
    check_inputs(options)
    settings: list[tuple[str, str]] = []
    step: Step
    for step in preparation(options):
        printed: str = run(options, step)
        if step.settings:
            settings.extend(settings_of(printed))
    if options.dry_run and options.platform == 'windows-x64':
        settings.append(('CMAKE_TOOLCHAIN_FILE', (options.app / '.ci' / 'gui_forms-tools' / 'cmake'
                                                  / 'llvm22-windows-msvc.cmake').as_posix()))
    run(options, environment_step(options, settings))
    display: bool = bool(os.environ.get('DISPLAY', '')) or shutil.which('xvfb-run') is None
    for step in build_steps(options, settings, display):
        run(options, step)
    print(('Dry run finished: nothing was changed' if options.dry_run else 'Built ' + str(options.app)
           + ' against the prebuilt GUI.Forms SDK (' + str(build_dir(options)) + ')'), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--app', type=Path, default=Path.cwd(), help='the app checkout and workspace')
    parser.add_argument('--project', type=Path, default=None, help='the project file (default: DIR/harness.toml)')
    parser.add_argument('--platform', choices=PLATFORMS, default='')
    parser.add_argument('--resolve', action='store_true', help='resolve GUI.Forms again (the newest green build)')
    moving: argparse._MutuallyExclusiveGroup = parser.add_mutually_exclusive_group()
    moving.add_argument('--floor', action='store_true', help='resolve the build at the pin\'s minimum')
    moving.add_argument('--revision', default='', help='resolve that GUI.Forms commit\'s build')
    parser.add_argument('--restore-devkit-cache', action='store_true', help="restore the devkit's compiler cache")
    parser.add_argument('--configure-only', action='store_true')
    parser.add_argument('--no-tests', action='store_true')
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--build-dir', type=Path, default=None)
    parser.add_argument('--allow-full-build', action='store_true', help='build even when the build guard objects')
    parser.add_argument('--dry-run', action='store_true', help='print every step; change nothing')
    args: argparse.Namespace = parser.parse_args(argv)
    app: Path = args.app.resolve()
    options: Options = Options(
        app=app, project=(args.project if args.project is not None else app / PROJECT_FILE).resolve(),
        platform=args.platform or host_platform_name(), resolve=args.resolve, floor=args.floor,
        revision=args.revision, restore_devkit_cache=args.restore_devkit_cache, configure_only=args.configure_only,
        tests=not args.no_tests, jobs=args.jobs, build_dir=None if args.build_dir is None else args.build_dir.resolve(),
        allow_full_build=args.allow_full_build, dry_run=args.dry_run)
    try:
        build(options)
    except BuildError as error:
        print('devkit_build: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
