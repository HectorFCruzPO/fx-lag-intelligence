"""Offline descriptive-report tests; all rates and scenarios are synthetic."""
import contextlib
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fx_lag import report
from fx_lag.csv_history import FIELDS

FIXTURES = Path(__file__).parent / 'fixtures/report'
AS_OF = datetime(2026, 10, 26, 17, tzinfo=timezone.utc)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'data'
        shutil.copytree(FIXTURES, self.root)

    def build(self, **kwargs):
        return report.build_report(self.root, as_of=kwargs.pop('as_of', AS_OF), **kwargs)

    def source(self, result, key):
        return next(item for item in result['sources'] if item['source_key'] == key)

    def read(self, key):
        with (self.root / f'{key}-history.csv').open(newline='') as stream:
            return list(csv.DictReader(stream))

    def write(self, key, rows):
        with (self.root / f'{key}-history.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def test_three_series_identity_precision_and_unknown_times(self):
        result = self.build()
        self.assertEqual(result['units'], 'CRC/USD')
        self.assertEqual([s['indicator'] for s in result['sources']], [317, 3323, 'promerica_branch_usd_compra'])
        self.assertEqual(self.source(result, 'bccr')['latest_observation']['rate'], '499.00000000')
        public = self.source(result, 'promerica')
        self.assertIsNone(public['latest_observation']['effective_date'])
        self.assertEqual(public['daily_history'], [])
        self.assertEqual(public['freshness'], 'unverified')
        self.assertEqual(public['minutes_since_last_retrieval'], '60.00')
        self.assertNotIn('published_at', public['latest_observation'])

    def test_changes_and_unchanged_polls_retained(self):
        result = self.build()
        bccr = self.source(result, 'bccr')['comparisons']
        self.assertEqual([x['direction'] for x in bccr], ['unchanged', 'decrease'])
        self.assertEqual(bccr[1]['delta_crc_per_usd'], '-1.00000000')
        self.assertEqual(bccr[1]['comparison_kind'], 'same_effective_date_revision')
        window = bccr[1]['observation_check_window']
        self.assertEqual(window['previous_check_at'], '2026-10-26T15:30:00Z')
        self.assertEqual(window['current_check_at'], '2026-10-26T16:00:00Z')
        self.assertEqual(window['elapsed_minutes'], '30.00')
        self.assertFalse(window['publication_transition_verified'])

    def test_increases_and_numeric_equality(self):
        rows = self.read('promerica')
        rows[1]['rate'] = '490.0000'
        rows[2]['rate'] = '491.125000000000000000000000000001'
        self.write('promerica', rows)
        comparisons = self.source(self.build(), 'promerica')['comparisons']
        self.assertEqual(comparisons[0]['direction'], 'unchanged')
        self.assertEqual(comparisons[1]['direction'], 'increase')
        self.assertEqual(Decimal(comparisons[1]['delta_crc_per_usd']), Decimal('1.125000000000000000000000000001'))

    def test_retrieval_sorting_not_file_order(self):
        before = self.build()
        self.write('bccr', list(reversed(self.read('bccr'))))
        self.assertEqual(self.build(), before)

    def test_backfilled_daily_batch_is_not_intraday_evidence(self):
        rows = self.read('monex')
        for row, day in zip(rows, ('2026-10-20', '2026-10-21', '2026-10-22')):
            row['effective_date'] = day
            row['retrieved_at'] = '2026-10-26T16:00:00Z'
        self.write('monex', rows)
        source = self.source(self.build(), 'monex')
        self.assertEqual(source['status'], 'historical_only')
        self.assertIsNone(source['latest_observation'])
        self.assertEqual(source['comparisons'], [])
        self.assertEqual(source['historical_row_count'], 3)
        self.assertEqual(len(source['daily_comparisons']), 2)
        self.assertIsNone(source['daily_comparisons'][0]['observation_check_window'])
        self.assertEqual(source['daily_comparisons'][0]['comparison_kind'], 'daily_period_change')

    def test_future_effective_dates_are_not_current_polls(self):
        rows = self.read('bccr')
        rows[-1]['effective_date'] = '2026-10-27'
        self.write('bccr', rows)
        source = self.source(self.build(), 'bccr')
        self.assertEqual(source['future_effective_row_count'], 1)
        self.assertEqual(source['eligible_poll_count'], 2)
        self.assertEqual(len(source['daily_history']), 1)

    def test_new_daily_period_has_no_intraday_transition_window(self):
        rows = self.read('bccr')
        rows[-1].update(effective_date='2026-10-27', retrieved_at='2026-10-27T15:00:00Z')
        self.write('bccr', rows)
        source = self.source(self.build(as_of=AS_OF + timedelta(days=1)), 'bccr')
        item = source['comparisons'][-1]
        self.assertEqual(item['comparison_kind'], 'daily_period_change')
        self.assertIsNone(item['observation_check_window'])

    def test_daily_latest_revision_retains_first_and_last_retrieval(self):
        source = self.source(self.build(), 'bccr')
        day = source['daily_history'][0]
        self.assertEqual(day['first_retrieved_at'], '2026-10-26T15:00:00Z')
        self.assertEqual(day['last_retrieved_at'], '2026-10-26T16:00:00Z')
        self.assertEqual(day['revision_count'], 1)
        self.assertEqual(day['retrieval_count'], 3)

    def test_as_of_excludes_later_retrievals(self):
        source = self.source(self.build(as_of=datetime(2026, 10, 26, 15, 15, tzinfo=timezone.utc)), 'bccr')
        self.assertEqual(source['observation_count'], 1)
        self.assertEqual(source['future_retrieval_rows_excluded'], 2)
        self.assertEqual(source['daily_history'][0]['rate'], '500.00000000')
        self.assertEqual(source['comparisons'], [])

    def test_all_future_retrievals_do_not_become_latest(self):
        source = self.source(self.build(as_of=AS_OF - timedelta(days=1)), 'bccr')
        self.assertIsNone(source['latest_observation'])
        self.assertEqual(source['status'], 'no_observations')

    def test_gap_diagnostic_and_schedule_break_not_outage(self):
        rows = self.read('promerica')
        rows[-1]['retrieved_at'] = '2026-10-27T15:00:00Z'
        self.write('promerica', rows)
        source = self.source(self.build(as_of=AS_OF + timedelta(days=1)), 'promerica')
        gap = source['observation_gaps'][0]
        self.assertTrue(gap['spans_local_dates'])
        self.assertEqual(gap['elapsed_minutes'], '1410.00')
        self.assertTrue(any('do not prove failed' in item for item in self.build()['limitations']))

    def test_gap_threshold_is_configurable_not_freshness_rule(self):
        source = self.source(self.build(gap_minutes=20), 'bccr')
        self.assertEqual(len(source['observation_gaps']), 2)
        self.assertEqual(source['freshness'], 'unverified')

    def test_utc_midnight_uses_costa_rica_effective_date(self):
        rows = self.read('bccr')[:1]
        rows[0].update(retrieved_at='2026-10-27T01:00:00Z', effective_date='2026-10-26')
        self.write('bccr', rows)
        source = self.source(self.build(as_of=AS_OF + timedelta(days=1)), 'bccr')
        self.assertEqual(source['eligible_poll_count'], 1)
        self.assertEqual(source['historical_row_count'], 0)

    def test_missing_and_empty_histories_are_explicit(self):
        (self.root / 'monex-history.csv').unlink()
        self.write('promerica', [])
        result = self.build()
        self.assertEqual(self.source(result, 'monex')['status'], 'missing_file')
        self.assertEqual(self.source(result, 'promerica')['status'], 'no_observations')

    def test_missing_directory_is_read_only(self):
        folder = self.root / 'not-created'
        result = report.build_report(folder, as_of=AS_OF)
        self.assertTrue(all(s['status'] == 'missing_file' for s in result['sources']))
        self.assertFalse(folder.exists())

    def test_conflicting_same_timestamp_is_rejected(self):
        rows = self.read('promerica')
        rows[1]['retrieved_at'] = rows[0]['retrieved_at']
        rows[1]['rate'] = '489'
        self.write('promerica', rows)
        with self.assertRaises(report.ReportError):
            self.build()

    def test_corrupt_and_foreign_history_fail_with_sanitized_error(self):
        for value in ('private-bad-csv', 'source,rate\nSECRET,=BAD\n'):
            (self.root / 'bccr-history.csv').write_text(value)
            with self.assertRaises(report.ReportError) as caught:
                self.build()
            self.assertNotIn(value, str(caught.exception))
        self.write('bccr', self.read('monex'))
        with self.assertRaises(report.ReportError):
            self.build()

    def test_symlink_history_is_rejected(self):
        path = self.root / 'bccr-history.csv'
        original = path.with_suffix('.backup')
        path.rename(original)
        try:
            path.symlink_to(original)
        except OSError:
            self.skipTest('Symlink creation unavailable')
        with self.assertRaises(report.ReportError):
            self.build()

    @patch('fx_lag.promerica.build_opener')
    @patch('fx_lag.bccr_sdde.build_opener')
    def test_report_has_no_network_or_history_writes(self, sdde_open, public_open):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.build()
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)
        sdde_open.assert_not_called()
        public_open.assert_not_called()

    def test_changed_timeline_is_chronological_without_lag_claim(self):
        timeline = self.build()['movement_timeline']
        self.assertEqual([x['source_key'] for x in timeline], ['monex', 'bccr', 'promerica'])
        self.assertTrue(all(x['direction'] != 'unchanged' for x in timeline))
        self.assertTrue(all('lag_minutes' not in x for x in timeline))

    def test_markdown_has_local_timezone_daily_and_unchanged_sections(self):
        text = report.markdown(self.build())
        for value in ('Costa Rica (UTC-06:00)', '2026-10-26T09:30:00-06:00',
                      'unchanged', 'same_effective_date_revision', 'unknown', 'Interpretation limits'):
            self.assertIn(value, text)
        self.assertNotIn('executable proceeds', text)

    def test_cli_json_and_markdown(self):
        for fmt in ('json', 'markdown'):
            with self.subTest(fmt=fmt), contextlib.redirect_stdout(io.StringIO()) as out:
                code = report.main(['--data-dir', str(self.root), '--as-of', AS_OF.isoformat(), '--format', fmt])
                self.assertEqual(code, 0)
                if fmt == 'json':
                    self.assertEqual(json.loads(out.getvalue())['as_of'], '2026-10-26T17:00:00Z')
                else:
                    self.assertIn('# Three-source', out.getvalue())

    def test_cli_safe_failures(self):
        for args in (['--as-of', 'bad'], ['--as-of', '2026-10-26T17:00:00']):
            with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(report.main(args), 1)
                self.assertEqual(out.getvalue(), '')
                self.assertIn('timezone-aware', err.getvalue())
        for args in (['--gap-minutes', '0'], ['--limit', '-1']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                report.main(args)
            self.assertEqual(caught.exception.code, 2)

    def test_invalid_report_options_and_arithmetic_limits(self):
        for value in (0, -1, True, 525601):
            with self.assertRaises(report.ReportError):
                self.build(gap_minutes=value)
        with self.assertRaises(report.ReportError):
            self.build(as_of=AS_OF.replace(tzinfo=None))
        with self.assertRaises(report.ReportError):
            report.difference('1E20000', '1')

    def test_prior_local_date_poll_is_labeled_without_freshness_claim(self):
        result = self.build(as_of=AS_OF + timedelta(days=1))
        self.assertTrue(self.source(result, 'monex')['latest_poll_from_prior_local_date'])
        self.assertIn('observed (prior local date)', report.markdown(result))
        self.assertEqual(self.source(result, 'monex')['freshness'], 'unverified')

    def test_historical_daily_changes_are_visible_in_markdown(self):
        rows = self.read('monex')[:2]
        rows[0]['effective_date'] = '2026-10-20'
        rows[1]['effective_date'] = '2026-10-21'
        self.write('monex', rows)
        text = report.markdown(self.build())
        self.assertIn('Daily change CRC/USD', text)
        self.assertIn('decrease -0.50000000', text)
        self.assertIn('historical_only', text)


if __name__ == '__main__':
    unittest.main()
