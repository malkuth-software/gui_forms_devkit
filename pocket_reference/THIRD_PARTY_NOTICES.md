# Third-party notices

Pocket Reference's own source is MIT (`LICENSE`). It bundles no third-party
source, font or image of its own: its icons are drawn from the SVGs in
`tools/make_icons.py`, and its reference text is generated from GUI.Forms'
documentation by `tools/make_reference_text.py`.

A built package carries content that keeps its own licence:

| Content | Comes from | Licence and notice |
|---|---|---|
| GUI.Forms and its fonts, icons and third-party parts | the GUI.Forms SDK the build links | the SDK's `share/licenses/GUIForms` (its `LICENSE`, `THIRD_PARTY_NOTICES.md` and each font's licence), copied into the package's `licenses/` by `tools/package.py` |
| The LLVM C++ runtime (macOS) | the harness's runtime | Apache-2.0 WITH LLVM-exception, copied into `licenses/LLVM` |
| STXlib | the SDK's `stx/share/licenses/stxlib` | STXlib's licence, as the SDK installs it |
