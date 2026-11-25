# {{title}}

A GUI.Forms application. It builds against the prebuilt GUI.Forms SDK
through gui_forms_devkit's harness, at the devkit commit `harness.lock`
pins, and compiles none of GUI.Forms itself. It was made by the devkit's
`new-app` command.

## Build and test

With LLVM 22.1.8 (clang), CMake, Ninja and ccache on PATH:

```sh
python3 build.py --jobs 4        # resolve, fetch the SDK, configure, build, test
python3 build.py check           # house style, lifetime rules, retained mode
python3 -B -m unittest discover -s . -p "test_*.py"
```

The first build checks the devkit out at `.devkit/` (at the `harness.lock`
commit), resolves `devkit.toml`'s GUI.Forms pin to the newest green build
within its major and at least its floor, and unpacks that SDK at
`.sdk/gui-forms-sdk`. Later builds stay on that GUI.Forms until
`python3 build.py --resolve` moves them; `--floor` builds against the floor
itself. On macOS and Linux the first build also builds the C++ runtime
(`.build/toolchain/`, several minutes, once); on Windows it restores
GUI.Forms' published toolchain and own runtime.

The devkit's build guard (`DevkitBuildGuard.cmake`, included by
`CMakeLists.txt`) stops a configure or build that would compile GUI.Forms
from source or miss the SDK, and says why. An IDE that only presses Build
gets the same guard; configure it once with `python3 build.py
--configure-only` first.

| Path | What |
|---|---|
| `src/`, `tests/` | the app's form, its entry point, the form's test and the interaction checks |
| `reference/` | the reference custom control to copy (GUI.Forms `examples/link_page`) |
| `CMakeLists.txt`, `build.py` | the build against the prebuilt SDK, with the devkit's build guard |
| `devkit.toml` | the GUI.Forms pin (major and floor) and the checks' profile (`consumer`; `strict` is opt-in) |
| `harness.toml`, `harness.lock` | the project file the devkit's tools read, and the devkit commit |

## License

Chosen when the app was made (`new-app --license`). GUI.Forms and its
components are permissively licensed and allow closed-source use; see
`THIRD_PARTY_NOTICES.md`.
