#pragma once

// The mockup factory (gui-forms-mockup; owner, 2026-11-24): a form
// document, its fixture data and a theme sheet shown at once, with no build.
// The window holds a menu, an optional catalogue of the mockups/ folder, the
// shown mockup and, when a file is refused, the refusal (file, line, column
// and message) in place of the mockup's update. The files are watched: a
// save reloads them, and the new tree replaces the old one in one step
// (gui_forms/forms/form_mockup). Retained: a reload builds the tree once,
// the watch only compares the files' times, and nothing is rebuilt per
// frame.
//
// Menus: File (Reload), Theme (the gui-forms or windows-professional base,
// with or without the mockup's sheet, or a familiar theme), Scheme (the
// system's, light or dark) and Mockups (the catalogue, opened by name).
//
// MCP: every GUI.Forms program serves MCP under --mcp; the factory adds
// mockup.list, mockup.open (by name), mockup.reload, mockup.check (the last
// load's diagnostics) and mockup.events (the declared handlers and what
// they recorded). A command a mockup binds is a model tool too
// (command.<name>), as every Command with an identity is.

#include "mockup_catalogue.hpp"

#include "gui_forms/controls/label.hpp"
#include "gui_forms/controls/list_box.hpp"
#include "gui_forms/controls/menu_strip.hpp"
#include "gui_forms/controls/panel.hpp"
#include "gui_forms/controls/text_box.hpp"
#include "gui_forms/forms/form_mockup/form_mockup.hpp"
#include "gui_forms/theme/familiar_themes/familiar_themes.hpp"
#include "gui_forms/theme/theme_compiler/theme_compiler.hpp"
#include "gui_forms/timer/timer/timer.hpp"
#include "gui_forms/window/window.hpp"

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace gui_forms::mockup {

inline constexpr std::string_view program_name = "GUI.Forms Mockup";
inline constexpr Size window_size{1100.0, 760.0};
// How often the watch compares the files' times.
inline constexpr std::chrono::milliseconds watch_interval{400};

// The theme a mockup is shown in: a base, with or without its sheet, or a
// familiar theme (which takes no sheet).
struct MockupTheme final {
    ThemeBase base{ThemeBase::windows_professional};
    bool use_sheet{true};
    std::optional<FamiliarTheme> familiar{};
};

// The colour scheme the window shows: the system's, or one of the two.
enum class MockupScheme : std::uint8_t {
    system,
    light,
    dark,
};

// What the window opens with.
struct MockupFactorySetup final {
    // Listed in the Mockups menu, and on the left when `show_catalogue`.
    std::vector<MockupFiles> catalogue{};
    bool show_catalogue{};
    // The position in `catalogue` shown first; none shows nothing until
    // one is chosen.
    std::optional<std::size_t> opened{};
    MockupTheme theme{};
    MockupScheme scheme{MockupScheme::system};
};

// The window's root. Make it with make_mockup_factory, put it in a window,
// then attach it to that window.
class MockupFactory final : public Panel {
public:
    explicit MockupFactory(StableId stable_id);
    ~MockupFactory() override;

    // Builds the children for `setup`. Once, before attach.
    void configure(MockupFactorySetup setup);
    // Starts the watch, registers the MCP tools, applies the scheme and
    // opens the first mockup. `window` holds this root and outlives it.
    void attach(Window& window);

    // Opens the catalogue's mockup at `index`; false for a position past
    // the end. A refusal is shown, not returned.
    bool open(std::size_t index);
    // Reads the shown mockup's files again and loads them.
    void reload();
    void choose_theme(const MockupTheme& theme);
    void choose_scheme(MockupScheme scheme);

    [[nodiscard]] FormMockup& mockup() noexcept { return *mockup_; }
    [[nodiscard]] const std::vector<MockupFiles>& catalogue() const& noexcept { return catalogue_; }
    const std::vector<MockupFiles>& catalogue() const&& = delete;
    // The shown mockup's position in the catalogue, if any.
    [[nodiscard]] std::optional<std::size_t> shown() const noexcept { return shown_; }
    // The refusal text shown (empty when nothing is refused).
    [[nodiscard]] const std::string& refusal() const& noexcept { return refusal_text_; }
    const std::string& refusal() const&& = delete;

    // Records the event in the status line and on standard output: the
    // mockup's event sink, `context` this root.
    static void event_recorded(void* context, const FormMockupEvent& event);

protected:
    void on_dispose() noexcept override;

private:
    void build_menu();
    void on_menu(const MenuStripInvocation& invocation);
    void on_catalogue_selection(const ListSelectionChange& change);
    void on_watch();
    void apply_theme();
    void show_refusal(std::string text);
    void update_status();
    void register_tools();

    // Declared before the mockup, which borrows the host and ends first.
    std::shared_ptr<MenuStrip> menu_{};
    std::shared_ptr<ListBox> list_{};
    std::shared_ptr<TextBox> refusal_box_{};
    std::shared_ptr<Label> status_{};
    std::shared_ptr<Panel> host_{};
    std::unique_ptr<FormMockup> mockup_{};
    std::unique_ptr<Timer> watch_{};
    Window* window_{};
    std::vector<MockupFiles> catalogue_{};
    std::optional<std::size_t> shown_{};
    std::optional<std::size_t> first_{};
    MockupStamps stamps_{};
    MockupTheme theme_{};
    MockupScheme scheme_{MockupScheme::system};
    std::string sheet_text_{};
    std::string refusal_text_{};
    std::string last_event_{};
    bool tools_registered_{};
};

// A factory root configured for `setup`.
[[nodiscard]] std::shared_ptr<MockupFactory> make_mockup_factory(MockupFactorySetup setup);

// The diagnostics of `check` as lines, `<file>:<line>:<column>: error
// E812 form_generation_refused: <detail>`, each cut to 4000 bytes (a
// multiline text box's line bound is 4096).
[[nodiscard]] std::string check_text(const FormDocumentCheck& check);

} // namespace gui_forms::mockup
