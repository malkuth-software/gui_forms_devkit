#pragma once

// gui-forms-mockup's command line and its windowless screenshots, shared by
// every host's main (programs/host/*/mockup_main.*). Header-only, as
// program_options.hpp is.
//
//   gui-forms-mockup [<file.form>] [--fixture <file>] [--sheet <file.theme.css>]
//                    [--mockups <dir>] [--interface=<name>] [--screenshots <dir>]
//                    [--base gui-forms|windows-professional] [--familiar-theme <id>]
//                    [--no-sheet] [--scheme light|dark] [--size <W>x<H>] [--smoke-test]
//                    [--mcp] [--mcp-script <file>] [--theme ...]
//
// - A form named on the command line is opened with its fixture and sheet
//   (the given ones, else the siblings that exist) and listed alone.
// - Otherwise the catalogue is every .form under --mockups (else
//   $GUI_FORMS_MOCKUPS, else ./mockups, else the devkit's own mockups/),
//   listed on the left; --interface=<name> opens that one.
// - --screenshots <dir> captures each listed mockup (only the one named by
//   a form or --interface, else the whole catalogue) to <dir>/<name>.png,
//   windowless, and exits: 0 when every one was written, 1 otherwise (a
//   refused mockup's diagnostics go to standard error).
// - The theme: the --base (windows-professional unless given) with the
//   mockup's sheet unless --no-sheet, or a --familiar-theme. --scheme
//   forces light or dark; the system's otherwise.
// - The MCP arguments and the user-theme options (--theme, --export-themes)
//   are the library's (program_options.hpp).

#include "mockup_catalogue.hpp"
#include "mockup_factory.hpp"

#include "gallery_headless_capture.hpp"
#include "program_options.hpp"

#include "gui_forms/controls/panel.hpp"
#include "gui_forms/forms/form_documents/form_documents.hpp"
#include "gui_forms/forms/form_mockup/form_mockup.hpp"
#include "gui_forms/window/presentation/presentation_types.hpp"
#include "gui_forms/window/window.hpp"

#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

#ifndef GUI_FORMS_DEVKIT_MOCKUPS_DIR
#define GUI_FORMS_DEVKIT_MOCKUPS_DIR ""
#endif

namespace gui_forms::mockup {

struct MockupProgramOptions final {
    std::filesystem::path form{};
    std::filesystem::path fixture{};
    std::filesystem::path sheet{};
    std::filesystem::path mockups{};
    std::filesystem::path screenshots{};
    std::string interface_name{};
    MockupTheme theme{};
    MockupScheme scheme{MockupScheme::system};
    std::optional<Size> size{};
    // The demonstration programs' options the hosts read (--smoke-test,
    // --size as the window's initial size).
    demo::ProgramOptions program{};
};

inline void print_mockup_usage() {
    std::fprintf(stderr,
                 "usage: gui-forms-mockup [<file.form>] [--fixture <file>] [--sheet <file.theme.css>]\n"
                 "       [--mockups <dir>] [--interface=<name>] [--screenshots <dir>]\n"
                 "       [--base gui-forms|windows-professional] [--familiar-theme <id>] [--no-sheet]\n"
                 "       [--scheme light|dark] [--size <W>x<H>] [--smoke-test] [--mcp] [--mcp-script <file>]\n");
}

// The options of `argv`, or none (usage printed) for an unknown option, a
// missing or malformed value, or a second form.
[[nodiscard]] inline std::optional<MockupProgramOptions> parse_mockup_options(int argc, char** argv) {
    MockupProgramOptions options{};
    std::vector<std::string_view> given{};
    for (int index = 1; index < argc; ++index) {
        if (argv[index] == nullptr) {
            print_mockup_usage();
            return std::nullopt;
        }
        given.push_back(std::string_view(argv[index]));
    }
    const std::vector<std::string_view> arguments = program_arguments(given);
    constexpr std::string_view interface_prefix = "--interface=";
    for (std::size_t index = 0U; index < arguments.size(); ++index) {
        const std::string_view argument = arguments[index];
        if (argument == "--mcp" || argument == "--model-directed" || argument == "--mcp-shared") continue;
        if (argument == "--smoke-test") {
            options.program.smoke_test = true;
            continue;
        }
        if (argument == "--no-sheet") {
            options.theme.use_sheet = false;
            continue;
        }
        if (argument.starts_with(interface_prefix)) {
            options.interface_name = std::string(argument.substr(interface_prefix.size()));
            if (options.interface_name.empty()) {
                print_mockup_usage();
                return std::nullopt;
            }
            continue;
        }
        if (!argument.starts_with("--")) {
            if (!options.form.empty()) {
                print_mockup_usage();
                return std::nullopt;
            }
            options.form = std::filesystem::path(std::string(argument));
            continue;
        }
        if (index + 1U >= arguments.size()) {
            print_mockup_usage();
            return std::nullopt;
        }
        ++index;
        const std::string_view value = arguments[index];
        if (argument == "--mcp-script") continue;
        if (argument == "--interface") {
            options.interface_name = std::string(value);
        } else if (argument == "--fixture") {
            options.fixture = std::filesystem::path(std::string(value));
        } else if (argument == "--sheet") {
            options.sheet = std::filesystem::path(std::string(value));
        } else if (argument == "--mockups") {
            options.mockups = std::filesystem::path(std::string(value));
        } else if (argument == "--screenshots") {
            options.screenshots = std::filesystem::path(std::string(value));
        } else if (argument == "--base" && (value == "gui-forms" || value == "windows-professional")) {
            options.theme.base = value == "gui-forms" ? ThemeBase::gui_forms : ThemeBase::windows_professional;
        } else if (argument == "--familiar-theme" && familiar_theme_named(value).present()) {
            options.theme.familiar = *familiar_theme_named(value).value();
        } else if (argument == "--scheme" && (value == "light" || value == "dark")) {
            options.scheme = value == "dark" ? MockupScheme::dark : MockupScheme::light;
            options.program.scheme = std::string(value);
        } else if (argument == "--size") {
            Size size{};
            if (!demo::detail::parse_size(value, size)) {
                print_mockup_usage();
                return std::nullopt;
            }
            options.size = size;
            options.program.capture_size = size;
        } else {
            print_mockup_usage();
            return std::nullopt;
        }
    }
    return options;
}

// The catalogue directory: --mockups, else $GUI_FORMS_MOCKUPS, else
// ./mockups, else the devkit's own.
[[nodiscard]] inline std::filesystem::path mockups_directory(const MockupProgramOptions& options) {
    if (!options.mockups.empty()) return options.mockups;
    // std-rules: allow(getenv) one read at start-up, on the main thread, before any thread exists
    const char* const environment = std::getenv("GUI_FORMS_MOCKUPS");
    if (environment != nullptr && *environment != '\0') return std::filesystem::path(environment);
    std::error_code error{};
    const std::filesystem::path local("mockups");
    if (std::filesystem::is_directory(local, error) && !error) return local;
    return std::filesystem::path(GUI_FORMS_DEVKIT_MOCKUPS_DIR);
}

// What the window lists and opens, or none (the reason printed) when the
// form, the interface or every mockup is missing.
[[nodiscard]] inline std::optional<MockupFactorySetup> mockup_setup(const MockupProgramOptions& options) {
    MockupFactorySetup setup{};
    setup.theme = options.theme;
    setup.scheme = options.scheme;
    if (!options.form.empty()) {
        std::filesystem::path stem = options.form.filename();
        stem.replace_extension();
        setup.catalogue.push_back(mockup_files(stem.generic_string(), options.form, options.fixture, options.sheet));
        setup.opened = 0U;
        return setup;
    }
    const std::filesystem::path directory = mockups_directory(options);
    setup.catalogue = find_mockups(directory);
    setup.show_catalogue = true;
    if (setup.catalogue.empty()) {
        std::fprintf(stderr, "gui-forms-mockup: no .form under %s\n", directory.generic_string().c_str());
        return std::nullopt;
    }
    if (!options.interface_name.empty()) {
        setup.opened = find_mockup(setup.catalogue, options.interface_name);
        if (!setup.opened) {
            std::fprintf(stderr, "gui-forms-mockup: no mockup named %s under %s\n", options.interface_name.c_str(),
                         directory.generic_string().c_str());
            return std::nullopt;
        }
    } else {
        setup.opened = 0U;
    }
    return setup;
}

// The factory's window over `factory`, attached.
[[nodiscard]] inline std::unique_ptr<Window> make_mockup_window(const std::shared_ptr<MockupFactory>& factory,
                                                                const MockupProgramOptions& options) {
    const Size size = options.size.value_or(window_size);
    std::unique_ptr<Window> window = std::make_unique<Window>(factory, size);
    (*factory).attach(*window);
    return window;
}

// Captures `files` into `directory` on a windowless window of its own;
// whether the PNG was written.
[[nodiscard]] inline bool capture_mockup(const MockupFiles& files, const MockupProgramOptions& options,
                                         const std::filesystem::path& directory) {
    const std::optional<std::string> form = read_mockup_file(files.form);
    const std::optional<std::string> fixture =
        files.fixture.empty() ? std::optional<std::string>(std::string()) : read_mockup_file(files.fixture);
    const std::optional<std::string> sheet =
        files.sheet.empty() ? std::optional<std::string>(std::string()) : read_mockup_file(files.sheet);
    if (!form || !fixture || !sheet) {
        std::fprintf(stderr, "%s: its files cannot be read\n", files.name.c_str());
        return false;
    }
    const std::shared_ptr<Panel> host = make_control<Panel>(StableId("mockup.host"));
    std::unique_ptr<Window> window = std::make_unique<Window>(host, options.size.value_or(window_size));
    // Declared after the window and the host it borrows, so it ends first.
    FormMockup mockup(*host);
    const std::string form_name = files.form.generic_string();
    const std::string fixture_name = files.fixture.generic_string();
    const std::string sheet_name = files.sheet.generic_string();
    FormMockupText document{};
    document.file = stxlib::View<char>(form_name.data(), form_name.size());
    document.text = stxlib::View<char>((*form).data(), (*form).size());
    FormMockupText data{};
    data.file = stxlib::View<char>(fixture_name.data(), fixture_name.size());
    data.text = stxlib::View<char>((*fixture).data(), (*fixture).size());
    if (mockup.load(FormDocumentSchema::registry(), document, data) == FormMockupLoadOutcome::refused) {
        const std::string text = check_text(mockup.check());
        std::fprintf(stderr, "%s\n", text.c_str());
        return false;
    }
    if (options.theme.familiar) {
        (*host).set_theme_override(familiar_theme(*options.theme.familiar));
    } else {
        FormMockupText theme_sheet{};
        if (options.theme.use_sheet) {
            theme_sheet.file = stxlib::View<char>(sheet_name.data(), sheet_name.size());
            theme_sheet.text = stxlib::View<char>((*sheet).data(), (*sheet).size());
        }
        const ThemeCompileResult compiled = mockup.set_theme(options.theme.base, theme_sheet);
        if (!compiled.succeeded()) {
            for (const ThemeCompileDiagnostic& finding : compiled.diagnostics()) {
                const std::string line = format_theme_diagnostic(finding);
                std::fprintf(stderr, "%s\n", line.c_str());
            }
            return false;
        }
    }
    if (options.scheme != MockupScheme::system) {
        PresentationOverrides overrides{};
        overrides.colour_scheme.set(options.scheme == MockupScheme::dark ? ColourScheme::dark : ColourScheme::light);
        (*window).set_presentation_overrides(overrides);
    }
    demo::ProgramOptions capture = options.program;
    capture.capture_path = (directory / (screenshot_file_name(files.name) + ".png")).generic_string();
    // The form's own client size unless --size names one.
    const Size client = mockup.client_size();
    if (!options.size && client.width > 0.0 && client.height > 0.0) capture.capture_size = client;
    if (!capture.capture_size) capture.capture_size = window_size;
    const int result = gallery::run_headless_gallery_capture(capture, *window);
    return result == 0;
}

// --screenshots: every listed mockup, or the one opened; the exit code.
[[nodiscard]] inline int run_mockup_screenshots(const MockupProgramOptions& options, const MockupFactorySetup& setup) {
    std::error_code error{};
    std::filesystem::create_directories(options.screenshots, error);
    if (error) {
        std::fprintf(stderr, "gui-forms-mockup: cannot make %s\n", options.screenshots.generic_string().c_str());
        return 1;
    }
    const bool one = !options.form.empty() || !options.interface_name.empty();
    bool written = true;
    for (std::size_t index = 0U; index < setup.catalogue.size(); ++index) {
        if (one && (!setup.opened || *setup.opened != index)) continue;
        if (!capture_mockup(setup.catalogue[index], options, options.screenshots)) written = false;
    }
    return written ? 0 : 1;
}

} // namespace gui_forms::mockup
