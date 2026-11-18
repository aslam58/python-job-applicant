import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import job_applicant as app


class ApplicationRecoveryTests(unittest.TestCase):
    def run_application(self, commands, title='Application', body='Application form', timeout=False,
                        history=(), url='https://example.com/job'):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'profile.json').write_text('{}')
            (folder / 'jobs.json').write_text(json.dumps({'jobs': [
                {'company': 'Example employer', 'title': 'Example role',
                 'url': url}]}))
            if history:
                app.save_json(folder / 'application-log.json', history)
            page = MagicMock()
            page.frames = [page]
            page.is_closed.return_value = False
            page.title.return_value = title
            page.url = url
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
            if not commands:
                sync.assert_not_called()
            else:
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

    def test_faq_match_keeps_session_open(self):
        rows, _ = self.run_application(['verify 1', 'no', 'skip'],
                                       body='Our receipt will say: Thank you for applying.')
        self.assertEqual([row['status'] for row in rows], ['skipped_by_user'])

    def test_confirmed_receipt_blocks_only_same_route(self):
        url = 'https://example.com/#/jobs/123'
        rows, _ = self.run_application(['verify 1', 'yes'], body='Application submitted', url=url)
        self.assertEqual(rows[0]['status'], 'submitted_by_user')
        self.assertEqual(rows[0]['receipt'], 'Application submitted')
        self.assertTrue(rows[0]['screenshot'].endswith('.png'))
        same, _ = self.run_application([], url=url, history=rows)
        self.assertEqual(same, rows)
        other, _ = self.run_application(['quit'], url='https://example.com/#/jobs/456', history=rows)
        self.assertEqual(other[-1]['status'], 'awaiting_manual_completion')

    def test_legacy_signal_allows_reopening(self):
        history = [{'job_url': 'https://example.com/job#apply', 'status': 'submitted_signal_detected'}]
        rows, _ = self.run_application(['quit'], history=history)
        self.assertEqual(rows[0], history[0])
        self.assertEqual(rows[-1]['status'], 'awaiting_manual_completion')
