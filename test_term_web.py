import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("term_web.py")
SPEC = importlib.util.spec_from_file_location("term_web", MODULE_PATH)
assert SPEC and SPEC.loader
web = importlib.util.module_from_spec(SPEC)
sys.modules["term_web"] = web
SPEC.loader.exec_module(web)


class BrowserTests(unittest.TestCase):
    def test_normalize_address_accepts_urls_and_hosts(self):
        self.assertEqual(web.normalize_address("https://example.com"), "https://example.com")
        self.assertEqual(web.normalize_address("example.com"), "https://example.com")
        self.assertEqual(web.normalize_address("about:home"), "about:home")

    def test_normalize_address_turns_words_into_search(self):
        self.assertEqual(
            web.normalize_address("terminal browser"),
            "https://www.mojeek.com/search?q=terminal+browser",
        )

    def test_normalize_address_supports_search_shortcuts(self):
        self.assertEqual(
            web.normalize_address("!ddg terminal browser"),
            "https://html.duckduckgo.com/html/?q=terminal+browser",
        )
        self.assertEqual(
            web.normalize_address("!brave terminal browser"),
            "https://search.brave.com/search?q=terminal+browser&source=web",
        )

    def test_absolutize_rejects_non_web_actions(self):
        self.assertEqual(web.absolutize("https://example.com", "javascript:void(0)"), "")
        self.assertEqual(web.absolutize("https://example.com", "mailto:a@example.com"), "")
        self.assertEqual(
            web.absolutize("https://example.com/path/", "../next"),
            "https://example.com/next",
        )

    def test_parse_html_extracts_text_title_and_numbered_links(self):
        page = web.parse_page(
            "https://example.com/",
            "text/html",
            """
            <html>
              <head><title>Example</title><style>body { color: red; }</style></head>
              <body>
                <h1>Hello</h1>
                <p>Read <a href="/docs">docs</a>.</p>
                <script>alert("ignored")</script>
              </body>
            </html>
            """,
            width=80,
        )
        rendered = "\n".join(page.lines)
        self.assertEqual(page.title, "Example")
        self.assertIn("Hello", rendered)
        self.assertIn("docs [1]", rendered)
        self.assertNotIn("ignored", rendered)
        self.assertEqual(page.links[0].url, "https://example.com/docs")

    def test_parse_plain_text_wraps_lines_without_links(self):
        page = web.parse_page("https://example.com/text", "text/plain", "hello world", width=80)
        self.assertEqual(page.lines, ["hello world"])
        self.assertEqual(page.links, [])

    def test_parse_html_extracts_get_forms(self):
        page = web.parse_page(
            "https://example.com/search",
            "text/html",
            """
            <form action="/find" method="get">
              <input type="hidden" name="source" value="web">
              <input name="q" placeholder="Search">
              <input type="submit" value="Go">
            </form>
            """,
            width=80,
        )
        self.assertEqual(len(page.forms), 1)
        form = page.forms[0]
        self.assertEqual(form.index, 1)
        self.assertEqual(form.method, "get")
        self.assertEqual(form.action, "https://example.com/find")
        self.assertEqual([field.name for field in form.fields], ["source", "q"])
        self.assertTrue(form.fields[0].hidden)

    def test_form_target_builds_get_url(self):
        form = web.Form(
            1,
            "get",
            "https://example.com/search?existing=1",
            [
                web.FormField("source", "web", hidden=True),
                web.FormField("q", ""),
            ],
        )
        self.assertEqual(
            web.form_target(form, {"q": "terminal browser"}),
            "https://example.com/search?existing=1&source=web&q=terminal+browser",
        )

    def test_about_home_has_starter_links(self):
        page = web.about_home()
        self.assertEqual(page.url, "about:home")
        self.assertGreaterEqual(len(page.links), 3)

    def test_clamp_scroll_stays_inside_page(self):
        page = web.Page("about:test", "Test", [str(index) for index in range(20)], [])
        self.assertEqual(web.clamp_scroll(page, -10), 0)
        with mock.patch.object(web, "viewport_height", return_value=5):
            self.assertEqual(web.clamp_scroll(page, 99), 15)

    def test_find_on_page_moves_scroll_to_match(self):
        page = web.Page(
            "about:test",
            "Test",
            ["alpha", "beta", "needle here", "gamma", "needle again"],
            [],
        )
        state = web.BrowserState(page=page, history=[])
        with mock.patch.object(web, "viewport_height", return_value=2):
            self.assertTrue(web.find_on_page(state, "needle"))
            self.assertEqual(state.scroll, 2)
            self.assertEqual(state.match_index, 0)
            self.assertTrue(web.find_on_page(state, "needle"))
            self.assertEqual(state.scroll, 3)
            self.assertEqual(state.match_index, 1)

    def test_bookmarks_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bookmarks.json"
            page = web.Page("https://example.com", "Example", [], [])

            self.assertTrue(web.add_bookmark(page, path))
            self.assertFalse(web.add_bookmark(page, path))

            bookmarks = web.load_bookmarks(path)
            self.assertEqual(len(bookmarks), 1)
            self.assertEqual(bookmarks[0].text, "Example")
            self.assertEqual(bookmarks[0].url, "https://example.com")

            bookmark_page = web.bookmarks_page(path)
            self.assertEqual(bookmark_page.title, "Bookmarks")
            self.assertEqual(bookmark_page.links[0].url, "https://example.com")


if __name__ == "__main__":
    unittest.main()
