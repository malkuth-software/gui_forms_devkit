// Interaction checks every app starts with: pointer motion, scrolling and
// resizing lay out no more than they must. They read the window's counters
// (GUI.Forms docs/user/custom-controls.md, "Prove it with the counters").
// Point them at the app's largest content as it grows.
//
// - The form: 100 pointer moves over the whole window lay out nothing.
// - The reference control (reference/link_page.hpp) over 2,000 paragraphs:
//   scrolled to the middle, 100 pointer moves lay out nothing and flow no
//   text; scrolling flows nothing; a new width flows at most twice and a
//   second layout at that width nothing; no layout diagnostic is recorded.
#include "greeter.hpp"
#include "link_page.hpp"
#include "sample_document.hpp"

#include <gui_forms/layout/diagnostics/pointer_motion_probe.hpp>
#include <gui_forms/window.hpp>

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>

namespace {

void require(const bool condition, const char* message) {
    if (condition) return;
    std::cerr << "interaction_tests: " << message << '\n';
    std::exit(1);
}

void form_pointer_motion() {
    {{namespace}}::Greeter greeter{};
    const std::unique_ptr<gui_forms::Window> window =
        std::make_unique<gui_forms::Window>(greeter.root, gui_forms::Size{420.0, 360.0});
    (*window).perform_layout();
    const gui_forms::PointerMotionCost cost =
        gui_forms::measure_pointer_motion(*window, gui_forms::Rect{0.0, 0.0, 420.0, 360.0}, 100U);
    require(cost.moves == 100U && cost.lays_out_nothing(), "100 pointer moves over the form lay out nothing");
    require((*window).layout_diagnostics().empty(), "the form records no layout diagnostic");
}

void reference_control() {
    const std::shared_ptr<link_page_example::LinkPage> page =
        gui_forms::make_control<link_page_example::LinkPage>(gui_forms::StableId("{{app}}.reference"));
    (*page).set_paragraphs(link_page_example::sample_document(2000U));
    const std::unique_ptr<gui_forms::Window> window =
        std::make_unique<gui_forms::Window>(page, gui_forms::Size{640.0, 480.0});
    gui_forms::Window& shown = *window;
    shown.perform_layout();
    static_cast<void>((*page).scroll_to(gui_forms::Point{0.0, (*page).content_height() * 0.5}));
    shown.perform_layout();
    require((*page).scroll_position().y > 0.0, "the page scrolled to the middle");
    const std::uint64_t flows = (*page).flow_count();

    const gui_forms::PointerMotionCost cost =
        gui_forms::measure_pointer_motion(shown, gui_forms::Rect{0.0, 0.0, 640.0, 480.0}, 100U);
    require(cost.moves == 100U && cost.lays_out_nothing(), "100 pointer moves over the page lay out nothing");
    require((*page).flow_count() == flows, "pointer motion flows no text");

    static_cast<void>((*page).scroll_by(gui_forms::Point{0.0, 400.0}));
    shown.perform_layout();
    require((*page).flow_count() == flows, "scrolling flows no text");

    shown.resize(gui_forms::Size{520.0, 480.0});
    shown.perform_layout();
    const std::uint64_t resized = (*page).flow_count();
    require(resized > flows && resized <= flows + 2U, "a new width flows the text at most twice");
    shown.perform_layout();
    require((*page).flow_count() == resized, "a second layout at the same width flows nothing");
    require(shown.layout_diagnostics().empty(), "the page records no layout diagnostic");
}

} // namespace

int main() {
    form_pointer_motion();
    reference_control();
    std::cout << "interaction: form motion, reference motion, scroll and resize passed\n";
    return 0;
}
