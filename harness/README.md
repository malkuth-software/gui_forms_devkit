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
- The one conflict copied, `example_app/gui_forms.lock`, took
  retained-mode-rules' side; the example and the app template have since
  moved to the prebuilt SDK (`devkit.toml`, `build.py`), so the source-SDK
  fetch (`fetch_sdk.py`, `ci_build.py`, `gui_forms.lock`) is gone.

## What is kept

| Kept | Why |
|---|---|
| `bootstrap.sh`, `bootstrap.ps1`, `harness/bootstrap.py` | sets up a consumer's workspace: toolchain, runtime, SDK and caches; the in-house notes and projects only with `--in-house`. `bootstrap.sh new-app` and `bootstrap.sh own-runtime` run the two local commands below |
| `harness/new_local_app.py`, `templates/consumer/` | new: `new-app NAME [DIR]`, an outsider's app from `templates/app/` without its in-house parts: `devkit.toml` (major and floor), the consumer check profile, the reference control, the interaction tests and the build guard; git init and a first commit, never a push |
| `harness/devkit_build.py` | new: resolve, fetch, runtime (the own runtime on Windows), build environment, configure with the build guard, build and test against the prebuilt SDK; an app's `build.py` runs it, and so does the devkit's bootstrap smoke build |
| `harness/own_runtime_local.py` | new: the Windows own runtime on a developer machine, as CI's `windows-own-runtime` action makes it (restored from the runtime asset, else built), printing its settings and `CMAKE_TOOLCHAIN_FILE` |
| `harness/restore_local.py` | restores the published toolchain, runtime and caches on a developer machine |
| `harness/build_environment.py` | reproduces CI's build environment from the cache manifest, so restored caches hit |
| `harness/lock.py`, `.github/actions/harness-checkout/` | reads and bumps an app's `harness.lock`; the CI checkout of the pinned harness |
| `harness/project.py`, `projects/example_app.toml`, `projects/gui_forms.toml` | the project files bootstrap and restore read |
| `harness/linux_runtime_manifest.py`, `macos_runtime_manifest.py`, `windows_toolchain.py` and its JSON, `ci_reuse.py`, `harness/cmake/` | what restore and bootstrap import: runtime and toolchain records |
| `templates/`, `new_app.sh`, `new_app.ps1`, `harness/new_app.py` | the app template (with "Building on GUI.Forms" and the reference control) and the in-house tool that renders it and pushes the repositories |
| `example_app/` (with `build.py`, `devkit.toml`, `harness.toml`) | the reference app, built against the prebuilt SDK |
| `harness/check_retained_mode.py` | the retained-mode review every GUI.Forms app benefits from (consumer profile) |
| `templates/app/tests/interaction_tests.cpp`, `example_app/tests/` | the pointer-motion test: hover and drag cost no layout |
| `harness/check_house_style.py`, `check_lifetime_rules.py` | opt-in, the strict profile (`harness/run_checks.py --profile strict`); our apps switch it on, outsiders may leave it off. The retained check also reuses the house-style lexer |
| `harness/resolve_gui_forms.py` | new: resolves `devkit.toml`'s pin to a published build, restores its `gui-forms-runtime-<platform>` asset when it has one, and unpacks its SDK at `.sdk/gui-forms-sdk` |
| `harness/build_guard.py`, `harness/cmake/DevkitBuildGuard.cmake` | new: stops a build that would not use the prebuilt SDK and restored cache ("likely misconfiguration preventing efficient incremental building"); a runtime to build is a warning only |
| `harness/build_macos_runtimes.py`, `build_linux_runtimes.py` | the fallback when no published runtime asset verifies: `restore_local.py runtime` builds one from source |
| `harness/devkit_cache.py` | new: the devkit's own compiler cache (pack, restore from the newest `gf-` pre-release) and the cache proof's computed expectation and verdicts (`.github/workflows/cache-proof.yml`) |
| `harness/publish_cache.py`, `prune_cache_releases.py`, `projects/gui_forms_devkit.toml` | the devkit publishes its own cache and packages per lockstep run (`--tag gf-<GUI.Forms sha>`, `--no-toolchain`, `--asset`) and keeps the five newest (`--tag-prefix gf-`); a consumer's CI can publish its cache the same way |
| `harness/prepare_build.py` | new: runs a project's `[bootstrap.<platform>]` prepare commands in CI and puts their settings in the build environment, as `bootstrap.py` does on a machine (GUI.Forms on Windows: the own runtime, reused from the restored runtime asset or built) |
| `harness/compiler_identity.py` | a consumer's own CI keys its caches on the compiler's identity, as ours does |
| `harness/ci_cache.py` | a consumer's own CI saves and restores its ccache the same way |
| `harness/install_linux_ci_packages.sh` | the Linux packages a consumer's CI runner needs to build against the SDK |
| `harness/audit_macos_minimum.py` | checks a consumer's macOS binaries against the deployment minimum before they ship |
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
| `ci_build_steps.py`, `ci_promote.py`, `ci_tree_receipt.py`, `ci_sanitizer_seed.py`, `bootstrap_proof.py`, `cache_manifest.py` | the library tier's CI pipeline: validating, promoting and recording the published caches and runtime assets (`devkit_cache.py pack` writes the devkit's own manifest) |
| `claude/` plugins, `fransushi`, `.github/workflows/harness-*.yml` | our agent tooling and the library tier's reusable workflows |
| `projects/{books,games,swiftedit,plan-paint,file_manager}.toml` | each app's project file moves into its own repository |
| `docs/contract.md`, `docs/workflow.md`, `docs/ic_declarations.md`, `CHANGELOG.md` | template_harness's own contract and history |

## Open

- `templates/app/.github/workflows/ci.yml` and `new_app.py` still name
  template_harness as `{{harness_repository}}` and call its reusable
  workflows; they move to this harness once the devkit is published.
