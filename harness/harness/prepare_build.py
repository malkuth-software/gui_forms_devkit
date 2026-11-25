#!/usr/bin/env python3
"""Run a project's [bootstrap.<platform>] prepare commands in CI, as bootstrap.py does on a machine.

    python3 -B harness/harness/prepare_build.py --platform P

For the project of HARNESS_PROJECT in the workspace of HARNESS_WORKSPACE
(run from the workspace root, in the environment restore_local.py env
wrote: `. .ci/local-build-env.sh` first). Each prepare command runs with
{python} replaced by this interpreter; the NAME=VALUE lines it prints are
collected, and restore_local.py env is run again with each as --set, so
.ci/local-build-env.sh then carries them for the build.

GUI.Forms on Windows: `own_runtime.py build --out .ci/own-runtime` reuses the
runtime restore_local.py cache restored from the build's
gui-forms-runtime-windows-x64 asset when its stamp matches, and builds it
otherwise; it prints the three settings its toolchain reads. A platform
with no prepare commands does nothing.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable

import project

HARNESS: Path = Path(__file__).resolve().parent
PYTHON_ARGUMENT: str = '{python}'
SETTING_LINE: re.Pattern[str] = re.compile(r'[A-Z][A-Z0-9_]*=.*')


def with_python(command: tuple[str, ...]) -> list[str]:
    return [sys.executable if argument == PYTHON_ARGUMENT else argument for argument in command]


def settings_of(printed: str) -> list[str]:
    found: list[str] = []
    line: str
    for line in printed.splitlines():
        if SETTING_LINE.fullmatch(line.strip()):
            found.append(line.strip())
    return found


def run_capturing(command: list[str]) -> str:
    print('+ ' + ' '.join(command), flush=True)
    completed: subprocess.CompletedProcess[str] = subprocess.run(command, capture_output=True, text=True,
                                                                 check=False)
    if completed.stdout.strip():
        print(completed.stdout.rstrip(), flush=True)
    if completed.returncode != 0:
        print(completed.stderr.rstrip(), file=sys.stderr, flush=True)
        raise SystemExit('prepare_build: ' + command[0] + ' failed (' + str(completed.returncode) + ')')
    return completed.stdout


def prepare(product: project.Project, platform: str, runner: Callable[[list[str]], str] = run_capturing) -> list[str]:
    """Runs the prepare commands and rewrites the build environment with what they printed; returns the settings."""
    table: project.BootstrapPlatform | None = (None if product.bootstrap is None
                                                else product.bootstrap.platforms.get(platform))
    if table is None or not table.prepare:
        print('prepare_build: ' + product.name + ' has no prepare commands for ' + platform, flush=True)
        return []
    settings: list[str] = []
    command: tuple[str, ...]
    for command in table.prepare:
        settings.extend(settings_of(runner(with_python(command))))
    rewrite: list[str] = [sys.executable, '-B', str(HARNESS / 'restore_local.py'), 'env', '--platform', platform]
    setting: str
    for setting in settings:
        rewrite.extend(['--set', setting])
    runner(rewrite)
    return settings


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--platform', required=True)
    arguments: argparse.Namespace = parser.parse_args(argv)
    prepare(project.current(), arguments.platform)
    return 0


if __name__ == '__main__':
    sys.exit(main())
