#!/bin/sh
# The devkit's local commands, for anyone (no in-house access needed):
#
#   sh bootstrap.sh --workspace DIR --project NAME [--in-house] [--dry-run]
#                   [--platform P] [--no-restore] [--no-smoke]
#       set up a workspace for one product (harness/bootstrap.py); the
#       in-house notes and projects only with --in-house
#   sh bootstrap.sh new-app NAME [DIR] [--title T] [--license L] [--strict] ...
#       make a new app from the template in DIR (default ./NAME), with git
#       init and a first commit; nothing is pushed (harness/new_local_app.py)
#   sh bootstrap.sh own-runtime [--workspace DIR] [--jobs N]
#       Windows: restore or build GUI.Forms' own runtime and print the
#       toolchain file, as CI's windows-own-runtime action does
#       (harness/own_runtime_local.py)
#
# Finds a Python of 3.11 or later (tomllib): $HARNESS_PYTHON when set, else
# python3, python or py -3 on PATH. The Windows toolchain restore needs 3.14.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
bootstrap="$here/harness/bootstrap.py"
case "${1:-}" in
    new-app) shift; bootstrap="$here/harness/new_local_app.py" ;;
    own-runtime) shift; bootstrap="$here/harness/own_runtime_local.py" ;;
esac

usable() {
    "$@" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

if [ -n "${HARNESS_PYTHON:-}" ]; then
    exec "$HARNESS_PYTHON" -B "$bootstrap" "$@"
elif usable python3; then
    exec python3 -B "$bootstrap" "$@"
elif usable python; then
    exec python -B "$bootstrap" "$@"
elif usable py -3; then
    exec py -3 -B "$bootstrap" "$@"
fi
echo "bootstrap: no Python 3.11 or later found; set HARNESS_PYTHON to one" >&2
exit 1
