// SPDX-License-Identifier: MIT
#include "reference_page.hpp"

#include <gui_forms/event/delegate/delegate.hpp>
#include <gui_forms/event/event/event.hpp>
#include <gui_forms/host/services/host_services.hpp>
#include <gui_forms/surface_root/surface_root.hpp>
#include <gui_forms/theme/part_painting/part_painting.hpp>
#include <gui_forms/theme/stock_anatomies/stock_anatomies.hpp>
#include <gui_forms/typography/types/typography_types.hpp>
#include <gui_forms/window/window.hpp>

#include <stxlib/optional.hpp>
#include <stxlib/syntax.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <span>
#include <utility>

namespace gf = gui_forms;

namespace pocket_reference {
namespace {

constexpr std::size_t part_count = 27U;

// The parts, in the order of ReferencePage::Part.
constexpr std::array<std::string_view, part_count> part_names{{
    "paper", "heading", "heading_rule", "section_rule", "text", "code_text", "code_span", "link", "signature", "signature_bar",
    "code_block", "keyword", "type", "function", "string", "number", "comment", "directive",
    "table_header", "table_cell", "find_match", "find_current", "preview", "caption", "card", "purpose",
    "selection",
}};
constexpr std::array<gf::PartRole, part_count> part_roles{{
    gf::PartRole::face, gf::PartRole::label, gf::PartRole::face, gf::PartRole::face, gf::PartRole::label,
    gf::PartRole::label, gf::PartRole::face, gf::PartRole::label, gf::PartRole::face, gf::PartRole::face,
    gf::PartRole::face, gf::PartRole::label, gf::PartRole::label, gf::PartRole::label, gf::PartRole::label,
    gf::PartRole::label, gf::PartRole::label, gf::PartRole::label, gf::PartRole::face, gf::PartRole::face,
    gf::PartRole::face, gf::PartRole::face, gf::PartRole::face, gf::PartRole::label, gf::PartRole::face,
    gf::PartRole::label, gf::PartRole::face,
}};
constexpr std::array<gf::AnatomyState, 2> link_states{{gf::AnatomyState::hot, gf::AnatomyState::pressed}};
constexpr std::array<gf::AnatomyState, 1> card_states{{gf::AnatomyState::hot}};

// The page's typography, in units of the mockup (mockup.html): the body is
// 13 units with lines of 1.5, the code 12, headings 22, 16 and 13.
constexpr double page_padding_x = 28.0;
constexpr double page_padding_top = 18.0;
constexpr double page_padding_bottom = 40.0;
constexpr double page_maximum_width = 860.0;
constexpr double nested_indent = 18.0;
constexpr double definition_indent = 22.0;
constexpr double card_minimum_width = 220.0;
constexpr double card_gap = 8.0;
// A table cell's padding on each side, and the narrowest a column gets.
constexpr double cell_padding = 8.0;
constexpr double column_minimum_width = 48.0;
// A column's least width never asks for more than this share of the
// table: a longer word in it breaks.
constexpr double column_word_share = 0.4;
// How far a press on a link moves before it selects instead.
constexpr double drag_slop = 4.0;

// The anatomy: ScrollableControl's parts, then the page's.
struct AnatomyStorage final {
    std::vector<gf::PartDeclaration> parts;
    gf::ControlAnatomy anatomy{};
};

AnatomyStorage make_anatomy() {
    AnatomyStorage storage;
    const gf::ControlAnatomy *base = nullptr;
    for (const gf::ControlAnatomy &stock : gf::stock_control_anatomies()) {
        if (stock.control_id == "scrollable_control")
            base = &stock;
    }
    if (base != nullptr)
        storage.parts.assign((*base).parts.begin(), (*base).parts.end());
    for (std::size_t index = 0U; index < part_count; ++index) {
        gf::PartDeclaration declaration{};
        declaration.name = part_names[index];
        declaration.role = part_roles[index];
        if (part_names[index] == "link")
            declaration.states = std::span<const gf::AnatomyState>(link_states);
        else if (part_names[index] == "card")
            declaration.states = std::span<const gf::AnatomyState>(card_states);
        storage.parts.push_back(declaration);
    }
    storage.anatomy.control_id = "reference_page";
    storage.anatomy.parts = std::span<const gf::PartDeclaration>(storage.parts.data(), storage.parts.size());
    if (base != nullptr)
        storage.anatomy.states = (*base).states;
    return storage;
}

bool is_space(char c) noexcept { return c == ' '; }

bool is_continuation(char c) noexcept { return (static_cast<unsigned char>(c) & 0xC0U) == 0x80U; }

// The start of the UTF-8 character at or before byte `at` of `text`.
std::size_t character_start(std::string_view text, std::size_t at) noexcept {
    while (at > 0U && at < text.size() && is_continuation(text[at]))
        --at;
    return at;
}

// The byte after the UTF-8 character that starts at `at`.
std::size_t next_character(std::string_view text, std::size_t at) noexcept {
    std::size_t next = at + 1U;
    while (next < text.size() && is_continuation(text[next]))
        ++next;
    return next;
}

// Where an identifier or a path may break: after one of these.
bool breaks_after(char c) noexcept {
    return c == '_' || c == ':' || c == '(' || c == ',' || c == '.' || c == '/';
}

// A byte of a word for a double-click: a letter, a digit, '_' or any byte
// of a non-ASCII character.
bool is_word_byte(char c) noexcept {
    const unsigned char byte = static_cast<unsigned char>(c);
    return (byte >= 'a' && byte <= 'z') || (byte >= 'A' && byte <= 'Z') || (byte >= '0' && byte <= '9') ||
           byte == '_' || byte >= 0x80U;
}

// Ctrl on Windows and Linux, Cmd on macOS: either is taken on every host,
// as TextBox takes them.
bool has_command_modifier(gf::Modifier value) noexcept {
    return gf::has_modifier(value, gf::Modifier::control) || gf::has_modifier(value, gf::Modifier::meta);
}

// The font a run is set in, within a flow whose faces are `body` and `code`.
gf::FontSpec font_of(const Run &run, const gf::FontSpec &body, const gf::FontSpec &code) noexcept {
    gf::FontSpec font = run.code ? code : body;
    if (run.bold)
        font.weight = 700;
    if (run.italic)
        font.italic = true;
    return font;
}

// The faces of a flow: its body and code faces, then each other face its
// runs use (bold, italic), each once. At most eight: two faces, each
// regular or bold, upright or italic.
struct FlowFaces final {
    std::array<gf::FontSpec, 8> faces{};
    std::size_t count{};
};

void add_face(FlowFaces &faces, const gf::FontSpec &font) noexcept {
    for (std::size_t index = 0U; index < faces.count; ++index) {
        if (faces.faces[index] == font)
            return;
    }
    if (faces.count < faces.faces.size()) {
        faces.faces[faces.count] = font;
        ++faces.count;
    }
}

// Every face a flow of `body` and `code` can set a run in: each regular or
// bold (font_of's 700), upright or italic.
void add_flow_faces(FlowFaces &faces, const gf::FontSpec &body, const gf::FontSpec &code) noexcept {
    const std::array<gf::FontSpec, 2> bases{{body, code}};
    for (const gf::FontSpec &base : bases) {
        for (std::size_t style = 0U; style < 4U; ++style) {
            gf::FontSpec font = base;
            if ((style & 1U) != 0U)
                font.weight = 700;
            if ((style & 2U) != 0U)
                font.italic = true;
            add_face(faces, font);
        }
    }
}

// Shares `width` among a table's columns. A column's least width is its
// widest word, capped at column_word_share of the table (a longer word
// breaks); its natural width is its text on one line. When the natural
// widths fit, the spare goes to each column by its natural share, so the
// table fills its width as the mockup's does; when only the least widths
// fit, each column gets its least width and a share of the rest by how much
// more it would take; when not even those fit, the least widths shrink
// together. The last column takes what rounding leaves, so the columns sum
// to `width` exactly.
std::vector<double> share_columns(const std::vector<double> &minimum_in, const std::vector<double> &natural_in,
                                  double width) {
    const std::size_t columns = minimum_in.size();
    std::vector<double> widths(columns, 0.0);
    if (columns == 0U)
        return widths;
    const double cap = columns > 1U ? std::max(column_minimum_width, std::floor(width * column_word_share)) : width;
    std::vector<double> minimum(columns, 0.0);
    std::vector<double> natural(columns, 0.0);
    double minimum_total = 0.0;
    double natural_total = 0.0;
    for (std::size_t column = 0U; column < columns; ++column) {
        minimum[column] = std::min(std::max(minimum_in[column], column_minimum_width), cap);
        natural[column] = std::max(natural_in[column], minimum[column]);
        minimum_total += minimum[column];
        natural_total += natural[column];
    }
    for (std::size_t column = 0U; column < columns; ++column) {
        double share = 0.0;
        if (natural_total <= width)
            share = width * natural[column] / natural_total;
        else if (minimum_total < width)
            share = minimum[column] +
                    (width - minimum_total) * (natural[column] - minimum[column]) / (natural_total - minimum_total);
        else
            share = width * minimum[column] / minimum_total;
        widths[column] = std::floor(share);
    }
    double others = 0.0;
    for (std::size_t column = 0U; column + 1U < columns; ++column)
        others += widths[column];
    widths[columns - 1U] = std::max(0.0, width - others);
    return widths;
}

char fold(char c, bool match_case) noexcept {
    if (match_case)
        return c;
    return c >= 'A' && c <= 'Z' ? static_cast<char>(c - 'A' + 'a') : c;
}

} // namespace

ReferencePage::ReferencePage(gf::StableId stable_id) : ScrollableControl(std::move(stable_id)) {
    auto_scroll = true;
    focusable = true;
    tab_stop = true;
    accessible_name = "Reference page";
    cursor = stxlib::Optional<gf::CursorKind>::of(gf::CursorKind::text);
    // Copy and Select All from a menu or a shortcut reach the page while it
    // holds focus (the focused route of the command chain).
    command_target_ = std::make_shared<gf::CommandTarget>("reference-page");
    (*command_target_)
        .set_handler("copy", gf::Delegate<const gf::CommandInvocation &>::bind<ReferencePage,
                                                                             &ReferencePage::on_routed_command>(*this));
    (*command_target_)
        .set_handler("select-all", gf::Delegate<const gf::CommandInvocation &>::bind<
                                       ReferencePage, &ReferencePage::on_routed_command>(*this));
    set_command_target(command_target_);
}

ReferencePage::~ReferencePage() {
    if (context_menu_ != nullptr)
        (*context_menu_).close();
}

void ReferencePage::on_dispose() noexcept {
    if (context_menu_ != nullptr)
        (*context_menu_).dispose();
    ScrollableControl::on_dispose();
}

const gf::ControlAnatomy &ReferencePage::page_anatomy() noexcept {
    static const AnatomyStorage storage = make_anatomy();
    return storage.anatomy;
}

const gf::ControlAnatomy &ReferencePage::anatomy() const noexcept { return page_anatomy(); }

// --- Content -------------------------------------------------------------------------

void ReferencePage::set_page(Page page) {
    page_ = std::move(page);
    matches_.clear();
    query_.clear();
    pending_anchor_.clear();
    pending_reveal_ = false;
    current_match_ = 0U;
    hovered_link_ = no_link;
    pressed_link_ = no_link;
    selection_anchor_ = 0U;
    selection_caret_ = 0U;
    selecting_ = false;
    table_measures_.clear();
    face_metrics_.clear();
    relayout();
    arrange_scroll_viewport(gf::Size{committed_arranged_bounds().width, committed_arranged_bounds().height},
                            gf::Size{content_width_, content_height_});
    scroll_to(gf::Point{0.0, 0.0});
    invalidate(gf::Dirty::paint);
}

bool ReferencePage::scroll_to_anchor(std::string_view anchor) {
    pending_anchor_ = std::string(anchor);
    return apply_anchor(anchor);
}

bool ReferencePage::apply_anchor(std::string_view anchor) {
    for (const Anchor &entry : anchors_) {
        if (entry.name == anchor) {
            scroll_to(gf::Point{0.0, std::max(0.0, entry.top - 8.0)});
            invalidate(gf::Dirty::paint);
            return true;
        }
    }
    return false;
}

void ReferencePage::scroll_to_top() {
    pending_anchor_.clear();
    scroll_to(gf::Point{0.0, 0.0});
    invalidate(gf::Dirty::paint);
}

// --- Find ----------------------------------------------------------------------------

std::size_t ReferencePage::find(std::string_view query, bool match_case) {
    query_ = std::string(query);
    match_case_ = match_case;
    matches_.clear();
    current_match_ = 0U;
    if (!query_.empty()) {
        for (std::size_t index = 0U; index < pieces_.size(); ++index) {
            const std::string_view text = pieces_[index].text;
            if (text.size() < query_.size())
                continue;
            for (std::size_t at = 0U; at + query_.size() <= text.size(); ++at) {
                std::size_t matched = 0U;
                while (matched < query_.size() &&
                       fold(text[at + matched], match_case_) == fold(query_[matched], match_case_))
                    ++matched;
                if (matched == query_.size()) {
                    matches_.push_back(Match{index, at, query_.size()});
                    at += query_.size() - 1U;
                }
            }
        }
    }
    reveal_current_match();
    invalidate(gf::Dirty::paint);
    return matches_.size();
}

void ReferencePage::find_next() {
    if (matches_.empty())
        return;
    current_match_ = (current_match_ + 1U) % matches_.size();
    reveal_current_match();
    invalidate(gf::Dirty::paint);
}

void ReferencePage::find_previous() {
    if (matches_.empty())
        return;
    current_match_ = current_match_ == 0U ? matches_.size() - 1U : current_match_ - 1U;
    reveal_current_match();
    invalidate(gf::Dirty::paint);
}

void ReferencePage::clear_find() {
    query_.clear();
    matches_.clear();
    current_match_ = 0U;
    invalidate(gf::Dirty::paint);
}

std::size_t ReferencePage::find_position() const noexcept { return matches_.empty() ? 0U : current_match_ + 1U; }

void ReferencePage::reveal_current_match() {
    pending_reveal_ = true;
    if (matches_.empty())
        return;
    const Piece &piece = pieces_[matches_[current_match_].piece];
    const gf::Rect viewport = viewport_rectangle();
    if (viewport.height <= 0.0)
        return;
    const gf::Point scrolled = scroll_position();
    const double top = piece.bounds.y;
    const double bottom = piece.bounds.y + piece.bounds.height;
    if (top >= scrolled.y && bottom <= scrolled.y + viewport.height)
        return;
    scroll_to(gf::Point{scrolled.x, std::max(0.0, top - viewport.height / 3.0)});
}

// --- Layout --------------------------------------------------------------------------

ReferencePage::Fonts ReferencePage::fonts() const noexcept {
    Fonts fonts{};
    fonts.body = text_font(gf::FontSpec{gf::FontRole::content, 13.0, 400, false});
    const double unit = fonts.body.size / 13.0;
    fonts.bold = fonts.body;
    fonts.bold.weight = 700;
    fonts.italic = fonts.body;
    fonts.italic.italic = true;
    // The code font is the monospace role's own family, not the body's.
    fonts.code = gf::FontSpec{};
    fonts.code.role = gf::FontRole::monospace;
    fonts.code.size = 12.0 * unit;
    fonts.code.language = fonts.body.language;
    fonts.small = fonts.body;
    fonts.small.size = 12.0 * unit;
    fonts.small_code = fonts.code;
    fonts.small_code.size = 11.5 * unit;
    fonts.caption = fonts.body;
    fonts.caption.size = 11.0 * unit;
    fonts.heading1 = fonts.body;
    fonts.heading1.size = 22.0 * unit;
    fonts.heading1.weight = 600;
    fonts.heading2 = fonts.body;
    fonts.heading2.size = 16.0 * unit;
    fonts.heading2.weight = 600;
    fonts.heading3 = fonts.body;
    fonts.heading3.weight = 600;
    return fonts;
}

double ReferencePage::width_of(std::string_view text, const gf::FontSpec &font) const {
    if (text.empty())
        return 0.0;
    return measure_text_extent_utf8(text, font).logical_size.width;
}

ReferencePage::FaceMetrics ReferencePage::face_metrics(const gf::FontSpec &font) {
    for (const FaceMetrics &known : face_metrics_) {
        if (known.font == font)
            return known;
    }
    const gf::ResolvedTextLayout layout = resolve_text_layout_utf8(" ", font);
    FaceMetrics metrics{};
    metrics.font = font;
    metrics.ascent = std::round(layout.ascent);
    metrics.descent = std::round(layout.descent);
    face_metrics_.push_back(metrics);
    return metrics;
}

// Each face keeps its own metrics: the line's ascent is the largest of the
// faces' ascents and its descent the largest descent, so no face's glyphs
// are placed by another face's metrics, and every face on the line sits on
// the one baseline. The leading (line height less ascent and descent) goes
// half above, rounded down, and the rest below, as CSS places it.
ReferencePage::LineFrame ReferencePage::line_frame(double line_height, std::span<const gf::FontSpec> faces) {
    double ascent = 0.0;
    double descent = 0.0;
    for (const gf::FontSpec &font : faces) {
        const FaceMetrics metrics = face_metrics(font);
        ascent = std::max(ascent, metrics.ascent);
        descent = std::max(descent, metrics.descent);
    }
    LineFrame frame{};
    frame.height = std::max(line_height, std::ceil(ascent + descent));
    frame.baseline = std::floor((frame.height - (ascent + descent)) / 2.0) + ascent;
    return frame;
}

std::size_t ReferencePage::break_length(std::string_view word, const gf::FontSpec &font, double room) const {
    if (word.empty())
        return 0U;
    // The longest head that fits, by halving over character starts; at
    // least the first character, so the break always makes progress.
    std::size_t low = next_character(word, 0U);
    std::size_t high = word.size();
    while (high > low) {
        const std::size_t middle = character_start(word, low + (high - low + 1U) / 2U);
        if (middle <= low)
            break;
        if (width_of(word.substr(0U, middle), font) <= room)
            low = middle;
        else
            high = middle - 1U;
    }
    const std::size_t fit = low;
    for (std::size_t at = fit; at > fit / 3U && at > 1U; --at) {
        if (breaks_after(word[at - 1U]))
            return at;
    }
    return fit;
}

void ReferencePage::push_piece(Piece piece) {
    piece.text_start = laid_text_size_;
    piece.block = layout_block_;
    piece.cell = layout_cell_;
    piece.stream = layout_stream_;
    laid_text_size_ += piece.text.size();
    pieces_.push_back(piece);
}

double ReferencePage::flow_runs(const std::vector<Run> &runs, const Flow &flow, double top) {
    const std::size_t first_piece = pieces_.size();
    ++layout_stream_;
    // One line box for every face the flow may use: inline code and prose
    // share a baseline. The faces are the flow's, not its runs', so every
    // flow with the same faces gets the same box: the cells of a table row
    // (a code-only name beside prose) align on their first baselines.
    FlowFaces faces{};
    add_flow_faces(faces, flow.body, flow.code);
    const LineFrame frame = line_frame(flow.line_height, std::span<const gf::FontSpec>(faces.faces.data(), faces.count));
    double x = 0.0;
    double line_top = top;
    bool placed = false;
    std::size_t last_run = static_cast<std::size_t>(-1);
    for (std::size_t run_index = 0U; run_index < runs.size(); ++run_index) {
        const Run &run = runs[run_index];
        const gf::FontSpec font = font_of(run, flow.body, flow.code);
        Part part = flow.part;
        if (run.link != no_link)
            part = Part::link;
        else if (run.code && flow.part == Part::text)
            part = Part::code_text;
        const std::string_view text(run.text);
        std::size_t at = 0U;
        while (at < text.size()) {
            std::size_t end = at;
            while (end < text.size() && !is_space(text[end]))
                ++end;
            const std::size_t word_end = end;
            while (end < text.size() && is_space(text[end]))
                ++end;
            std::string_view word = text.substr(at, end - at);
            double full = width_of(word, font);
            const double trimmed = word_end == end ? full : width_of(text.substr(at, word_end - at), font);
            if (x > 0.0 && x + trimmed > flow.width) {
                line_top += frame.height;
                x = 0.0;
            }
            // A word wider than the whole line (a long member name in a
            // narrow column) breaks where it fits, preferably after a '_'
            // or a '::', and its rest starts the next line.
            bool broken = false;
            if (trimmed > flow.width && word_end > at) {
                const std::size_t head = break_length(text.substr(at, word_end - at), font, flow.width);
                if (head < word_end - at) {
                    word = text.substr(at, head);
                    full = width_of(word, font);
                    end = at + head;
                    broken = true;
                }
            }
            const bool extends = placed && last_run == run_index && pieces_.back().bounds.y == line_top &&
                                 pieces_.back().text.data() + pieces_.back().text.size() == word.data();
            if (extends) {
                Piece &piece = pieces_.back();
                piece.text = std::string_view(piece.text.data(), piece.text.size() + word.size());
                piece.bounds.width += full;
                laid_text_size_ += word.size();
            } else {
                Piece piece{};
                piece.bounds = gf::Rect{flow.left + x, line_top, full, frame.height};
                piece.baseline = line_top + frame.baseline;
                piece.font = font;
                piece.text = word;
                piece.part = part;
                piece.link = run.link;
                push_piece(piece);
            }
            placed = true;
            last_run = run_index;
            x += full;
            at = end;
            if (broken) {
                line_top += frame.height;
                x = 0.0;
            }
        }
    }
    // Inline code sits on a tint, as in the mockup (p code): the code
    // face's own ascent and descent about the shared baseline.
    for (std::size_t index = first_piece; index < pieces_.size(); ++index) {
        const Piece &piece = pieces_[index];
        if (piece.part != Part::code_text)
            continue;
        const FaceMetrics code = face_metrics(piece.font);
        boxes_.push_back(Box{gf::Rect{piece.bounds.x - 1.0, piece.baseline - code.ascent - 1.0, piece.bounds.width + 2.0,
                                      code.ascent + code.descent + 2.0},
                             Part::code_span, no_link});
    }
    return placed ? line_top + frame.height : top;
}

double ReferencePage::place_code(std::string_view line, double left, double top, double line_height,
                                 const gf::FontSpec &font, double wrap_width, std::uint64_t &state, double &bottom) {
    namespace sx = stxlib::syntax;
    ++layout_stream_;
    const double space = width_of(" ", font);
    gf::FontSpec comment_font = font;
    comment_font.italic = true;
    const std::array<gf::FontSpec, 2> faces{{font, comment_font}};
    const LineFrame frame = line_frame(line_height, std::span<const gf::FontSpec>(faces));
    double x = left;
    double line_top = top;
    sx::LineCursor cursor = sx::LineCursor::at_line_start(sx::LineState{state});
    std::array<sx::LineToken, 64> tokens{};
    double right = left;
    std::size_t column = 0U;
    // The spaces since the last token placed, which copy puts back.
    std::size_t spaces_before = 0U;
    while (!cursor.done) {
        const std::size_t count =
            sx::lex_line(sx::Language::cpp, stxlib::View<char>(line.data(), line.size()), cursor,
                         stxlib::MutableView<sx::LineToken>(tokens.data(), tokens.size()));
        for (std::size_t index = 0U; index < count; ++index) {
            const sx::LineToken &token = tokens[index];
            // The lexer leaves gaps between tokens untold: they are spaces.
            if (token.column > column) {
                x += space * static_cast<double>(token.column - column);
                spaces_before += token.column - column;
            }
            column = token.column + token.length;
            const std::string_view text = line.substr(token.column, token.length);
            std::size_t spaces = 0U;
            while (spaces < text.size() && text[spaces] == ' ')
                ++spaces;
            if (spaces == text.size()) {
                x += space * static_cast<double>(spaces);
                spaces_before += spaces;
                continue;
            }
            Part part = Part::code_text;
            switch (token.kind) {
            case sx::TokenKind::comment:
            case sx::TokenKind::documentation:
                part = Part::comment;
                break;
            case sx::TokenKind::string:
            case sx::TokenKind::character:
                part = Part::string;
                break;
            case sx::TokenKind::number:
            case sx::TokenKind::constant:
                part = Part::number;
                break;
            case sx::TokenKind::keyword:
            case sx::TokenKind::control:
                part = Part::keyword;
                break;
            case sx::TokenKind::type:
                part = Part::type;
                break;
            case sx::TokenKind::function:
                part = Part::function;
                break;
            case sx::TokenKind::directive:
            case sx::TokenKind::macro:
                part = Part::directive;
                break;
            default:
                part = Part::code_text;
                break;
            }
            const gf::FontSpec &token_font = part == Part::comment ? comment_font : font;
            const double width = width_of(text, token_font);
            if (wrap_width > 0.0 && x > left && x + width - left > wrap_width) {
                line_top += frame.height;
                x = left + 4.0 * space;
            }
            Piece piece{};
            piece.bounds = gf::Rect{x, line_top, width, frame.height};
            piece.baseline = line_top + frame.baseline;
            piece.font = token_font;
            piece.text = text;
            piece.part = part;
            piece.lead_spaces = spaces_before;
            spaces_before = 0U;
            push_piece(piece);
            x += width;
            right = std::max(right, x);
        }
    }
    state = cursor.state.value;
    bottom = line_top + frame.height;
    return right;
}

const ReferencePage::TableMeasure &ReferencePage::table_measure(std::size_t first, std::size_t end, const Fonts &f) {
    for (const TableMeasure &known : table_measures_) {
        if (known.first == first && known.font == f.small)
            return known;
    }
    std::size_t columns = 1U;
    for (std::size_t index = first; index < end; ++index)
        columns = std::max(columns, page_.blocks[index].cells.size());
    TableMeasure measure{};
    measure.first = first;
    measure.font = f.small;
    measure.minimum.assign(columns, 0.0);
    measure.natural.assign(columns, 0.0);
    // Each cell measured in the faces it is set in (the code face for a
    // member name), word by word as flow_runs places it.
    for (std::size_t index = first; index < end; ++index) {
        const Block &block = page_.blocks[index];
        gf::FontSpec body = f.small;
        if (block.kind == BlockKind::table_header)
            body.weight = 600;
        for (std::size_t column = 0U; column < block.cells.size(); ++column) {
            double widest_word = 0.0;
            double line = 0.0;
            for (const Run &run : block.cells[column]) {
                const gf::FontSpec font = font_of(run, body, f.small_code);
                const std::string_view text(run.text);
                std::size_t at = 0U;
                while (at < text.size()) {
                    std::size_t end_of_word = at;
                    while (end_of_word < text.size() && !is_space(text[end_of_word]))
                        ++end_of_word;
                    std::size_t next = end_of_word;
                    while (next < text.size() && is_space(text[next]))
                        ++next;
                    widest_word = std::max(widest_word, width_of(text.substr(at, end_of_word - at), font));
                    line += width_of(text.substr(at, next - at), font);
                    at = next;
                }
            }
            measure.minimum[column] = std::max(measure.minimum[column], std::ceil(widest_word) + 2.0 * cell_padding);
            measure.natural[column] = std::max(measure.natural[column], std::ceil(line) + 2.0 * cell_padding);
        }
    }
    table_measures_.push_back(std::move(measure));
    return table_measures_.back();
}

double ReferencePage::lay_out_table(std::size_t first, std::size_t end, double left, double width, double top) {
    const Fonts f = fonts();
    const double line_height = std::round(f.small.size * 1.45);
    // The columns come from their content's measured widths (table_measure),
    // shared within the column the page lays out in, so no cell's text runs
    // into its neighbour or past the page.
    // The measure is borrowed from table_measures_ only until the widths
    // are shared; nothing below reads it.
    const TableMeasure &measure = table_measure(first, end, f);
    const std::vector<double> shared = share_columns(measure.minimum, measure.natural, width);
    const std::size_t columns = shared.size();
    double y = top;
    for (std::size_t index = first; index < end; ++index) {
        const Block &block = page_.blocks[index];
        const bool header = block.kind == BlockKind::table_header;
        layout_block_ = index;
        Flow flow{};
        flow.line_height = line_height;
        flow.body = f.small;
        if (header)
            flow.body.weight = 600;
        flow.code = f.small_code;
        flow.part = Part::text;
        double x = left;
        double row_bottom = y + line_height + 8.0;
        for (std::size_t column = 0U; column < columns; ++column) {
            if (column < block.cells.size()) {
                layout_cell_ = column;
                flow.left = x + cell_padding;
                flow.width = std::max(16.0, shared[column] - 2.0 * cell_padding);
                const double bottom = flow_runs(block.cells[column], flow, y + 4.0);
                row_bottom = std::max(row_bottom, bottom + 4.0);
            }
            x += shared[column];
        }
        layout_cell_ = no_cell;
        x = left;
        for (std::size_t column = 0U; column < columns; ++column) {
            boxes_.push_back(Box{gf::Rect{x, y, shared[column] + 1.0, row_bottom - y + 1.0},
                                 header ? Part::table_header : Part::table_cell, no_link});
            cells_.push_back(CellBounds{index, column, gf::Rect{x, y, shared[column], row_bottom - y}});
            x += shared[column];
        }
        y = row_bottom;
    }
    return y + 1.0;
}

double ReferencePage::lay_out_cards(std::size_t first, std::size_t end, double left, double width, double top) {
    const Fonts f = fonts();
    const double line_height = std::round(f.body.size * 1.45);
    const std::size_t columns =
        std::max<std::size_t>(1U, static_cast<std::size_t>((width + card_gap) / (card_minimum_width + card_gap)));
    const double card_width = std::floor((width - card_gap * static_cast<double>(columns - 1U)) /
                                         static_cast<double>(columns));
    double y = top;
    for (std::size_t row = first; row < end; row += columns) {
        const std::size_t row_end = std::min(end, row + columns);
        const std::size_t first_box = boxes_.size();
        double row_bottom = y;
        for (std::size_t index = row; index < row_end; ++index) {
            const Block &block = page_.blocks[index];
            layout_block_ = index;
            const double x = left + static_cast<double>(index - row) * (card_width + card_gap);
            const std::size_t box_index = boxes_.size();
            boxes_.push_back(Box{gf::Rect{x, y, card_width, 0.0}, Part::card,
                                 block.runs.empty() ? no_link : block.runs.front().link});
            Flow flow{};
            flow.left = x + 10.0;
            flow.width = card_width - 20.0;
            flow.line_height = line_height;
            flow.body = f.body;
            flow.code = f.code;
            flow.part = Part::text;
            double bottom = flow_runs(block.runs, flow, y + 7.0);
            if (!block.cells.empty() && !block.cells.front().empty()) {
                flow.part = Part::purpose;
                flow.body = f.small;
                flow.line_height = std::round(f.small.size * 1.45);
                bottom = flow_runs(block.cells.front(), flow, bottom + 1.0);
            }
            boxes_[box_index].bounds.height = bottom + 7.0 - y;
            row_bottom = std::max(row_bottom, bottom + 7.0);
        }
        for (std::size_t index = first_box; index < boxes_.size(); ++index) {
            if (boxes_[index].part == Part::card)
                boxes_[index].bounds.height = row_bottom - y;
        }
        y = row_bottom + card_gap;
    }
    return y - card_gap;
}

void ReferencePage::relayout() {
    const gf::Rect viewport = viewport_rectangle();
    const double width = viewport.width > 0.0 ? viewport.width : client_rectangle().width;
    laid_width_ = width;
    // The kept measures hold for one source of metrics: attaching to a
    // window (or an off-screen capture) can change it.
    std::uint64_t source = 0U;
    const gf::BorrowedPointer<gf::SurfaceRoot> root = attached_surface_root();
    if (root && (*root).text_metrics_provider() != nullptr)
        source = (*(*root).text_metrics_provider()).measurement_identity();
    if (source != metrics_source_) {
        metrics_source_ = source;
        table_measures_.clear();
        face_metrics_.clear();
    }
    pieces_.clear();
    boxes_.clear();
    anchors_.clear();
    cells_.clear();
    laid_text_size_ = 0U;
    layout_block_ = 0U;
    layout_cell_ = no_cell;
    layout_stream_ = 0U;
    const Fonts f = fonts();
    const double unit = f.body.size / 13.0;
    const double body_line = std::round(f.body.size * 1.5);
    const double code_line = std::round(f.code.size * 1.5);
    const double paragraph_width = 80.0 * width_of("0", f.body);
    const double column = std::max(120.0, std::min(width, page_maximum_width * unit) - 2.0 * page_padding_x);
    column_right_ = page_padding_x + column;
    double right = width;
    double y = page_padding_top;
    double pending = 0.0;
    bool first_block = true;
    std::size_t index = 0U;
    while (index < page_.blocks.size()) {
        const Block &block = page_.blocks[index];
        layout_block_ = index;
        const double indent = nested_indent * static_cast<double>(block.depth);
        const double left = page_padding_x + indent;
        const double available = std::max(80.0, column - indent);
        if (block.kind == BlockKind::figure && figure_size(block.target).width <= 0.0) {
            // No specimen of this control: no figure, and no space for one.
            ++index;
            continue;
        }
        double top_margin = 0.0;
        double bottom_margin = 0.0;
        switch (block.kind) {
        case BlockKind::heading1: top_margin = 0.0; bottom_margin = 4.0; break;
        case BlockKind::heading2: top_margin = 22.0; bottom_margin = 8.0; break;
        case BlockKind::heading3: top_margin = 16.0; bottom_margin = 6.0; break;
        case BlockKind::paragraph: top_margin = 6.0; bottom_margin = 8.0; break;
        case BlockKind::signature: top_margin = 14.0; bottom_margin = 4.0; break;
        case BlockKind::term: top_margin = 8.0; bottom_margin = 0.0; break;
        case BlockKind::definition: top_margin = 2.0; bottom_margin = 0.0; break;
        case BlockKind::code: top_margin = 8.0; bottom_margin = 12.0; break;
        case BlockKind::table_header:
        case BlockKind::table_row: top_margin = 8.0; bottom_margin = 14.0; break;
        case BlockKind::figure: top_margin = 10.0; bottom_margin = 12.0; break;
        case BlockKind::card: top_margin = 10.0; bottom_margin = 10.0; break;
        }
        y += first_block ? 0.0 : std::max(top_margin, pending);
        first_block = false;
        pending = bottom_margin;
        if (!block.anchor.empty())
            anchors_.push_back(Anchor{block.anchor, y});
        Flow flow{};
        flow.left = left;
        flow.width = available;
        flow.line_height = body_line;
        flow.body = f.body;
        flow.code = f.code;
        flow.part = Part::text;
        std::size_t next = index + 1U;
        switch (block.kind) {
        case BlockKind::heading1:
        case BlockKind::heading2: {
            const bool first_level = block.kind == BlockKind::heading1;
            flow.body = first_level ? f.heading1 : f.heading2;
            flow.code = f.code;
            flow.code.size = flow.body.size;
            flow.code.weight = flow.body.weight;
            flow.line_height = std::round(flow.body.size * 1.3);
            flow.part = Part::heading;
            y = flow_runs(block.runs, flow, y);
            y += first_level ? 6.0 : 3.0;
            boxes_.push_back(Box{gf::Rect{left, y, available, 1.0}, first_level ? Part::heading_rule : Part::section_rule, no_link});
            y += 1.0;
            break;
        }
        case BlockKind::heading3:
            flow.body = f.heading3;
            flow.part = Part::heading;
            y = flow_runs(block.runs, flow, y);
            break;
        case BlockKind::paragraph:
            flow.width = std::min(available, paragraph_width);
            y = flow_runs(block.runs, flow, y);
            break;
        case BlockKind::term:
            y = flow_runs(block.runs, flow, y);
            break;
        case BlockKind::definition:
            flow.left = left + definition_indent;
            flow.width = std::min(available - definition_indent, paragraph_width);
            y = flow_runs(block.runs, flow, y);
            break;
        case BlockKind::signature: {
            const std::size_t box_index = boxes_.size();
            boxes_.push_back(Box{gf::Rect{left, y, available, 0.0}, Part::signature, no_link});
            boxes_.push_back(Box{gf::Rect{left, y, 3.0, 0.0}, Part::signature_bar, no_link});
            std::uint64_t state = 0U;
            double bottom = y;
            const std::string_view line = block.lines.empty() ? std::string_view{} : std::string_view(block.lines[0]);
            place_code(line, left + 11.0, y + 5.0, code_line, f.code, available - 19.0, state, bottom);
            boxes_[box_index].bounds.height = bottom + 5.0 - y;
            boxes_[box_index + 1U].bounds.height = bottom + 5.0 - y;
            y = bottom + 5.0;
            break;
        }
        case BlockKind::code: {
            const std::size_t box_index = boxes_.size();
            boxes_.push_back(Box{gf::Rect{left, y, available, 0.0}, Part::code_block, no_link});
            std::uint64_t state = 0U;
            double line_top = y + 10.0;
            double widest = left + available;
            for (const std::string &line : block.lines) {
                double bottom = line_top;
                const double line_right =
                    place_code(line, left + 12.0, line_top, code_line, f.code, 0.0, state, bottom);
                widest = std::max(widest, line_right + 12.0);
                line_top = bottom;
            }
            boxes_[box_index].bounds.width = widest - left;
            boxes_[box_index].bounds.height = line_top + 10.0 - y;
            right = std::max(right, widest + page_padding_x);
            y = line_top + 10.0;
            break;
        }
        case BlockKind::table_header:
        case BlockKind::table_row:
            while (next < page_.blocks.size() &&
                   (page_.blocks[next].kind == BlockKind::table_row) && page_.blocks[next].depth == block.depth)
                ++next;
            y = lay_out_table(index, next, left, available, y);
            break;
        case BlockKind::figure: {
            // The control's specimen at its own size, shrunk to fit. A
            // control with no specimen (a component, a dialog) has no
            // figure, so the block shows nothing.
            const gf::Size image = figure_size(block.target);
            const double fit = std::min(1.0, (available - 2.0) / image.width);
            const double box_width = std::round(image.width * fit) + 2.0;
            const double box_height = std::round(image.height * fit) + 2.0;
            boxes_.push_back(Box{gf::Rect{left, y, box_width, box_height}, Part::preview, no_link, block.target});
            flow.body = f.caption;
            flow.line_height = std::round(f.caption.size * 1.4);
            flow.part = Part::caption;
            flow.width = std::min(available, 420.0 * unit);
            y = flow_runs(block.runs, flow, y + box_height + 4.0);
            break;
        }
        case BlockKind::card:
            while (next < page_.blocks.size() && page_.blocks[next].kind == BlockKind::card)
                ++next;
            y = lay_out_cards(index, next, left, available, y);
            break;
        }
        index = next;
    }
    content_height_ = y + page_padding_bottom;
    content_width_ = right;
    // The laid text does not change with the width, so a selection made at
    // another width still names the same text; a shorter text (none here)
    // would clamp it.
    selection_anchor_ = std::min(selection_anchor_, laid_text_size_);
    selection_caret_ = std::min(selection_caret_, laid_text_size_);
    if (!query_.empty()) {
        const std::size_t keep = current_match_;
        const std::string query = query_;
        find(query, match_case_);
        if (keep < matches_.size())
            current_match_ = keep;
    }
}

gf::Size ReferencePage::measure(gf::Size available) {
    const gf::Rect requested = requested_bounds();
    const gf::Size result{requested.width > 0.0 ? requested.width : std::min(available.width, 640.0),
                          requested.height > 0.0 ? requested.height : std::min(available.height, 480.0)};
    return result;
}

void ReferencePage::arrange(gf::Rect final_bounds) {
    // ScrollableControl::arrange measures no children here and so clamps
    // the position to nothing; the page's own extent is set below, and the
    // position it had is put back within it.
    const gf::Point kept = scroll_position();
    ScrollableControl::arrange(final_bounds);
    relayout();
    arrange_scroll_viewport(gf::Size{final_bounds.width, final_bounds.height},
                            gf::Size{content_width_, content_height_});
    const gf::Rect viewport = viewport_rectangle();
    if (viewport.width > 0.0 && std::abs(viewport.width - laid_width_) > 0.5) {
        relayout();
        arrange_scroll_viewport(gf::Size{final_bounds.width, final_bounds.height},
                                gf::Size{content_width_, content_height_});
    }
    scroll_to(kept);
    if (final_bounds.height > 0.0) {
        if (!pending_anchor_.empty()) {
            const std::string anchor = pending_anchor_;
            pending_anchor_.clear();
            static_cast<void>(apply_anchor(anchor));
        }
        if (pending_reveal_) {
            reveal_current_match();
            pending_reveal_ = false;
        }
    }
}

std::vector<ReferencePage::TextPlacement> ReferencePage::text_placements() const {
    std::vector<TextPlacement> placements;
    placements.reserve(pieces_.size());
    for (const Piece &piece : pieces_) {
        TextPlacement placement{};
        placement.bounds = piece.bounds;
        placement.baseline = piece.baseline;
        placement.text = std::string(piece.text);
        placement.code = piece.font.role == gf::FontRole::monospace;
        if (piece.cell != no_cell) {
            for (const CellBounds &cell : cells_) {
                if (cell.block == piece.block && cell.cell == piece.cell) {
                    placement.in_table = true;
                    placement.cell = cell.bounds;
                }
            }
        }
        placements.push_back(std::move(placement));
    }
    return placements;
}

gf::Point ReferencePage::content_offset() const noexcept {
    const gf::Rect viewport = viewport_rectangle();
    const gf::Point scrolled = scroll_position();
    return gf::Point{viewport.x - scrolled.x, viewport.y - scrolled.y};
}

// --- Links ---------------------------------------------------------------------------

std::size_t ReferencePage::link_at(gf::Point local) const noexcept {
    const gf::Point offset = content_offset();
    const gf::Point content{local.x - offset.x, local.y - offset.y};
    for (const Piece &piece : pieces_) {
        if (piece.link != no_link && piece.bounds.contains(content))
            return piece.link;
    }
    for (const Box &box : boxes_) {
        if (box.link != no_link && box.bounds.contains(content))
            return box.link;
    }
    return no_link;
}

// --- Selection ----------------------------------------------------------------------

std::size_t ReferencePage::piece_at(std::size_t offset) const noexcept {
    // The last piece starting at or before `offset` (house lower bound over
    // text_start, which rises with the index).
    std::size_t low = 0U;
    std::size_t high = pieces_.size();
    while (high - low > 1U) {
        const std::size_t middle = low + (high - low) / 2U;
        if (pieces_[middle].text_start <= offset)
            low = middle;
        else
            high = middle;
    }
    return low;
}

std::size_t ReferencePage::offset_at(gf::Point content) const {
    if (pieces_.empty())
        return 0U;
    // The piece under the point, else the nearest: first by line (a point
    // between the cells of a row is on their line), then along it.
    std::size_t best = 0U;
    double best_vertical = std::numeric_limits<double>::infinity();
    double best_horizontal = std::numeric_limits<double>::infinity();
    for (std::size_t index = 0U; index < pieces_.size(); ++index) {
        const gf::Rect &bounds = pieces_[index].bounds;
        double vertical = 0.0;
        if (content.y < bounds.y)
            vertical = bounds.y - content.y;
        else if (content.y >= bounds.y + bounds.height)
            vertical = content.y - (bounds.y + bounds.height) + 0.5;
        double horizontal = 0.0;
        if (content.x < bounds.x)
            horizontal = bounds.x - content.x;
        else if (content.x > bounds.x + bounds.width)
            horizontal = content.x - (bounds.x + bounds.width);
        if (vertical < best_vertical || (vertical == best_vertical && horizontal < best_horizontal)) {
            best = index;
            best_vertical = vertical;
            best_horizontal = horizontal;
        }
    }
    const Piece &piece = pieces_[best];
    const double into = content.x - piece.bounds.x;
    if (into <= 0.0)
        return piece.text_start;
    if (into >= piece.bounds.width)
        return piece.text_start + piece.text.size();
    // The character boundary nearest the point: the last whose head fits,
    // by halving, then that one or the next, whichever is nearer.
    std::size_t low = 0U;
    std::size_t high = piece.text.size();
    while (high > low) {
        const std::size_t middle = character_start(piece.text, low + (high - low + 1U) / 2U);
        if (middle <= low)
            break;
        if (width_of(piece.text.substr(0U, middle), piece.font) <= into)
            low = middle;
        else
            high = middle - 1U;
    }
    std::size_t chosen = low;
    if (low < piece.text.size()) {
        const std::size_t next = next_character(piece.text, low);
        const double before = width_of(piece.text.substr(0U, low), piece.font);
        const double after = width_of(piece.text.substr(0U, next), piece.font);
        if (after - into < into - before)
            chosen = next;
    }
    return piece.text_start + chosen;
}

void ReferencePage::set_selection(std::size_t anchor, std::size_t caret) {
    anchor = std::min(anchor, laid_text_size_);
    caret = std::min(caret, laid_text_size_);
    if (anchor == selection_anchor_ && caret == selection_caret_)
        return;
    selection_anchor_ = anchor;
    selection_caret_ = caret;
    // A selection only repaints: the layout does not depend on it.
    invalidate(gf::Dirty::paint);
}

void ReferencePage::select_all() { set_selection(0U, laid_text_size_); }

void ReferencePage::clear_selection() { set_selection(selection_caret_, selection_caret_); }

// A word: the run of word bytes about `offset`, across the pieces of one
// stream that join with no space (a name broken over two lines); a click on
// a space or a mark selects that character.
void ReferencePage::select_word_at(std::size_t offset) {
    if (pieces_.empty())
        return;
    std::size_t index = piece_at(offset);
    std::size_t local = offset - pieces_[index].text_start;
    if (local >= pieces_[index].text.size() && index + 1U < pieces_.size() &&
        pieces_[index + 1U].text_start == offset) {
        ++index;
        local = 0U;
    }
    const std::string_view text = pieces_[index].text;
    if (local >= text.size() || !is_word_byte(text[local])) {
        if (local > 0U && local <= text.size() && is_word_byte(text[local - 1U])) {
            --local;
        } else {
            const std::size_t begin = pieces_[index].text_start + character_start(text, local);
            const std::size_t end =
                local < text.size() ? pieces_[index].text_start + next_character(text, character_start(text, local))
                                    : begin;
            set_selection(begin, end);
            return;
        }
    }
    // Backward, then forward, from the byte under the click.
    std::size_t first_piece = index;
    std::size_t begin = local;
    while (true) {
        const std::string_view piece_text = pieces_[first_piece].text;
        while (begin > 0U && is_word_byte(piece_text[begin - 1U]))
            --begin;
        const bool joins = begin == 0U && first_piece > 0U &&
                           pieces_[first_piece - 1U].stream == pieces_[first_piece].stream &&
                           pieces_[first_piece].lead_spaces == 0U && !pieces_[first_piece - 1U].text.empty() &&
                           is_word_byte(pieces_[first_piece - 1U].text.back());
        if (!joins)
            break;
        --first_piece;
        begin = pieces_[first_piece].text.size();
    }
    std::size_t last_piece = index;
    std::size_t end = local;
    while (true) {
        const std::string_view piece_text = pieces_[last_piece].text;
        while (end < piece_text.size() && is_word_byte(piece_text[end]))
            ++end;
        const bool joins = end == piece_text.size() && last_piece + 1U < pieces_.size() &&
                           pieces_[last_piece + 1U].stream == pieces_[last_piece].stream &&
                           pieces_[last_piece + 1U].lead_spaces == 0U && !pieces_[last_piece + 1U].text.empty() &&
                           is_word_byte(pieces_[last_piece + 1U].text.front());
        if (!joins)
            break;
        ++last_piece;
        end = 0U;
    }
    set_selection(pieces_[first_piece].text_start + begin, pieces_[last_piece].text_start + end);
}

// A line of prose or code, or a table cell: the whole stream.
void ReferencePage::select_stream_at(std::size_t offset) {
    if (pieces_.empty())
        return;
    const std::size_t index = piece_at(offset);
    std::size_t first = index;
    while (first > 0U && pieces_[first - 1U].stream == pieces_[index].stream)
        --first;
    std::size_t last = index;
    while (last + 1U < pieces_.size() && pieces_[last + 1U].stream == pieces_[index].stream)
        ++last;
    set_selection(pieces_[first].text_start, pieces_[last].text_start + pieces_[last].text.size());
}

std::string ReferencePage::selected_text() const {
    std::string text;
    const std::size_t low = std::min(selection_anchor_, selection_caret_);
    const std::size_t high = std::max(selection_anchor_, selection_caret_);
    if (low == high || pieces_.empty())
        return text;
    const Piece *previous = nullptr;
    for (std::size_t index = piece_at(low); index < pieces_.size(); ++index) {
        const Piece &piece = pieces_[index];
        const std::size_t start = piece.text_start;
        const std::size_t end = start + piece.text.size();
        if (start >= high)
            break;
        if (end <= low)
            continue;
        if (previous != nullptr) {
            // What joins two pieces: nothing within a stream; a tab between
            // the cells of a row (one per cell passed); a line break within
            // a block (one per code line passed, so blank lines stay) and
            // between table rows; a blank line between other blocks. Spaces
            // end no line.
            const Piece &before = *previous;
            std::size_t tabs = 0U;
            std::size_t breaks = 0U;
            if (piece.block == before.block && piece.stream != before.stream) {
                if (piece.cell != no_cell && before.cell != no_cell && piece.cell > before.cell)
                    tabs = piece.cell - before.cell;
                else
                    breaks = std::max<std::size_t>(1U, piece.stream - before.stream);
            } else if (piece.block != before.block) {
                breaks = piece.cell != no_cell && before.cell != no_cell ? 1U : 2U;
                if (piece.cell != no_cell)
                    tabs = piece.cell;
            }
            if (tabs > 0U || breaks > 0U) {
                while (!text.empty() && text.back() == ' ')
                    text.pop_back();
            }
            text.append(breaks, '\n');
            text.append(tabs, '\t');
            text.append(piece.lead_spaces, ' ');
        }
        const std::size_t from = std::max(low, start) - start;
        const std::size_t to = std::min(high, end) - start;
        text.append(piece.text.substr(from, to - from));
        previous = &piece;
    }
    return text;
}

bool ReferencePage::copy() {
    const std::string text = selected_text();
    if (text.empty())
        return false;
    const gf::BorrowedPointer<gf::Window> owner = attached_window();
    if (!owner)
        return false;
    gf::HostServices *services = (*owner).host_services();
    if (services == nullptr)
        return false;
    const gf::HostServiceStatus written = (*services).write_clipboard_text(text);
    return written.accepted();
}

void ReferencePage::on_routed_command(const gf::CommandInvocation &invocation) {
    if (invocation.command_id == "copy")
        static_cast<void>(copy());
    else if (invocation.command_id == "select-all")
        select_all();
}

void ReferencePage::on_menu_item(const gf::MenuItemInvocation &invocation) {
    if (invocation.item_id == "copy")
        static_cast<void>(copy());
    else if (invocation.item_id == "select-all")
        select_all();
}

// --- Input ---------------------------------------------------------------------------

void ReferencePage::handle_mouse(gf::MouseEventArgs &arguments) {
    scroll_pointer(arguments);
    if (arguments.handled)
        return;
    const gf::Point local = arguments.location;
    const gf::Point offset = content_offset();
    const gf::Point content{local.x - offset.x, local.y - offset.y};
    const std::size_t link = link_at(local);
    if (arguments.action == gf::PointerAction::move) {
        if (link != hovered_link_) {
            hovered_link_ = link;
            cursor = stxlib::Optional<gf::CursorKind>::of(link != no_link ? gf::CursorKind::hand : gf::CursorKind::text);
            if (listener_ != nullptr)
                (*listener_).hover_link(link != no_link ? std::string_view(page_.links[link]) : std::string_view{});
            invalidate(gf::Dirty::paint);
        }
        // A press on a link that moves on selects from where it began.
        if (pressed_link_ != no_link && (std::abs(local.x - press_location_.x) > drag_slop ||
                                         std::abs(local.y - press_location_.y) > drag_slop)) {
            pressed_link_ = no_link;
            selecting_ = true;
            const std::size_t from =
                offset_at(gf::Point{press_location_.x - offset.x, press_location_.y - offset.y});
            set_selection(from, from);
            invalidate(gf::Dirty::paint);
        }
        if (selecting_)
            set_selection(selection_anchor_, offset_at(content));
    } else if (arguments.action == gf::PointerAction::down && arguments.button == gf::PointerButton::primary) {
        press_location_ = local;
        const bool extend = gf::has_modifier(arguments.modifiers, gf::Modifier::shift);
        if (link != no_link && !extend && arguments.clicks <= 1U) {
            pressed_link_ = link;
            arguments.handled = true;
            invalidate(gf::Dirty::paint);
            return;
        }
        pressed_link_ = no_link;
        const std::size_t at = offset_at(content);
        if (extend)
            set_selection(selection_anchor_, at);
        else if (arguments.clicks == 2U)
            select_word_at(at);
        else if (arguments.clicks >= 3U)
            select_stream_at(at);
        else
            set_selection(at, at);
        // A double or triple click keeps its unit; a drag after it moves
        // the caret by character from the unit's start.
        selecting_ = arguments.clicks <= 1U || extend;
    } else if (arguments.action == gf::PointerAction::up && arguments.button == gf::PointerButton::primary) {
        selecting_ = false;
        const std::size_t pressed = pressed_link_;
        pressed_link_ = no_link;
        invalidate(gf::Dirty::paint);
        if (pressed != no_link && pressed == link && listener_ != nullptr) {
            arguments.handled = true;
            const std::string target = page_.links[link];
            (*listener_).open_link(target);
        }
    }
}

void ReferencePage::on_key_down(gf::KeyEventArgs &arguments) {
    ScrollableControl::on_key_down(arguments);
    if (arguments.handled || !has_command_modifier(arguments.modifiers))
        return;
    if (arguments.physical_key == gf::PhysicalKey::c && has_selection()) {
        static_cast<void>(copy());
        arguments.handled = true;
    } else if (arguments.physical_key == gf::PhysicalKey::a) {
        select_all();
        arguments.handled = true;
    }
}

void ReferencePage::on_context_menu_requested(gf::ContextMenuRequest &request) {
    if (!request.handled) {
        if (context_menu_ == nullptr) {
            context_menu_ = std::make_unique<gf::ContextMenu>(std::string(stable_id().value()) + ".context-menu");
            gf::on((*context_menu_).item_invoked(), *this, &ReferencePage::on_menu_item);
        }
        std::vector<gf::MenuItemSpec> items;
        gf::MenuItemSpec copy_item{"copy", gf::MenuItemKind::command, {}, "&Copy"};
        copy_item.enabled = has_selection();
        items.push_back(std::move(copy_item));
        gf::MenuItemSpec select_all_item{"select-all", gf::MenuItemKind::command, {}, "Select &All"};
        select_all_item.enabled = laid_text_size_ > 0U;
        items.push_back(std::move(select_all_item));
        (*context_menu_).set_items(std::move(items));
        const gf::MenuOpenMode mode =
            request.origin == gf::ContextRequestOrigin::keyboard ? gf::MenuOpenMode::keyboard : gf::MenuOpenMode::pointer;
        (*context_menu_).show(shared_from_this(), request.window_position, mode);
        request.handled = true;
    }
    ScrollableControl::on_context_menu_requested(request);
}

void ReferencePage::on_mouse_down(gf::MouseEventArgs &arguments) {
    handle_mouse(arguments);
    Control::on_mouse_down(arguments);
}

void ReferencePage::on_mouse_up(gf::MouseEventArgs &arguments) {
    handle_mouse(arguments);
    Control::on_mouse_up(arguments);
}

void ReferencePage::on_mouse_move(gf::MouseEventArgs &arguments) {
    handle_mouse(arguments);
    Control::on_mouse_move(arguments);
}

void ReferencePage::on_mouse_wheel(gf::MouseEventArgs &arguments) {
    handle_mouse(arguments);
    Control::on_mouse_wheel(arguments);
}

void ReferencePage::on_mouse_leave() {
    scroll_pointer_left();
    if (hovered_link_ != no_link) {
        hovered_link_ = no_link;
        cursor = stxlib::Optional<gf::CursorKind>::of(gf::CursorKind::text);
        if (listener_ != nullptr)
            (*listener_).hover_link(std::string_view{});
        invalidate(gf::Dirty::paint);
    }
    Control::on_mouse_leave();
}

// --- Paint ---------------------------------------------------------------------------

void ReferencePage::set_figures(const Book *book, std::shared_ptr<gf::ImageList> images) {
    figure_book_ = book;
    figure_images_ = std::move(images);
    relayout();
}

gf::Size ReferencePage::figure_size(const std::string &id) {
    if (figure_book_ == nullptr || figure_images_ == nullptr || id.empty())
        return gf::Size{};
    gf::ImageList &images = *figure_images_;
    if (!images.contains_key(id)) {
        for (const FigureImage &figure : (*figure_book_).figures()) {
            if (figure.id != id)
                continue;
            const std::span<const std::byte> png(reinterpret_cast<const std::byte *>(figure.png.data()),
                                                 figure.png.size());
            if (!images.contains_key(id))
                static_cast<void>(images.add_png(id, png, static_cast<double>(figure.density)));
            else
                static_cast<void>(images.set_variant_png(id, gf::ImageVisualState::normal,
                                                         static_cast<double>(figure.density), png));
        }
        if (!images.contains_key(id))
            return gf::Size{};
    }
    const gf::ImageListResolution resolved = images.resolve(std::string_view(id), gf::ImageVisualState::normal, 1.0);
    if (!resolved || resolved.resolved_scale <= 0.0)
        return gf::Size{};
    return gf::Size{resolved.source_size.width / resolved.resolved_scale,
                    resolved.source_size.height / resolved.resolved_scale};
}

void ReferencePage::paint_box(gf::Painter &painter, const Box &box, gf::Point offset) const {
    gf::PartPaint part{};
    part.family = gf::ControlVisualRole::editor;
    part.role = part_roles[static_cast<std::size_t>(box.part)];
    part.bounds = gf::Rect{box.bounds.x + offset.x, box.bounds.y + offset.y, box.bounds.width, box.bounds.height};
    if (box.link != no_link && box.link == hovered_link_)
        part.states.insert(gf::AnatomyState::hot);
    part.key.set(gf::PartKey{part_names[static_cast<std::size_t>(box.part)], {}, {}});
    gf::paint_part(painter, *this, part);
    if (!box.figure.empty() && figure_images_ != nullptr) {
        double scale = 1.0;
        const gf::BorrowedPointer<gf::SurfaceRoot> root = attached_surface_root();
        if (root)
            scale = (*root).scale();
        const gf::ImageListResolution resolved =
            (*figure_images_).resolve(std::string_view(box.figure), gf::ImageVisualState::normal, scale);
        if (resolved)
            painter.draw_image(resolved.image, gf::Rect{part.bounds.x + 1.0, part.bounds.y + 1.0,
                                                        part.bounds.width - 2.0, part.bounds.height - 2.0});
    }
}

void ReferencePage::paint_piece(gf::Painter &painter, const Piece &piece, gf::Point offset) const {
    gf::PartPaint part{};
    part.family = piece.part == Part::link ? gf::ControlVisualRole::link : gf::ControlVisualRole::editor;
    part.role = gf::PartRole::label;
    part.font = piece.font;
    part.text = gf::lend_paint_text(piece.text);
    if (piece.link != no_link && piece.link == hovered_link_)
        part.states.insert(gf::AnatomyState::hot);
    if (piece.link != no_link && piece.link == pressed_link_)
        part.states.insert(gf::AnatomyState::pressed);
    part.key.set(gf::PartKey{part_names[static_cast<std::size_t>(piece.part)], {}, {}});
    const gf::Rect bounds{piece.bounds.x + offset.x, piece.bounds.y + offset.y, piece.bounds.width + 2.0,
                          piece.bounds.height};
    gf::paint_text_part_at(painter, *this, part, gf::Point{bounds.x, piece.baseline + offset.y}, bounds.width);
    if (piece.link != no_link && piece.link == hovered_link_) {
        gf::PartPaint underline{};
        underline.family = gf::ControlVisualRole::link;
        underline.role = gf::PartRole::glyph;
        underline.mark = gf::PartMark::underline;
        underline.bounds = gf::Rect{bounds.x, bounds.y, piece.bounds.width, piece.baseline + offset.y + 2.0 - bounds.y};
        underline.states = part.states;
        gf::paint_part(painter, *this, underline);
    }
}

// The selection behind the text it holds: whole pieces by their bounds, the
// pieces at its two ends measured to the offset. Painting measures at most
// those two; the selection never lays out.
void ReferencePage::paint_selection(gf::Painter &painter, gf::Point offset, double visible_top,
                                    double visible_bottom) const {
    const std::size_t low = std::min(selection_anchor_, selection_caret_);
    const std::size_t high = std::max(selection_anchor_, selection_caret_);
    if (low == high || pieces_.empty())
        return;
    for (std::size_t index = piece_at(low); index < pieces_.size(); ++index) {
        const Piece &piece = pieces_[index];
        const std::size_t start = piece.text_start;
        const std::size_t end = start + piece.text.size();
        if (start >= high)
            break;
        if (end <= low)
            continue;
        if (piece.bounds.y + piece.bounds.height < visible_top || piece.bounds.y > visible_bottom)
            continue;
        double left = piece.bounds.x;
        double right = piece.bounds.x + piece.bounds.width;
        if (start < low)
            left += width_of(piece.text.substr(0U, low - start), piece.font);
        if (end > high)
            right = piece.bounds.x + width_of(piece.text.substr(0U, high - start), piece.font);
        Box mark{};
        mark.bounds = gf::Rect{left, piece.bounds.y, right - left, piece.bounds.height};
        mark.part = Part::selection;
        paint_box(painter, mark, offset);
    }
}

void ReferencePage::on_paint(gf::Painter &painter, gf::Rect) {
    const gf::Rect bounds = client_rectangle();
    gf::PartPaint paper{};
    paper.family = gf::ControlVisualRole::editor;
    paper.role = gf::PartRole::face;
    paper.bounds = bounds;
    paper.corner_radius.set(0.0);
    paper.key.set(gf::PartKey{"paper", {}, {}});
    gf::paint_part(painter, *this, paper);
    const gf::Rect viewport = viewport_rectangle();
    const gf::Point offset = content_offset();
    const double visible_top = viewport.y - offset.y;
    const double visible_bottom = visible_top + viewport.height;
    painter.save();
    painter.clip_rect(viewport);
    for (const Box &box : boxes_) {
        if (box.bounds.y + box.bounds.height < visible_top || box.bounds.y > visible_bottom)
            continue;
        paint_box(painter, box, offset);
    }
    for (std::size_t index = 0U; index < matches_.size(); ++index) {
        const Match &match = matches_[index];
        const Piece &piece = pieces_[match.piece];
        if (piece.bounds.y + piece.bounds.height < visible_top || piece.bounds.y > visible_bottom)
            continue;
        const double before = width_of(piece.text.substr(0U, match.begin), piece.font);
        const double width = width_of(piece.text.substr(match.begin, match.length), piece.font);
        Box mark{};
        mark.bounds = gf::Rect{piece.bounds.x + before - 1.0, piece.bounds.y + 1.0, width + 2.0, piece.bounds.height - 2.0};
        mark.part = index == current_match_ ? Part::find_current : Part::find_match;
        paint_box(painter, mark, offset);
    }
    paint_selection(painter, offset, visible_top, visible_bottom);
    for (const Piece &piece : pieces_) {
        if (piece.bounds.y + piece.bounds.height < visible_top || piece.bounds.y > visible_bottom)
            continue;
        paint_piece(painter, piece, offset);
    }
    painter.restore();
}

} // namespace pocket_reference
