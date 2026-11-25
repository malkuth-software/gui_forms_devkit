# The devkit harness

The harness everything a consumer downloads builds with: our apps (Plan
Paint, PlaySuite, SwiftEdit, Pocket Library, Explore), the devkit's own
Pocket Reference and programs, and outside developers' apps. It pins
released, green GUI.Forms builds within a major whose SDK and caches are
published (`../devkit.toml`, `harness/resolve_gui_forms.py`), and it never
rebuilds GUI.Forms behind a consumer's back (the build guard,
`harness/build_guard.py`).

template_harness stays the library tier's harness (stx, STXlib, gui_forms,
gui_forms_tests), with exact pins and strict, selective tests. It is not
merged here and does not depend on the devkit.

## Where it came from

A plain copy, no history, of template_harness's consumer-facing parts. The
internal layout is template_harness's (`harness/`, `templates/`,
`example_app/`, `projects/`, `bootstrap.sh`), so a later resync is a
path-for-path copy.

- Source: template_harness `fold/cache-bootstrap` 56821b3 (the bootstrap's
  runtime restore and `build_environment.py`, on #24 11652ba) merged with
  `claude/retained-mode-rules` c4a7594 (the retained-mode check, the
  reference control, the pointer-motion test and the template's "Building
  on GUI.Forms" section, on main b713da0). Neither branch is on
  template_harness main yet; resync when they land.
- The one conflict copied, `example_app/gui_forms.lock`, takes
  retained-mode-rules' side: the v1.0.5 placeholder the reference control
  needs (run `fetch_sdk.py pin <tag>` once that release exists).

## What is kept

| Kept | Why |
|---|---|
| `bootstrap.sh`, `bootstrap.ps1`, `harness/bootstrap.py` | sets up a consumer's workspace: toolchain, runtime, SDK and caches |
| `harness/restore_local.py` | restores the published toolchain, runtime and caches on a developer machine |
| `harness/build_environment.py` | reproduces CI's build environment from the cache manifest, so restored caches hit |
| `harness/lock.py`, `.github/actions/harness-checkout/` | reads and bumps an app's `harness.lock`; the CI checkout of the pinned harness |
| `harness/project.py`, `projects/example_app.toml`, `projects/gui_forms.toml` | the project files bootstrap and restore read |
| `harness/linux_runtime_manifest.py`, `macos_runtime_manifest.py`, `windows_toolchain.py` and its JSON, `ci_reuse.py`, `harness/cmake/` | what restore and bootstrap import: runtime and toolchain records |
| `templates/`, `new_app.sh`, `new_app.ps1`, `harness/new_app.py` | the app template (with "Building on GUI.Forms" and the reference control) and the tool that renders it |
| `example_app/` (with `fetch_sdk.py`) | the reference app, built against the pinned SDK |
| `harness/check_retained_mode.py` | the retained-mode review every GUI.Forms app benefits from (consumer profile) |
| `templates/app/tests/interaction_tests.cpp`, `example_app/tests/` | the pointer-motion test: hover and drag cost no layout |
| `harness/check_house_style.py`, `check_lifetime_rules.py` | opt-in, the strict profile (`harness/run_checks.py --profile strict`); our apps switch it on, outsiders may leave it off. The retained check also reuses the house-style lexer |
| `harness/run_checks.py` | new: runs the checks of the consumer or strict profile |
| `docs/adopting.md`, `docs/new_app.md` | how an app adopts the harness and how new_app works |
| the tests of each kept tool (`harness/test_*.py`) | run with `python3 -B -m unittest discover -s harness/harness -p "test_*.py"` |

## What is dropped

| Dropped | Why |
|---|---|
| `check_std_rules`, `check_platform_headers`, code-integrity "no outside code" checks | they police our library's own boundaries, not an app's |
| own-runtime import evidence | a library-tier release proof; consumers link the SDK as published |
| `check_state_machines.py`, `clang_ast*`, `check_loop_branches.py`, `codemod_records.py`, `check_const_restrict.py`, `check_copies.py` | the state-machine gate and its AST tooling are the library tier's strict review |
| `checkpoint/`, `lockstep.py`, `change_selection.py`, `native_tests.py` | checkpoint and lockstep tooling for our repositories |
| `ci_build_steps.py`, `ci_cache.py`, `ci_promote.py`, `ci_tree_receipt.py`, `ci_sanitizer_seed.py`, `publish_cache.py`, `prune_cache_releases.py`, `bootstrap_proof.py`, `compiler_identity.py`, `install_linux_ci_packages.sh`, `audit_macos_minimum.py`, `build_macos_runtimes.py`, `cache_manifest.py` | the library tier's CI pipeline: producing and promoting caches and runtimes, which consumers only restore |
| `claude/` plugins, `fransushi`, `.github/workflows/harness-*.yml` | our agent tooling and the library tier's reusable workflows |
| `projects/{books,games,swiftedit,plan-paint,file_manager}.toml` | each app's project file moves into its own repository |
| `docs/contract.md`, `docs/workflow.md`, `docs/ic_declarations.md`, `CHANGELOG.md` | template_harness's own contract and history |

## Open

- `templates/app/.github/workflows/ci.yml` and `new_app.py` still name
  template_harness as `{{harness_repository}}` and call its reusable
  workflows; they move to this harness once the devkit is published.
