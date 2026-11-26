# Pocket Reference

Pocket Reference is GUI.Forms' API reference as a desktop program. It reads
one file, `reference.pack`, made at build time from GUI.Forms' generated
docs: a page for every control and type, with a contents tree, links, search,
find in page, back and forward, and page text you can select and copy (a
table copies as tab-separated rows). Each control's page shows that control as
GUI.Forms draws it, rendered from its stock specimen when the pack is built.

It is built with GUI.Forms, so it is also a small example of a GUI.Forms
program: its window and panes are forms (`forms/`), its look is a theme
package (`themes/pocket_reference`), and the page view is a control of its
own (`src/reference_page.cpp`).

![Pocket Reference showing the Button page](docs/capture.png)

## Download

Builds for macOS, Windows and Linux are attached to each
[release](https://github.com/malkuth-software/pocket_reference/releases).

## Building

Pocket Reference needs GUI.Forms 0.6 and LLVM 22. Either point CMake at an
installed GUI.Forms SDK:

```sh
cmake -S . -B build -G Ninja -DCMAKE_PREFIX_PATH=<sdk> \
  -DCMAKE_TOOLCHAIN_FILE=<sdk>/lib/cmake/GUIForms/llvm22.cmake \
  -DPOCKET_REFERENCE_DOCS=<GUI.Forms checkout>
cmake --build build --target pocket-reference
```

or build GUI.Forms from the pinned source, which is also where the docs come
from:

```sh
python3 scripts/fetch-gui-forms.py
cmake -S . -B build -G Ninja -DCMAKE_TOOLCHAIN_FILE=gui_forms/cmake/llvm22.cmake \
  -DPOCKET_REFERENCE_TOOLKIT_SOURCE_DIR=$PWD/gui_forms
cmake --build build --target pocket-reference
```

The pages name the GUI.Forms build the program links. With an SDK, the
reference docs come from the SDK itself when it ships them
(`share/GUIForms/docs/api` and `share/GUIForms/ledgers/controls.json`), and
otherwise from `POCKET_REFERENCE_DOCS`, a checkout of the same GUI.Forms
build: its version must match the SDK's, and `-DPOCKET_REFERENCE_COMMIT=<sha>`
makes the commit checked too. Docs of another build are refused.

The pin is in `third_party/gui-forms.lock.json`. `tools/package.py` makes the
download for the host it runs on.

## Licence

MIT; see `LICENSE` (owner's decision, 2026-11-24: Pocket Reference is the
all-in-one demonstrator and is MIT like GUI.Forms). The pack coder in
`pack_coder/` is copied from Pocket Library and is MIT in this copy. The
fonts, icons and runtime libraries a build ships come from the GUI.Forms SDK
and keep their own licences: `tools/package.py` copies the SDK's notices
(`share/licenses/GUIForms`) and, on macOS, the LLVM runtime's into each
package's `licenses/`. See `THIRD_PARTY_NOTICES.md`.
