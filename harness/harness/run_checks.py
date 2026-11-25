#!/usr/bin/env python3
"""Runs the devkit's source checks over an app's paths, by profile.

The devkit harness serves apps outside our house as well as our own, so the
house's strict checks are opt-in:

- consumer (the default): the retained-mode review (check_retained_mode.py),
  which every GUI.Forms app benefits from: it reports layout requested from
  paint, text flowed on every arrange, and the other ways a control stops
  being retained.
- strict: consumer, plus the house style (check_house_style.py) and the
  lifetime rules (check_lifetime_rules.py). Our apps (Plan Paint, PlaySuite,
  SwiftEdit, Pocket Library, Explore) and the devkit's own code switch it on.

The profile is `--profile`, else the environment variable
GUI_FORMS_DEVKIT_CHECKS, else consumer. Every check of the profile runs, so
one report shows every failure; the exit status is 1 when any failed, 2 for
a usage error.

    python3 -B harness/harness/run_checks.py [--profile strict] src tests
"""

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys

HERE: Path = Path(__file__).resolve().parent
PROFILE_VARIABLE: str = 'GUI_FORMS_DEVKIT_CHECKS'
DEFAULT_PROFILE: str = 'consumer'


@dataclass(frozen=True)
class Check:
    label: str
    script: str


RETAINED: Check = Check('retained mode', 'check_retained_mode.py')
HOUSE_STYLE: Check = Check('house style', 'check_house_style.py')
LIFETIME: Check = Check('lifetime rules', 'check_lifetime_rules.py')

PROFILES: dict[str, tuple[Check, ...]] = {
    'consumer': (RETAINED,),
    'strict': (RETAINED, HOUSE_STYLE, LIFETIME),
}


def chosen_profile(argument: str | None, environment: dict[str, str]) -> str:
    """The profile named by the argument, else the environment, else consumer; raises ValueError for an unknown name."""
    name: str = argument or environment.get(PROFILE_VARIABLE, '') or DEFAULT_PROFILE
    if name not in PROFILES:
        raise ValueError('unknown check profile ' + repr(name) + ' (expected ' + ' or '.join(sorted(PROFILES)) + ')')
    return name


def run(profile: str, paths: list[str]) -> list[str]:
    """Runs every check of the profile over the paths; returns the labels of those that failed."""
    failed: list[str] = []
    check: Check
    for check in PROFILES[profile]:
        command: list[str] = [sys.executable, '-B', str(HERE / check.script), *paths]
        print('== ' + check.label + ' (' + profile + ')', flush=True)
        completed: subprocess.CompletedProcess[bytes] = subprocess.run(command, check=False)
        if completed.returncode != 0:
            failed.append(check.label)
    return failed


def main() -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--profile', choices=sorted(PROFILES), default=None,
                        help='consumer (default) or strict; else ' + PROFILE_VARIABLE)
    parser.add_argument('paths', nargs='+')
    arguments: argparse.Namespace = parser.parse_args()
    try:
        profile: str = chosen_profile(arguments.profile, dict(os.environ))
    except ValueError as error:
        print('run_checks: ' + str(error), file=sys.stderr)
        return 2
    failed: list[str] = run(profile, arguments.paths)
    if failed:
        print('run_checks: failed: ' + ', '.join(failed), file=sys.stderr)
        return 1
    print('run_checks: ' + profile + ' checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
