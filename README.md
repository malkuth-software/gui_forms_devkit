# gui_forms_devkit

The GUI.Forms companion ecosystem, built in lockstep with GUI.Forms:
Pocket Reference, the demonstrator views and programs, and the devkit
harness that consumer apps build with. MIT; see `LICENSE` and
`THIRD_PARTY_NOTICES.md`.

## Layout

```text
devkit.toml          the GUI.Forms pin: major 1, floor 1.0.3, channel main
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

Kept in gui_forms, against the first cut of the design, because the
installed `GalleryModel` component or its `Lab` and `DemoControls`
dependencies build them (CMakeLists.txt, `gui_forms_gallery_model`):
`demo/gallery.cpp`, `gallery.hpp`, `gallery_instrument.*`, `gallery_parts.*`,
`gallery_assets.hpp`, `gallery.form`, `gallery_form_pages.form`,
`demo/composites/`, `demo/themes/{gallery,industrial,gost_paints}`,
`demo/lab_controls/` and `lab/`. `windows/menu_probe_main.cpp` stays too: it
is gui_forms_tests' menu probe, not a program.

## Checks

```sh
python3 -B -m unittest discover -s harness/harness -p "test_*.py"
python3 -B harness/harness/run_checks.py --profile strict views programs
```
