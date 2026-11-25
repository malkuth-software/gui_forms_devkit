// The mockup factory's window: see mockup_factory.hpp.

#include "mockup_factory.hpp"

#include "gui_forms/automation/tools/model_tools.hpp"
#include "gui_forms/event/event/event.hpp"
#include "gui_forms/forms/form_documents/form_documents.hpp"
#include "gui_forms/window/presentation/presentation_types.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace gui_forms::mockup {

namespace {

constexpr double catalogue_width = 220.0;
constexpr double refusal_height = 150.0;
constexpr double status_height = 24.0;
constexpr std::size_t maximum_line_bytes = 4000U;

// The familiar themes the Theme menu lists (every one but the base it
// repeats, windows-professional).
constexpr FamiliarTheme listed_familiar_themes[] = {
    FamiliarTheme::classic, FamiliarTheme::modern_flat, FamiliarTheme::xp_style,
    FamiliarTheme::windows7_style, FamiliarTheme::macos_style,
};

[[nodiscard]] std::string_view text_of(stxlib::View<char> view) noexcept {
    if (view.data() == nullptr) return std::string_view();
    const std::string_view text(view.data(), static_cast<std::size_t>(view.count()));
    return text;
}

[[nodiscard]] stxlib::View<char> view_of(std::string_view text) noexcept {
    const stxlib::View<char> view(text.data(), static_cast<stxlib::usize>(text.size()));
    return view;
}

// `text` as a JSON string's body: '"' and '\\' escaped, control bytes as
// \u00XX.
[[nodiscard]] std::string json_body(std::string_view text) {
    constexpr char hex_digits[] = "0123456789abcdef";
    std::string escaped{};
    escaped.reserve(text.size());
    for (const char character : text) {
        const unsigned char byte = static_cast<unsigned char>(character);
        if (character == '"' || character == '\\') {
            escaped.push_back('\\');
            escaped.push_back(character);
        } else if (byte < 0x20U) {
            escaped.append("\\u00");
            escaped.push_back(hex_digits[byte >> 4U]);
            escaped.push_back(hex_digits[byte & 0x0FU]);
        } else {
            escaped.push_back(character);
        }
    }
    return escaped;
}

// The string value of `"<key>": "<value>"` in a flat JSON object, its
// escapes `\"` and `\\` read; none when the key is absent.
[[nodiscard]] std::optional<std::string> json_string_member(std::string_view json, std::string_view key) {
    const std::string quoted = "\"" + std::string(key) + "\"";
    const std::size_t at = json.find(quoted);
    if (at == std::string_view::npos) return std::nullopt;
    std::size_t position = json.find(':', at + quoted.size());
    if (position == std::string_view::npos) return std::nullopt;
    position = json.find('"', position);
    if (position == std::string_view::npos) return std::nullopt;
    std::string value{};
    for (++position; position < json.size() && json[position] != '"'; ++position) {
        if (json[position] == '\\' && position + 1U < json.size()) ++position;
        value.push_back(json[position]);
    }
    if (position >= json.size()) return std::nullopt;
    return value;
}

void reply_text(ModelToolReply& reply, const std::string& text) {
    static_cast<void>(reply.text(text.data(), text.size()));
}

[[nodiscard]] std::string_view base_id(ThemeBase base) noexcept {
    if (base == ThemeBase::gui_forms) return "gui-forms";
    return "windows-professional";
}

// The menu's item IDs.
constexpr std::string_view reload_item = "file.reload";
constexpr std::string_view gui_forms_item = "theme.gui-forms";
constexpr std::string_view professional_item = "theme.windows-professional";
constexpr std::string_view sheet_item = "theme.sheet";
constexpr std::string_view familiar_prefix = "theme.familiar.";
constexpr std::string_view system_item = "scheme.system";
constexpr std::string_view light_item = "scheme.light";
constexpr std::string_view dark_item = "scheme.dark";
constexpr std::string_view open_prefix = "open.";

[[nodiscard]] MenuItemSpec item(std::string_view id, MenuItemKind kind, std::string text, bool checked) {
    MenuItemSpec spec(std::string(id), kind, {}, std::move(text));
    spec.checked = checked;
    return spec;
}

[[nodiscard]] MenuItemSpec separator(std::string id) {
    MenuItemSpec spec(std::move(id), MenuItemKind::separator);
    return spec;
}

// The MCP tools' handlers: `context` is the factory.
void list_tool(void* context, const ModelToolCall&, ModelToolReply& reply) {
    const MockupFactory& factory = *static_cast<const MockupFactory*>(context);
    std::string text = "{\"mockups\":[";
    const std::vector<MockupFiles>& catalogue = factory.catalogue();
    for (std::size_t index = 0U; index < catalogue.size(); ++index) {
        if (index != 0U) text.push_back(',');
        text.append("\"" + json_body(catalogue[index].name) + "\"");
    }
    text.append("]}");
    reply_text(reply, text);
}

void open_tool(void* context, const ModelToolCall& call, ModelToolReply& reply) {
    MockupFactory& factory = *static_cast<MockupFactory*>(context);
    const std::string_view arguments(call.arguments_json, call.arguments_bytes);
    const std::optional<std::string> name = json_string_member(arguments, "name");
    const std::optional<std::size_t> index = name ? find_mockup(factory.catalogue(), *name) : std::nullopt;
    if (!index) {
        reply.fail(ModelToolError::not_found, "no mockup of that name", "mockup.list lists the names");
        return;
    }
    static_cast<void>(factory.open(*index));
    const std::string text = factory.refusal().empty() ? std::string("opened") : factory.refusal();
    reply_text(reply, text);
}

void reload_tool(void* context, const ModelToolCall&, ModelToolReply& reply) {
    MockupFactory& factory = *static_cast<MockupFactory*>(context);
    factory.reload();
    const std::string text = factory.refusal().empty() ? std::string("reloaded") : factory.refusal();
    reply_text(reply, text);
}

void check_tool(void* context, const ModelToolCall&, ModelToolReply& reply) {
    MockupFactory& factory = *static_cast<MockupFactory*>(context);
    const std::string text = check_text(factory.mockup().check());
    reply_text(reply, text.empty() ? std::string("no diagnostics") : text);
}

void events_tool(void* context, const ModelToolCall&, ModelToolReply& reply) {
    MockupFactory& factory = *static_cast<MockupFactory*>(context);
    const FormMockup& mockup = factory.mockup();
    std::string text = "{\"handlers\":[";
    for (stxlib::usize index = 0U; index < mockup.handler_count(); ++index) {
        const FormMockupHandler handler = mockup.handler(index);
        if (index != 0U) text.push_back(',');
        text.append("{\"handler\":\"" + json_body(text_of(handler.handler)) + "\",\"id\":\"" +
                    json_body(text_of(handler.stable_id)) + "\",\"interaction\":\"" +
                    json_body(text_of(handler.interaction)) + "\",\"observed\":" +
                    (handler.observed ? "true" : "false") + "}");
    }
    text.append("],\"events\":[");
    for (stxlib::usize index = 0U; index < mockup.event_count(); ++index) {
        const FormMockupEvent event = mockup.event(index);
        if (index != 0U) text.push_back(',');
        text.append("{\"sequence\":" + std::to_string(event.sequence) + ",\"handler\":\"" +
                    json_body(text_of(event.handler)) + "\",\"id\":\"" + json_body(text_of(event.stable_id)) +
                    "\",\"interaction\":\"" + json_body(text_of(event.interaction)) + "\"}");
    }
    text.append("]}");
    reply_text(reply, text);
}

struct ToolEntry final {
    const char* name;
    const char* description;
    const char* input_schema;
    ModelToolAccess access;
    bool settles;
    ModelToolHandler handler;
};

constexpr ToolEntry factory_tools[] = {
    {"mockup.list", "Lists the mockups of the catalogue by name.", nullptr, ModelToolAccess::read_only, false,
     &list_tool},
    {"mockup.open", "Opens the mockup named `name` (as mockup.list gives it).",
     "{\"type\":\"object\",\"properties\":{\"name\":{\"type\":\"string\"}},\"required\":[\"name\"]}",
     ModelToolAccess::acting, true, &open_tool},
    {"mockup.reload", "Reads the shown mockup's files again and shows them, or says why they are refused.",
     nullptr, ModelToolAccess::acting, true, &reload_tool},
    {"mockup.check", "The last load's diagnostics: file, line, column, code and message.", nullptr,
     ModelToolAccess::read_only, false, &check_tool},
    {"mockup.events",
     "The shown mockup's declared handlers and commands, and the events they recorded (oldest first).", nullptr,
     ModelToolAccess::read_only, false, &events_tool},
};

} // namespace

std::string check_text(const FormDocumentCheck& check) {
    std::string text{};
    for (stxlib::usize index = 0U; index < check.count(); ++index) {
        const FormDocumentDiagnostic found = check.diagnostic(index);
        std::string line = std::string(text_of(found.file)) + ":" + std::to_string(found.line) + ":" +
                           std::to_string(found.column) + ": " + (found.error ? "error " : "warning ") +
                           std::string(text_of(found.code_label)) + " " + std::string(text_of(found.code_name)) +
                           ": " + std::string(text_of(found.detail));
        if (line.size() > maximum_line_bytes) line.resize(maximum_line_bytes);
        if (!text.empty()) text.push_back('\n');
        text.append(line);
    }
    return text;
}

MockupFactory::MockupFactory(StableId stable_id) : Panel(std::move(stable_id)) {}

MockupFactory::~MockupFactory() = default;

void MockupFactory::configure(MockupFactorySetup setup) {
    catalogue_ = std::move(setup.catalogue);
    first_ = setup.opened;
    theme_ = setup.theme;
    scheme_ = setup.scheme;
    menu_ = make_control<MenuStrip>(StableId("mockup.menu"));
    (*menu_).dock = DockStyle::top;
    status_ = make_control<Label>(StableId("mockup.status"), std::string("No mockup is shown"));
    (*status_).dock = DockStyle::bottom;
    (*status_).set_requested_bounds(Rect{0.0, 0.0, window_size.width, status_height});
    refusal_box_ = make_control<TextBox>(StableId("mockup.refusal"));
    (*refusal_box_).multiline = true;
    (*refusal_box_).read_only = true;
    (*refusal_box_).dock = DockStyle::bottom;
    (*refusal_box_).set_requested_bounds(Rect{0.0, 0.0, window_size.width, refusal_height});
    (*refusal_box_).visible = false;
    host_ = make_control<Panel>(StableId("mockup.host"));
    (*host_).dock = DockStyle::fill;
    // Dock order: the last child added docks first, so the fill goes in
    // first and the edges after it.
    add_child(host_);
    if (setup.show_catalogue) {
        list_ = make_control<ListBox>(StableId("mockup.catalogue"));
        (*list_).dock = DockStyle::left;
        (*list_).set_requested_bounds(Rect{0.0, 0.0, catalogue_width, window_size.height});
        std::vector<std::string> names{};
        names.reserve(catalogue_.size());
        for (const MockupFiles& files : catalogue_) names.push_back(files.name);
        (*list_).items = std::move(names);
        on((*list_).selection_changed(), *this, &MockupFactory::on_catalogue_selection);
        add_child(list_);
    }
    add_child(refusal_box_);
    add_child(status_);
    add_child(menu_);
    mockup_ = std::make_unique<FormMockup>(*host_);
    (*mockup_).set_event_sink(&MockupFactory::event_recorded, this);
    build_menu();
    on((*menu_).item_invoked(), *this, &MockupFactory::on_menu);
}

void MockupFactory::attach(Window& window) {
    window_ = &window;
    watch_ = std::make_unique<Timer>(window, watch_interval);
    on((*watch_).tick(), *this, &MockupFactory::on_watch);
    (*watch_).start();
    register_tools();
    choose_scheme(scheme_);
    if (first_) static_cast<void>(open(*first_));
}

bool MockupFactory::open(std::size_t index) {
    if (index >= catalogue_.size()) return false;
    shown_ = index;
    reload();
    build_menu();
    return true;
}

void MockupFactory::reload() {
    if (!shown_) return;
    const MockupFiles& files = catalogue_[*shown_];
    stamps_ = mockup_stamps(files);
    const std::optional<std::string> form = read_mockup_file(files.form);
    if (!form) {
        show_refusal(files.form.generic_string() + ": cannot be read");
        return;
    }
    std::string fixture{};
    if (!files.fixture.empty()) {
        const std::optional<std::string> read = read_mockup_file(files.fixture);
        if (!read) {
            show_refusal(files.fixture.generic_string() + ": cannot be read");
            return;
        }
        fixture = *read;
    }
    sheet_text_.clear();
    if (!files.sheet.empty()) {
        const std::optional<std::string> read = read_mockup_file(files.sheet);
        if (read) sheet_text_ = *read;
    }
    const std::string form_name = files.form.generic_string();
    const std::string fixture_name = files.fixture.generic_string();
    FormMockupText document{};
    document.file = view_of(form_name);
    document.text = view_of(*form);
    FormMockupText data{};
    data.file = view_of(fixture_name);
    data.text = view_of(fixture);
    const FormMockupLoadOutcome outcome = (*mockup_).load(FormDocumentSchema::registry(), document, data);
    if (outcome == FormMockupLoadOutcome::refused) {
        const std::string text = check_text((*mockup_).check());
        std::fprintf(stderr, "%s\n", text.c_str());
        show_refusal(text);
        return;
    }
    show_refusal({});
    apply_theme();
    update_status();
}

void MockupFactory::choose_theme(const MockupTheme& theme) {
    theme_ = theme;
    apply_theme();
    build_menu();
}

void MockupFactory::choose_scheme(MockupScheme scheme) {
    scheme_ = scheme;
    if (window_ != nullptr) {
        PresentationOverrides overrides{};
        const PresentationOverrides* const current = (*window_).presentation_overrides();
        if (current != nullptr) overrides = *current;
        if (scheme == MockupScheme::system) {
            overrides.colour_scheme.reset();
        } else {
            overrides.colour_scheme.set(scheme == MockupScheme::dark ? ColourScheme::dark : ColourScheme::light);
        }
        (*window_).set_presentation_overrides(overrides);
    }
    build_menu();
}

void MockupFactory::event_recorded(void* context, const FormMockupEvent& event) {
    MockupFactory& factory = *static_cast<MockupFactory*>(context);
    const std::string handler(text_of(event.handler));
    const std::string stable_id(text_of(event.stable_id));
    const std::string interaction(text_of(event.interaction));
    std::fprintf(stdout,
                 "{\"mockup\":\"event\",\"sequence\":%llu,\"handler\":\"%s\",\"id\":\"%s\",\"interaction\":\"%s\"}\n",
                 static_cast<unsigned long long>(event.sequence), json_body(handler).c_str(),
                 json_body(stable_id).c_str(), json_body(interaction).c_str());
    std::fflush(stdout);
    factory.last_event_ = "#" + std::to_string(event.sequence) + " " + handler + " (" + stable_id + " " +
                          interaction + ")";
    factory.update_status();
}

void MockupFactory::on_dispose() noexcept {
    if (tools_registered_) {
        for (const ToolEntry& tool : factory_tools) static_cast<void>(unregister_model_tool(tool.name));
        tools_registered_ = false;
    }
    if (watch_) (*watch_).stop();
    Panel::on_dispose();
}

void MockupFactory::build_menu() {
    if (!menu_) return;
    std::vector<MenuStripItemSpec> menus{};
    MenuStripItemSpec file{};
    file.stable_id = "mockup.menu.file";
    file.text = "&File";
    file.items.push_back(item(reload_item, MenuItemKind::command, "&Reload", false));
    menus.push_back(std::move(file));

    MenuStripItemSpec theme{};
    theme.stable_id = "mockup.menu.theme";
    theme.text = "&Theme";
    const bool on_base = !theme_.familiar.has_value();
    theme.items.push_back(item(gui_forms_item, MenuItemKind::radio, "&GUI.Forms",
                               on_base && theme_.base == ThemeBase::gui_forms));
    theme.items.push_back(item(professional_item, MenuItemKind::radio, "&Windows professional",
                               on_base && theme_.base == ThemeBase::windows_professional));
    theme.items.push_back(separator("theme.separator.sheet"));
    theme.items.push_back(item(sheet_item, MenuItemKind::check, "The mockup's &sheet", theme_.use_sheet));
    theme.items.push_back(separator("theme.separator.familiar"));
    for (const FamiliarTheme familiar : listed_familiar_themes) {
        const std::string_view id = familiar_theme_id(familiar);
        const bool chosen = theme_.familiar.has_value() && *theme_.familiar == familiar;
        theme.items.push_back(item(std::string(familiar_prefix) + std::string(id), MenuItemKind::radio,
                                   std::string(id), chosen));
    }
    menus.push_back(std::move(theme));

    MenuStripItemSpec scheme{};
    scheme.stable_id = "mockup.menu.scheme";
    scheme.text = "&Scheme";
    scheme.items.push_back(item(system_item, MenuItemKind::radio, "&System", scheme_ == MockupScheme::system));
    scheme.items.push_back(item(light_item, MenuItemKind::radio, "&Light", scheme_ == MockupScheme::light));
    scheme.items.push_back(item(dark_item, MenuItemKind::radio, "&Dark", scheme_ == MockupScheme::dark));
    menus.push_back(std::move(scheme));

    MenuStripItemSpec mockups{};
    mockups.stable_id = "mockup.menu.mockups";
    mockups.text = "&Mockups";
    mockups.enabled = !catalogue_.empty();
    for (std::size_t index = 0U; index < catalogue_.size(); ++index) {
        const bool chosen = shown_.has_value() && *shown_ == index;
        mockups.items.push_back(item(std::string(open_prefix) + std::to_string(index), MenuItemKind::radio,
                                     catalogue_[index].name, chosen));
    }
    menus.push_back(std::move(mockups));
    (*menu_).set_items(std::move(menus));
}

void MockupFactory::on_menu(const MenuStripInvocation& invocation) {
    const std::string& id = invocation.item.item_id;
    MockupTheme theme = theme_;
    if (id == reload_item) {
        reload();
    } else if (id == gui_forms_item || id == professional_item) {
        theme.familiar.reset();
        theme.base = id == gui_forms_item ? ThemeBase::gui_forms : ThemeBase::windows_professional;
        choose_theme(theme);
    } else if (id == sheet_item) {
        theme.use_sheet = !theme.use_sheet;
        choose_theme(theme);
    } else if (id.starts_with(familiar_prefix)) {
        const stxlib::Optional<FamiliarTheme> named =
            familiar_theme_named(std::string_view(id).substr(familiar_prefix.size()));
        if (named.present()) {
            theme.familiar = *named.value();
            choose_theme(theme);
        }
    } else if (id == system_item) {
        choose_scheme(MockupScheme::system);
    } else if (id == light_item) {
        choose_scheme(MockupScheme::light);
    } else if (id == dark_item) {
        choose_scheme(MockupScheme::dark);
    } else if (id.starts_with(open_prefix)) {
        const std::string_view number = std::string_view(id).substr(open_prefix.size());
        std::size_t index = 0U;
        for (const char digit : number) index = index * 10U + static_cast<std::size_t>(digit - '0');
        static_cast<void>(open(index));
    }
}

void MockupFactory::on_catalogue_selection(const ListSelectionChange&) {
    const stxlib::Optional<std::size_t> selected = (*list_).selected_index();
    if (selected.absent()) return;
    const std::size_t index = *selected.value();
    if (shown_.has_value() && *shown_ == index) return;
    static_cast<void>(open(index));
}

void MockupFactory::on_watch() {
    if (!shown_) return;
    const MockupStamps now = mockup_stamps(catalogue_[*shown_]);
    if (now == stamps_) return;
    reload();
}

void MockupFactory::apply_theme() {
    if (theme_.familiar) {
        (*host_).set_theme_override(familiar_theme(*theme_.familiar));
        return;
    }
    const std::string sheet_name = shown_ ? catalogue_[*shown_].sheet.generic_string() : std::string();
    FormMockupText sheet{};
    if (theme_.use_sheet) {
        sheet.file = view_of(sheet_name);
        sheet.text = view_of(sheet_text_);
    }
    const ThemeCompileResult compiled = (*mockup_).set_theme(theme_.base, sheet);
    if (compiled.succeeded()) return;
    std::string text{};
    for (const ThemeCompileDiagnostic& finding : compiled.diagnostics()) {
        std::string line = format_theme_diagnostic(finding);
        if (line.size() > maximum_line_bytes) line.resize(maximum_line_bytes);
        if (!text.empty()) text.push_back('\n');
        text.append(line);
    }
    std::fprintf(stderr, "%s\n", text.c_str());
    show_refusal(text);
}

void MockupFactory::show_refusal(std::string text) {
    refusal_text_ = std::move(text);
    (*refusal_box_).text = refusal_text_;
    (*refusal_box_).visible = !refusal_text_.empty();
    update_status();
}

void MockupFactory::update_status() {
    std::string text = shown_ ? catalogue_[*shown_].name : std::string("No mockup is shown");
    if (shown_) {
        text.append(" - load " + std::to_string((*mockup_).generation()));
        if (!theme_.familiar) {
            text.append(" - " + std::string(base_id(theme_.base)));
        } else {
            text.append(" - " + std::string(familiar_theme_id(*theme_.familiar)));
        }
        if (!refusal_text_.empty()) text.append(" - refused, showing the last good load");
    }
    if (!last_event_.empty()) text.append(" - last event " + last_event_);
    (*status_).text = text;
}

void MockupFactory::register_tools() {
    if (tools_registered_) return;
    for (const ToolEntry& tool : factory_tools) {
        ModelToolSpec spec{};
        spec.name = tool.name;
        spec.description = tool.description;
        spec.input_schema = tool.input_schema;
        spec.access = tool.access;
        spec.settles = tool.settles;
        spec.thread = ModelToolThread::ui;
        const ModelToolRegistration registered = register_model_tool(spec, tool.handler, this);
        if (registered != ModelToolRegistration::added) {
            std::fprintf(stderr, "gui-forms-mockup: tool %s not registered: %s\n", tool.name,
                         model_tool_registration_name(registered));
        }
    }
    tools_registered_ = true;
}

std::shared_ptr<MockupFactory> make_mockup_factory(MockupFactorySetup setup) {
    const std::shared_ptr<MockupFactory> factory = make_control<MockupFactory>(StableId("mockup.root"));
    (*factory).configure(std::move(setup));
    return factory;
}

} // namespace gui_forms::mockup
