# gui_forms_devkit

The GUI.Forms companion ecosystem, built in lockstep with GUI.Forms:
Pocket Reference, the demonstrator views and programs, and the devkit
harness that consumer apps build with. MIT; see `LICENSE` and
`THIRD_PARTY_NOTICES.md`.

## Quick start

Build GUI.Forms applications here: the devkit fetches a prebuilt GUI.Forms
SDK and builds only your code; GUI.Forms itself is not compiled. The
GUI.Forms guide's [Get started](https://gui-forms.readthedocs.io/en/latest/user/get-started.html) page gives the same
steps.

You need Git, Python 3.11 or later, CMake 3.25 or later, Ninja and ccache.
On macOS and Linux you also need LLVM 22.1.8 (clang) on `PATH`. On Windows
you need Git for Windows, whose Git Bash runs the bootstrap; the build
restores the LLVM toolchain itself.

### 1. Bootstrap

Clone the devkit.

macOS:

```sh
git clone https://github.com/malkuth-software/gui_forms_devkit
```

Linux:

```sh
git clone https://github.com/malkuth-software/gui_forms_devkit
```

Windows (PowerShell):

```powershell
git clone https://github.com/malkuth-software/gui_forms_devkit
```

### 2. Create your app

The bootstrap's `new-app` command makes an app from the devkit's template
in a new directory, copies the devkit into it at `.devkit/`, and makes the
first commit with `git init`. It pushes nothing and adds no remote.

macOS and Linux:

```sh
sh gui_forms_devkit/harness/bootstrap.sh new-app hello_forms --license mit
```

Windows (PowerShell):

```powershell
powershell -File gui_forms_devkit\harness\bootstrap.ps1 new-app hello_forms --license mit
```

The name is in snake case. The app goes in `./hello_forms` unless you name
a directory after it. `--title` sets the window title, `--license` picks
`mit`, `proprietary`, `polyform-noncommercial` or `none` (the default), and
`--strict` turns on the devkit's stricter house checks. `--dry-run` shows
what it would write.

The app holds:

| Path | What |
|---|---|
| `src/`, `tests/` | a greeter form, its entry point, the form's test and the interaction test, which holds hover and drag to no layout work |
| `reference/` | the reference custom control, a retained control to copy when you write your own |
| `CMakeLists.txt`, `build.py` | the build against the prebuilt SDK, with the build guard |
| `devkit.toml` | the GUI.Forms pin (major and floor) and the checks' profile |
| `harness.toml`, `harness.lock` | the project file the devkit's tools read, and the devkit commit the app uses |
| `AGENTS.md`, `CLAUDE.md` | the rules for building on GUI.Forms, for you and for any coding agent you work with |

### 3. Build

macOS and Linux:

```sh
cd hello_forms
python3 build.py --jobs 4
```

Windows (PowerShell):

```powershell
cd hello_forms
python build.py --jobs 4
```

`build.py` resolves the GUI.Forms pin to one build, downloads that build's
SDK, checks its SHA-256 and unpacks it at `.sdk/gui-forms-sdk`. It then sets
up the toolchain and the C++ runtime, writes the build environment to
`.ci/local-build-env.sh` (and `.ps1`), configures with CMake and Ninja,
builds and runs the tests. GUI.Forms is not compiled.

The first build on macOS and Linux also builds the C++ runtime once, which
takes several minutes. On Windows it restores GUI.Forms' published LLVM
toolchain and its own C++ runtime, and builds the runtime only when no
published one fits. To do that Windows step on its own, run
`powershell -File .devkit\harness\bootstrap.ps1 own-runtime --workspace .`
in the app after a first build: it prints the runtime settings and the
`CMAKE_TOOLCHAIN_FILE` to configure with.

Later builds stay on the same GUI.Forms build until you move them with
`python3 build.py --resolve`; `--floor` builds against the floor itself.
`--configure-only`, `--no-tests` and `--dry-run` do what they say.
`python3 build.py check` runs the checks for house style, lifetime rules and
retained mode over `src`, `tests` and `reference`. The checks cover only the
mechanical part of the style: read [`HOUSE_STYLE.md`](HOUSE_STYLE.md) (in an
app, `.devkit/HOUSE_STYLE.md`) before writing code. It is a verbatim copy of
the canonical text in the notes repository;
`python3 harness/harness/sync_house_style.py` refreshes it.

#### The build guard

The devkit's CMake module (`DevkitBuildGuard.cmake`, included by the app's
`CMakeLists.txt`) checks the build when configuring ends and again before
the first compile. If the build would compile GUI.Forms, or would not use
the prebuilt SDK and the compiler cache, it stops with:

```text
devkit build guard: likely misconfiguration preventing efficient incremental building.
```

Each finding below that line names what does not match and how to fix it.
The usual causes:

- the SDK is missing or is not the resolved build: run
  `python3 build.py --resolve`;
- the compiler, the ccache settings or the locale differ from the ones the
  SDK was built with, usually because a build ran outside `build.py` without
  the build environment: load `.ci/local-build-env.sh` (or `.ps1`) first;
- ccache is not installed, or is not the compiler launcher;
- a GUI.Forms source tree is on the build's path, so its sources would be
  compiled.

The guard works the same when an IDE runs the build: configure once with
`python3 build.py --configure-only`, then point the IDE at the build
directory. A missing C++ runtime on macOS or Linux is a warning, not a stop.
To build anyway, run `python3 build.py --allow-full-build`, configure with
`-DGUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=ON` or set
`GUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=1`, and expect a much longer build.

### 4. Run

macOS:

```sh
open .build/native-macos-arm64/hello_forms.app
```

Linux (on arm64, `native-linux-arm64`):

```sh
.build/native-linux-x64/hello_forms
```

Windows:

```powershell
.build\native-windows-x64\hello_forms.exe
```

### Pocket Reference and the demonstrators

The devkit builds its own programs the same way. One command sets up its
workspace and builds Pocket Reference, the Gallery, Explore, Correspondence
and the other demonstrators against the prebuilt SDK.

macOS and Linux:

```sh
sh gui_forms_devkit/harness/bootstrap.sh --workspace gui_forms_devkit --project gui_forms_devkit
```

Windows (PowerShell):

```powershell
powershell -File gui_forms_devkit\harness\bootstrap.ps1 --workspace gui_forms_devkit --project gui_forms_devkit
```

Pocket Reference is then at
`gui_forms_devkit/.build/native-<platform>/pocket_reference/` and the other
programs under `programs/` beside it.

### Next

- [Your first window](https://gui-forms.readthedocs.io/en/latest/user/first-window.html): a form document, the model
  it binds, a theme and an event handler.
- [Custom controls](https://gui-forms.readthedocs.io/en/latest/user/custom-controls.html): the tutorial for a
  retained control of your own.
- [Mockups](https://gui-forms.readthedocs.io/en/latest/user/mockups.html): a form and a theme from files alone, with
  no compile.
- [Talk to a running program](https://gui-forms.readthedocs.io/en/latest/user/talk-to-a-program.html): any GUI.Forms
  program over MCP.

## Layout

```text
devkit.toml          the GUI.Forms pin: major 1, floor 1.0.5, channel main
harness/             the devkit harness (see harness/README.md)
pocket_reference/    Pocket Reference, with its history
views/<id>/          demonstrator views, one static library each
mockups/             mockups gui-forms-mockup lists: .form, .fixture, .theme.css
programs/            host mains, labs, the File Manager demoboard, packaging
```

## Mockups

`gui-forms-mockup` (programs/host/<os>/mockup_main.*, views/mockup_factory)
shows a form document, its fixture data and its theme sheet at once, with
no build, and shows them again each time one is saved. A mockup is files:
add `mockups/<name>.form` (and, if it wants them, `<name>.fixture` and
`<name>.theme.css`) and it is listed. GUI.Forms' `docs/user/mockups.md`
describes the fixture format and the library API (`FormMockup`).

```text
gui-forms-mockup                          the catalogue: every .form under mockups/
gui-forms-mockup --interface=claim_form   opens one by name
gui-forms-mockup path/to/my.form [--fixture f] [--sheet s.theme.css]
gui-forms-mockup --screenshots out/       writes out/<name>.png for each, then exits
```

- A refused file is shown in the window with its file, line, column and
  code; the last good mockup stays on screen.
- The Theme menu switches the base (windows-professional by default,
  gui-forms), the mockup's sheet on or off, or a familiar theme; the Scheme
  menu the system's, light or dark colour scheme. `--base`, `--no-sheet`,
  `--familiar-theme` and `--scheme` choose them at start.
- Declared handlers (`on-click="save_claim"`) and bound commands record
  each time they run: the status line, a JSON line on standard output, and
  over MCP (`--mcp`) the tools `mockup_list`, `mockup_open`,
  `mockup_reload`, `mockup_check` and `mockup_events`.
- `--mockups <dir>` (or `$GUI_FORMS_MOCKUPS`, else `./mockups`) lists
  another folder. `python3 -B programs/tools/check_mockups.py` checks the
  checked-in mockups' XML, sources and stable IDs without a build.

## The pin

`devkit.toml` names the GUI.Forms major and the oldest 1.x whose API the
devkit uses. A build takes the newest green GUI.Forms build in that range:
the newest `build-<sha>` pre-release carrying every platform's SDK and cache
(or, on the stable channel, the newest `v1.*` release). GUI.Forms refuses
breaking changes within a major, so the devkit evolves with it without a
pin bump; raise `minimum` when the devkit starts using newer API.

## Where the histories came from

| Path | Source | History |
|---|---|---|
| root | new | this repository's own |
| `pocket_reference/` | malkuth-software/pocket_reference main 3328697, relicensed to MIT (936bcb5) | all 13 commits plus the relicence, merged with `--allow-unrelated-histories` |
| `programs/`, `views/` | malkuth-software/gui_forms main 8b920c0f2 (1.0.3) | the 308 commits touching the moving paths (filter-repo `--path` then `--path-rename`), merged the same way |
| `harness/` | template_harness, see `harness/README.md` | none: a plain copy |

Pocket Reference's unpushed `claude/helpbook-port` (b59a1e1) has diverged
from its main (6 commits each way) and is still in the integration queue; it
arrives as a rebase onto `pocket_reference/`.

## What came from gui_forms

| gui_forms path | Here |
|---|---|
| `demo/{code_zoom,correspondence,data_workbench,process_control,touch_start}/` | `views/<id>/` |
| `demo/program_options.hpp`, `gallery_staging.hpp`, `gallery_headless_capture.hpp` | `programs/shell/` |
| `demo/*_lab.{cpp,hpp}` (nine labs), `demo/visual_inspector_poll.hpp` | `programs/labs/` |
| `src/host/{macos,windows,linux}/*_main.*` except `windows/menu_probe_main.cpp` | `programs/host/<os>/` |
| `file_manager_demoboard/` | `programs/file_manager_demoboard/` |
| `packaging/{programs.json,deb_control.in,linux_desktop.in,windows_installer.nsi.in}` | `programs/packaging/` (moved) |
| `packaging/licenses.json`, `packaging/licenses/` | `programs/packaging/` (copied: the SDK and the STXlib package read them too) |
| `tools/{package_programs,smoke_package,test_package_programs}.py` | `programs/tools/` |
| `tools/{publication_version,check_mcp_launch}.py` | `programs/tools/` (copied: the package and smoke tools import them) |

Kept in gui_forms, against the first cut of the design, because the
installed `GalleryModel` component or its `Lab` and `DemoControls`
dependencies build them (CMakeLists.txt, `gui_forms_gallery_model`):
`demo/gallery.cpp`, `gallery.hpp`, `gallery_instrument.*`, `gallery_parts.*`,
`gallery_assets.hpp`, `gallery.form`, `gallery_form_pages.form`,
`demo/composites/`, `demo/themes/{gallery,industrial,gost_paints}`,
`demo/lab_controls/` and `lab/`. `windows/menu_probe_main.cpp` stays too: it
is gui_forms_tests' menu probe, not a program.

## Building the programs

```sh
python3 -B harness/harness/resolve_gui_forms.py resolve
python3 -B harness/harness/resolve_gui_forms.py fetch --platform macos-arm64
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_TOOLCHAIN_FILE=harness/harness/cmake/llvm22.cmake
cmake --build build
python3 -B programs/tools/package_programs.py --platform macos-arm64 --build-dir build --version 1.0.0 --out dist
```

`fetch` restores the build's C++ runtime (`gui-forms-runtime-<platform>`)
when it publishes one, and unpacks its SDK at `.sdk/gui-forms-sdk`.
`programs/CMakeLists.txt` builds each program under its GUI.Forms target and
output name (`gui_forms_gallery`, `gui_forms_gallery_windows`,
`gui_forms_gallery_linux`, ...), so `programs/packaging/programs.json` and the
package and smoke tools are unchanged. Every program links
`GUIForms::Application` and its model: the Gallery `GUIForms::GalleryModel`,
a demonstrator its view (`views/`), a lab `programs/labs/<lab>.cpp`, Explore
the demoboard's model over `GUIForms::Lab`. The faces' notices come from the
SDK's `share/GUIForms/fonts`, as does the packager's (`--sdk`, default
`.sdk/gui-forms-sdk`).

The programs used two private GUI.Forms headers (a thread starter and a file
writer); `programs/shell/program_support.hpp` rebuilds them on STXlib and the
standard library, so nothing here includes a `src/` header. The Code Zoom
view shows one of this repository's files
(`GUI_FORMS_DEVKIT_CODE_ZOOM_SOURCE`, default `views/code_zoom/code_sheet.cpp`)
where GUI.Forms showed one of its own.

## Local commands

Anyone can run these from a devkit checkout; none needs in-house access.

```sh
sh harness/bootstrap.sh new-app paint_box ~/apps/paint_box   # a new app, git init, never pushed
cd ~/apps/paint_box && python3 build.py --jobs 4              # resolve, fetch, build, test
sh harness/bootstrap.sh own-runtime --workspace DIR           # Windows: the own runtime and its toolchain file
sh harness/bootstrap.sh --workspace DIR --project gui_forms_devkit   # this devkit, built as a consumer
```

`harness/harness/devkit_build.py --app .` builds this devkit the same way
(`--project harness/projects/gui_forms_devkit.toml --restore-devkit-cache`).

## CI

| Workflow | When | What |
|---|---|---|
| `lockstep.yml` | `repository_dispatch` `gui-forms-advanced` from GUI.Forms (and Run workflow) | builds everything against exactly that GUI.Forms build, packages and smoke-launches it, runs the cache proof; on success publishes the packages and the devkit cache into the pre-release `gf-<GUI.Forms sha>` and prunes to the five newest; on failure opens one issue |
| `cache-proof.yml` | every lockstep run, nightly, Run workflow | the devkit against GUI.Forms R, R-1, the newest stable and (weekly) the floor, with the devkit cache of the previous lockstep run: at least 99% of the computed expected hits for R and R-1; GUI.Forms itself at R from its own cache: at least 98% |
| `pull-request.yml` | pull requests, pushes to main | harness and packaging tests, strict checks, a build against the newest green build and (pull requests) the floor's |
| `release.yml` | tag `v<x.y.z>` (Run workflow: a draft) | Pocket Reference and the programs as per-platform downloads with `SHA256SUMS.txt` and the GUI.Forms build they were made on; no harness or cache |

`build.yml` is the one build all of them call (`.github/actions/devkit-setup`
sets up the toolchain and compile environment).

## Checks

```sh
python3 -B -m unittest discover -s harness/harness -p "test_*.py"
python3 -B -m unittest discover -s programs/tools -p "test_*.py"
python3 -B harness/harness/run_checks.py --profile strict views programs
```
