"""Offline tests for optional local CSV history; all observations are synthetic."""
import contextlib
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fx_lag import bccr_sdde as sdde
from fx_lag import csv_history as history


def observation(day="2026-01-01", rate="502.12000", stamp="2026-01-04T12:00:00Z"):
    return {
        "source": "BCCR", "interface": "SDDE", "source_url": sdde.ENDPOINT,
        "indicator": 317, "rate": rate, "units": "CRC/USD",
        "effective_date": day, "retrieved_at": stamp,
    }


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "data" / "bccr-history.csv"

    def save(self, rows):
        return history.save_observations(self.path, rows, source_url=sdde.ENDPOINT)

    def read(self):
        with self.path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_create_parent_header_precision_and_provenance(self):
        row = observation(rate="500.12345678901234567890")
        self.assertEqual(self.save([row]), {"added": 1, "skipped": 0})
        expected = dict(row, indicator="317")
        self.assertEqual(self.read(), [expected])
        self.assertEqual(self.path.read_text().splitlines()[0], ",".join(history.FIELDS))
        self.assertEqual(len(self.path.read_text().splitlines()), 2)
        self.assertFalse(self.path.with_suffix(".csv.lock").exists())

    def test_unchanged_rate_from_later_retrieval_gets_a_new_row(self):
        self.save([observation()])
        later = observation(stamp="2026-01-04T13:00:00Z")
        self.assertEqual(self.save([later]), {"added": 1, "skipped": 0})
        rows = self.read()
        self.assertEqual([r["rate"] for r in rows], ["502.12000", "502.12000"])
        self.assertEqual([r["retrieved_at"] for r in rows], ["2026-01-04T12:00:00Z", "2026-01-04T13:00:00Z"])

    def test_exact_same_observation_does_not_rewrite_file(self):
        self.save([observation()])
        before = self.path.read_bytes()
        with patch("fx_lag.csv_history.os.replace") as replace:
            self.assertEqual(self.save([observation()]), {"added": 0, "skipped": 1})
        replace.assert_not_called()
        self.assertEqual(before, self.path.read_bytes())

    def test_numerically_equal_rates_and_batch_duplicates_are_skipped(self):
        result = self.save([observation(), observation(rate="502.12"), observation(rate="5.0212E+2")])
        self.assertEqual(result, {"added": 1, "skipped": 2})
        self.assertEqual(self.read()[0]["rate"], "502.12000")

    def test_overlapping_ranges_append_new_dates(self):
        self.save([observation(), observation("2026-01-02")])
        result = self.save([observation("2026-01-02"), observation("2026-01-03")])
        self.assertEqual(result, {"added": 1, "skipped": 1})
        self.assertEqual([r["effective_date"] for r in self.read()], ["2026-01-01", "2026-01-02", "2026-01-03"])

    def test_changed_rate_preserved_without_overwrite(self):
        self.save([observation()])
        result = self.save([observation(rate="503.00", stamp="2026-01-05T00:00:00Z")])
        self.assertEqual(result, {"added": 1, "skipped": 0})
        self.assertEqual([r["rate"] for r in self.read()], ["502.12000", "503.00"])
        self.assertEqual(self.save([observation()]), {"added": 0, "skipped": 1})

    def test_rate_returns_to_previous_value_in_a_later_query(self):
        self.save([observation()])
        self.save([observation(rate="503", stamp="2026-01-04T13:00:00Z")])
        self.save([observation(stamp="2026-01-04T14:00:00Z")])
        self.assertEqual([r["rate"] for r in self.read()], ["502.12000", "503", "502.12000"])

    def test_equivalent_utc_timestamp_is_an_exact_duplicate(self):
        self.save([observation()])
        same = observation(rate="502.12", stamp="2026-01-04T12:00:00+00:00")
        self.assertEqual(self.save([same]), {"added": 0, "skipped": 1})

    def test_invalid_incoming_batch_cannot_change_existing_file(self):
        self.save([observation()])
        before = self.path.read_bytes()
        bad = observation("2026-01-02"); bad["token"] = "secret-never-display"
        with self.assertRaises(history.HistoryError) as caught:
            self.save([observation("2026-01-03"), bad])
        self.assertNotIn("secret-never-display", str(caught.exception))
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_input_does_not_create_file(self):
        with self.assertRaises(history.HistoryError):
            self.save([])
        self.assertFalse(self.path.exists())

    def test_invalid_values(self):
        changes = [
            ("source", "other"), ("interface", "SOAP"), ("indicator", 318),
            ("units", "USD/CRC"), ("source_url", "https://example.invalid"),
            ("effective_date", "2026-02-30"), ("effective_date", "20260101"),
            ("rate", "=1+2"), ("rate", "+502"), ("rate", "NaN"),
            ("rate", "Infinity"), ("rate", "-1"), ("rate", "0"),
            ("rate", 502), ("retrieved_at", "2026-01-04"),
            ("retrieved_at", "2026-01-04T00:00:00"),
            ("retrieved_at", "2026-01-04T00:00:00-06:00"),
        ]
        for field, value in changes:
            row = observation(); row[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(history.HistoryError):
                self.save([row])
        self.assertFalse(self.path.exists())

    def test_foreign_or_malformed_csv_left_intact(self):
        self.path.parent.mkdir()
        for content in ("", "other,header\nsecret-never-display,1\n", ",".join(history.FIELDS) + '\n"unterminated'):
            self.path.write_text(content)
            before = self.path.read_bytes()
            with self.assertRaises(history.HistoryError) as caught:
                self.save([observation()])
            self.assertEqual(self.path.read_bytes(), before)
            self.assertNotIn("secret-never-display", str(caught.exception))

    def test_corrupt_existing_rows_and_duplicates_rejected(self):
        self.save([observation()])
        header, row = self.path.read_text().splitlines()
        for content in (header + "\n" + row.replace("502.12000", "0") + "\n", header + "\n" + row + "\n" + row + "\n", header + "\n" + row + ",unexpected\n"):
            self.path.write_text(content)
            before = self.path.read_bytes()
            with self.assertRaises(history.HistoryError):
                self.save([observation("2026-01-02")])
            self.assertEqual(before, self.path.read_bytes())

    def test_existing_lock_not_removed(self):
        self.path.parent.mkdir()
        lock = self.path.with_suffix(".csv.lock")
        lock.write_text("another writer")
        with self.assertRaisesRegex(history.HistoryError, "locked"):
            self.save([observation()])
        self.assertEqual(lock.read_text(), "another writer")
        self.assertFalse(self.path.exists())

    def test_replace_failure_preserves_history_and_cleans_temporary(self):
        self.save([observation()])
        before = self.path.read_bytes()
        with patch("fx_lag.csv_history.os.replace", side_effect=PermissionError("secret-never-display")):
            with self.assertRaises(history.HistoryError) as caught:
                self.save([observation("2026-01-02")])
        self.assertNotIn("secret-never-display", str(caught.exception))
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_write_failure_preserves_history(self):
        self.save([observation()])
        before = self.path.read_bytes()
        with patch("fx_lag.csv_history.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(history.HistoryError):
                self.save([observation("2026-01-02")])
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_directory_destination_and_invalid_parent(self):
        self.path.mkdir(parents=True)
        with self.assertRaises(history.HistoryError):
            self.save([observation()])
        (self.root / "blocker").write_text("not a directory")
        with self.assertRaises(history.HistoryError):
            history.save_observations(self.root / "blocker" / "x.csv", [observation()], source_url=sdde.ENDPOINT)

    def test_root_destination_fails_safely(self):
        with self.assertRaises(history.HistoryError):
            history.save_observations(self.root.anchor, [observation()], source_url=sdde.ENDPOINT)

    def test_symlink_destination_rejected(self):
        self.path.parent.mkdir()
        target = self.root / "other.csv"
        try:
            self.path.symlink_to(target)
        except OSError:
            self.skipTest("Creating symlinks is not permitted on this platform")
        with self.assertRaises(history.HistoryError):
            self.save([observation()])
        self.assertTrue(self.path.is_symlink())
        self.assertFalse(target.exists())


class CsvCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "history.csv"

    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sdde.main(args)
        return code, out.getvalue(), err.getvalue()

    @patch("fx_lag.bccr_sdde.collect")
    def test_save_and_repeat_keep_json_contract(self, collect):
        result = {"observations": [observation()], "missing_dates": []}
        collect.return_value = result
        args = ["--date", "2026-01-01", "--csv", str(self.path)]
        code, out, err = self.run_cli(args)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), result)
        self.assertIn("1 added, 0 already saved", err)
        code, out, err = self.run_cli(args)
        self.assertEqual(code, 0)
        self.assertIn("0 added, 1 already saved", err)
        self.assertEqual(len(self.path.read_text().splitlines()), 2)

    @patch("fx_lag.bccr_sdde.save_observations")
    @patch("fx_lag.bccr_sdde.collect")
    def test_no_csv_flag_does_not_save(self, collect, save):
        collect.return_value = {"observations": [observation()], "missing_dates": []}
        code, out, err = self.run_cli(["--date", "2026-01-01"])
        self.assertEqual(code, 0)
        save.assert_not_called()
        self.assertNotIn("CSV", err)

    @patch("fx_lag.bccr_sdde.save_observations")
    @patch("fx_lag.bccr_sdde.collect", side_effect=sdde.NetworkError("Network failure"))
    def test_collection_failure_does_not_write(self, collect, save):
        code, out, err = self.run_cli(["--date", "2026-01-01", "--csv", str(self.path)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        save.assert_not_called()

    @patch("fx_lag.bccr_sdde.save_observations", side_effect=history.HistoryError("Could not save CSV history"))
    @patch("fx_lag.bccr_sdde.collect")
    def test_storage_error_exits_one_and_does_not_print_success_json(self, collect, save):
        collect.return_value = {"observations": [observation()], "missing_dates": []}
        code, out, err = self.run_cli(["--date", "2026-01-01", "--csv", str(self.path)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("Could not save CSV", err)
        self.assertNotIn("Traceback", err)

    @patch("fx_lag.bccr_sdde.collect")
    def test_partial_range_saves_only_available_observations(self, collect):
        collect.return_value = {"observations": [observation()], "missing_dates": ["2026-01-02"]}
        code, out, err = self.run_cli(["--start", "2026-01-01", "--end", "2026-01-02", "--csv", str(self.path)])
        self.assertEqual(code, 0)
        self.assertIn("missing", err)
        self.assertEqual(len(self.path.read_text().splitlines()), 2)
        self.assertEqual(json.loads(out)["missing_dates"], ["2026-01-02"])


if __name__ == "__main__":
    unittest.main()
