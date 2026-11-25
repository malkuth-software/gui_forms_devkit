// The mockup factory on this host (owner, 2026-11-24;
// views/mockup_factory/mockup_factory.hpp): a form document, its fixture and
// a theme sheet shown at once and reloaded on save, with no build.
#include "gui_forms/platform/linux_host.hpp"
#include "mockup_factory.hpp"
#include "mockup_program.hpp"
#include "program_options.hpp"

#include <clocale>
#include <memory>
#include <optional>
#include <string>
#include <utility>

int main(int argc, char** argv) {
    // std-rules: allow(locale-change) the program, not the library, chooses its locale: the environment's character type, for X input methods and compose
    std::setlocale(LC_CTYPE, "");
    const std::optional<gui_forms::mockup::MockupProgramOptions> program =
        gui_forms::mockup::parse_mockup_options(argc, argv);
    if (!program) return 2;
    const std::optional<gui_forms::mockup::MockupFactorySetup> setup = gui_forms::mockup::mockup_setup(*program);
    if (!setup) return 2;
    if (!(*program).screenshots.empty()) return gui_forms::mockup::run_mockup_screenshots(*program, *setup);
    gui_forms::host::LinuxHostOptions options;
    options.title = std::string(gui_forms::mockup::program_name);
    options.initial_size = (*program).size.value_or(gui_forms::mockup::window_size);
    gui_forms::demo::apply_program_options((*program).program, options);
    const std::shared_ptr<gui_forms::mockup::MockupFactory> factory = gui_forms::mockup::make_mockup_factory(*setup);
    std::unique_ptr<gui_forms::Window> window = gui_forms::mockup::make_mockup_window(factory, *program);
    const std::shared_ptr<gui_forms::demo::SmokeTest> smoke =
        gui_forms::demo::arm_smoke_test((*program).program, options, *window);
    return gui_forms::demo::smoke_test_result(
        smoke, gui_forms::host::run_linux(std::move(window), std::move(options)));
}
