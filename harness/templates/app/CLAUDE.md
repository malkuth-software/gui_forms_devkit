# {{title}}

@AGENTS.md

## House style

The canonical house style is `HOUSE_STYLE.md` in the notes clone beside this
checkout: `../notes/HOUSE_STYLE.md` (the `main` branch of
`{{notes_repository}}`). Read it before writing code. SushiStyle checks the
mechanical part of it after each C/C++ edit, from the harness's single rule
pack (`../template_harness/claude/rules/house.json`), each rule naming its
HOUSE_STYLE section. Where a rule and HOUSE_STYLE.md disagree, HOUSE_STYLE.md
wins: report the rule.

## Building on GUI.Forms

Follow house style, and remember that GUI.Forms and the programs built on it
are retained mode. Keep immediate-mode paradigms to the situations where
their use is obvious and sensible, such as games that must update
constantly. Most programs should never use immediate-mode principles, and
should follow the behaviour of the reference application code in
`reference/` (`LinkPage`, with its checks in `tests/interaction_tests.cpp`).

- **Search first.** Before writing a control, look for one that already does
  the job: the GUI.Forms guide's control pages and API reference, and
  `include/gui_forms/controls/` in the SDK.
- **The guide:** GUI.Forms `docs/user/custom-controls.md` ("Custom
  controls").

## This app's notes

Planning, decisions and interviews live on the `{{app}}` branch of
`{{notes_repository}}`, checked out at `../notes-{{app}}/`. Coordination
(tracks, seats, desks) lives in `../projects/` (`{{projects_repository}}`).
