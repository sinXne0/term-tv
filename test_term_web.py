import importlib.util
import sys
import unittest
from pathlib import Path


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
            "https://duckduckgo.com/html/?q=terminal+browser",
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

    def test_about_home_has_starter_links(self):
        page = web.about_home()
        self.assertEqual(page.url, "about:home")
        self.assertGreaterEqual(len(page.links), 3)


if __name__ == "__main__":
    unittest.main()
