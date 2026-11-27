#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Writes Pocket Reference's page text from GUI.Forms' generated reference.

Reads GUI.Forms' reference inputs, from either of two roots:

    a checkout       manifests/controls.json (the control registry),
                     docs/api/library.*.rst (the library topics) and
                     docs/api/generated/gui_forms.*.rst (one page a type);
                     the version from CMakeLists.txt, the commit from git
    an installed     share/GUIForms/ledgers/controls.json, and the same
    SDK prefix       pages under share/GUIForms/docs/api/; the version from
                     lib/cmake/GUIForms/GUIFormsConfigVersion.cmake, the
                     commit from share/GUIForms/docs/api/REVISION

--version and --commit name the GUI.Forms build the program is built
against (the build passes the SDK's version and, in the devkit, the resolved
revision). The pages then name exactly that build, and a root that describes
another build is refused rather than packed under the wrong name.

Writes one UTF-8 file of pages in the reference markup, which
reference_document.cpp reads; pocket-reference-pack then codes it into the
pack. The markup is line-based: a keyword, a tab, then tab-separated fields.

    @@pack <version> <commit>      the GUI.Forms release the pages describe
    @@tree                         the contents, one row a line until @@page:
      <depth> <page id> <label> <icon>
    @@page <id>                    a page, its blocks until the next @@page:
      title <text>, source <path>, crumb <id> <label> (root first)
      h1 <text>, h2 <anchor> <text>, h3 <text>, p <inline>
      sig <anchor> <code>, in, out   (a signature, the blocks it holds)
      dt <anchor> <inline>, dd <inline>
      code <line>  (consecutive lines are one block), codeend
      th <cells>, tr <cells>, fig <control id> <caption>, card <target> <title> <purpose>

Inline text marks spans with control characters: \\x01 code \\x02, \\x03
target \\x04 label \\x05 (a link), \\x06 bold \\x06, \\x07 italic \\x07.
"""
import argparse
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

CODE_ON = "\x01"
CODE_OFF = "\x02"
LINK_ON = "\x03"
LINK_MID = "\x04"
LINK_OFF = "\x05"
BOLD = "\x06"
ITALIC = "\x07"

ROLE = re.compile(r':(?:cpp:)?(\w+):`([^`]*)`')
STRONG = re.compile(r'\*\*(.+?)\*\*')
EMPHASIS = re.compile(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])')


def clean(text: str) -> str:
    """Text with no tabs, newlines or marks of its own."""
    text = text.replace("\t", " ").replace("\n", " ")
    return re.sub(r'[\x00-\x08]', "", text)


class Pages:
    """The page ids that exist, so links to missing pages stay plain."""

    def __init__(self) -> None:
        self.types: set[str] = set()


PAGES = Pages()


def role_text(match: re.Match[str]) -> str:
    role: str = match.group(1)
    body: str = match.group(2)
    label: str = body
    target: str = body
    inner: re.Match[str] | None = re.match(r'(.*?)\s*<([^>]*)>$', body, re.S)
    if inner is not None:
        label = inner.group(1)
        target = inner.group(2)
    if role in ("src", "ref", "doc"):
        return clean(label)
    parts: list[str] = [p for p in target.split("::") if p]
    if parts and parts[0] == "gui_forms":
        parts = parts[1:]
    code: str = CODE_ON + clean(label) + CODE_OFF
    if not parts or parts[0] not in PAGES.types:
        return code
    anchor: str = ("#" + parts[1]) if len(parts) > 1 else ""
    return LINK_ON + "type/" + parts[0] + anchor + LINK_MID + code + LINK_OFF


def plain(text: str) -> str:
    text = clean(text)
    text = STRONG.sub(BOLD + r"\1" + BOLD, text)
    text = EMPHASIS.sub(ITALIC + r"\1" + ITALIC, text)
    return text


def inline(text: str) -> str:
    pieces: list[str] = []
    position: int = 0
    for match in re.finditer(r'``.+?``|:(?:cpp:)?\w+:`[^`]*`', text):
        pieces.append(plain(text[position:match.start()]))
        token: str = match.group(0)
        if token.startswith("``"):
            pieces.append(CODE_ON + clean(token[2:-2]) + CODE_OFF)
        else:
            pieces.append(ROLE.sub(role_text, token))
        position = match.end()
    pieces.append(plain(text[position:]))
    return "".join(pieces)


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


class Page:
    """Converts one generated page. Walks lines once; each directive consumes
    the block indented under it."""

    def __init__(self, text: str) -> None:
        self.lines: list[str] = text.split("\n")
        self.at: int = 0
        self.out: list[str] = []
        self.source: str = ""
        self.title: str = ""

    def emit(self, *fields: str) -> None:
        self.out.append("\t".join(fields))

    def block_end(self, start: int, base: int) -> int:
        index: int = start
        while index < len(self.lines):
            line: str = self.lines[index]
            if line.strip() and indent_of(line) <= base:
                return index
            index += 1
        return index

    def paragraph(self) -> None:
        collected: list[str] = []
        while self.at < len(self.lines):
            stripped: str = self.lines[self.at].strip()
            if not stripped or stripped.startswith(".. ") or re.match(r'^:[A-Za-z ]+:$', stripped):
                break
            collected.append(stripped)
            self.at += 1
        if collected and collected[0].startswith(("* ", "- ")):
            for item in " ".join(collected).split(" * " if collected[0].startswith("*") else " - "):
                self.emit("p", "• " + inline(item.lstrip("*- ").strip()))
            return
        self.emit("p", inline(" ".join(collected)))

    def code_block(self, base: int) -> None:
        end: int = self.block_end(self.at, base)
        body: list[str] = self.lines[self.at:end]
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        depth: int = min((indent_of(l) for l in body if l.strip()), default=0)
        for line in body:
            self.emit("code", line[depth:].replace("\t", "    "))
        self.emit("codeend")
        self.at = end

    def signature(self, kind: str, text: str, base: int) -> None:
        name: re.Match[str] | None = re.search(r'(~?\w+)\s*(\(|$|\s*=|\s*\{)', text)
        anchor: str = name.group(1) if name is not None else ""
        self.emit("sig", anchor, clean(text))
        end: int = self.block_end(self.at, base)
        if any(l.strip() for l in self.lines[self.at:end]):
            self.emit("in")
            self.walk(end)
            self.emit("out")
        self.at = end

    def field_list(self, name: str, base: int) -> None:
        end: int = self.block_end(self.at, base)
        self.emit("h3", clean(name))
        if name == "Inherited":
            self.walk(end)
            return
        while self.at < end:
            line: str = self.lines[self.at]
            entry: re.Match[str] | None = re.match(r'\s*\*\*(\w+)\*\*\s*:\s*(.*)$', line)
            if entry is None:
                self.at += 1
                continue
            item_indent: int = indent_of(line)
            self.at += 1
            self.emit("dt", entry.group(1), BOLD + entry.group(1) + BOLD + " : " + inline(entry.group(2)))
            description_end: int = self.block_end(self.at, item_indent)
            words: list[str] = [l.strip() for l in self.lines[self.at:description_end] if l.strip()]
            if words:
                self.emit("dd", inline(" ".join(words)))
            self.at = description_end
        self.at = end

    def list_table(self, base: int) -> None:
        end: int = self.block_end(self.at, base)
        header: bool = False
        rows: list[list[str]] = []
        for line in self.lines[self.at:end]:
            stripped: str = line.strip()
            if stripped.startswith(":header-rows:"):
                header = True
            elif stripped.startswith("* - ") or stripped == "* -":
                rows.append([stripped[4:]])
            elif (stripped.startswith("- ") or stripped == "-") and rows:
                # A cell with nothing in it ("-" and spaces, as the
                # library pages write a type with no summary) is an empty
                # cell, not a "-" on the end of the cell before.
                rows[-1].append(stripped[2:])
            elif stripped and rows and not stripped.startswith(":"):
                rows[-1][-1] += " " + stripped
        for index, row in enumerate(rows):
            self.emit("th" if header and index == 0 else "tr", *[inline(cell) for cell in row])
        self.at = end

    def see_also(self, base: int) -> None:
        end: int = self.block_end(self.at, base)
        self.emit("h3", "See also")
        lines: list[str] = [l for l in self.lines[self.at:end] if l.strip()]
        top: int = min((indent_of(l) for l in lines), default=0)
        for line in lines:
            self.emit("dt" if indent_of(line) == top else "dd", *([""] if indent_of(line) == top else []),
                      inline(line.strip()))
        self.at = end

    def preview(self, argument: str, base: int) -> None:
        end: int = self.block_end(self.at, base)
        control: str = argument.strip().removeprefix("controls/")
        alt: str = ""
        for line in self.lines[self.at:end]:
            if line.strip().startswith(":alt:"):
                alt = line.strip()[5:].strip()
        self.emit("fig", control, clean(alt))
        self.at = end

    def walk(self, end: int) -> None:
        while self.at < end:
            line: str = self.lines[self.at]
            stripped: str = line.strip()
            base: int = indent_of(line)
            if not stripped:
                self.at += 1
                continue
            if (self.at + 1 < len(self.lines) and re.match(r'^[=#]+$', self.lines[self.at + 1].strip())
                    and base == 0):
                self.title = stripped
                self.emit("h1", clean(stripped))
                self.at += 2
                continue
            if re.match(r'^[=#*~^-]{3,}$', stripped):
                self.at += 1
                continue
            if self.at + 1 < len(self.lines) and re.match(r'^[-~^]{3,}$', self.lines[self.at + 1].strip()):
                self.emit("h2", clean(stripped.lower()), clean(stripped))
                self.at += 2
                continue
            if stripped.startswith(":gf_source:"):
                self.source = stripped.split(":", 2)[2].strip()
                self.at += 1
                continue
            directive: re.Match[str] | None = re.match(r'\.\. ([\w:-]+)::\s*(.*)$', stripped)
            if directive is not None:
                name: str = directive.group(1)
                argument: str = directive.group(2)
                self.at += 1
                if name in ("code-block", "code"):
                    self.code_block(base)
                elif name.startswith("cpp:") and name != "cpp:namespace":
                    self.signature(name[4:], argument, base)
                elif name == "rubric":
                    self.emit("h2", clean(argument.lower()), clean(argument))
                elif name == "list-table":
                    self.list_table(base)
                elif name == "seealso":
                    self.see_also(base)
                elif name == "gf-preview":
                    self.preview(argument, base)
                else:
                    self.at = self.block_end(self.at, base)
                continue
            if stripped.startswith(".. "):
                self.at = self.block_end(self.at + 1, base)
                continue
            field: re.Match[str] | None = re.match(r'^:([A-Za-z ]+):$', stripped)
            if field is not None:
                self.at += 1
                self.field_list(field.group(1), base)
                continue
            self.paragraph()

    def render(self) -> list[str]:
        self.walk(len(self.lines))
        return self.out


def topic_title(text: str, fallback: str) -> str:
    lines: list[str] = text.split("\n")
    for index, line in enumerate(lines[:-1]):
        if line.strip() and re.match(r'^[=#]+$', lines[index + 1].strip()):
            return line.strip()
    return fallback


COMMIT_LENGTH = 12


class Inputs:
    """Where one root keeps the reference inputs, and the build they describe."""

    def __init__(self, api: Path, registry: Path, version: str, commit: str) -> None:
        self.api: Path = api
        self.registry: Path = registry
        self.version: str = version
        self.commit: str = commit


def checkout_commit(root: Path) -> str:
    """The checkout's HEAD, or "" when the root is not a git checkout."""
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def locate(root: Path) -> Inputs:
    """The inputs of a checkout or of an installed SDK prefix; raises SystemExit naming what is missing."""
    if (root / "manifests/controls.json").is_file() and (root / "docs/api").is_dir():
        found: re.Match[str] | None = None
        if (root / "CMakeLists.txt").is_file():
            found = re.search(r'project\(GUIForms VERSION ([\d.]+)', (root / "CMakeLists.txt").read_text())
        return Inputs(root / "docs/api", root / "manifests/controls.json",
                      found.group(1) if found is not None else "", checkout_commit(root))
    share: Path = root / "share/GUIForms"
    if (share / "ledgers/controls.json").is_file() and (share / "docs/api").is_dir():
        version: str = ""
        config: Path = root / "lib/cmake/GUIForms/GUIFormsConfigVersion.cmake"
        if config.is_file():
            match: re.Match[str] | None = re.search(r'set\(PACKAGE_VERSION "([\d.]+)"\)', config.read_text())
            version = match.group(1) if match is not None else ""
        revision: Path = share / "docs/api/REVISION"
        commit: str = revision.read_text().strip() if revision.is_file() else ""
        return Inputs(share / "docs/api", share / "ledgers/controls.json", version, commit)
    raise SystemExit(f"{root} holds no GUI.Forms reference inputs: neither a checkout (manifests/controls.json, "
                     "docs/api/) nor an installed SDK (share/GUIForms/ledgers/controls.json, share/GUIForms/docs/api/)")


def settle(found: str, requested: str, what: str, root: Path, same: Callable[[str, str], bool]) -> str:
    """The requested value when the root agrees with it (or cannot say), else the root's own."""
    if requested and found and not same(found, requested):
        raise SystemExit(f"{root} describes GUI.Forms {what} {found}, not the {requested} the program is built "
                         "against: point the build at the inputs of that build")
    value: str = requested or found
    if not value:
        raise SystemExit(f"{root} does not say its GUI.Forms {what}: pass --{what}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui-forms", type=Path, required=True,
                        help="a GUI.Forms checkout or an installed GUI.Forms SDK prefix")
    parser.add_argument("--version", default="", help="the GUI.Forms version the program is built against")
    parser.add_argument("--commit", default="", help="the GUI.Forms commit the program is built against")
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    root: Path = arguments.gui_forms
    inputs: Inputs = locate(root)
    version: str = settle(inputs.version, arguments.version, "version", root, lambda a, b: a == b)
    commit: str = settle(inputs.commit, arguments.commit.lower(), "commit", root,
                         lambda a, b: a.startswith(b) or b.startswith(a))[:COMMIT_LENGTH]
    registry: list[dict] = json.loads(inputs.registry.read_text())["controls"]
    api: Path = inputs.api
    generated: Path = api / "generated"
    type_files: list[Path] = sorted(generated.glob("gui_forms.*.rst"))
    for path in type_files:
        PAGES.types.add(path.stem.split(".", 1)[1])
    purposes: dict[str, str] = {e["type"]: e["purpose"] for e in registry}

    out: list[str] = [f"@@pack\t{version}\t{commit}", "@@tree"]
    home_label: str = f"GUI.Forms {version}"
    out.append(f"0\thome\t{home_label}\troot")
    categories: dict[str, list[str]] = {}
    for entry in registry:
        if entry["type"] in PAGES.types:
            categories.setdefault(entry["category"], []).append(entry["type"])
    out.append("1\tgroup/controls\tControls\tbook")
    for category in sorted(categories):
        out.append(f"2\tgroup/category/{category}\t{category}\tbook")
        for name in sorted(categories[category]):
            out.append(f"3\ttype/{name}\t{name}\tcontrol")
    topics: list[tuple[str, str, list[str]]] = []
    for path in sorted(api.glob("library.*.rst")):
        text: str = path.read_text()
        stem: str = path.stem.split(".", 1)[1]
        types: list[str] = [t for t in dict.fromkeys(re.findall(r'generated/gui_forms\.(\w+)', text))
                            if t in PAGES.types]
        topics.append((stem, topic_title(text, stem), types))
    out.append("1\tgroup/library\tLibrary\tbook")
    for stem, title, types in topics:
        out.append(f"2\ttopic/{stem}\t{clean(title)}\tbook")
        for name in types:
            out.append(f"3\ttype/{name}\t{name}\ttype")
    out.append("1\tgroup/all\tAll types, A to Z\tbook")
    for name in sorted(PAGES.types, key=str.lower):
        out.append(f"2\ttype/{name}\t{name}\ttype")

    def page(page_id: str, title: str, crumbs: list[tuple[str, str]], source: str, body: list[str]) -> None:
        out.append(f"@@page\t{page_id}")
        out.append(f"title\t{clean(title)}")
        if source:
            out.append(f"source\t{clean(source)}")
        for crumb_id, crumb_label in crumbs:
            out.append(f"crumb\t{crumb_id}\t{clean(crumb_label)}")
        out.extend(body)

    home: tuple[str, str] = ("home", home_label)
    page("home", f"GUI.Forms {version} reference", [home], "", [
        f"h1\tGUI.Forms {version} reference",
        "p\tThe API reference of GUI.Forms " + version + ", generated from the library's public headers "
        "and docs at commit " + CODE_ON + commit + CODE_OFF + ". Pick a control by its category, a library "
        "topic, or a type from the A to Z list; type in the search box to find a page by name.",
        "h2\tcontrols\tControls",
        *[f"card\tgroup/category/{c}\t{c}\t{len(categories[c])} controls" for c in sorted(categories)],
        "h2\tlibrary\tLibrary",
        *[f"card\ttopic/{stem}\t{clean(title)}\t{len(types)} types" for stem, title, types in topics],
    ])
    controls_crumbs: list[tuple[str, str]] = [home, ("group/controls", "Controls")]
    page("group/controls", "Controls", controls_crumbs, "", [
        "h1\tControls",
        "p\tThe controls of the registry (controls.json), by category.",
        *[f"card\tgroup/category/{c}\t{c}\t{len(categories[c])} controls" for c in sorted(categories)],
    ])
    for category in sorted(categories):
        page(f"group/category/{category}", category, controls_crumbs + [(f"group/category/{category}", category)],
             "", [f"h1\t{category}",
                  *[f"card\ttype/{t}\t{t}\t{clean(purposes.get(t, ''))}" for t in sorted(categories[category])]])
    library_crumbs: list[tuple[str, str]] = [home, ("group/library", "Library")]
    page("group/library", "Library", library_crumbs, "", [
        "h1\tLibrary",
        *[f"card\ttopic/{stem}\t{clean(title)}\t{len(types)} types" for stem, title, types in topics],
    ])
    for stem, title, types in topics:
        converted = Page((api / f"library.{stem}.rst").read_text())
        body: list[str] = converted.render()
        body.extend(f"card\ttype/{t}\t{t}\t{clean(purposes.get(t, ''))}" for t in types)
        page(f"topic/{stem}", title, library_crumbs + [(f"topic/{stem}", title)], "", body)
    page("group/all", "All types, A to Z", [home, ("group/all", "All types, A to Z")], "", [
        "h1\tAll types, A to Z",
        *[f"card\ttype/{t}\t{t}\t{clean(purposes.get(t, ''))}" for t in sorted(PAGES.types, key=str.lower)],
    ])
    category_of: dict[str, str] = {e["type"]: e["category"] for e in registry}
    for path in type_files:
        name: str = path.stem.split(".", 1)[1]
        converted = Page(path.read_text())
        body = converted.render()
        crumbs: list[tuple[str, str]] = [home]
        if name in category_of:
            crumbs += [("group/controls", "Controls"),
                       (f"group/category/{category_of[name]}", category_of[name])]
        else:
            crumbs += [("group/all", "All types, A to Z")]
        page(f"type/{name}", name, crumbs + [(f"type/{name}", name)], converted.source, body)

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    text: str = "\n".join(out) + "\n"
    arguments.out.write_text(text, encoding="utf-8")
    print(f"{arguments.out}: {len(text.encode()):,} bytes, {len(type_files)} type pages, {len(topics)} topics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
