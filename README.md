# gui_forms_devkit

The GUI.Forms companion ecosystem, built in lockstep with GUI.Forms:
Pocket Reference, the demonstrator views and programs, and the devkit
harness that consumer apps build with. MIT; see `LICENSE` and
`THIRD_PARTY_NOTICES.md`.

## Quick start

Build GUI.Forms applications here: the devkit fetches a prebuilt GUI.Forms
SDK and a compiler cache and builds only your code; GUI.Forms itself is not
compiled. The GUI.Forms guide's
[Get started](https://gui-forms.readthedocs.io/en/latest/user/get-started.html) page gives the same steps.

You need Git, Python 3.11 or later, CMake 3.25 or later, Ninja and ccache.
On Windows you also need Git for Windows, whose Git Bash runs the scripts.

### 1. Bootstrap

One command clones the devkit and sets up its workspace: the pinned LLVM 22
toolchain, the C++ runtime, the compiler cache and the build environment.

macOS:

```sh
git clone https://github.com/malkuth-software/gui_forms_devkit && sh gui_forms_devkit/harness/bootstrap.sh --workspace gui_forms_devkit --project gui_forms_devkit
```

Linux:

```sh
git clone https://github.com/malkuth-software/gui_forms_devkit && sh gui_forms_devkit/harness/bootstrap.sh --workspace gui_forms_devkit --project gui_forms_devkit
```

Windows (PowerShell):

```powershell
git clone https://github.com/malkuth-software/gui_forms_devkit; powershell -File gui_forms_devkit\harness\bootstrap.ps1 --workspace gui_forms_devkit --project gui_forms_devkit
```

Add `--dry-run` to see every step without changing anything. Running the
command again updates the workspace instead of starting over. On Linux the
bootstrap prints the packages to install with `sudo` rather than installing
them itself.

The bootstrap writes the build environment to `.ci/local-build-env.sh` (and
`.ci/local-build-env.ps1` for PowerShell). Load it in every shell you build
from, so the compiler and the cache settings match the ones the cache was
made with.

### 2. Build

The build fetches the prebuilt SDK and compiles only the devkit's own code;
GUI.Forms is not compiled.

macOS:

```sh
cd gui_forms_devkit
. .ci/local-build-env.sh
python3 -B harness/harness/resolve_gui_forms.py resolve
python3 -B harness/harness/resolve_gui_forms.py fetch --platform macos-arm64
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_TOOLCHAIN_FILE=harness/harness/cmake/llvm22.cmake
cmake --build build
```

Linux (on an arm64 machine, use `--platform linux-arm64`):

```sh
cd gui_forms_devkit
. .ci/local-build-env.sh
python3 -B harness/harness/resolve_gui_forms.py resolve
python3 -B harness/harness/resolve_gui_forms.py fetch --platform linux-x64
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_TOOLCHAIN_FILE=harness/harness/cmake/llvm22.cmake
cmake --build build
```

Windows (PowerShell):

```powershell
cd gui_forms_devkit
. .ci\local-build-env.ps1
python -B harness/harness/resolve_gui_forms.py resolve
python -B harness/harness/resolve_gui_forms.py fetch --platform windows-x64
```

On Windows the configure step takes GUI.Forms' Windows toolchain file with
its own C++ runtime. The devkit's CI prepares it (its `windows-own-runtime`
action); the harness has no local command for it yet.

`resolve` picks the GUI.Forms build and records it in
`.ci/gui_forms-resolved.json`. `fetch` downloads that build's SDK, checks its
SHA-256 and unpacks it at `.sdk/gui-forms-sdk`. The SDK is always unpacked at
that path, whatever the build, so the compiler cache keeps hitting when
GUI.Forms moves on.

#### The build guard

The devkit's CMake module (`harness/harness/cmake/DevkitBuildGuard.cmake`)
checks the build when configuring ends and again before the first compile.
If the build would compile GUI.Forms, or would not use the prebuilt SDK and
the restored compiler cache, it stops with:

```text
devkit build guard: likely misconfiguration preventing efficient incremental building.
```

Each finding below that line names what does not match and how to fix it.
The usual causes:

- the SDK is missing or is not the resolved build: run `resolve` and
  `fetch` again;
- the build environment is not loaded, so the compiler, the ccache settings
  or the locale differ from the ones the cache was made with: load
  `.ci/local-build-env.sh` (or `.ps1`) and configure again;
- ccache is not installed, or is not the compiler launcher;
- a GUI.Forms source tree is on the build's path, so its sources would be
  compiled.

The guard works the same when an IDE runs the build. A missing C++ runtime
on macOS or Linux is a warning, not a stop: the bootstrap builds one, once
per workspace. To build anyway, configure with
`-DGUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=ON` or set
`GUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=1` in the environment, and expect a much
longer build.

### 3. Run

Pocket Reference opens on the GUI.Forms reference.

macOS:

```sh
open build/pocket_reference/PocketReference.app
```

Linux:

```sh
build/pocket_reference/PocketReference
```

Windows:

```powershell
build\pocket_reference\PocketReference.exe
```

The same build holds the Gallery, Explore, Correspondence and the other
demonstrators under `build/programs/`.

### 4. Your own app

The devkit's app template (`harness/templates/app/`) is what every app
starts from. Its reference app, `harness/example_app/`, is the template
filled in: a greeter form, its test, the interaction test that holds hover
and drag to no layout work, and `reference/`, the retained custom control to
copy when you write your own. The template's `AGENTS.md` carries the rules
in its "Building on GUI.Forms" section, for you and for any coding agent you
work with.

The harness's `new_app` command, which turns the template into a new
repository, works on Malkuth's own repositories only. Until it can create an
app in yours, start from the reference app's sources, beside the devkit:

```sh
mkdir hello_forms && cp -R gui_forms_devkit/harness/example_app/src gui_forms_devkit/harness/example_app/tests gui_forms_devkit/harness/example_app/reference hello_forms/
```

Give it a `CMakeLists.txt` that builds through the devkit's module, so it
uses the same SDK, cache and build guard:

```cmake
cmake_minimum_required(VERSION 3.25)
project(HelloForms LANGUAGES CXX)

include("${GUI_FORMS_DEVKIT_WORKSPACE}/harness/harness/cmake/DevkitBuildGuard.cmake")
gui_forms_devkit_use_sdk()
gui_forms_devkit_cache_launcher()

set(CMAKE_NO_SYSTEM_FROM_IMPORTED ON)
find_package(GUIForms 1.0 CONFIG REQUIRED COMPONENTS Application Controls)
enable_testing()

add_executable(greeter_tests src/greeter.cpp tests/greeter_tests.cpp)
target_compile_features(greeter_tests PRIVATE cxx_std_20)
target_include_directories(greeter_tests PRIVATE src)
target_link_libraries(greeter_tests PRIVATE GUIForms::Controls)
add_test(NAME greeter_tests COMMAND greeter_tests)

add_executable(interaction_tests src/greeter.cpp reference/link_page.cpp reference/sample_document.cpp
    tests/interaction_tests.cpp)
target_compile_features(interaction_tests PRIVATE cxx_std_20)
target_include_directories(interaction_tests PRIVATE src reference)
target_link_libraries(interaction_tests PRIVATE GUIForms::Controls)
add_test(NAME interaction_tests COMMAND interaction_tests)

add_executable(hello_forms src/greeter.cpp src/main.cpp)
target_compile_features(hello_forms PRIVATE cxx_std_20)
target_include_directories(hello_forms PRIVATE src)
target_link_libraries(hello_forms PRIVATE GUIForms::Application)
if(APPLE)
    set_target_properties(hello_forms PROPERTIES MACOSX_BUNDLE TRUE)
    set(hello_forms_fonts "$<TARGET_BUNDLE_CONTENT_DIR:hello_forms>/Resources/fonts")
else()
    set(hello_forms_fonts "$<TARGET_FILE_DIR:hello_forms>/fonts")
endif()
add_custom_command(TARGET hello_forms POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory "${GUIForms_FONT_DIR}" "${hello_forms_fonts}")

gui_forms_devkit_build_guard()
```

Then, from the directory that holds `gui_forms_devkit/` and `hello_forms/`
(macOS and Linux):

```sh
. gui_forms_devkit/.ci/local-build-env.sh
cmake -S hello_forms -B hello_forms/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_TOOLCHAIN_FILE=gui_forms_devkit/harness/harness/cmake/llvm22.cmake -DGUI_FORMS_DEVKIT_WORKSPACE="$PWD/gui_forms_devkit"
cmake --build hello_forms/build
ctest --test-dir hello_forms/build
```

Run it with `open hello_forms/build/hello_forms.app` on macOS, or
`hello_forms/build/hello_forms` on Linux.

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
programs/            host mains, labs, the File Manager demoboard, packaging
```

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
