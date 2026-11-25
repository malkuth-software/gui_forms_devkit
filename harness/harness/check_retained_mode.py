"""Report retained-mode review candidates in GUI.Forms control code; a review aid, not proof.

GUI.Forms is retained: a control keeps its layout, computed when an input
changes, and its paint and input handlers only read it (GUI.Forms
docs/user/custom-controls.md). This scanner looks inside the bodies of the
layout, paint and pointer-move hooks for calls that break that model:

- layout-requests-layout: `measure`, `arrange` or `on_layout`
  unconditionally asks for layout or moves state that does: a call on the
  control itself to `invalidate` with `Dirty::measure`, `Dirty::arrange` or
  `Dirty::layout`, `invalidate_declared`, `scroll_to`, `scroll_by` or a
  `set_...` setter (not the `set_child_layout...` slot calls). A call inside
  an `if` is a reaction to a detected change and is not reported;
- paint-mutates: `on_paint` or `on_paint_overlay` makes any of those calls,
  or invalidates paint, guarded or not;
- pointer-move-requests-layout: a pointer-move handler invalidates layout
  (`Dirty::measure`, `Dirty::arrange` or `Dirty::layout`);
- unguarded-text-flow: `arrange` or a paint hook flows or wraps text with no
  early return before the call and no `if` around it (a layout cache's
  key check), so it runs on every arrange or paint;
- window-position-as-local: `window_position` stored as it is (not through
  a conversion such as `point_from_window`) in a name that says local,
  client or content coordinates.

Comments and literals are excluded. A line, or the line before it, carrying
`retained-mode: allow <rule>` in a comment is not reported; give the reason
in the same comment. Explicit paths define scope, as in check_house_style.py.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re

from check_house_style import LEXEMES, collect, mask_literal


@dataclass(frozen=True)
class Finding:
    line: int
    rule: str


LAYOUT_HOOKS: frozenset[str] = frozenset(("measure", "measure_intrinsic", "arrange", "on_layout"))
PAINT_HOOKS: frozenset[str] = frozenset(("on_paint", "on_paint_overlay", "on_paint_background"))
MOVE_HOOKS: frozenset[str] = frozenset(("on_mouse_move", "on_pointer_move", "on_pointer_bubble", "on_mouse_hover"))
FLOW_HOOKS: frozenset[str] = frozenset(("arrange",)) | PAINT_HOOKS

# A hook's definition: its name (qualified or not), its parameter list and
# what may follow before the body's brace. A call ends in ';' and never
# matches.
DEFINITION: re.Pattern[str] = re.compile(
    r"\b(?:[A-Za-z_]\w*\s*::\s*)?(?P<name>" + "|".join(sorted(LAYOUT_HOOKS | PAINT_HOOKS | MOVE_HOOKS)) + r")"
    r"\s*\((?P<parameters>[^;{}()]*(?:\([^;{}()]*\)[^;{}()]*)*)\)\s*"
    r"(?:const\s*)?(?:noexcept\s*(?:\([^()]*\)\s*)?)?(?:override\s*)?(?:final\s*)?\{")

# A call on the control itself: no object before the name (`.`, `)` or `::`
# of a qualified base call would name another receiver or a base hook).
SELF_CALL: str = r"(?<![\w.)>:])\s*"
MUTATION: re.Pattern[str] = re.compile(
    SELF_CALL + r"\b(?P<call>invalidate_declared|scroll_to|scroll_by|set_(?!child_layout)\w+)\s*\(|"
    + SELF_CALL + r"\b(?P<invalidate>invalidate)\s*\((?P<arguments>[^;]*)\)\s*;")
LAYOUT_DIRTY_NAMES: re.Pattern[str] = re.compile(r"\bDirty\s*::\s*(?:measure|arrange|layout)\b")
PAINT_DIRTY_NAMES: re.Pattern[str] = re.compile(r"\bDirty\s*::\s*(?:measure|arrange|layout|paint)\b|^\s*[^D\s]")
LAYOUT_DIRTY: re.Pattern[str] = re.compile(
    r"\binvalidate(?:_declared)?\s*\([^;]*\bDirty\s*::\s*(?:measure|arrange|layout)\b")
FLOW_CALL: re.Pattern[str] = re.compile(
    r"\b(?P<call>lay_out_paragraph|measure_paragraph|fill_line_break_opportunities_utf8|"
    r"relayout\w*|reflow\w*|re_flow\w*|lay_out\w*|layout_text\w*|wrap_\w+|\w+_wrapped\w*|"
    r"break_lines\w*|rebuild_(?:lines|rows|layout|wrap)\w*|flow_\w+)\s*\(")
RETURN: re.Pattern[str] = re.compile(r"\breturn\b")
GUARD_STATEMENT: re.Pattern[str] = re.compile(r"^\s*(?:\}\s*)?(?:else\s+)?(?:if|while|for|switch)\b|^\s*(?:\}\s*)?else\b")
WINDOW_AS_LOCAL: re.Pattern[str] = re.compile(
    r"\b(?P<name>\w*(?:local|client|content)\w*)\s*=\s*(?:(?:\w+|\(\s*\*\s*\w+\s*\))\s*\.\s*)?window_position\s*[;,)]",
    re.IGNORECASE)
ALLOW: re.Pattern[str] = re.compile(r"retained-mode:\s*allow\s+(?P<rules>[\w\-, ]+)")


def body_end(masked: str, open_brace: int) -> int:
    """The index just past the brace that closes the one at open_brace (the text's end if unbalanced)."""
    depth: int = 0
    index: int = open_brace
    while index < len(masked):
        character: str = masked[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(masked)


def statement_start(masked: str, position: int, floor: int) -> int:
    """The index after the last ';', '{' or '}' before position, not before floor."""
    index: int = position - 1
    while index >= floor:
        if masked[index] in ";{}":
            return index + 1
        index -= 1
    return floor


GUARD_KEYWORD: re.Pattern[str] = re.compile(r"\b(?:if|while|for|switch)\s*$")
ELSE_KEYWORD: re.Pattern[str] = re.compile(r"\belse\s*$")


def guard_before(masked: str, index: int, floor: int) -> bool:
    """Whether the text ending just before index is a guard's head: `if (...)`, a loop's or `else`."""
    cursor: int = index - 1
    while cursor >= floor and masked[cursor].isspace():
        cursor -= 1
    if cursor < floor:
        return False
    if masked[cursor] == ")":
        depth: int = 0
        while cursor >= floor:
            if masked[cursor] == ")":
                depth += 1
            elif masked[cursor] == "(":
                depth -= 1
                if depth == 0:
                    break
            cursor -= 1
        result: bool = GUARD_KEYWORD.search(masked[max(floor, cursor - 16):cursor]) is not None
        return result
    found: bool = ELSE_KEYWORD.search(masked[max(floor, cursor - 8):cursor + 1]) is not None
    return found


def guarded(masked: str, body_start: int, position: int) -> bool:
    """Whether the call at position sits under an if, loop, switch or else: its statement's or an enclosing block's."""
    start: int = statement_start(masked, position, body_start + 1)
    if guard_before(masked, position, start) or GUARD_STATEMENT.search(masked[start:position]):
        return True
    # Walk out through the enclosing blocks up to the body's own brace.
    depth: int = 0
    index: int = start - 1
    while index > body_start:
        character: str = masked[index]
        if character == "}":
            depth += 1
        elif character == "{":
            if depth == 0:
                if guard_before(masked, index, body_start + 1):
                    return True
            else:
                depth -= 1
        index -= 1
    return False


def early_return_before(masked: str, body_start: int, position: int) -> bool:
    """Whether a conditional return (a cache's key check) comes before position in the body."""
    found: re.Match[str]
    for found in RETURN.finditer(masked, body_start, position):
        if guarded(masked, body_start, found.start()):
            return True
    return False


def line_of(masked: str, position: int) -> int:
    line: int = masked.count("\n", 0, position) + 1
    return line


def inspect(source: str) -> list[Finding]:
    masked: str = LEXEMES.sub(mask_literal, source)
    findings: list[Finding] = []
    definition: re.Match[str]
    for definition in DEFINITION.finditer(masked):
        name: str = definition.group("name")
        open_brace: int = definition.end() - 1
        end: int = body_end(masked, open_brace)
        body: str = masked[open_brace:end]
        if name in LAYOUT_HOOKS or name in PAINT_HOOKS:
            rule: str = "layout-requests-layout" if name in LAYOUT_HOOKS else "paint-mutates"
            mutation: re.Match[str]
            for mutation in MUTATION.finditer(body):
                call: str = "invalidate" if mutation.group("invalidate") else mutation.group("call")
                position: int = open_brace + mutation.start("invalidate" if call == "invalidate" else "call")
                if call == "invalidate":
                    arguments: str = mutation.group("arguments")
                    names: re.Pattern[str] = LAYOUT_DIRTY_NAMES if name in LAYOUT_HOOKS else PAINT_DIRTY_NAMES
                    if not names.search(arguments):
                        continue
                if name in LAYOUT_HOOKS and guarded(masked, open_brace, position):
                    continue
                findings.append(Finding(line_of(masked, position), rule))
        if name in MOVE_HOOKS:
            dirty: re.Match[str]
            for dirty in LAYOUT_DIRTY.finditer(body):
                findings.append(Finding(line_of(masked, open_brace + dirty.start()), "pointer-move-requests-layout"))
        if name in FLOW_HOOKS:
            flow: re.Match[str]
            for flow in FLOW_CALL.finditer(body):
                position: int = open_brace + flow.start("call")
                if early_return_before(masked, open_brace, position) or guarded(masked, open_brace, position):
                    continue
                findings.append(Finding(line_of(masked, position), "unguarded-text-flow"))
    local: re.Match[str]
    for local in WINDOW_AS_LOCAL.finditer(masked):
        findings.append(Finding(line_of(masked, local.start("name")), "window-position-as-local"))
    allowed: list[Finding] = []
    lines: list[str] = source.split("\n")
    finding: Finding
    for finding in sorted(set(findings), key=finding_order):
        if not allowed_on(lines, finding):
            allowed.append(finding)
    return allowed


def finding_order(finding: Finding) -> tuple[int, str]:
    key: tuple[int, str] = (finding.line, finding.rule)
    return key


def allowed_on(lines: list[str], finding: Finding) -> bool:
    """Whether the finding's line or the line before it allows its rule in a comment."""
    index: int
    for index in (finding.line - 1, finding.line - 2):
        if index < 0 or index >= len(lines):
            continue
        marker: re.Match[str] | None = ALLOW.search(lines[index])
        if marker is not None and finding.rule in re.split(r"[\s,]+", marker.group("rules")):
            return True
    return False


def main() -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__,
                                                              formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+")
    arguments: argparse.Namespace = parser.parse_args()
    paths: list[Path] = collect(arguments.paths)
    if not paths:
        parser.error("No C++ files selected; empty scope is not a pass.")
    count: int = 0
    path: Path
    for path in paths:
        source: str = path.read_text(encoding="utf-8-sig")
        findings: list[Finding] = inspect(source)
        finding: Finding
        for finding in findings:
            print(f"{path}:{finding.line}: {finding.rule}")
        count += len(findings)
    print(f"{len(paths)} files; {count} retained-mode review candidates. Semantic review still required.")
    if count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
