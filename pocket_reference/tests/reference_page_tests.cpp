// SPDX-License-Identifier: MIT
// ReferencePage's layout and selection (owner's report on the 1.0.6 Methods
// table, 2026-11-25, defects/2026-11-25-methods-table.png): a long member
// name stays inside its table cell and the description wraps inside the
// page's column; inline code and prose share one baseline, and a table
// row's cells align on their first baselines; selecting and copying yields
// the page's text, a table as tab-separated rows.
//
// The page is laid out in a window with no host, measured by a fixture
// whose two faces have different ascents, so a baseline taken from either
// face alone would not match the other's.
#include "reference_document.hpp"
#include "reference_page.hpp"

#include <gui_forms/events/input_events/input_events.hpp>
#include <gui_forms/typography/types/typography_types.hpp>
#include <gui_forms/window/window.hpp>

#include <cmath>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

namespace gf = gui_forms;
using pocket_reference::Block;
using pocket_reference::BlockKind;
using pocket_reference::Page;
using pocket_reference::ReferencePage;
using pocket_reference::Run;

void require(bool condition, const char *message) {
    if (!condition)
        throw std::runtime_error(message);
}

bool near(double left, double right, double tolerance = 0.001) { return std::abs(left - right) <= tolerance; }

// Carlito-like prose (narrow, tall ascent) and Cousine-like code (wide,
// shorter ascent), at fixed advances per character.
class TwoFaceText final : public gf::TextMetricsProvider {
  public:
    gf::ResolvedTextLayout resolve_text_layout_utf8(std::string_view text, gf::FontSpec font) override {
        const bool code = font.role == gf::FontRole::monospace;
        gf::ResolvedTextLayout result;
        result.effective_font = font;
        result.primary_family = code ? "Cousine" : "Carlito";
        std::size_t characters = 0U;
        for (const char byte : text) {
            if ((static_cast<unsigned char>(byte) & 0xC0U) != 0x80U)
                ++characters;
        }
        const double advance = font.size * (code ? 0.6 : 0.5);
        result.ascent = font.size * (code ? 0.78 : 0.95);
        result.descent = font.size * (code ? 0.22 : 0.26);
        result.logical_size = {static_cast<double>(characters) * advance, result.ascent + result.descent};
        result.status = gf::TextResolutionStatus::exact;
        result.runs.push_back({0U, text.size(), result.primary_family, font.weight, font.italic, false});
        return result;
    }
};

constexpr std::string_view long_name = "request_open_files_from_the_platform_and_keep_them_until_taken";
constexpr std::string_view description_head = "Files the platform asks the running application to open, ";
constexpr std::string_view description_code = "take_open_files";
constexpr std::string_view description_tail =
    " hands them over oldest first and forgets them, so a second call returns none until the platform asks again.";
constexpr std::string_view prose_head = "Compiles first the base (";
constexpr std::string_view prose_code = "ApplicationThemeConfig::base";
constexpr std::string_view prose_tail = "), then the packages in order.";

Run text_run(std::string_view text) {
    Run run{};
    run.text = std::string(text);
    return run;
}

Run code_run(std::string_view text) {
    Run run = text_run(text);
    run.code = true;
    return run;
}

// A heading, a Methods table (header, a short name, a name too long for any
// column, a name with no description) and a paragraph with inline code.
Page methods_page() {
    Page page{};
    page.id = "methods";
    page.title = "Methods";
    Block heading{};
    heading.kind = BlockKind::heading2;
    heading.runs.push_back(text_run("Methods"));
    page.blocks.push_back(heading);
    Block header{};
    header.kind = BlockKind::table_header;
    header.cells.push_back({text_run("Member")});
    header.cells.push_back({text_run("Description")});
    page.blocks.push_back(header);
    Block row{};
    row.kind = BlockKind::table_row;
    row.cells.push_back({code_run("request_open_files")});
    row.cells.push_back({text_run(description_head), code_run(description_code), text_run(description_tail)});
    page.blocks.push_back(row);
    Block long_row{};
    long_row.kind = BlockKind::table_row;
    long_row.cells.push_back({code_run(long_name)});
    long_row.cells.push_back({text_run("Too long for its column.")});
    page.blocks.push_back(long_row);
    // A type with no summary: the pack gives its row an empty cell.
    Block empty_row{};
    empty_row.kind = BlockKind::table_row;
    empty_row.cells.push_back({code_run("ApplicationResult")});
    empty_row.cells.push_back({});
    page.blocks.push_back(empty_row);
    Block paragraph{};
    paragraph.kind = BlockKind::paragraph;
    paragraph.runs.push_back(text_run(prose_head));
    paragraph.runs.push_back(code_run(prose_code));
    paragraph.runs.push_back(text_run(prose_tail));
    page.blocks.push_back(paragraph);
    return page;
}

// The page in a window of `size`, laid out with the fixture's faces. The
// window borrows the provider, which the fixture keeps beside it.
struct Fixture final {
    TwoFaceText text;
    std::shared_ptr<ReferencePage> page;
    std::unique_ptr<gf::Window> window;
};

std::unique_ptr<Fixture> make_fixture(gf::Size size) {
    std::unique_ptr<Fixture> fixture = std::make_unique<Fixture>();
    (*fixture).page = gf::make_control<ReferencePage>(gf::StableId("page"));
    (*fixture).window = std::make_unique<gf::Window>((*fixture).page, size);
    (*(*fixture).window).set_text_metrics_provider(&(*fixture).text);
    (*(*fixture).page).set_page(methods_page());
    (*(*fixture).window).perform_layout();
    return fixture;
}

// Defect 1: no text overprints a neighbouring cell or runs past the page.
void check_cells_hold_their_text(const ReferencePage &page, const char *where) {
    const std::vector<ReferencePage::TextPlacement> placements = page.text_placements();
    std::size_t in_table = 0U;
    // The table's code, in reading order: the names, the long one broken
    // into pieces that each fit.
    std::string table_code;
    std::size_t code_pieces = 0U;
    for (const ReferencePage::TextPlacement &placement : placements) {
        if (!placement.in_table)
            continue;
        ++in_table;
        const double right = placement.bounds.x + placement.bounds.width;
        require(placement.bounds.x >= placement.cell.x - 0.001, where);
        require(right <= placement.cell.x + placement.cell.width + 0.001,
                "a table cell's text runs past its cell into the next");
        require(placement.cell.x + placement.cell.width <= page.column_right() + 1.001,
                "a table runs past the page's column");
        if (placement.code) {
            table_code += placement.text;
            ++code_pieces;
        }
    }
    require(in_table > 0U, "the table laid no text");
    require(table_code.find(std::string(long_name)) != std::string::npos,
            "the long member name lost text when it broke");
    // request_open_files, take_open_files, and the long name in two pieces
    // or more.
    require(code_pieces >= 4U, "the long member name did not break inside its column");
    // The cells of one row never overlap.
    for (const ReferencePage::TextPlacement &left : placements) {
        for (const ReferencePage::TextPlacement &right : placements) {
            if (!left.in_table || !right.in_table || near(left.cell.x, right.cell.x) || !near(left.cell.y, right.cell.y))
                continue;
            const bool apart = left.cell.x + left.cell.width <= right.cell.x + 0.001 ||
                               right.cell.x + right.cell.width <= left.cell.x + 0.001;
            require(apart, "two cells of a row overlap");
        }
    }
}

void test_long_member_name_does_not_overprint() {
    const std::unique_ptr<Fixture> wide = make_fixture(gf::Size{900.0, 700.0});
    check_cells_hold_their_text(*(*wide).page, "wide: a cell's text starts left of its cell");
    // The name column fits its content: request_open_files on one line.
    bool whole = false;
    for (const ReferencePage::TextPlacement &placement : (*(*wide).page).text_placements()) {
        if (placement.in_table && placement.text == "request_open_files")
            whole = true;
    }
    require(whole, "the name column is narrower than request_open_files");
    // A row with no description is one line high, its name alone on it.
    std::size_t empty_row_pieces = 0U;
    for (const ReferencePage::TextPlacement &placement : (*(*wide).page).text_placements()) {
        if (placement.in_table && placement.text.find("ApplicationResult") != std::string::npos) {
            ++empty_row_pieces;
            require(placement.text == "ApplicationResult", "a row with no description gained text");
            // One line of 12 x 1.45, rounded, and the cell's 4 + 4.
            require(placement.cell.height <= 25.001, "a row with no description is taller than one line");
        }
    }
    require(empty_row_pieces == 1U, "a row with no description wrapped");
    const std::unique_ptr<Fixture> narrow = make_fixture(gf::Size{420.0, 700.0});
    check_cells_hold_their_text(*(*narrow).page, "narrow: a cell's text starts left of its cell");
}

// Defect 2: one baseline per line, whichever faces are on it.
void test_inline_code_sits_on_the_body_baseline() {
    const std::unique_ptr<Fixture> fixture = make_fixture(gf::Size{900.0, 700.0});
    const std::vector<ReferencePage::TextPlacement> placements = (*(*fixture).page).text_placements();
    std::size_t mixed_lines = 0U;
    for (const ReferencePage::TextPlacement &first : placements) {
        for (const ReferencePage::TextPlacement &second : placements) {
            if (!near(first.bounds.y, second.bounds.y) || first.code == second.code)
                continue;
            ++mixed_lines;
            require(near(first.baseline, second.baseline), "inline code and prose on one line have two baselines");
        }
    }
    require(mixed_lines > 0U, "no line mixed code and prose");
    // A row's code-only name and its prose description start on one
    // baseline.
    double name_baseline = -1.0;
    double description_baseline = -1.0;
    for (const ReferencePage::TextPlacement &placement : placements) {
        if (placement.text == "request_open_files")
            name_baseline = placement.baseline;
        if (placement.text.rfind("Files", 0U) == 0U && description_baseline < 0.0)
            description_baseline = placement.baseline;
    }
    require(name_baseline > 0.0 && description_baseline > 0.0, "the row's cells were not found");
    require(near(name_baseline, description_baseline), "a row's cells do not align on their first baselines");
}

std::string expected_page_text() {
    std::string text = "Methods\n\nMember\tDescription\nrequest_open_files\t";
    text += description_head;
    text += description_code;
    text += description_tail;
    text += "\n";
    text += long_name;
    text += "\tToo long for its column.\nApplicationResult\n\n";
    text += prose_head;
    text += prose_code;
    text += prose_tail;
    return text;
}

gf::PointerEvent pointer(gf::PointerAction action, gf::Point position, std::uint32_t clicks) {
    gf::PointerEvent event{};
    event.action = action;
    event.button = action == gf::PointerAction::move ? gf::PointerButton::none : gf::PointerButton::primary;
    event.position = position;
    event.click_count = clicks;
    return event;
}

// Defect 3: the page's text can be selected and copied.
void test_select_and_copy() {
    const std::unique_ptr<Fixture> fixture = make_fixture(gf::Size{900.0, 700.0});
    ReferencePage &page = *(*fixture).page;
    gf::Window &window = *(*fixture).window;
    require(!page.has_selection() && page.selected_text().empty(), "a new page has a selection");
    require(!page.copy(), "copy with nothing selected wrote the clipboard");

    page.select_all();
    require(page.selected_text() == expected_page_text(), "Select All does not copy the page as text and rows");

    // The page is the window's root, so window positions are local ones;
    // content sits at the viewport's origin while unscrolled.
    const gf::Rect viewport = page.viewport_rectangle();
    gf::Rect name{};
    gf::Rect description{};
    for (const ReferencePage::TextPlacement &placement : page.text_placements()) {
        if (placement.text == "request_open_files")
            name = placement.bounds;
        if (placement.text.rfind("Files", 0U) == 0U && description.width <= 0.0)
            description = placement.bounds;
    }
    require(name.width > 0.0 && description.width > 0.0, "the row's text was not found");
    const gf::Point name_middle{viewport.x + name.x + name.width / 2.0, viewport.y + name.y + name.height / 2.0};

    // A double-click selects the word under it, '_' included.
    static_cast<void>(window.dispatch_pointer(pointer(gf::PointerAction::down, name_middle, 1U)));
    static_cast<void>(window.dispatch_pointer(pointer(gf::PointerAction::up, name_middle, 1U)));
    static_cast<void>(window.dispatch_pointer(pointer(gf::PointerAction::down, name_middle, 2U)));
    static_cast<void>(window.dispatch_pointer(pointer(gf::PointerAction::up, name_middle, 2U)));
    require(page.selected_text() == "request_open_files", "a double-click does not select the member name");

    // A drag from before the name to past the description's first word
    // copies the name, a tab, then the word.
    const gf::Point before_name{viewport.x + name.x - 2.0, name_middle.y};
    const gf::Point after_files{viewport.x + description.x + description.width + 1.0,
                                viewport.y + description.y + description.height / 2.0};
    static_cast<void>(window.dispatch_pointer(pointer(gf::PointerAction::down, before_name, 1U)));
    static_cast<void>(window.dispatch_pointer(pointer(gf::PointerAction::move, after_files, 0U)));
    static_cast<void>(window.dispatch_pointer(pointer(gf::PointerAction::up, after_files, 1U)));
    const std::string dragged = page.selected_text();
    require(dragged.rfind("request_open_files\tFiles", 0U) == 0U, "a drag across a row does not copy its cells");

    // Shift+click extends from the drag's start.
    gf::PointerEvent extend = pointer(gf::PointerAction::down, name_middle, 1U);
    extend.modifiers = gf::Modifier::shift;
    static_cast<void>(window.dispatch_pointer(extend));
    extend.action = gf::PointerAction::up;
    static_cast<void>(window.dispatch_pointer(extend));
    require(page.selected_text().size() < dragged.size() && page.selected_text().rfind("request_", 0U) == 0U,
            "Shift+click does not move the selection's end");

    // Ctrl+A (Cmd+A) selects the page; the press above gave it focus.
    gf::KeyEvent select_all{};
    select_all.physical_key = gf::PhysicalKey::a;
    select_all.modifiers = gf::Modifier::control;
    static_cast<void>(window.dispatch_key(select_all));
    require(page.selected_text() == expected_page_text(), "Ctrl+A does not select the page");
    select_all.modifiers = gf::Modifier::meta;
    page.clear_selection();
    static_cast<void>(window.dispatch_key(select_all));
    require(page.selected_text() == expected_page_text(), "Cmd+A does not select the page");

    // A new width relays the page out; the selection keeps its text.
    window.resize(gf::Size{460.0, 700.0});
    window.perform_layout();
    require(page.selected_text() == expected_page_text(), "a relayout changed the selected text");

    // Without a host there is no clipboard: copy refuses and keeps the
    // selection.
    require(!page.copy() && page.has_selection(), "copy without a host claimed the clipboard");
}

} // namespace

int main() {
    try {
        test_long_member_name_does_not_overprint();
        test_inline_code_sits_on_the_body_baseline();
        test_select_and_copy();
        std::cout << "pocket_reference_page_tests: all tests passed\n";
        return EXIT_SUCCESS;
    } catch (const std::exception &error) {
        std::cerr << "pocket_reference_page_tests: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
