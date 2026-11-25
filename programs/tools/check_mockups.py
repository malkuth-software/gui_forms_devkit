#!/usr/bin/env python3
"""Checks the mockups gui-forms-mockup lists, without building anything.

Each `<name>.form` under the mockups folder (../../mockups by default) is
read with its siblings `<name>.fixture` and `<name>.theme.css`, and the
checks the window would otherwise report only when the mockup is opened are
made here:

- the form and the fixture are well-formed XML whose root declares the
  form (`urn:gui-forms:form:1`) or fixture (`urn:gui-forms:fixture:1`)
  namespace, and every object has an `id`, used once;
- every `bind` names a source: a Command (`property="command"`) is made by
  the mockup itself, any other source must be a fixture `value` or
  `records` name, and a `field` must be one of the records' columns (the
  window shows a stand-in, the property's default, for a source the
  fixture lacks; a checked-in mockup gives each one sample data);
- every fixture `shown-in` names an object of the form;
- a fixture name is used once, and no row has more values than columns.

The library's own checks (types, properties, values) need the library:
`gui-forms-mockup --screenshots <dir>` makes them, as the window does.

    python3 -B programs/tools/check_mockups.py [mockups-dir]

Exit 0 when every mockup passes, 1 otherwise; each finding is printed as
`<file>:<line>: <message>`.
"""
from __future__ import annotations

import sys
import xml.parsers.expat
from dataclasses import dataclass, field
from pathlib import Path

FORM_NAMESPACE = "urn:gui-forms:form:1"
FIXTURE_NAMESPACE = "urn:gui-forms:fixture:1"
DEFAULT_DIRECTORY = Path(__file__).resolve().parents[2] / "mockups"
RESERVED_ELEMENTS = ("bind", "span")


@dataclass
class Element:
    name: str
    attributes: dict[str, str]
    line: int
    parent: "Element | None" = None
    children: list["Element"] = field(default_factory=list)


def parse(path: Path, findings: list[str]) -> Element | None:
    """The element tree of `path`, or None after reporting why not."""
    root: list[Element] = []
    stack: list[Element] = []
    parser = xml.parsers.expat.ParserCreate()

    def start(name: str, attributes: dict[str, str]) -> None:
        element = Element(name, dict(attributes), parser.CurrentLineNumber, stack[-1] if stack else None)
        if stack:
            stack[-1].children.append(element)
        else:
            root.append(element)
        stack.append(element)

    def end(name: str) -> None:
        stack.pop()

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    try:
        parser.Parse(path.read_bytes(), True)
    except xml.parsers.expat.ExpatError as error:
        findings.append(f"{path}:{error.lineno}: not well-formed XML: {xml.parsers.expat.ErrorString(error.code)}")
        return None
    except OSError as error:
        findings.append(f"{path}:0: cannot be read: {error.strerror}")
        return None
    return root[0] if root else None


def walk(element: Element):
    yield element
    for child in element.children:
        yield from walk(child)


def split_list(text: str) -> list[str]:
    """A form list's items: whitespace-separated, single or double quotes
    around an item with whitespace, backslash escapes inside quotes."""
    items: list[str] = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        if text[index] in "'\"":
            quote = text[index]
            index += 1
            item = []
            while index < len(text) and text[index] != quote:
                if text[index] == "\\" and index + 1 < len(text):
                    index += 1
                item.append(text[index])
                index += 1
            items.append("".join(item))
            index += 1
            continue
        start = index
        while index < len(text) and not text[index].isspace():
            index += 1
        items.append(text[start:index])
    return items


@dataclass
class Fixture:
    values: set[str] = field(default_factory=set)
    records: dict[str, list[str]] = field(default_factory=dict)
    shown_in: list[tuple[str, int]] = field(default_factory=list)


def read_fixture(path: Path, findings: list[str]) -> Fixture:
    fixture = Fixture()
    if not path.exists():
        return fixture
    root = parse(path, findings)
    if root is None:
        return fixture
    if root.name != "fixture" or root.attributes.get("xmlns") != FIXTURE_NAMESPACE:
        findings.append(f'{path}:{root.line}: the root is <fixture xmlns="{FIXTURE_NAMESPACE}">')
        return fixture
    names: set[str] = set()
    for element in root.children:
        name = element.attributes.get("name", "")
        if element.name in ("value", "records"):
            if not name.isidentifier():
                findings.append(f"{path}:{element.line}: <{element.name}> needs a name that is one identifier")
            elif name in names:
                findings.append(f"{path}:{element.line}: the name {name} is used twice")
            names.add(name)
        if element.name == "value":
            fixture.values.add(name)
        elif element.name == "records":
            columns = [column.split(":", 1)[0] for column in split_list(element.attributes.get("columns", ""))]
            if not columns:
                findings.append(f"{path}:{element.line}: <records> needs columns")
            fixture.records[name] = columns
            for row in element.children:
                count = len(split_list(row.attributes.get("values", "")))
                if count > len(columns):
                    findings.append(f"{path}:{row.line}: {count} values for {len(columns)} columns")
        elif element.name != "tree":
            findings.append(f"{path}:{element.line}: <{element.name}> is no fixture element")
            continue
        for shown in split_list(element.attributes.get("shown-in", "")):
            fixture.shown_in.append((shown, element.line))
    return fixture


def check_mockup(form_path: Path) -> list[str]:
    """The findings for one mockup: its form and its fixture."""
    findings: list[str] = []
    fixture_path = form_path.with_suffix(".fixture")
    root = parse(form_path, findings)
    fixture = read_fixture(fixture_path, findings)
    if root is None:
        return findings
    if root.attributes.get("xmlns") != FORM_NAMESPACE:
        findings.append(f'{form_path}:{root.line}: the root declares xmlns="{FORM_NAMESPACE}"')
    identities: set[str] = set()
    for element in walk(root):
        if element.name in RESERVED_ELEMENTS:
            continue
        identity = element.attributes.get("id")
        if not identity:
            findings.append(f"{form_path}:{element.line}: <{element.name}> needs an id")
        elif identity in identities:
            findings.append(f"{form_path}:{element.line}: the id {identity} is used twice")
        else:
            identities.add(identity)
    for element in walk(root):
        if element.name != "bind":
            continue
        source = element.attributes.get("to", "")
        if element.attributes.get("property") == "command":
            continue
        if source in fixture.values:
            continue
        if source in fixture.records:
            field_name = element.attributes.get("field")
            if field_name is not None and field_name not in fixture.records[source]:
                findings.append(f"{form_path}:{element.line}: {source} has no column {field_name}")
            continue
        findings.append(f"{form_path}:{element.line}: no fixture value or records named {source!r} "
                        f"({fixture_path.name})")
    for shown, line in fixture.shown_in:
        if shown not in identities:
            findings.append(f"{fixture_path}:{line}: shown-in names {shown}, which {form_path.name} does not hold")
    return findings


def main(arguments: list[str]) -> int:
    directory = Path(arguments[0]) if arguments else DEFAULT_DIRECTORY
    forms = sorted(directory.rglob("*.form"))
    if not forms:
        print(f"no .form under {directory}")
        return 1
    findings: list[str] = []
    for form in forms:
        findings.extend(check_mockup(form))
    for line in findings:
        print(line)
    print(f"{len(forms)} mockups, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
