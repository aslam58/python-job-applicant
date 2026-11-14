import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from board_search import adzuna_jobs, search_links, write_search_page


class BoardTests(unittest.TestCase):
    def test_search_encodes_preferences_without_resume(self):
        links = search_links({"title_keywords": ["C++ & testing"], "location_keywords": ["Paris", "Remote"]})
        self.assertEqual(len(links), 38)
        q = parse_qs(urlsplit(links[0]["url"]).query)["q"][0]
        self.assertIn("C++ & testing", q)
        self.assertIn("Paris", q)

    def test_html_escapes_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, path = write_search_page({"title_keywords": ["<script>"]}, Path(tmp)/"jobs.json")
            text = path.read_text()
            self.assertIn("&lt;script&gt;", text)
            self.assertNotIn("<script>", text)

    def test_api_errors_do_not_leak_credentials(self):
        with patch.dict("os.environ", {"ADZUNA_APP_ID": "privateid", "ADZUNA_APP_KEY": "privatekey"}):
            with patch("board_search.urlopen", side_effect=OSError("https://privatekey")):
                with self.assertRaises(ValueError) as caught:
                    adzuna_jobs({"adzuna": {"country": "in"}})
                self.assertNotIn("privatekey", str(caught.exception))
