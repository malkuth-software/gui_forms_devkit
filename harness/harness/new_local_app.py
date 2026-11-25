#!/usr/bin/env python3
"""Make a new GUI.Forms app on this machine from the devkit's app template; nothing is pushed anywhere.

    sh harness/bootstrap.sh new-app NAME [DIR] [--title TITLE] [--namespace NS]
                                      [--license CHOICE] [--licensor HOLDER]
                                      [--repository OWNER/NAME] [--strict]
                                      [--no-devkit-clone] [--dry-run]

(bootstrap.sh runs this with a suitable Python; so does bootstrap.ps1 on
Windows.) NAME is the app's name in snake case (paint_box); DIR defaults to
./NAME and must be missing or empty. In order:

1. derive the names from NAME as new_app.py does (the type name, the build
   and environment names), refusing a reserved name or one starting with gui;
2. render templates/app/ into DIR without its in-house parts (the agents,
   FranSushi and CI configuration that name the in-house repositories and
   build host), with templates/consumer/'s README.md, AGENTS.md and
   CLAUDE.md in their place. The app gets:
   - devkit.toml: GUI.Forms pinned by this devkit's major and floor, and
     [checks] profile "consumer" (--strict opts into "strict");
   - build.py and CMakeLists.txt: the build against the prebuilt SDK
     through this devkit's devkit_build.py, with DevkitBuildGuard.cmake;
   - harness.toml: its project file, declaring no notes;
   - harness.lock: this devkit's repository and current commit;
   - the reference control (reference/), the form's test and the
     interaction tests;
   - LICENSE when --license names one (default none);
3. clone this devkit checkout into DIR/.devkit at that commit (ignored by
   the app's .gitignore), so the first build needs no network for the
   devkit; --no-devkit-clone leaves it to build.py, which clones it from
   GitHub;
4. git init DIR on main and commit the rendered tree. No remote is added and
   nothing is pushed.

--dry-run prints what it would write and changes nothing.
"""
from __future__ import annotations
import argparse
import datetime
from pathlib import Path
import subprocess
import sys

import new_app
import project

HARNESS: Path = Path(__file__).resolve().parent
REPOSITORY: Path = HARNESS.parent
DEVKIT_ROOT: Path = REPOSITORY.parent
DEVKIT_PROJECT: Path = REPOSITORY / 'projects' / 'gui_forms_devkit.toml'
TEMPLATES: Path = REPOSITORY / 'templates'
# templates/app/ paths an outsider's app leaves out: in-house agent, plugin and CI configuration
# (the in-house repositories, the build host wrapper, template_harness's reusable workflows).
IN_HOUSE_PREFIXES: tuple[str, ...] = ('.claude/', '.sushi/', '.github/')
# Replaced by templates/consumer/.
REPLACED: frozenset[str] = frozenset({'README.md', 'AGENTS.md', 'CLAUDE.md'})
DEVKIT_CLONE: str = '.devkit'
STRICT_LINE: tuple[str, str] = ('profile = "consumer"', 'profile = "strict"')


class LocalAppError(Exception):
    """An expected refusal or failure; the command prints it and exits 1."""


def say(text: str) -> None:
    print(text, flush=True)


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed: subprocess.CompletedProcess[str] = subprocess.run(['git', *arguments], capture_output=True, text=True,
                                                                 check=False)
    if check and completed.returncode != 0:
        raise LocalAppError('git ' + ' '.join(arguments) + ' failed: ' + completed.stderr.strip())
    return completed


def devkit_pin() -> tuple[str, str]:
    """This devkit's repository (its project file's) and commit (its checkout's HEAD)."""
    repository: str = project.load(DEVKIT_PROJECT).repository
    head: subprocess.CompletedProcess[str] = git('-C', str(DEVKIT_ROOT), 'rev-parse', 'HEAD', check=False)
    commit: str = head.stdout.strip()
    if head.returncode != 0 or len(commit) != 40:
        raise LocalAppError(str(DEVKIT_ROOT) + ' is not a git checkout of the devkit; run new-app from one')
    return repository, commit


def wanted(relative: Path) -> bool:
    """Whether a templates/app/ file belongs in an outsider's app."""
    text: str = relative.as_posix()
    keep: bool = not text.startswith(IN_HOUSE_PREFIXES) and text not in REPLACED
    return keep


def values_for(names: new_app.Names, repository: str, devkit: tuple[str, str], licensor: str) -> dict[str, str]:
    now: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
    major: str
    minimum: str
    major, minimum = new_app.gui_forms_pin()
    values: dict[str, str] = {
        'app': names.app, 'App': names.pascal, 'namespace': names.namespace, 'title': names.title,
        'build_name': names.build_name, 'env_prefix': names.env_prefix, 'artifact_prefix': names.artifact_prefix,
        'cache_asset_prefix': names.cache_asset_prefix, 'repository': repository,
        'harness_repository': devkit[0], 'harness_commit': devkit[1], 'harness_ref': devkit[1],
        'licensor': licensor, 'year': str(now.year), 'date': now.strftime('%Y-%m-%d'),
        'gui_forms_major': major, 'gui_forms_minimum': minimum}
    return values


def planned_files() -> list[tuple[Path, Path]]:
    """(source, path in the app) for every file the app gets, the consumer overlay last."""
    files: list[tuple[Path, Path]] = []
    relative: Path
    for relative in new_app.template_files(TEMPLATES / 'app'):
        if wanted(relative):
            files.append((TEMPLATES / 'app' / relative, relative))
    for relative in new_app.template_files(TEMPLATES / 'consumer'):
        files.append((TEMPLATES / 'consumer' / relative, relative))
    return files


def render(destination: Path, values: dict[str, str], license_choice: str, strict: bool) -> list[Path]:
    """Writes the app's files into destination; returns them, relative."""
    written: list[Path] = []
    source: Path
    relative: Path
    for source, relative in planned_files():
        target: Path = Path(new_app.render_text(relative.as_posix(), values, str(source)))
        text: str = new_app.render_text(source.read_text(encoding='utf-8'), values, str(source))
        if target.as_posix() == 'devkit.toml' and strict:
            text = text.replace(*STRICT_LINE)
        if new_app.leftover_placeholders(text) or new_app.leftover_placeholders(target.as_posix()):
            raise LocalAppError(str(source) + ' leaves a {{ after rendering')
        path: Path = destination / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8', newline='\n')
        path.chmod(source.stat().st_mode & 0o777)
        written.append(target)
    if license_choice not in new_app.LICENSES:
        raise LocalAppError('--license must be one of ' + ', '.join(new_app.LICENSES))
    if license_choice != 'none':
        notice: Path = TEMPLATES / 'licenses' / (license_choice + '.txt')
        (destination / 'LICENSE').write_text(new_app.render_text(notice.read_text(encoding='utf-8'), values,
                                                                 str(notice)), encoding='utf-8', newline='\n')
        written.append(Path('LICENSE'))
    return written


def clone_devkit(destination: Path, commit: str) -> None:
    """DIR/.devkit: this devkit checkout at commit, detached (build.py then needs no network for it)."""
    clone: Path = destination / DEVKIT_CLONE
    git('clone', '--quiet', '--no-checkout', str(DEVKIT_ROOT), str(clone))
    git('-C', str(clone), 'checkout', '--quiet', '--detach', commit)


def first_commit(destination: Path, message: str) -> str:
    """git init on main and the first commit; the commit, or '' when git has no identity to commit with."""
    git('init', '--quiet', '-b', 'main', str(destination))
    git('-C', str(destination), 'add', '--all')
    committed: subprocess.CompletedProcess[str] = git('-C', str(destination), 'commit', '--quiet', '-m', message,
                                                      check=False)
    if committed.returncode != 0:
        reason: list[str] = committed.stderr.strip().splitlines() or ['git commit failed']
        say('Not committed (' + reason[-1] + '); the files are staged: set git user.name and user.email, '
            'then git commit')
        return ''
    head: str = git('-C', str(destination), 'rev-parse', 'HEAD').stdout.strip()
    return head


def make_app(args: argparse.Namespace) -> int:
    names: new_app.Names = new_app.derive_names(args.name, args.title, args.namespace)
    destination: Path = (args.directory if args.directory is not None else Path.cwd() / names.app).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise LocalAppError(str(destination) + ' exists and is not an empty directory')
    devkit: tuple[str, str] = devkit_pin()
    repository: str = args.repository or 'local/' + names.app
    licensor: str = args.licensor or new_app.default_licensor()
    values: dict[str, str] = values_for(names, repository, devkit, licensor)
    say('New app ' + names.app + ' (' + names.title + ', type ' + names.pascal + ') in ' + str(destination))
    say('  GUI.Forms ' + values['gui_forms_major'] + '.x, at least ' + values['gui_forms_minimum']
        + '; checks profile ' + ('strict' if args.strict else 'consumer'))
    say('  devkit ' + devkit[0] + ' at ' + devkit[1][:12])
    if args.dry_run:
        source: Path
        relative: Path
        for source, relative in planned_files():
            say('  would write ' + new_app.render_text(relative.as_posix(), values, str(source)))
        say('  would ' + ('not clone the devkit' if args.no_devkit_clone else 'clone ' + str(DEVKIT_ROOT) + ' into '
                          + DEVKIT_CLONE) + ', git init on main and commit; nothing is pushed')
        return 0
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = render(destination, values, args.license, args.strict)
    say('  rendered ' + str(len(written)) + ' files')
    if not args.no_devkit_clone:
        clone_devkit(destination, devkit[1])
        say('  cloned the devkit into ' + DEVKIT_CLONE + ' at ' + devkit[1][:12])
    commit: str = first_commit(destination, names.title + ': made with gui_forms_devkit new-app\n\n'
                               'From the devkit\'s templates/app/ at ' + devkit[0] + ' ' + devkit[1][:12] + '.')
    if commit:
        say('  committed ' + commit[:12] + ' on main (no remote; nothing pushed)')
    say('')
    say('Next, with LLVM 22.1.8, CMake, Ninja and ccache on PATH:')
    say('  cd ' + str(destination))
    say('  python3 build.py --jobs 4')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog='new-app', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('name', help='the app name, snake case (paint_box)')
    parser.add_argument('directory', nargs='?', type=Path, default=None, help='where to make it (default ./NAME)')
    parser.add_argument('--title', default='', help='the window title and display name (default: from NAME)')
    parser.add_argument('--namespace', default='', help='the C++ namespace (default: NAME)')
    parser.add_argument('--license', choices=new_app.LICENSES, default='none')
    parser.add_argument('--licensor', default='', help='the copyright holder (default: your git user.name)')
    parser.add_argument('--repository', default='', help='owner/name for the project file (default local/NAME)')
    parser.add_argument('--strict', action='store_true', help='check at the strict profile instead of consumer')
    parser.add_argument('--no-devkit-clone', action='store_true', help='leave the devkit checkout to build.py')
    parser.add_argument('--dry-run', action='store_true', help='print what it would write; change nothing')
    args: argparse.Namespace = parser.parse_args(argv)
    try:
        return make_app(args)
    except (LocalAppError, new_app.NewAppError) as error:
        print('new-app: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
