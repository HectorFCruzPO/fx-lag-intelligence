"""Synthetic offline fixtures; no bank requests or real Task Scheduler calls."""
import contextlib
from datetime import datetime, timedelta, timezone
from email.message import Message
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from fx_lag import bccr_sdde as sdde, csv_history, monex, promerica
from fx_lag import scheduled_bccr as runner

RAW = (Path(__file__).parent / 'fixtures/promerica/branch.html').read_bytes()
STAMP = '2026-10-26T15:00:00Z'
NOW = datetime(2026, 10, 26, 15, tzinfo=timezone.utc)  # Monday 09:00 Costa Rica


def public_result():
    return promerica.parse_page(RAW, STAMP)


def market_result(indicator=3323):
    return {'observations': [{
        'source': 'BCCR', 'interface': 'SDDE',
        'source_url': sdde.series_endpoint(indicator), 'indicator': indicator,
        'rate': '454.31000000', 'units': 'CRC/USD',
        'effective_date': '2026-10-26', 'retrieved_at': STAMP,
    }], 'missing_dates': []}


class PageTests(unittest.TestCase):
    def test_compra_selected_and_accounting_reference_excluded(self):
        result = public_result()
        row = result['observations'][0]
        self.assertEqual(row['rate'], '443.00')
        self.assertEqual(row['indicator'], promerica.SERIES)
        self.assertEqual(row['source'], 'Promerica')
        self.assertEqual(row['units'], 'CRC/USD')
        self.assertIsNone(row['effective_date'])
        self.assertEqual(row['retrieved_at'], STAMP)
        self.assertNotIn('published_at', row)

    def test_inline_markup_entities_and_ignored_script(self):
        raw = RAW.replace(b'USD / CRC', b'<b>USD</b> / <b>CRC</b>')
        raw = raw.replace('¢443.00'.encode(), b'&#8353;&nbsp;443.00')
        raw = raw.replace(b'<body>', b'<body><script>Referencia contable USD/CRC 0</script>')
        self.assertEqual(promerica.parse_page(raw, STAMP)['observations'][0]['rate'], '443.00')

    def test_duplicate_quotes_are_ambiguous(self):
        section = RAW.split(b'<section>')[1].split(b'</section>')[0]
        raw = RAW.replace(b'<body>', b'<body>' + section)
        with self.assertRaises(sdde.ResponseError):
            promerica.parse_page(raw, STAMP)

    def test_missing_or_changed_layout_fails_closed(self):
        for raw in (b'<html>Access denied</html>', RAW.replace(b'Compra', b'Venta'),
                    RAW.replace(b'USD / CRC', b'EUR / CRC'),
                    RAW.replace(b'Referencia contable', b'Unknown section'),
                    RAW.replace(b'443.00', b'443,00'), RAW.replace(b'443.00', b'0.00'),
                    RAW.replace(b'443.00', b'999.00'), b'\xff'):
            with self.subTest(raw=raw[:30]), self.assertRaises(sdde.ResponseError):
                promerica.parse_page(raw, STAMP)

    def test_hidden_quote_is_not_used(self):
        for attribute in (b'hidden', b'aria-hidden="true"', b'style="display: none"'):
            raw = RAW.replace(b'<section>', b'<section ' + attribute + b'>', 1)
            with self.assertRaises(sdde.ResponseError):
                promerica.parse_page(raw, STAMP)

    def test_only_accounting_numbers_cannot_be_misclassified(self):
        raw = RAW.replace('¢443.00'.encode(), b'').replace('¢461.00'.encode(), b'')
        with self.assertRaises(sdde.ResponseError):
            promerica.parse_page(raw, STAMP)


class PublicTransportTests(unittest.TestCase):
    @patch.dict('os.environ', {'BCCR_SDDE_TOKEN': 'synthetic-never-forward'}, clear=True)
    @patch('fx_lag.promerica.build_opener')
    def test_public_request_never_sends_bccr_credentials(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.status = 200
        response.headers = Message()
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        response.read.return_value = RAW
        result = promerica.collect()
        req = opener.return_value.open.call_args.args[0]
        self.assertEqual(req.full_url, promerica.URL)
        self.assertIsNone(req.get_header('Authorization'))
        self.assertIsNone(req.get_header('Cookie'))
        self.assertIn('FXLagIntelligence', req.get_header('User-agent'))
        self.assertIsInstance(opener.call_args.args[0], promerica.NoRedirect)
        self.assertTrue(result['observations'][0]['retrieved_at'].endswith('Z'))

    @patch('fx_lag.promerica.build_opener')
    def test_http_errors_are_closed_unread_and_sanitized(self, opener):
        for code, kind in ((401, sdde.AuthenticationError), (403, sdde.AuthenticationError),
                           (429, sdde.RateLimitError), (500, sdde.NetworkError),
                           (302, sdde.NetworkError)):
            body = MagicMock()
            opener.return_value.open.side_effect = HTTPError(promerica.URL, code, 'private-body', {'Retry-After': '120'}, body)
            with self.subTest(code=code), self.assertRaises(kind) as caught:
                promerica.collect()
            body.read.assert_not_called()
            body.close.assert_called_once()
            self.assertNotIn('private-body', str(caught.exception))
            if code == 429:
                self.assertEqual(caught.exception.retry_after, '120')

    @patch('fx_lag.promerica.build_opener')
    def test_transport_failures_and_invalid_timeout(self, opener):
        for exc in (TimeoutError('private'), URLError('private')):
            opener.return_value.open.side_effect = exc
            with self.assertRaises(sdde.NetworkError) as caught:
                promerica.collect()
            self.assertNotIn('private', str(caught.exception))
        opener.reset_mock()
        for timeout in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(sdde.CollectorError):
                promerica.collect(timeout)
        opener.assert_not_called()

    @patch('fx_lag.promerica.build_opener')
    def test_content_type_status_and_size_limits(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.headers = Message()
        response.headers['Content-Type'] = 'application/json'
        response.status = 200
        with self.assertRaises(sdde.ResponseError):
            promerica.collect()
        response.headers.replace_header('Content-Type', 'text/html')
        response.status = 204
        with self.assertRaises(sdde.ResponseError):
            promerica.collect()
        response.status = 200
        response.read.return_value = b'x' * (promerica.MAX_BYTES + 1)
        with self.assertRaises(sdde.ResponseError):
            promerica.collect()

    def test_all_redirects_rejected(self):
        for url in (promerica.URL + 'other', 'http://www.promerica.fi.cr/', 'https://example.invalid/'):
            with self.assertRaises(sdde.NetworkError):
                promerica.NoRedirect().redirect_request(Request(promerica.URL), None, 302, '', {}, url)


class PublicHistoryAndCLITests(unittest.TestCase):
    @patch('fx_lag.promerica.build_opener')
    def test_cli_mocked_http_to_csv_without_source_date(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.status = 200
        response.headers = Message()
        response.headers['Content-Type'] = 'text/html'
        response.read.return_value = RAW
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            path = Path(folder) / 'public.csv'
            self.assertEqual(promerica.main(['--csv', str(path)]), 0)
            row = json.loads(out.getvalue())['observations'][0]
            self.assertIsNone(row['effective_date'])
            self.assertEqual(row['rate'], '443.00')
            self.assertIn('promerica_branch_usd_compra,443.00,CRC/USD,,', path.read_text())

    def test_csv_unknown_date_retention_and_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'public.csv'
            row = public_result()['observations'][0]
            for stamp, added in ((STAMP, 1), ('2026-10-26T15:30:00Z', 1), (STAMP, 0)):
                result = csv_history.save_observations(path, [dict(row, retrieved_at=stamp)], source_url=promerica.URL, indicator=promerica.SERIES)
                self.assertEqual(result['added'], added)
            self.assertEqual(len(path.read_text().splitlines()), 3)
            original = path.read_bytes()
            with self.assertRaises(csv_history.HistoryError):
                csv_history.save_observations(path, market_result()['observations'], source_url=monex.ENDPOINT, indicator=3323)
            self.assertEqual(path.read_bytes(), original)
            for field, value in (('effective_date', '2026-10-26'), ('source_url', monex.ENDPOINT), ('rate', '0.00')):
                with self.assertRaises(csv_history.HistoryError):
                    csv_history.save_observations(path, [dict(row, **{field: value})], source_url=promerica.URL, indicator=promerica.SERIES)

    @patch('fx_lag.promerica.collect')
    def test_cli_success_and_error(self, collect):
        collect.return_value = public_result()
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            path = str(Path(folder) / 'public.csv')
            self.assertEqual(promerica.main(['--csv', path]), 0)
            self.assertEqual(json.loads(out.getvalue())['observations'][0]['rate'], '443.00')
            collect.side_effect = sdde.NetworkError('Safe failure')
            before = Path(path).read_bytes()
            self.assertEqual(promerica.main(['--csv', path]), 1)
            self.assertEqual(Path(path).read_bytes(), before)


class AdditionalScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    @patch('fx_lag.scheduled_bccr.monex.collect', side_effect=lambda *args: market_result())
    def test_monex_once_per_slot_retains_unchanged_next_poll(self, collect):
        first = runner.run_once(self.root, now=NOW, source='monex')
        self.assertEqual(first['status'], 'saved')
        self.assertEqual(runner.run_once(self.root, now=NOW + timedelta(seconds=45), source='monex')['status'], 'already_attempted')
        self.assertEqual(runner.run_once(self.root, now=NOW + timedelta(minutes=30), source='monex')['status'], 'saved')
        self.assertTrue((self.root / 'monex-history.csv').exists())
        self.assertFalse((self.root / 'bccr-history.csv').exists())
        collect.assert_called_with(NOW.date() - timedelta(days=3), NOW.date() - timedelta(days=3), 30)
        self.assertEqual(collect.call_count, 2)

    @patch('fx_lag.scheduled_bccr.sdde.collect', side_effect=lambda *args: market_result(317))
    @patch('fx_lag.scheduled_bccr.monex.collect', side_effect=sdde.RateLimitError('429', '120'))
    def test_monex_429_pauses_both_bccr_sources_across_restart(self, monex_collect, bccr_collect):
        self.assertEqual(runner.run_once(self.root, now=NOW, source='monex')['status'], 'rate_limited')
        self.assertEqual(runner.run_once(self.root, now=NOW + timedelta(minutes=30))['status'], 'paused')
        bccr_collect.assert_not_called()
        self.assertEqual(runner.run_once(self.root, now=NOW + timedelta(days=1))['status'], 'saved')

    @patch('fx_lag.scheduled_bccr.sdde.collect', side_effect=sdde.RateLimitError('429', '172800'))
    @patch('fx_lag.scheduled_bccr.monex.collect')
    def test_bccr_429_pauses_monex_for_long_retry_after(self, monex_collect, bccr_collect):
        runner.run_once(self.root, now=NOW)
        self.assertEqual(runner.run_once(self.root, now=NOW + timedelta(days=1), source='monex')['status'], 'paused')
        monex_collect.assert_not_called()

    @patch('fx_lag.scheduled_bccr.promerica.collect', return_value=public_result())
    def test_promerica_saves_unknown_source_date(self, collect):
        result = runner.run_once(self.root, now=NOW, source='promerica')
        self.assertEqual(result['status'], 'saved')
        self.assertTrue((self.root / 'promerica-history.csv').exists())
        self.assertFalse((self.root / 'bccr-schedule.json').exists())
        collect.assert_called_once_with(30)

    @patch('fx_lag.scheduled_bccr.promerica.collect', side_effect=sdde.RateLimitError('429'))
    def test_public_429_persists_without_affecting_bccr(self, collect):
        self.assertEqual(runner.run_once(self.root, now=NOW, source='promerica')['status'], 'rate_limited')
        self.assertEqual(runner.run_once(self.root, now=NOW + timedelta(minutes=30), source='promerica')['status'], 'paused')
        collect.assert_called_once()
        with patch('fx_lag.scheduled_bccr.sdde.collect', return_value=market_result(317)):
            self.assertEqual(runner.run_once(self.root, now=NOW)['status'], 'saved')

    @patch('fx_lag.scheduled_bccr.promerica.collect', side_effect=sdde.AuthenticationError('403'))
    def test_public_access_rejection_stops_future_days(self, collect):
        self.assertEqual(runner.run_once(self.root, now=NOW, source='promerica')['status'], 'access_blocked')
        self.assertEqual(runner.run_once(self.root, now=NOW + timedelta(days=1), source='promerica')['status'], 'access_blocked')
        collect.assert_called_once()

    @patch('fx_lag.scheduled_bccr.monex.collect')
    def test_no_nights_weekends_or_outside_final_grace(self, collect):
        for now in (NOW - timedelta(hours=1), NOW + timedelta(hours=8, minutes=1), NOW + timedelta(days=5)):
            self.assertEqual(runner.run_once(self.root, now=now, source='monex')['status'], 'outside_window')
        collect.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    @patch('fx_lag.scheduled_bccr.monex.collect')
    def test_shared_api_lock_and_invalid_peer_state_fail_closed(self, collect):
        lock = self.root / 'sdde-schedule.lock'
        lock.write_text('')
        with self.assertRaises(runner.ScheduleError):
            runner.run_once(self.root, now=NOW, source='monex')
        lock.unlink()
        (self.root / 'bccr-schedule.json').write_text('not json')
        with self.assertRaises(runner.ScheduleError):
            runner.run_once(self.root, now=NOW, source='monex')
        collect.assert_not_called()

    @patch('fx_lag.scheduled_bccr.monex.collect', side_effect=sdde.NoDataError('Missing current closing rate'))
    def test_missing_monex_data_does_not_relabel_yesterday(self, collect):
        self.assertEqual(runner.run_once(self.root, now=NOW, source='monex')['status'], 'error')
        self.assertFalse((self.root / 'monex-history.csv').exists())
        self.assertEqual(runner.run_once(self.root, now=NOW + timedelta(seconds=30), source='monex')['status'], 'already_attempted')

    @patch('fx_lag.scheduled_bccr.run_once', return_value={'status': 'access_blocked'})
    def test_public_source_cli_propagates_blocked_exit(self, run):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(['--source', 'promerica', '--data-dir', str(self.root)]), 1)
        run.assert_called_once_with(str(self.root), 30, source='promerica')

    @patch('fx_lag.scheduled_bccr.monex.collect')
    def test_interrupted_bccr_peer_prevents_new_monex_request(self, collect):
        runner.write_state(self.root / 'bccr-schedule.json', {
            'version': 1, 'last_slot': runner.collection_slot(NOW),
            'last_attempt': runner.timestamp(NOW), 'status': 'started', 'blocked_until': None,
        })
        with self.assertRaises(runner.ScheduleError):
            runner.run_once(self.root, now=NOW + timedelta(minutes=30), source='monex')
        collect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
