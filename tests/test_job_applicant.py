import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("job_applicant", Path(__file__).parents[1] / "job_applicant.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class ApplicantTests(unittest.TestCase):
    def test_greenhouse_public_feed(self):
        jobs = app.fetch_board({"type": "greenhouse", "token": "test", "company": "Test"},
            lambda url: {"jobs": [{"id": 123, "title": "AML Analyst", "location": {"name": "India"},
                                   "absolute_url": "https://example.com/jobs/123", "content": "<p>Risk &amp; controls</p>"}]})
        self.assertEqual(jobs[0]["id"], "123")
        self.assertIn("Risk & controls", jobs[0]["description"])
        self.assertEqual(jobs[0]["status"], "published_on_board")

    def test_lever_eu_and_apply_url(self):
        urls = []
        def fetch(url):
            urls.append(url)
            return [{"id": "x", "text": "Fraud Analyst", "categories": {"location": "India"},
                     "applyUrl": "https://example.com/apply", "descriptionPlain": "Fraud investigations"}]
        jobs = app.fetch_board({"type": "lever", "token": "test", "region": "eu"}, fetch)
        self.assertIn("api.eu.lever.co", urls[0])
        self.assertEqual(jobs[0]["url"], "https://example.com/apply")

    def test_filters_title_location_exclusion(self):
        settings = {"title_keywords": ["AML", "fraud"], "location_keywords": ["Mumbai"],
                    "exclude_title_keywords": ["director"]}
        self.assertTrue(app.matches({"title": "Fraud Analyst", "location": "Mumbai, India"}, settings))
        self.assertFalse(app.matches({"title": "Director AML", "location": "Mumbai"}, settings))
        self.assertFalse(app.matches({"title": "AML Analyst", "location": "London"}, settings))

    def test_unknown_is_not_no_or_zero(self):
        self.assertIsNone(app.profile_value({"label": "Email", "type": "email"}, app.PROFILE))
        self.assertIsNone(app.profile_value({"label": "Years of AML experience", "type": "number"}, app.PROFILE))

    def test_name_is_not_guessed_from_single_field(self):
        self.assertIsNone(app.profile_value({"label": "First Name"}, {"full_name": "Test Candidate"}))
        self.assertEqual(app.profile_value({"label": "Full Legal Name*"}, {"first_name": "Test", "last_name": "Candidate"}), "Test Candidate")

    def test_sensitive_fields_never_autofilled(self):
        for label in ("PAN", "Date of birth", "Gender", "Passport", "I agree to terms", "Medical disability"):
            with self.subTest(label=label):
                self.assertIsNone(app.profile_value({"label": label}, {"questions": {label: "secret"}}))

    def test_checkbox_and_custom_combobox_require_manual_input(self):
        self.assertIsNone(app.profile_value({"label": "Email", "type": "checkbox"}, {"email": "test@example.com"}))
        self.assertIsNone(app.profile_value({"label": "Country", "role": "combobox"}, {"country": "Test"}))

    def test_explicit_question_exact_match(self):
        profile = {"questions": {"What is your notice period?": "30 days", "Years of experience": 0}}
        self.assertEqual(app.profile_value({"label": "What is your notice period?*"}, profile), "30 days")
        self.assertEqual(app.profile_value({"label": "Years of experience", "type": "number"}, profile), "0")
        self.assertIsNone(app.profile_value({"label": "Required notice period"}, profile))

    def test_resume_not_cover_letter_or_photo(self):
        self.assertTrue(app.is_resume_input({"id": "resume-upload-input"}))
        self.assertTrue(app.is_resume_input({"label": "English Resume*"}))
        self.assertFalse(app.is_resume_input({"label": "Cover letter", "id": "cover-resume"}))
        self.assertFalse(app.is_resume_input({"label": "Photo"}))

    def test_url_and_token_validation(self):
        for value in ("file:///private/path", "javascript:alert(1)", "https://user:password@example.com"):
            with self.assertRaises(ValueError):
                app.validate_url(value)
        with self.assertRaises(ValueError):
            app.fetch_board({"type": "greenhouse", "token": "../private"})
        self.assertEqual(app.canonical_url("https://example.com/job/1/?utm_source=test#apply"), "https://example.com/job/1")

    def test_search_deduplicates_and_reports_board_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources, output = Path(tmp)/"sources.json", Path(tmp)/"jobs.json"
            app.save_json(sources, {"boards": [{"type": "unknown", "token": "test"}], "direct_jobs": [
                {"company": "Test", "title": "AML Analyst", "location": "India", "url": "https://example.com/job/1"},
                {"company": "Test", "title": "AML Analyst", "location": "India", "url": "https://example.com/job/1?source=test"}]})
            with patch("builtins.print"):
                payload = app.search(sources, output)
            self.assertEqual(len(payload["jobs"]), 1)
            self.assertEqual(len(payload["errors"]), 1)
            self.assertTrue(output.with_suffix(".csv").exists())
            self.assertEqual(payload["jobs"][0]["status"], "not_verified")

    def test_log_preserves_history_without_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"log.json"
            app.log_result(path, "https://example.com/job", "awaiting_manual_completion")
            app.log_result(path, "https://example.com/job", "submitted_by_user")
            rows = json.loads(path.read_text())
            self.assertEqual(len(rows), 2)
            self.assertNotIn("email", rows[1])
            self.assertEqual(rows[1]["status"], "submitted_by_user")


if __name__ == "__main__":
    unittest.main()
