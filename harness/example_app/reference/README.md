# Reference control: LinkPage

The reference application code that apps made from the harness's app
template emulate (`templates/app/AGENTS.md`, "Building on GUI.Forms"); the
example app carries it too. `LinkPage` is a scrolling page of wrapped
paragraphs with links, painted by the control itself and written the
retained way:

- `ensure_layout` flows the text, and only when its key changes: the
  content revision, the flow width, the font, the text engine or the scale.
- `arrange` brings the layout up to date and lets `ScrollableControl` place
  the bars and keep the scroll position, from `painted_content_extent`.
- Paint draws the kept lines the damage crosses; hit testing finds them the
  same way, in control coordinates (`MouseEventArgs::location`).
- Hover and press repaint the link they touch and nothing else.

`tests/interaction_tests.cpp` proves it with the window's counters, and runs
the same pointer-motion check over the app's own form. GUI.Forms explains
each step in its guide, docs/user/custom-controls.md ("Custom controls").

These files are a copy of GUI.Forms `examples/link_page` (link_page.hpp,
link_page.cpp, sample_document.hpp, sample_document.cpp). Change them there
first, then copy them here and to `templates/app/reference/`, so the
guide, the example and the template agree.
