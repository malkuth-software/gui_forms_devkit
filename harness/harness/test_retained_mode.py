"""Focused scanner tests for check_retained_mode: each rule, its guards and its exemptions."""

import unittest
from check_retained_mode import Finding, inspect


class RetainedModeTests(unittest.TestCase):
    def test_unconditional_layout_request_in_arrange(self) -> None:
        source: str = ('void Page::arrange(Rect bounds) {\n'
                       '    ScrollableControl::arrange(bounds);\n'
                       '    scroll_to(kept);\n'
                       '    invalidate(Dirty::arrange);\n'
                       '}\n')
        self.assertEqual(inspect(source), [Finding(3, "layout-requests-layout"), Finding(4, "layout-requests-layout")])

    def test_guarded_requests_and_paint_damage_in_arrange_pass(self) -> None:
        source: str = ('void Page::arrange(Rect bounds) {\n'
                       '    if (child_changed) invalidate(Dirty::measure | Dirty::arrange);\n'
                       '    if (moved != Point{}) {\n'
                       '        scroll_to(position);\n'
                       '    }\n'
                       '    invalidate(Dirty::paint);\n'
                       '    set_child_layout(child, slot);\n'
                       '    set_child_layout_collapsed(bar, true);\n'
                       '    (*child).invalidate(Dirty::arrange);\n'
                       '}\n')
        self.assertEqual(inspect(source), [])

    def test_setter_in_measure(self) -> None:
        source: str = 'Size Page::measure(Size available) {\n    set_text(label);\n    return available;\n}\n'
        self.assertEqual(inspect(source), [Finding(2, "layout-requests-layout")])

    def test_paint_mutates(self) -> None:
        source: str = ('void Page::on_paint(Painter& painter, Rect damage) {\n'
                       '    if (stale) invalidate(Dirty::paint);\n'
                       '    invalidate(Dirty::semantics);\n'
                       '    invalidate(damage);\n'
                       '}\n')
        self.assertEqual(inspect(source), [Finding(2, "paint-mutates"), Finding(4, "paint-mutates")])

    def test_pointer_move_layout_request(self) -> None:
        source: str = ('void Page::on_mouse_move(MouseEventArgs& arguments) {\n'
                       '    hovered_ = link_at(arguments.location);\n'
                       '    invalidate(Dirty::paint);\n'
                       '    invalidate(Dirty::layout);\n'
                       '}\n')
        self.assertEqual(inspect(source), [Finding(4, "pointer-move-requests-layout")])

    def test_unguarded_text_flow_in_arrange_and_paint(self) -> None:
        source: str = ('void Page::arrange(Rect bounds) {\n'
                       '    relayout();\n'
                       '}\n'
                       'void Page::on_paint(Painter& painter, Rect) {\n'
                       '    const std::vector<std::string> lines = wrap_lines(text, width);\n'
                       '}\n')
        self.assertEqual(inspect(source), [Finding(2, "unguarded-text-flow"), Finding(5, "unguarded-text-flow")])

    def test_cached_text_flow_passes(self) -> None:
        source: str = ('void Page::arrange(Rect bounds) {\n'
                       '    if (bounds.width == flowed_width_ && revision_ == flowed_revision_) {\n'
                       '        Control::arrange(bounds);\n'
                       '        return;\n'
                       '    }\n'
                       '    relayout();\n'
                       '}\n'
                       'void Other::arrange(Rect bounds) {\n'
                       '    if (bounds.width != flowed_width_) {\n'
                       '        reflow(bounds.width);\n'
                       '    }\n'
                       '    ensure_layout(bounds.width);\n'
                       '}\n'
                       'void Third::on_paint(Painter& painter, Rect) {\n'
                       '    if (!lines_agree()) rebuild_lines();\n'
                       '}\n')
        self.assertEqual(inspect(source), [])

    def test_window_position_as_local(self) -> None:
        source: str = ('void Page::on_mouse_down(MouseEventArgs& arguments) {\n'
                       '    const Point local = arguments.window_position;\n'
                       '    const Point converted_local = point_from_window(arguments.window_position);\n'
                       '    const Point anchor = arguments.window_position;\n'
                       '    Point client_point = (*event).window_position;\n'
                       '}\n')
        self.assertEqual(inspect(source), [Finding(2, "window-position-as-local"),
                                           Finding(5, "window-position-as-local")])

    def test_calls_and_declarations_are_not_definitions(self) -> None:
        source: str = ('class Page final : public Control {\n'
                       '    void arrange(Rect bounds) override;\n'
                       '};\n'
                       'void Host::run() {\n'
                       '    page.arrange(bounds);\n'
                       '    Control::arrange(bounds);\n'
                       '    scroll_to(target);\n'
                       '}\n')
        self.assertEqual(inspect(source), [])

    def test_comments_literals_and_allow_markers(self) -> None:
        source: str = ('void Page::arrange(Rect bounds) {\n'
                       '    // scroll_to(kept); relayout();\n'
                       '    const char* text = "invalidate(Dirty::arrange);";\n'
                       '    // retained-mode: allow layout-requests-layout (converges: one pass)\n'
                       '    scroll_to(kept);\n'
                       '    relayout(); // retained-mode: allow unguarded-text-flow (three labels)\n'
                       '}\n')
        self.assertEqual(inspect(source), [])

    def test_an_allow_marker_names_its_rule(self) -> None:
        source: str = ('void Page::arrange(Rect bounds) {\n'
                       '    relayout(); // retained-mode: allow layout-requests-layout\n'
                       '}\n')
        self.assertEqual(inspect(source), [Finding(2, "unguarded-text-flow")])


if __name__ == "__main__":
    unittest.main()
