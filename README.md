# gui_forms_devkit

The GUI.Forms companion ecosystem, built in lockstep with GUI.Forms:
Pocket Reference, the demonstrator views and programs, and the devkit
harness that consumer apps build with. MIT; see `LICENSE` and
`THIRD_PARTY_NOTICES.md`.

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
cmake -S . -B build -G Ninja && cmake --build build
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
