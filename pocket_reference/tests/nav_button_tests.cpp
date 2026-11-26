// SPDX-License-Identifier: MIT
// Pocket Reference's round Back and Forward buttons (owner's report on the
// 1.0.6 toolbar, 2026-11-25, defects/2026-11-25-back-button-active.png): the
// enabled Back button, hot or pressed, showed its blue ring as separate arcs
// with gaps, a dashed look. The base theme's push-button bevel (keylines,
// one colour per box edge) was drawn on the circle, and the toolkit splits a
// rounded box's edge colours at the 45-degree lines, so the ring broke into
// light and dark quadrants. The theme package now names no keylines.
//
// Each state (rest, hot, pressed, focused, focused and hot, disabled) is
// drawn off screen at 1x and 2x through the program's own theme, and the
// ring is checked: continuous (its darkest pixel across the ring is as dark
// at every angle), inside the button (nothing drawn past the circle's
// corners), and concentric (left and right mirror each other, rings
// included).
#include "pocket_reference_theme.hpp"  // generated from themes/pocket_reference

#include <gui_forms/application/application.hpp>
#include <gui_forms/capture/offscreen_raster/offscreen_raster.hpp>
#include <gui_forms/capture/specimen_states/specimen_states.hpp>
#include <gui_forms/controls/button.hpp>
#include <gui_forms/controls/panel.hpp>
#include <gui_forms/window/window.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

namespace gf = gui_forms;

void require(bool condition, const std::string &message) {
    if (!condition)
        throw std::runtime_error(message);
}

constexpr double button_size = 28.0;
constexpr double capture_margin = 4.0;
constexpr double pi = 3.14159265358979323846;

// One state to draw: none for rest; two for focused and hot.
struct ButtonState final {
    const char *name;
    std::array<gf::AnatomyState, 2> states;
    std::size_t count;
};

constexpr std::array<ButtonState, 6> button_states{{
    {"rest", {gf::AnatomyState::normal, gf::AnatomyState::normal}, 0U},
    {"hot", {gf::AnatomyState::hot, gf::AnatomyState::normal}, 1U},
    {"pressed", {gf::AnatomyState::pressed, gf::AnatomyState::normal}, 1U},
    {"focused", {gf::AnatomyState::focused, gf::AnatomyState::focus_visible}, 2U},
    {"focused-hot", {gf::AnatomyState::focus_visible, gf::AnatomyState::hot}, 2U},
    {"disabled", {gf::AnatomyState::disabled, gf::AnatomyState::normal}, 1U},
}};

// A capture's pixel as luminance, 0 to 255; outside the capture, white.
double luminance(const gf::WindowCapture &capture, double x, double y) {
    const long column = std::lround(std::floor(x));
    const long row = std::lround(std::floor(y));
    if (column < 0 || row < 0 || column >= static_cast<long>(capture.pixel_width) ||
        row >= static_cast<long>(capture.pixel_height))
        return 255.0;
    const std::size_t at = (static_cast<std::size_t>(row) * capture.pixel_width + static_cast<std::size_t>(column)) * 4U;
    const double blue = static_cast<double>(std::to_integer<unsigned>(capture.bgra[at]));
    const double green = static_cast<double>(std::to_integer<unsigned>(capture.bgra[at + 1U]));
    const double red = static_cast<double>(std::to_integer<unsigned>(capture.bgra[at + 2U]));
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

// The darkest pixel along the ray at `angle` from the centre, between
// radii `from` and `to` (device pixels), and the radius it is at.
struct Darkest final {
    double value{255.0};
    double radius{};
};

Darkest darkest_along(const gf::WindowCapture &capture, double centre, double angle, double from, double to) {
    Darkest found{};
    const double step = 0.25;
    for (double radius = from; radius <= to; radius += step) {
        const double value =
            luminance(capture, centre + radius * std::cos(angle), centre - radius * std::sin(angle));
        if (value < found.value) {
            found.value = value;
            found.radius = radius;
        }
    }
    return found;
}

// The ink along the ray at `angle` between radii `from` and `to` (device
// pixels): how much darker than the lighter of the two ends each sample
// is, summed over the ray's length, in luminance levels x device pixels.
double ink_across(const gf::WindowCapture &capture, double centre, double angle, double from, double to) {
    const double step = 0.25;
    const double inside = luminance(capture, centre + from * std::cos(angle), centre - from * std::sin(angle));
    const double outside = luminance(capture, centre + to * std::cos(angle), centre - to * std::sin(angle));
    const double base = std::max(inside, outside);
    double ink = 0.0;
    for (double radius = from; radius <= to; radius += step) {
        const double value =
            luminance(capture, centre + radius * std::cos(angle), centre - radius * std::sin(angle));
        ink += std::max(0.0, base - value) * step;
    }
    return ink;
}

void check_ring(const gf::WindowCapture &capture, const ButtonState &state, double scale) {
    const std::string where = std::string(state.name) + " at " + std::to_string(scale) + "x: ";
    require(capture.pixel_width > 0U && capture.bgra.size() >= capture.pixel_width * capture.pixel_height * 4U,
            where + "no pixels");
    // The capture holds the button and its margin, so the button's centre
    // is at the middle of it.
    const double centre = (capture_margin + button_size / 2.0) * scale;
    const double ring = button_size / 2.0 * scale;
    const double paper = luminance(capture, 1.0, 1.0);

    // Continuous: the ring's ink across its width, sampled every 5.625
    // degrees, varies little round the circle. The ink, not the darkest
    // pixel: at 1x the ring is one device pixel wide, so on the axes it
    // covers one pixel fully and at the diagonals it is antialiased over
    // two, each half covered; its peak darkness then depends on where the
    // circle crosses the pixel grid (the first measure, which failed at 1x
    // by 55 levels on a whole ring), while the ink a ray crosses does not.
    // A bevel split into quadrants or a dashed stroke leaves angles with
    // far less ink, or none.
    std::vector<double> inks;
    for (std::size_t index = 0U; index < 64U; ++index) {
        const double angle = 2.0 * pi * static_cast<double>(index) / 64.0;
        // The shadow sits under the bottom only; keep to the upper half
        // and the sides for the ring's own colour.
        if (std::sin(angle) < -0.5)
            continue;
        inks.push_back(ink_across(capture, centre, angle, ring - 1.75 * scale, ring + 1.0 * scale));
    }
    const double most = *std::max_element(inks.begin(), inks.end());
    const double least = *std::min_element(inks.begin(), inks.end());
    // The border is about 120 levels darker than the paper over one unit:
    // about 120 x scale of ink. A third of that is the loss allowed.
    require(least >= 40.0 * scale, where + "the ring is missing somewhere round the circle (ink " +
                                       std::to_string(least) + ")");
    require(most - least <= most / 3.0, where + "the ring is not continuous (its ink runs from " +
                                            std::to_string(least) + " to " + std::to_string(most) + ")");

    // Inside: past the circle, toward the button's corners, only the paper
    // (the contact shadow stays under the bottom edge).
    const std::array<double, 2> upper_corners{{3.0 * pi / 4.0, pi / 4.0}};
    for (const double angle : upper_corners) {
        const Darkest outside = darkest_along(capture, centre, angle, ring + 1.5 * scale, ring * std::sqrt(2.0));
        require(paper - outside.value <= 12.0, where + "something is drawn outside the ring, in the button's corner");
    }

    // A focus ring is a circle inside the ring: its darkest radius is the
    // same, within a device pixel, along every ray (a square ring's is
    // further out on the diagonals by a factor of the square root of two).
    // The window starts past the chevron and ends inside the outer ring.
    if (state.count > 0U && (state.states[0] == gf::AnatomyState::focused ||
                             state.states[0] == gf::AnatomyState::focus_visible)) {
        const std::array<double, 5> rays{{0.0, pi / 4.0, pi / 2.0, 3.0 * pi / 4.0, pi}};
        std::vector<double> radii;
        for (const double angle : rays)
            radii.push_back(darkest_along(capture, centre, angle, ring - 5.0 * scale, ring - 1.5 * scale).radius);
        const double outermost = *std::max_element(radii.begin(), radii.end());
        const double innermost = *std::min_element(radii.begin(), radii.end());
        require(outermost - innermost <= 1.0, where + "the focus ring is not a circle concentric with the ring");
    }

    // Concentric: the left half mirrors the right, the ring and any focus
    // ring inside it at the same radii.
    for (std::size_t index = 0U; index <= 8U; ++index) {
        const double angle = -pi / 4.0 + pi / 2.0 * static_cast<double>(index) / 8.0;
        for (double radius = 2.0 * scale; radius <= ring + 0.5 * scale; radius += 0.5) {
            const double y = centre - radius * std::sin(angle);
            const double right = luminance(capture, centre + radius * std::cos(angle), y);
            const double left = luminance(capture, centre - radius * std::cos(angle) - 1.0, y);
            require(std::abs(right - left) <= 40.0, where + "the rings are not concentric (left and right differ)");
        }
    }
    // And top to bottom: the outer ring's darkest radius is the same above
    // and below, within a device pixel.
    const Darkest top = darkest_along(capture, centre, pi / 2.0, ring - 2.0 * scale, ring + 0.5 * scale);
    const Darkest bottom = darkest_along(capture, centre, -pi / 2.0, ring - 2.0 * scale, ring + 0.5 * scale);
    require(std::abs(top.radius - bottom.radius) <= 1.0, where + "the ring is not a circle top to bottom");
}

std::optional<gf::WindowCapture> draw_state(gf::Application &application, gf::OffscreenRaster &raster,
                                            const ButtonState &state, double scale) {
    std::shared_ptr<gf::Panel> root = gf::make_control<gf::Panel>(gf::StableId("root"));
    std::shared_ptr<gf::Button> button = gf::make_control<gf::Button>(gf::StableId("reference.back"));
    static_cast<void>((*button).add_class("nav-round"));
    (*button).set_requested_bounds(gf::Rect{12.0, 12.0, button_size, button_size});
    (*root).add_child(button);
    gf::Window window(application, root, gf::Size{60.0, 60.0});
    gf::OffscreenAttachment attached(raster, window);
    for (std::size_t index = 0U; index < state.count; ++index) {
        const gf::SpecimenStateResult shown = gf::show_specimen_state(*button, state.states[index]);
        require(shown.route != gf::SpecimenStateRoute::refused, std::string(state.name) + ": state refused");
    }
    window.perform_layout();
    gf::OffscreenCaptureOptions options{};
    options.scale = scale;
    options.margin = capture_margin;
    return attached.capture_control(button, options);
}

void test_round_button_ring_in_every_state() {
    gf::ApplicationConfig config{};
    config.theme.base = gf::ThemeBase::windows_professional;
    config.theme.packages.push_back(pocket_reference::pocket_reference_theme());
    gf::ApplicationCreateResult created = gf::Application::create(std::move(config));
    require(static_cast<bool>(created), "cannot create the application");
    gf::OffscreenRasterCreateResult made = gf::OffscreenRaster::create();
    std::unique_ptr<gf::OffscreenRaster> raster = made.take_raster();
    require(raster != nullptr, "cannot make the off-screen raster");
    const std::array<double, 2> scales{{1.0, 2.0}};
    for (const ButtonState &state : button_states) {
        for (const double scale : scales) {
            const std::optional<gf::WindowCapture> capture = draw_state(*created.application, *raster, state, scale);
            require(capture.has_value(), std::string(state.name) + ": the capture failed");
            check_ring(*capture, state, scale);
        }
    }
    // Every window has ended (each in draw_state); the raster goes before
    // the library ends, as main.cpp ends it.
    raster.reset();
    static_cast<void>(gf::Application::shutdown());
}

} // namespace

int main() {
    try {
        test_round_button_ring_in_every_state();
        std::cout << "pocket_reference_nav_button_tests: all tests passed\n";
        return EXIT_SUCCESS;
    } catch (const std::exception &error) {
        std::cerr << "pocket_reference_nav_button_tests: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
