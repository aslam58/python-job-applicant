import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import job_applicant as app


class ApplicationRecoveryTests(unittest.TestCase):
    def run_application(self, commands, title='Application', body='Application form', timeout=False):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'profile.json').write_text('{}')
            (folder / 'jobs.json').write_text(json.dumps({'jobs': [
                {'company': 'Example employer', 'title': 'Example role',
                 'url': 'https://example.com/job'}]}))
            page = MagicMock()
            page.is_closed.return_value = False
            page.title.return_value = title
            page.url = 'https://example.com/job'
            page.locator.return_value.inner_text.return_value = body
            if timeout:
                page.goto.side_effect = TimeoutError('Timed out')
            context = MagicMock()
            context.pages = [page]
            playwright = MagicMock()
            playwright.chromium.launch_persistent_context.return_value = context
            sync = MagicMock()
            sync.return_value.__enter__.return_value = playwright
            module = types.ModuleType('playwright.sync_api')
            module.sync_playwright = sync
            module.TimeoutError = TimeoutError
            args = types.SimpleNamespace(profile=str(folder/'profile.json'), url=None,
                                         jobs=str(folder/'jobs.json'), job=1, scope=None)
            with patch.dict(sys.modules, {'playwright': types.ModuleType('playwright'),
                                         'playwright.sync_api': module}), \
                    patch('builtins.input', side_effect=commands), \
                    patch('builtins.print'), patch.object(app, 'autofill') as fill:
                app.apply(args)
            context.new_page.assert_not_called()
            context.close.assert_called_once()
            rows = json.loads((folder/'application-log.json').read_text())
            return rows, fill.call_count

    def test_security_page_blocks_fill_and_records_verification(self):
        rows, calls = self.run_application(['fill 1', 'quit'], title='Just a moment...')
        self.assertEqual(calls, 0)
        self.assertEqual([r['status'] for r in rows],
                         ['needs_manual_verification', 'awaiting_manual_completion'])

    def test_body_detects_verification_with_other_title(self):
        rows, calls = self.run_application(['check 1', 'skip'],
                                           body='Performing security verification')
        self.assertEqual(calls, 0)
        self.assertEqual(rows[0]['status'], 'needs_manual_verification')
        self.assertEqual(rows[-1]['status'], 'skipped_by_user')

    def test_timeout_still_allows_skip(self):
        rows, calls = self.run_application(['skip'], timeout=True)
        self.assertEqual(rows[-1]['status'], 'skipped_by_user')
        self.assertEqual(calls, 0)
