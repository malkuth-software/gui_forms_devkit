# {{title}}: instructions for agents

{{title}} is a GUI.Forms application built against the prebuilt GUI.Forms
SDK with gui_forms_devkit (the commit `harness.lock` pins, checked out at
`.devkit/`).

## House style

Read `.devkit/HOUSE_STYLE.md` in full before writing code: it is the house
style GUI.Forms itself is written in, sections ordered by importance.
`python3 build.py check` checks the mechanical part; where a check and
HOUSE_STYLE.md disagree, HOUSE_STYLE.md wins.

## Building on GUI.Forms

Follow house style. GUI.Forms and the programs built on it are retained mode. Keep
immediate-mode paradigms to the situations where their use is obvious and
sensible, such as games that must update constantly. Most programs should
follow the behaviour of the reference application code in `reference/`
(`LinkPage`, with its checks in `tests/interaction_tests.cpp`).

- **Search first.** Before writing a control, look for one that already does
  the job: the GUI.Forms guide's control pages and API reference, and
  `include/gui_forms/controls/` in the SDK (`.sdk/gui-forms-sdk`).
- **The guide:** GUI.Forms `docs/user/custom-controls.md` ("Custom
  controls").
- **Memory errors and undefined behaviour are defects,** tests included.

## Commands

| What | Command |
|---|---|
| Build and test | `python3 build.py --jobs 4` |
| Configure only (IDEs, compile commands) | `python3 build.py --configure-only` |
| Move to the newest green GUI.Forms in the pin | `python3 build.py --resolve` |
| Static checks (devkit.toml `[checks]` profile) | `python3 build.py check` |
| Python tests | `python3 -B -m unittest discover -s . -p "test_*.py"` |

Never pass `--allow-full-build` to get past the build guard: fix what it
names instead.
