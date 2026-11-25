# {{title}}: brief

_Skeleton written by template_harness `new_app` on {{date}}; the owner fills it in._

## What it is

{{title}} is a GUI.Forms application (`{{repository}}`).

## Who it is for

## What the first version does

## What it does not do

## Performance

_What "fast enough" means, stated so that a test can check it._

- Largest content: the biggest document, list or page the program must
  handle (for example: 300 help pages, the longest 40,000 words; 100,000
  rows).
- Budgets: what each interaction may cost on that content (for example: no
  layout on pointer motion; a resize lays the content out once; a frame
  within 16 ms while scrolling).
- Existing controls considered for the content, and why each fits or does
  not (GUI.Forms docs/user/custom-controls.md, "Look for an existing control
  first").

## Interaction

_What the user does to the largest content, each item a check in
`tests/interaction_tests.cpp`._

- Scroll: wheel, scroll bars, keyboard paging, jumps to a place.
- Resize: the window narrower and wider, and what reflows.
- Hover: what responds to the pointer, and that motion alone lays out
  nothing.
- Input: clicks, keys and text entry, and where each lands.

## Constraints

- Built with template_harness at the commit `harness.lock` pins, against the
  pinned GUI.Forms source SDK.
- House style: `HOUSE_STYLE.md` on `main`.

## Open questions
