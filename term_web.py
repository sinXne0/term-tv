#!/usr/bin/env python3
"""A small text-only web browser for the terminal."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import select
import shutil
import sys
import termios
import textwrap
import tty
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path


CSI = "\x1b["
CLEAR_SCREEN = CSI + "2J"
HOME = CSI + "H"
RESET = CSI + "0m"
BOLD = CSI + "1m"
DIM = CSI + "2m"
UNDERLINE = CSI + "4m"
SHOW_CURSOR = CSI + "?25h"


USER_AGENT = "term-web/0.1 (+https://github.com/sinXne0/term-tv)"
SEARCH_ENGINES = {
    "mojeek": "https://www.mojeek.com/search?q={query}",
    "ddg": "https://html.duckduckgo.com/html/?q={query}",
    "duckduckgo": "https://html.duckduckgo.com/html/?q={query}",
    "brave": "https://search.brave.com/search?q={query}&source=web",
}
DEFAULT_SEARCH_ENGINE = "mojeek"


@dataclass(frozen=True)
class Link:
    index: int
    text: str
    url: str


@dataclass(frozen=True)
class FormField:
    name: str
    value: str = ""
    label: str = ""
    hidden: bool = False


@dataclass(frozen=True)
class Form:
    index: int
    method: str
    action: str
    fields: list[FormField]


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    lines: list[str]
    links: list[Link]
    forms: list[Form] = field(default_factory=list)


@dataclass
class BrowserState:
    page: Page
    history: list[Page]
    scroll: int = 0
    search: str = ""
    match_index: int = -1


class BrowserTerminal:
    def __init__(self) -> None:
        self.fd = sys.stdin.fileno()
        self.original: list[int] | None = None

    def __enter__(self) -> "BrowserTerminal":
        if sys.stdin.isatty() and sys.stdout.isatty():
            self.original = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        return self

    def __exit__(self, *_: object) -> None:
        self.restore()
        print(SHOW_CURSOR + RESET, end="")

    def restore(self) -> None:
        if self.original is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.original)

    def cbreak(self) -> None:
        if self.original is not None:
            tty.setcbreak(self.fd)

    def read_key(self) -> str:
        data = os.read(self.fd, 1).decode(errors="ignore")
        if data != "\x1b":
            return data
        sequence = data
        while select.select([self.fd], [], [], 0.01)[0]:
            sequence += os.read(self.fd, 1).decode(errors="ignore")
            if sequence.endswith("~") or len(sequence) >= 6:
                break
        return {
            "\x1b[A": "up",
            "\x1b[B": "down",
            "\x1b[C": "right",
            "\x1b[D": "left",
            "\x1b[5~": "pageup",
            "\x1b[6~": "pagedown",
            "\x1b[H": "home",
            "\x1b[F": "end",
            "\x1bOH": "home",
            "\x1bOF": "end",
        }.get(sequence, "escape")

    def prompt(self, label: str) -> str:
        self.restore()
        try:
            return input(label).strip()
        finally:
            self.cbreak()

    def pause(self, message: str = "Press Enter to continue.") -> None:
        self.restore()
        try:
            input(message)
        finally:
            self.cbreak()


def terminal_width() -> int:
    return max(40, shutil.get_terminal_size((100, 30)).columns)


def terminal_height() -> int:
    return max(12, shutil.get_terminal_size((100, 30)).lines)


def viewport_height() -> int:
    return max(1, terminal_height() - 8)


def clamp_scroll(page: Page, scroll: int) -> int:
    return max(0, min(scroll, max(0, len(page.lines) - viewport_height())))


def bookmarks_path() -> Path:
    return Path.home() / ".local" / "share" / "term-web" / "bookmarks.json"


def load_bookmarks(path: Path | None = None) -> list[Link]:
    path = path or bookmarks_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    bookmarks = []
    for index, item in enumerate(data, 1):
        if isinstance(item, dict) and isinstance(item.get("url"), str):
            title = item.get("title") if isinstance(item.get("title"), str) else item["url"]
            bookmarks.append(Link(index, title, item["url"]))
    return bookmarks


def save_bookmarks(bookmarks: list[Link], path: Path | None = None) -> None:
    path = path or bookmarks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [{"title": bookmark.text, "url": bookmark.url} for bookmark in bookmarks]
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def add_bookmark(page: Page, path: Path | None = None) -> bool:
    if page.url == "about:home":
        return False
    bookmarks = load_bookmarks(path)
    if any(bookmark.url == page.url for bookmark in bookmarks):
        return False
    bookmarks.append(Link(len(bookmarks) + 1, page.title, page.url))
    save_bookmarks(bookmarks, path)
    return True


def bookmarks_page(path: Path | None = None) -> Page:
    bookmarks = load_bookmarks(path)
    lines = [
        "Bookmarks",
        "",
        "Type a bookmark number to open it, or use normal browser commands.",
    ]
    if not bookmarks:
        lines.extend(["", "No bookmarks yet. Use 'mark' on a page to save it."])
    return Page(
        url="about:bookmarks",
        title="Bookmarks",
        lines=lines,
        links=bookmarks,
    )


def help_page() -> Page:
    return Page(
        url="about:help",
        title="term-web help",
        lines=[
            "term-web navigation",
            "",
            "Fast keys do not require Enter:",
            "  j / Down       scroll down",
            "  k / Up         scroll up",
            "  d / PageDown   page down",
            "  u / PageUp     page up",
            "  g / Home       top",
            "  G / End        bottom",
            "  o              open URL or search",
            "  l              open link by number",
            "  /              search within page",
            "  n / N          next or previous search match",
            "  s              submit a simple GET form",
            "  m              bookmark current page",
            "  M              open bookmarks",
            "  b              back",
            "  r              reload",
            "  h              home",
            "  ?              this help",
            "  :              command prompt",
            "  q              quit",
            "",
            "Command prompt examples:",
            "  open example.com",
            "  search terminal browser",
            "  link 3",
            "  submit 1",
            "  mark",
            "  marks",
        ],
        links=[],
    )


def looks_like_host(value: str) -> bool:
    return bool(re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(:\d+)?(/.*)?$", value, re.I))


def normalize_address(value: str) -> str:
    value = value.strip()
    if not value:
        return "about:home"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"http", "https", "about"}:
        return value
    if looks_like_host(value):
        return f"https://{value}"
    engine = DEFAULT_SEARCH_ENGINE
    query = value
    shortcut = re.match(r"^!(\w+)\s+(.+)$", value)
    if shortcut and shortcut.group(1).casefold() in SEARCH_ENGINES:
        engine = shortcut.group(1).casefold()
        query = shortcut.group(2)
    return SEARCH_ENGINES[engine].format(query=urllib.parse.quote_plus(query))


def absolutize(base: str, href: str) -> str:
    href = html.unescape(href.strip())
    if not href or href.startswith(("javascript:", "mailto:", "tel:")):
        return ""
    return urllib.parse.urljoin(base, href)


class TextHTMLParser(HTMLParser):
    """Render readable text and collect links from basic HTML."""

    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tr",
        "ul",
    }

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self._in_title = False
        self._ignored_depth = 0
        self._link_stack: list[tuple[int, str, list[str]]] = []
        self._form_stack: list[dict[str, object]] = []
        self._links: list[Link] = []
        self._forms: list[Form] = []
        self._chunks: list[str] = []
        self._pending_space = False

    @property
    def links(self) -> list[Link]:
        return self._links

    @property
    def forms(self) -> list[Form]:
        return self._forms

    def _newline(self) -> None:
        while self._chunks and self._chunks[-1] == " ":
            self._chunks.pop()
        if not self._chunks or self._chunks[-1].endswith("\n\n"):
            return
        if self._chunks[-1].endswith("\n"):
            self._chunks.append("\n")
        else:
            self._chunks.append("\n\n")
        self._pending_space = False

    def _space(self) -> None:
        if self._chunks and not self._chunks[-1].endswith(("\n", " ")):
            self._pending_space = True

    def _append(self, text: str) -> None:
        collapsed = re.sub(r"\s+", " ", text)
        if not collapsed.strip():
            self._space()
            return
        if collapsed[:1].isspace():
            self._space()
        if self._pending_space:
            self._chunks.append(" ")
            self._pending_space = False
        text = collapsed.strip()
        self._chunks.append(text)
        if self._link_stack:
            self._link_stack[-1][2].append(text)
        if collapsed[-1:].isspace():
            self._pending_space = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in self.BLOCK_TAGS:
            self._newline()
        if tag == "li":
            self._append("- ")
        if tag == "a":
            href = dict(attrs).get("href") or ""
            url = absolutize(self.base_url, href)
            if url:
                index = len(self._links) + 1
                self._link_stack.append((index, url, []))
        if tag == "form":
            attributes = dict(attrs)
            action = absolutize(self.base_url, attributes.get("action") or self.base_url)
            method = (attributes.get("method") or "get").lower()
            self._form_stack.append(
                {"action": action, "method": method, "fields": []}
            )
        if tag == "input" and self._form_stack:
            attributes = dict(attrs)
            name = attributes.get("name") or ""
            if not name:
                return
            input_type = (attributes.get("type") or "text").lower()
            if input_type in {"button", "image", "reset", "submit"}:
                return
            field = FormField(
                name=name,
                value=attributes.get("value") or "",
                label=attributes.get("aria-label") or attributes.get("placeholder") or name,
                hidden=input_type == "hidden",
            )
            fields = self._form_stack[-1]["fields"]
            assert isinstance(fields, list)
            fields.append(field)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if tag == "title":
            self._in_title = False
            return
        if tag == "a" and self._link_stack:
            index, url, parts = self._link_stack.pop()
            label = " ".join(part for part in parts if part).strip() or url
            self._links.append(Link(index, label, url))
            self._space()
            self._append(f"[{index}]")
        if tag == "form" and self._form_stack:
            form_data = self._form_stack.pop()
            fields = form_data["fields"]
            assert isinstance(fields, list)
            form = Form(
                index=len(self._forms) + 1,
                method=str(form_data["method"]),
                action=str(form_data["action"]),
                fields=fields,
            )
            self._forms.append(form)
            if fields:
                self._newline()
                self._append(f"[form {form.index}: {form.method.upper()} {form.action}]")
        if tag in self.BLOCK_TAGS:
            self._newline()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._in_title:
            self.title += data.strip()
            return
        self._append(data)

    def render(self, width: int) -> list[str]:
        text = html.unescape("".join(self._chunks))
        paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
        lines: list[str] = []
        for paragraph in paragraphs:
            for line in paragraph.splitlines():
                if line.strip():
                    lines.extend(textwrap.wrap(line.strip(), width=width) or [""])
            lines.append("")
        if lines and lines[-1] == "":
            lines.pop()
        return lines or ["(No readable text found.)"]


def decode_response(data: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w.-]+)", content_type, re.I)
    charset = match.group(1) if match else "utf-8"
    try:
        return data.decode(charset, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def fetch(url: str, timeout: int = 20) -> tuple[str, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        content_type = response.headers.get("content-type", "text/html")
        data = response.read(3_000_000)
    return final_url, content_type, decode_response(data, content_type)


def parse_page(url: str, content_type: str, body: str, width: int | None = None) -> Page:
    width = width or terminal_width()
    render_width = max(40, width - 4)
    if "html" not in content_type.lower():
        lines = []
        for raw_line in body.splitlines() or [""]:
            lines.extend(textwrap.wrap(raw_line, width=render_width) or [""])
        return Page(url=url, title=url, lines=lines, links=[])

    parser = TextHTMLParser(url)
    parser.feed(body)
    parser.close()
    return Page(
        url=url,
        title=parser.title.strip() or url,
        lines=parser.render(render_width),
        links=parser.links,
        forms=parser.forms,
    )


def about_home() -> Page:
    return Page(
        url="about:home",
        title="term-web",
        lines=[
            "term-web",
            "",
            "A terminal-only text browser.",
            "",
            "Enter a URL, search words, or a link number.",
            "Default search uses Mojeek because DuckDuckGo often challenges terminal traffic.",
            "Use shortcuts like !ddg cats or !brave cats to choose another engine.",
            "",
            "Controls:",
            "  number  follow link",
            "  j/k     scroll down/up",
            "  d/u     page down/up",
            "  /text   search page",
            "  n/N     next/previous match",
            "  mark    bookmark current page",
            "  marks   show bookmarks",
            "  b       back",
            "  r       reload",
            "  h       home",
            "  q       quit",
        ],
        links=[
            Link(1, "Python", "https://www.python.org/"),
            Link(2, "Wikipedia", "https://www.wikipedia.org/"),
            Link(3, "Mojeek", "https://www.mojeek.com/"),
        ],
    )


def load_page(address: str) -> Page:
    url = normalize_address(address)
    if url == "about:home":
        return about_home()
    if url == "about:bookmarks":
        return bookmarks_page()
    if url == "about:help":
        return help_page()
    final_url, content_type, body = fetch(url)
    return parse_page(final_url, content_type, body)


def search_matches(page: Page, query: str) -> list[int]:
    query = query.casefold().strip()
    if not query:
        return []
    return [
        index
        for index, line in enumerate(page.lines)
        if query in line.casefold()
    ]


def form_target(form: Form, values: dict[str, str]) -> str:
    parameters = [(field.name, values.get(field.name, field.value)) for field in form.fields]
    if form.method == "get":
        parsed = urllib.parse.urlparse(form.action)
        existing = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query = urllib.parse.urlencode(existing + parameters)
        return urllib.parse.urlunparse(parsed._replace(query=query))
    return form.action


def prompt_form(form: Form, ask=input) -> str:
    if form.method != "get":
        raise RuntimeError("Only GET forms are supported in this version.")
    values = {}
    for field in form.fields:
        if field.hidden:
            values[field.name] = field.value
            continue
        prompt = field.label or field.name
        suffix = f" [{field.value}]" if field.value else ""
        answer = ask(f"{prompt}{suffix}: ").strip()
        values[field.name] = answer if answer else field.value
    return form_target(form, values)


def set_page(state: BrowserState, page: Page, push_history: bool = True) -> None:
    if push_history:
        state.history.append(state.page)
    state.page = page
    state.scroll = 0
    state.search = ""
    state.match_index = -1


def find_on_page(state: BrowserState, query: str, direction: int = 1) -> bool:
    matches = search_matches(state.page, query)
    if not matches:
        return False
    if state.search.casefold() != query.casefold():
        state.match_index = 0
    else:
        state.match_index = (state.match_index + direction) % len(matches)
    state.search = query
    state.scroll = clamp_scroll(state.page, matches[state.match_index])
    return True


def go_back(state: BrowserState) -> None:
    if state.history:
        state.page = state.history.pop()
        state.scroll = 0
        state.search = ""
        state.match_index = -1


def open_target(state: BrowserState, target: str) -> str | None:
    try:
        next_page = load_page(target)
    except (OSError, urllib.error.URLError, UnicodeError) as error:
        return str(error)
    set_page(state, next_page)
    return None


def link_target(page: Page, value: str) -> tuple[str | None, str | None]:
    if not value.isdigit():
        return None, "Enter a link number."
    index = int(value)
    link = next((link for link in page.links if link.index == index), None)
    if link is None:
        return None, f"No link numbered {index}."
    return link.url, None


def form_by_number(page: Page, value: str) -> tuple[Form | None, str | None]:
    if not value.isdigit():
        return None, "Enter a form number."
    form = next((form for form in page.forms if form.index == int(value)), None)
    if form is None:
        return None, f"No form numbered {value}."
    return form, None


def command_target(state: BrowserState, command: str) -> tuple[str | None, str | None]:
    lowered = command.lower().strip()
    if lowered.startswith("open "):
        return command[5:].strip(), None
    if lowered.startswith("search "):
        return command[7:].strip(), None
    if lowered.startswith("link "):
        return link_target(state.page, lowered.removeprefix("link ").strip())
    if command.isdigit():
        return link_target(state.page, command)
    if lowered in {"reload", "r"}:
        return state.page.url, None
    return command, None


def print_page(state: BrowserState, error: str | None = None) -> None:
    page = state.page
    width = terminal_width()
    height = viewport_height()
    state.scroll = clamp_scroll(page, state.scroll)
    total = max(1, len(page.lines))
    top = min(state.scroll + 1, total)
    bottom = min(state.scroll + height, total)
    search_label = f" search: {state.search}" if state.search else ""
    print(CLEAR_SCREEN + HOME, end="")
    print(f"{BOLD}{page.title[:width]}{RESET}")
    print(f"{DIM}{page.url[:width]} · lines {top}-{bottom}/{total}{search_label}{RESET}")
    print()
    if error:
        print(f"error: {error}\n")
    visible_lines = page.lines[state.scroll : state.scroll + height]
    for line in visible_lines:
        if state.search and state.search.casefold() in line.casefold():
            print((BOLD + line[:width] + RESET))
        else:
            print(line[:width])
    if page.links:
        print()
        print(f"{UNDERLINE}Links{RESET}")
        for link in page.links[:10]:
            print(f"  {link.index:>2}. {link.text[: width - 8]}")
    if page.forms:
        print()
        print(f"{UNDERLINE}Forms{RESET}")
        for form in page.forms[:5]:
            visible_fields = [field.label or field.name for field in form.fields if not field.hidden]
            fields = ", ".join(visible_fields[:4]) or "hidden fields only"
            print(f"  {form.index:>2}. {form.method.upper()} {fields[: width - 12]}")
    print()
    print(
        f"{DIM}j/k/↑/↓ scroll · d/u/Pg page · o open · l links · / find · "
        f"s submit · m mark · ? help · q quit{RESET}"
    )


def handle_prompt_command(
    state: BrowserState,
    command: str,
    ask=input,
) -> tuple[bool, str | None]:
    if not command:
        return False, None
    lowered = command.lower()
    if lowered == "q":
        return True, None
    if lowered in {"j", "down"}:
        state.scroll = clamp_scroll(state.page, state.scroll + 1)
        return False, None
    if lowered in {"k", "up"}:
        state.scroll = clamp_scroll(state.page, state.scroll - 1)
        return False, None
    if lowered in {"d", "pagedown"}:
        state.scroll = clamp_scroll(state.page, state.scroll + viewport_height())
        return False, None
    if lowered in {"u", "pageup"}:
        state.scroll = clamp_scroll(state.page, state.scroll - viewport_height())
        return False, None
    if lowered == "g":
        state.scroll = 0
        return False, None
    if command == "G":
        state.scroll = clamp_scroll(state.page, len(state.page.lines))
        return False, None
    if command.startswith("/") and len(command) > 1:
        if not find_on_page(state, command[1:]):
            return False, f"No matches for {command[1:]!r}."
        return False, None
    if command == "n" and state.search:
        find_on_page(state, state.search, 1)
        return False, None
    if command == "N" and state.search:
        find_on_page(state, state.search, -1)
        return False, None
    if lowered in {"mark", "m"}:
        return (
            False,
            "Bookmark saved."
            if add_bookmark(state.page)
            else "Bookmark already exists or cannot be saved.",
        )
    if lowered in {"marks", "bookmarks"}:
        set_page(state, bookmarks_page())
        return False, None
    if lowered in {"?", "help"}:
        set_page(state, help_page())
        return False, None
    if lowered == "forms":
        return (
            False,
            f"{len(state.page.forms)} form(s) on this page."
            if state.page.forms
            else "No forms on this page.",
        )
    if lowered.startswith("submit "):
        form, error = form_by_number(state.page, lowered.removeprefix("submit ").strip())
        if error:
            return False, error
        assert form is not None
        try:
            target = prompt_form(form, ask)
        except RuntimeError as error:
            return False, str(error)
        return False, open_target(state, target)
    if lowered == "h":
        set_page(state, about_home())
        return False, None
    if lowered == "b":
        go_back(state)
        return False, None

    target, error = command_target(state, command)
    if error:
        return False, error
    assert target is not None
    return False, open_target(state, target)


def browse_prompt(state: BrowserState) -> int:
    while True:
        print_page(state)
        try:
            command = input("term-web> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 130
        should_quit, message = handle_prompt_command(state, command)
        if should_quit:
            return 0
        if message:
            print_page(state, message)
            input("Press Enter to continue.")


def browse(start: str = "about:home") -> int:
    state = BrowserState(page=load_page(start), history=[])
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return browse_prompt(state)

    with BrowserTerminal() as terminal:
        while True:
            print_page(state)
            key = terminal.read_key()
            if key in {"q", "\x03"}:
                return 0 if key == "q" else 130
            if key in {"j", "down"}:
                state.scroll = clamp_scroll(state.page, state.scroll + 1)
            elif key in {"k", "up"}:
                state.scroll = clamp_scroll(state.page, state.scroll - 1)
            elif key in {"d", "pagedown", " "}:
                state.scroll = clamp_scroll(state.page, state.scroll + viewport_height())
            elif key in {"u", "pageup"}:
                state.scroll = clamp_scroll(state.page, state.scroll - viewport_height())
            elif key in {"g", "home"}:
                state.scroll = 0
            elif key in {"G", "end"}:
                state.scroll = clamp_scroll(state.page, len(state.page.lines))
            elif key == "b":
                go_back(state)
            elif key == "h":
                set_page(state, about_home())
            elif key == "?":
                set_page(state, help_page())
            elif key == "r":
                message = open_target(state, state.page.url)
                if message:
                    print_page(state, message)
                    terminal.pause()
            elif key == "m":
                message = (
                    "Bookmark saved."
                    if add_bookmark(state.page)
                    else "Bookmark already exists or cannot be saved."
                )
                print_page(state, message)
                terminal.pause()
            elif key == "M":
                set_page(state, bookmarks_page())
            elif key == "n" and state.search:
                find_on_page(state, state.search, 1)
            elif key == "N" and state.search:
                find_on_page(state, state.search, -1)
            elif key == "/":
                query = terminal.prompt("Find: ")
                if query and not find_on_page(state, query):
                    print_page(state, f"No matches for {query!r}.")
                    terminal.pause()
            elif key == "o":
                target = terminal.prompt("Open URL/search: ")
                if target:
                    message = open_target(state, target)
                    if message:
                        print_page(state, message)
                        terminal.pause()
            elif key == "l":
                value = terminal.prompt("Link number: ")
                target, message = link_target(state.page, value)
                if message:
                    print_page(state, message)
                    terminal.pause()
                elif target:
                    message = open_target(state, target)
                    if message:
                        print_page(state, message)
                        terminal.pause()
            elif key == "s":
                value = terminal.prompt("Form number: ")
                form, message = form_by_number(state.page, value)
                if message:
                    print_page(state, message)
                    terminal.pause()
                elif form:
                    try:
                        target = prompt_form(form, terminal.prompt)
                    except RuntimeError as error:
                        print_page(state, str(error))
                        terminal.pause()
                        continue
                    message = open_target(state, target)
                    if message:
                        print_page(state, message)
                        terminal.pause()
            elif key == ":":
                command = terminal.prompt(":")
                should_quit, message = handle_prompt_command(
                    state, command, terminal.prompt
                )
                if should_quit:
                    return 0
                if message:
                    print_page(state, message)
                    terminal.pause()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Browse the web as text in a terminal.")
    parser.add_argument("address", nargs="?", default="about:home", help="URL or search")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return browse(args.address)


if __name__ == "__main__":
    raise SystemExit(main())
