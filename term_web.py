#!/usr/bin/env python3
"""A small text-only web browser for the terminal."""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser


CSI = "\x1b["
CLEAR_SCREEN = CSI + "2J"
HOME = CSI + "H"
RESET = CSI + "0m"
BOLD = CSI + "1m"
DIM = CSI + "2m"
UNDERLINE = CSI + "4m"


USER_AGENT = "term-web/0.1 (+https://github.com/sinXne0/term-tv)"
SEARCH_URL = "https://duckduckgo.com/html/?q={query}"


@dataclass(frozen=True)
class Link:
    index: int
    text: str
    url: str


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    lines: list[str]
    links: list[Link]


def terminal_width() -> int:
    return max(40, shutil.get_terminal_size((100, 30)).columns)


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
    return SEARCH_URL.format(query=urllib.parse.quote_plus(value))


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
        self._links: list[Link] = []
        self._chunks: list[str] = []
        self._pending_space = False

    @property
    def links(self) -> list[Link]:
        return self._links

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
            "",
            "Controls:",
            "  number  follow link",
            "  b       back",
            "  r       reload",
            "  h       home",
            "  q       quit",
        ],
        links=[
            Link(1, "Python", "https://www.python.org/"),
            Link(2, "Wikipedia", "https://www.wikipedia.org/"),
            Link(3, "DuckDuckGo", "https://duckduckgo.com/html/"),
        ],
    )


def load_page(address: str) -> Page:
    url = normalize_address(address)
    if url == "about:home":
        return about_home()
    final_url, content_type, body = fetch(url)
    return parse_page(final_url, content_type, body)


def print_page(page: Page, error: str | None = None) -> None:
    width = terminal_width()
    print(CLEAR_SCREEN + HOME, end="")
    print(f"{BOLD}{page.title[:width]}{RESET}")
    print(f"{DIM}{page.url[:width]}{RESET}")
    print()
    if error:
        print(f"error: {error}\n")
    for line in page.lines[: max(1, shutil.get_terminal_size((100, 30)).lines - 8)]:
        print(line[:width])
    if page.links:
        print()
        print(f"{UNDERLINE}Links{RESET}")
        for link in page.links[:10]:
            print(f"  {link.index:>2}. {link.text[: width - 8]}")
    print()
    print(f"{DIM}Enter URL/search/link · b back · r reload · h home · q quit{RESET}")


def browse(start: str = "about:home") -> int:
    history: list[Page] = []
    page = load_page(start)
    while True:
        print_page(page)
        try:
            command = input("term-web> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 130
        if not command:
            continue
        lowered = command.lower()
        if lowered == "q":
            return 0
        if lowered == "h":
            history.append(page)
            page = about_home()
            continue
        if lowered == "b":
            if history:
                page = history.pop()
            continue
        if lowered == "r":
            target = page.url
        elif command.isdigit():
            index = int(command)
            link = next((link for link in page.links if link.index == index), None)
            if link is None:
                print_page(page, f"No link numbered {index}.")
                input("Press Enter to continue.")
                continue
            target = link.url
        else:
            target = command

        try:
            next_page = load_page(target)
        except (OSError, urllib.error.URLError, UnicodeError) as error:
            print_page(page, str(error))
            input("Press Enter to continue.")
            continue
        history.append(page)
        page = next_page


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Browse the web as text in a terminal.")
    parser.add_argument("address", nargs="?", default="about:home", help="URL or search")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return browse(args.address)


if __name__ == "__main__":
    raise SystemExit(main())
