"""Tests covering reliability fixes, new providers, matching improvements, and CLI features."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import board_search
import india_sources
import job_applicant as app
import resume_match
from applicant.http_client import get_json
from applicant.models import sanitize_csv_cell, validate_profile, validate_sources


class _FakeHTTPResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class ImprovementTests(unittest.TestCase):
    def test_docx_preserves_breaks_tabs_and_headers(self):
        import zipfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resume.docx"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr(
                    "word/document.xml",
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    "<w:p><w:r><w:t>Python</w:t><w:br/><w:t>FastAPI</w:t><w:tab/><w:t>PostgreSQL</w:t></w:r></w:p>"
                    "</w:document>",
                )
                z.writestr(
                    "word/header1.xml",
                    '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    "<w:p><w:r><w:t>Kubernetes Architect</w:t></w:r></w:p>"
                    "</w:hdr>",
                )
            text = resume_match.read_resume(path)
            self.assertIn("Python\nFastAPI PostgreSQL", text)
            self.assertIn("Kubernetes Architect", text)
            toks = resume_match.tokens(text)
            self.assertIn("python", toks)
            self.assertIn("fastapi", toks)
            self.assertIn("postgresql", toks)
            self.assertIn("kubernetes", toks)

    def test_tech_tokenization_synonyms_and_missing_terms(self):
        toks = resume_match.tokens("Built Node.js, CI/CD pipelines, and K8s with Postgres")
        self.assertIn("node.js", toks)
        self.assertIn("ci/cd", toks)
        self.assertIn("kubernetes", toks)
        self.assertIn("postgresql", toks)
        self.assertIn("pipeline", toks)

        jobs = [
            {"title": "Backend Engineer", "company": "Acme", "description": "NodeJS, PostgreSQL, Docker, GraphQL"},
            {"title": "Frontend Engineer", "company": "Beta", "description": "Vue.js and CSS"},
        ]
        ranked = resume_match.rank(jobs, "Node.js Postgres developer")
        self.assertEqual(ranked[0]["company"], "Acme")
        self.assertIn("node.js", ranked[0]["matched_terms"])
        self.assertIn("postgresql", ranked[0]["matched_terms"])
        self.assertIn("docker", ranked[0]["missing_terms"])
        self.assertIn("graphql", ranked[0]["missing_terms"])

    def test_csv_formula_injection_sanitized(self):
        self.assertEqual(sanitize_csv_cell("=HYPERLINK(\"https://evil.example\")"), "'=HYPERLINK(\"https://evil.example\")")
        self.assertEqual(sanitize_csv_cell("+CMD|'/C calc'!A0"), "'+CMD|'/C calc'!A0")
        self.assertEqual(sanitize_csv_cell("-2+3"), "'-2+3")
        self.assertEqual(sanitize_csv_cell("@SUM(1,2)"), "'@SUM(1,2)")
        self.assertEqual(sanitize_csv_cell("https://example.com/job"), "https://example.com/job")
        self.assertEqual(sanitize_csv_cell("Acme Corp"), "Acme Corp")

        with tempfile.TemporaryDirectory() as tmp, patch("builtins.print"):
            out = Path(tmp) / "jobs.json"
            settings = {
                "public_sources": [],
                "direct_jobs": [
                    {
                        "company": "=CMD|'calc'",
                        "title": "Python Engineer",
                        "location": "Remote",
                        "url": "https://example.com/job/1",
                        "description": "Python FastAPI Docker",
                    }
                ],
            }
            app.search(None, out, settings=settings, resume="Python FastAPI")
            with out.with_suffix(".csv").open(encoding="utf-8-sig") as f:
                row = list(csv.DictReader(f))[0]
            self.assertEqual(row["company"], "'=CMD|'calc'")
            self.assertIn("docker", row["missing_terms"])

    def test_http_get_json_retries_transient_503_and_429(self):
        calls = {"count": 0}
        sleeps = []

        def fake_urlopen(req, timeout=30):
            calls["count"] += 1
            if calls["count"] == 1:
                raise HTTPError(req.full_url, 429, "Too Many Requests", {"Retry-After": "0.1"}, None)
            if calls["count"] == 2:
                raise HTTPError(req.full_url, 503, "Unavailable", {}, None)
            return _FakeHTTPResponse(b'{"ok": true}')

        result = get_json(
            "https://example.com/api",
            retries=3,
            backoff_base=0.05,
            urlopen_fn=fake_urlopen,
            sleep_fn=sleeps.append,
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls["count"], 3)
        self.assertEqual(len(sleeps), 2)
        self.assertAlmostEqual(sleeps[0], 0.1)

    def test_ashby_board_and_arbeitnow_pagination(self):
        ashby_payload = {
            "jobs": [
                {
                    "id": "a1",
                    "title": "Staff Python Engineer",
                    "location": "Bengaluru",
                    "secondaryLocations": [{"location": "Mumbai"}],
                    "isRemote": True,
                    "isListed": True,
                    "applyUrl": "https://jobs.ashbyhq.com/acme/a1/application",
                    "jobUrl": "https://jobs.ashbyhq.com/acme/a1",
                    "descriptionPlain": "Python distributed systems",
                },
                {"id": "a2", "title": "Hidden Role", "isListed": False, "jobUrl": "https://jobs.ashbyhq.com/acme/a2"},
            ]
        }
        jobs = app.fetch_board({"type": "ashby", "token": "acme", "company": "Acme"}, lambda url: ashby_payload)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["source"], "ashby")
        self.assertIn("Bengaluru, Mumbai | Remote", jobs[0]["location"])
        self.assertEqual(jobs[0]["url"], "https://jobs.ashbyhq.com/acme/a1/application")

        seen_urls = []

        def fake_fetch(url):
            seen_urls.append(url)
            if "page=2" in url:
                return {"data": [{"title": "Role 2", "company_name": "Co", "url": "https://example.com/2", "location": "Berlin", "description": "Python"}]}
            return {"data": [{"title": "Role 1", "company_name": "Co", "url": "https://example.com/1", "location": "Berlin", "description": "Python"}]}

        failures = []
        with patch.object(app, "get_json", side_effect=fake_fetch):
            collected, _ = app.collect_public_jobs({"public_sources": ["arbeitnow"], "arbeitnow_pages": 2}, failures)
        self.assertEqual(len(collected), 2)
        self.assertEqual(len(seen_urls), 2)
        self.assertIn("page=2", seen_urls[1])
        self.assertEqual(failures, [])

    def test_adzuna_preserves_partial_results_and_skips_remote_where(self):
        calls = []

        def fake_urlopen(req, timeout=30):
            calls.append(req.full_url)
            if len(calls) == 1:
                body = json.dumps({
                    "results": [
                        {
                            "title": "Python Engineer",
                            "company": {"display_name": "Acme"},
                            "location": {"display_name": "India"},
                            "redirect_url": "https://example.com/adzuna/1",
                            "description": "Python role",
                        }
                    ]
                }).encode("utf-8")
                return _FakeHTTPResponse(body)
            raise OSError("https://secret-key-leak")

        errors = []
        settings = {
            "title_keywords": ["Python", "Backend"],
            "location_keywords": ["Remote"],
            "adzuna": {"enabled": True, "country": "in", "pages": 1},
        }
        with patch.dict("os.environ", {"ADZUNA_APP_ID": "id", "ADZUNA_APP_KEY": "secret-key-leak"}):
            with patch("board_search.urlopen", side_effect=fake_urlopen):
                jobs = board_search.adzuna_jobs(settings, errors=errors)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(errors), 1)
        self.assertNotIn("secret-key-leak", errors[0]["error"])
        self.assertNotIn("where=Remote", calls[0])

    def test_india_compound_locations_and_malformed_board_handling(self):
        self.assertTrue(india_sources.india_search({"location_keywords": ["Bangalore, India"]}))
        self.assertTrue(india_sources.india_search({"location_keywords": ["Hyderabad, Telangana"]}))
        self.assertTrue(india_sources.india_search({"location_keywords": ["New Delhi, NCR"]}))
        self.assertFalse(india_sources.india_search({"location_keywords": ["Indiana, USA"]}))

        errors = []
        boards = india_sources.effective_boards(
            {
                "boards": [
                    {"type": "lever", "token": "Acme"},
                    {"type": "LEVER", "token": "acme"},
                    {"type": "lever"},  # Missing token
                    "not-a-dict",
                ]
            },
            errors=errors,
        )
        self.assertEqual(len(boards), 1)
        self.assertEqual(len(errors), 2)

    def test_description_keywords_and_variant_matching(self):
        settings = {
            "title_keywords": ["backend engineer", "frontend developer"],
            "description_keywords": ["fastapi", "microservices"],
        }
        self.assertTrue(
            app.matches(
                {"title": "Back-End Engineer", "location": "Remote", "description": "Build micro-service APIs with FastAPI"},
                settings,
            )
        )
        self.assertFalse(
            app.matches(
                {"title": "Back-End Engineer", "location": "Remote", "description": "Java Spring only"},
                settings,
            )
        )

    def test_expanded_profile_aliases_and_schema_validation(self):
        profile = {
            "github_url": "https://github.com/ada",
            "portfolio_url": "https://ada.dev",
            "state": "Karnataka",
            "current_company": "Analytical Engines",
            "current_title": "Staff Engineer",
            "notice_period": "30 days",
        }
        self.assertEqual(app.profile_value({"label": "GitHub Profile"}, profile), "https://github.com/ada")
        self.assertEqual(app.profile_value({"label": "Personal Website"}, profile), "https://ada.dev")
        self.assertEqual(app.profile_value({"label": "State / Province"}, profile), "Karnataka")
        self.assertEqual(app.profile_value({"label": "Current Employer"}, profile), "Analytical Engines")
        self.assertEqual(app.profile_value({"label": "Current Role"}, profile), "Staff Engineer")
        self.assertEqual(app.profile_value({"label": "Notice Period"}, profile), "30 days")

        with self.assertRaises(ValueError):
            validate_profile(["not", "a", "dict"])
        with self.assertRaises(ValueError):
            validate_sources({"title_keywords": "not-a-list"})

    def test_apply_safe_open_scope_preview_and_status_tracking(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            profile_path = folder / "profile.json"
            jobs_path = folder / "jobs.json"
            profile_path.write_text(json.dumps({"email": "ada@example.com"}))
            jobs_path.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "company": "Acme",
                                "title": "Python Engineer",
                                "location": "Remote",
                                "url": "https://board.example/jobs/1",
                            }
                        ]
                    }
                )
            )

            page = MagicMock()
            page.frames = [page]
            page.is_closed.return_value = False
            page.title.return_value = "Application"
            page.url = "https://board.example/jobs/1"
            page.locator.return_value.inner_text.return_value = "Application submitted"

            def fake_goto(dest, **kwargs):
                page.url = dest

            page.goto.side_effect = fake_goto

            context = MagicMock()
            context.pages = [page]
            playwright = MagicMock()
            playwright.chromium.launch_persistent_context.return_value = context
            sync = MagicMock()
            sync.return_value.__enter__.return_value = playwright
            module = types.ModuleType("playwright.sync_api")
            module.sync_playwright = sync
            module.TimeoutError = TimeoutError

            args = types.SimpleNamespace(
                profile=str(profile_path), url=None, jobs=str(jobs_path), job=1, scope=None
            )
            commands = [
                "open",
                "http://insecure.example/bad",  # Must NOT crash the session
                "open",
                "https://employer.example/direct-apply",
                "scope form#main",
                "preview 1",
                "verify 1",
                "yes",
            ]
            with patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"), "playwright.sync_api": module}), \
                    patch("builtins.input", side_effect=commands), \
                    patch("builtins.print"), \
                    patch.object(app, "preview_autofill", return_value={"status": "ok"}) as preview_mock:
                app.apply(args)

            preview_mock.assert_called_once()
            self.assertEqual(preview_mock.call_args.args[3], "form#main")

            log_rows = json.loads((folder / "application-log.json").read_text())
            self.assertEqual(len(log_rows), 1)
            self.assertEqual(log_rows[0]["status"], "submitted_by_user")
            self.assertEqual(log_rows[0]["company"], "Acme")
            self.assertEqual(log_rows[0]["title"], "Python Engineer")
            self.assertEqual(log_rows[0]["applied_url"], "https://employer.example/direct-apply")

            # Search with --hide-applied filters out the already submitted job.
            out_path = folder / "new_jobs.json"
            settings = {
                "public_sources": [],
                "direct_jobs": [
                    {"company": "Acme", "title": "Python Engineer", "location": "Remote", "url": "https://board.example/jobs/1"},
                    {"company": "Beta", "title": "Python Engineer", "location": "Remote", "url": "https://board.example/jobs/2"},
                ],
            }
            with patch("builtins.print"):
                payload = app.search(None, out_path, settings=settings, profile_path=profile_path, hide_applied=True)
            self.assertEqual([j["company"] for j in payload["jobs"]], ["Beta"])
            self.assertEqual(payload["diagnostics"]["hidden_already_processed"], 1)

            # Status subcommand runs cleanly and reports counts.
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                rc = app.main(["status", "--profile", str(profile_path), "--jobs", str(out_path)])
            self.assertEqual(rc, 0)
            output_text = buf.getvalue()
            self.assertIn("submitted_by_user: 1", output_text)
            self.assertIn("1 unapplied/remaining", output_text)

    def test_verification_log_deduplicated_in_same_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            profile_path = folder / "profile.json"
            profile_path.write_text("{}")

            page = MagicMock()
            page.frames = [page]
            page.is_closed.return_value = False
            page.title.return_value = "Just a moment..."
            page.url = "https://board.example/jobs/1"
            page.locator.return_value.inner_text.return_value = "Verifying you are human"

            context = MagicMock()
            context.pages = [page]
            playwright = MagicMock()
            playwright.chromium.launch_persistent_context.return_value = context
            sync = MagicMock()
            sync.return_value.__enter__.return_value = playwright
            module = types.ModuleType("playwright.sync_api")
            module.sync_playwright = sync
            module.TimeoutError = TimeoutError

            args = types.SimpleNamespace(
                profile=str(profile_path), url="https://board.example/jobs/1", jobs="jobs.json", job=None, scope=None
            )
            with patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"), "playwright.sync_api": module}), \
                    patch("builtins.input", side_effect=["check 1", "check 1", "skip"]), \
                    patch("builtins.print"):
                app.apply(args)

            rows = json.loads((folder / "application-log.json").read_text())
            self.assertEqual([r["status"] for r in rows], ["needs_manual_verification", "skipped_by_user"])


if __name__ == "__main__":
    unittest.main()
