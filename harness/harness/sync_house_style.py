#!/usr/bin/env python3
"""Keep the devkit's HOUSE_STYLE.md a verbatim copy of the notes repository's.

The canonical text is HOUSE_STYLE.md on the main branch of
malkuth-software/notes. The devkit carries a copy so that every project built
with it can read the style offline, at `.devkit/HOUSE_STYLE.md`.

    python3 harness/harness/sync_house_style.py          # refresh the copy
    python3 harness/harness/sync_house_style.py --check  # exit 1 if it drifted
"""
import argparse
from pathlib import Path
import sys
import urllib.request

SOURCE: str = 'https://raw.githubusercontent.com/malkuth-software/notes/main/HOUSE_STYLE.md'
COPY: Path = Path(__file__).resolve().parent.parent.parent / 'HOUSE_STYLE.md'


def fetch_canonical() -> bytes:
    response: object
    with urllib.request.urlopen(SOURCE, timeout=30) as response:
        return response.read()


def main() -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='report whether the copy matches; change nothing')
    arguments: argparse.Namespace = parser.parse_args()
    canonical: bytes = fetch_canonical()
    current: bytes = COPY.read_bytes() if COPY.exists() else b''
    if canonical == current:
        print('HOUSE_STYLE.md matches notes main')
        return 0
    if arguments.check:
        print('HOUSE_STYLE.md differs from notes main; run '
              'python3 harness/harness/sync_house_style.py', file=sys.stderr)
        return 1
    COPY.write_bytes(canonical)
    print('HOUSE_STYLE.md refreshed from notes main')
    return 0


if __name__ == '__main__':
    sys.exit(main())
