"""Opt-in real Chromium regression test. Set RUN_BROWSER_TESTS=1 to enable."""
import os
from pathlib import Path
import tempfile
import unittest

import job_applicant as app


@unittest.skipUnless(os.getenv("RUN_BROWSER_TESTS") == "1", "Opt-in Chromium check")
class BrowserFormTests(unittest.TestCase):
    def test_wrapped_select_label_and_resume_upload(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
            resume = Path(tmp)/"sample.txt"
            resume.write_text("Synthetic resume")
            browser = pw.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content("""
                  <form>
                    <label>Country<select id="country"><option value=""></option>
                      <option value="test">Test country</option></select></label>
                    <label>City<input id="city" value="Existing city"></label>
                    <label>Gender<input id="gender"></label>
                    <label>Resume<input type="file" id="resume"></label>
                  </form>
                """)
                app.autofill(page, {"country": "Test country", "city": "Replacement"}, resume)
                self.assertEqual(page.locator("#country").input_value(), "test")
                self.assertEqual(page.locator("#city").input_value(), "Existing city")
                self.assertEqual(page.locator("#gender").input_value(), "")
                self.assertEqual(page.locator("#resume").evaluate("e => e.files[0].name"), "sample.txt")
            finally:
                browser.close()
