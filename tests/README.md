# Program tests

The suites that moved here from
[gui_forms_tests](https://github.com/malkuth-software/gui_forms_tests) with
the programs (DEVKIT_DESIGN.md, step 7). They test the labs, the
demonstrators, Correspondence, the File Manager demoboard and the shared
program command line. `programs_tests.cmake` configures them; the top-level
`CMakeLists.txt` includes it after the program targets
(`GUI_FORMS_DEVKIT_BUILD_TESTS`, on by default), and `build.yml` runs them
with ctest on every platform.

The Gallery model's own tests (its pages, interaction, display traces and
the UI Automation, MSAA, macOS AX and AT-SPI clients) stay in gui_forms_tests,
since gui_forms still builds and installs the model.

| Suite | Source | Links |
|---|---|---|
| `gui_forms_program_options_tests` | `program_options_tests.cpp` | `GUIForms::Controls` |
| `gui_forms_<lab>_tests` (six labs) | `<lab>_tests.cpp` | `gui_forms_devkit_lab_<lab>` |
| `gui_forms_process_control_tests` | `process_control_tests.cpp` | `gui_forms_devkit_view_process_control` |
| `gui_forms_correspondence_tests`, `_interaction_tests` | `correspondence_*tests.cpp` | `gui_forms_devkit_view_correspondence` |
| `gui_forms_file_manager_demoboard_tests`, `_public_policy` | `file_manager_demoboard/` | `gui_forms_devkit_file_manager_demoboard` |
| `gui_forms_<program>_font_policy` | `cmake/check_gallery_fonts.cmake` | the program bundles (macOS) |
| `gui_forms_gallery_headless_capture_tests` | `gallery_headless_capture_tests.cpp` | `GUIForms::GalleryModel`, `GUIForms::Application` |

Suites that read GUI.Forms' private sources (the layered-material raster,
compositor and custom-chrome lab suites, the macOS live-resize probe) and the
SDK's installed-consumer proof stay in gui_forms_tests: the devkit is a
consumer and uses the public API only.
