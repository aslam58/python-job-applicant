import unittest
from urllib.parse import parse_qs, urlsplit

import job_applicant as app
from india_sources import effective_boards, india_search


class IndiaTests(unittest.TestCase):
    def test_existing_city_settings_enable_preset_without_overwriting_boards(self):
        board = {"type": "lever", "token": "custom"}
        settings = {"location_keywords": ["chennai"], "boards": [board]}
        self.assertTrue(india_search(settings))
        result = effective_boards(settings)
        self.assertIn(board, result)
        self.assertTrue(any(b["type"] == "smartrecruiters" for b in result))
        self.assertEqual(settings["boards"], [board])

    def test_no_india_preset_for_unrelated_location(self):
        self.assertEqual(effective_boards({"location_keywords": ["Paris"]}), [])

    def test_explicit_preset_override_and_deduplication(self):
        board = {"type": "lever", "token": "test"}
        self.assertEqual(effective_boards({"india": {"enabled": True, "boards": [board]},
                                          "boards": [board]}), [board])

    def test_aliases_and_full_stack_title(self):
        for requested, actual in (("bangalore", "Bengaluru"), ("vizag", "Visakhapatnam"),
                                  ("gurgaon", "Gurugram"), ("kochi", "Cochin")):
            self.assertTrue(app.matches({"title": "Full-Stack Developer", "location": actual},
                                       {"title_keywords": ["full stack developer"],
                                        "location_keywords": [requested]}))
        self.assertFalse(app.matches({"title": "Developer", "location": "Paris"},
                                    {"location_keywords": ["bangalore"]}))
        self.assertFalse(app.matches({"title": "Developer", "location": "Remote | India"},
                                    {"location_keywords": ["chennai"]}))

    def test_smartrecruiters_paginates_country_filter_and_skips_internal(self):
        urls = []
        row = {"id": "123", "name": "Developer",
               "location": {"city": "Bengaluru", "country": "in"}}
        def fetch(url):
            urls.append(url)
            offset = parse_qs(urlsplit(url).query)["offset"][0]
            return {"totalFound": 101, "content": [row] * 100 if offset == "0"
                    else [{**row, "id": "private", "visibility": "INTERNAL"}]}
        jobs = app.fetch_board({"type": "smartrecruiters", "token": "Test", "country": "in"}, fetch)
        self.assertEqual(len(urls), 2)
        self.assertIn("country=in", urls[0])
        self.assertEqual(len(jobs), 100)
        self.assertIn("India", jobs[0]["location"])
        self.assertTrue(jobs[0]["url"].startswith("https://jobs.smartrecruiters.com/Test/"))

    def test_india_remote_query_and_returned_location(self):
        urls = []
        def fetch(url):
            urls.append(url)
            return {"jobs": []}
        app.public_jobs("himalayas", "php", fetch, country="IN")
        self.assertIn("country=IN", urls[0])
