"""Offline schedule, state, HTTP 429 and restart tests (no real credentials)."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import io
import contextlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from fx_lag import bccr_sdde as sdde
from fx_lag import scheduled_bccr as schedule
from fx_lag.csv_history import HistoryError


def local(day="2026-10-23", at="09:00:00"):
    return datetime.fromisoformat(day + "T" + at + "-06:00")


def result(now):
    return {"observations": [{
        "source": "BCCR", "interface": "SDDE", "source_url": sdde.ENDPOINT,
        "indicator": 317, "rate": "500.12000", "units": "CRC/USD",
        "effective_date": now.astimezone(schedule.COSTA_RICA).date().isoformat(),
        "retrieved_at": schedule.timestamp(now),
    }], "missing_dates": []}


class WindowTests(unittest.TestCase):
    def test_weekdays_and_boundaries(self):
        for day in ("2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"):
            for at, allowed in (("08:59:59", False), ("09:00:00", True), ("09:30:00", True),
                                ("16:59:59", True), ("17:00:00", True), ("17:00:59", True),
                                ("17:01:00", False), ("17:30:00", False), ("23:59:59", False)):
                with self.subTest(day=day, at=at):
                    self.assertEqual(schedule.collection_slot(local(day, at)) is not None, allowed)
        for day in ("2026-10-24", "2026-10-25"):
            self.assertIsNone(schedule.collection_slot(local(day)))

    def test_timezone_and_halfhour_slots(self):
        self.assertEqual(schedule.collection_slot(datetime(2026, 10, 23, 15, tzinfo=timezone.utc)),
                         "2026-10-23T09:00:00-06:00")
        self.assertEqual(schedule.collection_slot(local(at="09:29:59")), schedule.collection_slot(local()))
        self.assertNotEqual(schedule.collection_slot(local(at="09:30:00")), schedule.collection_slot(local()))

    def test_next_weekday_and_year_boundary(self):
        self.assertEqual(schedule.next_weekday_open(local("2026-10-22")), local("2026-10-23").astimezone(timezone.utc))
        self.assertEqual(schedule.next_weekday_open(local("2026-10-23")), local("2026-10-26").astimezone(timezone.utc))
        self.assertEqual(schedule.next_weekday_open(local("2027-12-31")), local("2028-01-03").astimezone(timezone.utc))

    def test_retry_after_never_shortens_cooldown(self):
        now = local("2026-10-22")
        minimum = schedule.next_weekday_open(now)
        for header in (None, "60", "0", "bad secret", "-1", "9" * 50):
            self.assertEqual(schedule.cooldown_until(now, header), minimum)
        self.assertEqual(schedule.cooldown_until(now, "172800"), now.astimezone(timezone.utc) + timedelta(days=2))
        later = now.astimezone(timezone.utc) + timedelta(days=5)
        self.assertEqual(schedule.cooldown_until(now, format_datetime(later)), later)


@patch("fx_lag.scheduled_bccr.sdde.collect")
class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "data"

    def state(self):
        return json.loads((self.root / "bccr-schedule.json").read_text())

    def test_outside_window_does_not_create_files_or_connect(self, collect):
        self.assertEqual(schedule.run_once(self.root, now=local(at="18:00:00")), {"status": "outside_window"})
        self.assertFalse(self.root.exists())
        collect.assert_not_called()

    def test_saves_current_local_date_and_no_repeat_same_slot(self, collect):
        now = local()
        collect.return_value = result(now)
        self.assertEqual(schedule.run_once(self.root, now=now), {"status": "saved", "added": 1, "skipped": 0})
        collect.assert_called_once_with(now.date(), now.date(), 30)
        self.assertEqual(schedule.run_once(self.root, now=local(at="09:29:00")), {"status": "already_attempted"})
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(self.state()["status"], "saved")
        self.assertNotIn("token", (self.root / "bccr-schedule.json").read_text().lower())

    def test_next_slot_retains_unchanged_rate(self, collect):
        for at in ("09:00:00", "09:30:00"):
            now = local(at=at); collect.return_value = result(now)
            self.assertEqual(schedule.run_once(self.root, now=now)["status"], "saved")
        self.assertEqual(collect.call_count, 2)
        self.assertEqual(len((self.root / "bccr-history.csv").read_text().splitlines()), 3)

    def test_delayed_attempt_does_not_retry_just_ten_minutes_later(self, collect):
        now = local(at="09:20:00"); collect.return_value = result(now)
        schedule.run_once(self.root, now=now)
        self.assertEqual(schedule.run_once(self.root, now=local(at="09:30:00")), {"status": "too_soon"})
        self.assertEqual(collect.call_count, 1)
        later = local(at="10:00:00"); collect.return_value = result(later)
        self.assertEqual(schedule.run_once(self.root, now=later)["status"], "saved")

    def test_small_task_scheduler_jitter_does_not_skip_next_slot(self, collect):
        beginning = local(at="09:00:05"); collect.return_value = result(beginning)
        schedule.run_once(self.root, now=beginning)
        following = local(at="09:30:00"); collect.return_value = result(following)
        self.assertEqual(schedule.run_once(self.root, now=following)["status"], "saved")
        self.assertEqual(collect.call_count, 2)

    def test_exactly_seventeen_weekday_slots_and_fresh_start_next_day(self, collect):
        beginning = local("2026-10-22")
        for index in range(17):
            now = beginning + timedelta(minutes=30 * index)
            collect.return_value = result(now)
            self.assertEqual(schedule.run_once(self.root, now=now)["status"], "saved")
        self.assertEqual(collect.call_count, 17)
        self.assertEqual(schedule.run_once(self.root, now=local("2026-10-22", "17:30:00"))["status"], "outside_window")
        collect.return_value = result(local())
        self.assertEqual(schedule.run_once(self.root, now=local())["status"], "saved")
        self.assertEqual(collect.call_count, 18)

    def test_429_persists_and_blocks_until_next_weekday_nine(self, collect):
        collect.side_effect = sdde.RateLimitError("secret-never-display", "60")
        first = schedule.run_once(self.root, now=local("2026-10-22", "10:30:00"))
        self.assertEqual(first, {"status": "rate_limited", "resume_at": "2026-10-23T15:00:00Z"})
        persisted = self.state()
        self.assertEqual(persisted["status"], "rate_limited")
        for at in (local("2026-10-22", "11:00:00"), local("2026-10-23", "08:59:59")):
            self.assertIn(schedule.run_once(self.root, now=at)["status"], ("paused", "outside_window"))
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(self.state(), persisted)
        collect.side_effect = None
        collect.return_value = result(local())
        self.assertEqual(schedule.run_once(self.root, now=local())["status"], "saved")
        self.assertEqual(collect.call_count, 2)
        self.assertIsNone(self.state()["blocked_until"])

    def test_friday_429_resumes_monday_and_repeated_429_repauses(self, collect):
        collect.side_effect = sdde.RateLimitError("limited")
        first = schedule.run_once(self.root, now=local())
        self.assertEqual(first["resume_at"], "2026-10-26T15:00:00Z")
        self.assertEqual(schedule.run_once(self.root, now=local(at="16:30:00"))["status"], "paused")
        for day in ("2026-10-24", "2026-10-25"):
            self.assertEqual(schedule.run_once(self.root, now=local(day))["status"], "outside_window")
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(schedule.run_once(self.root, now=local("2026-10-26"))["resume_at"], "2026-10-27T15:00:00Z")
        self.assertEqual(collect.call_count, 2)

    def test_long_retry_after_survives_date_change(self, collect):
        collect.side_effect = sdde.RateLimitError("limited", "172800")
        first = schedule.run_once(self.root, now=local("2026-10-19"))
        self.assertEqual(first["resume_at"], "2026-10-21T15:00:00Z")
        self.assertEqual(schedule.run_once(self.root, now=local("2026-10-20"))["status"], "paused")
        self.assertEqual(collect.call_count, 1)

    def test_other_failures_do_not_retry_in_the_same_slot(self, collect):
        for error in (sdde.AuthenticationError("secret"), sdde.NetworkError("secret"), sdde.NoDataError("secret")):
            collect.side_effect = error
            if (self.root / "bccr-schedule.json").exists():
                (self.root / "bccr-schedule.json").unlink()
            response = schedule.run_once(self.root, now=local())
            self.assertEqual(response["status"], "error")
            self.assertNotIn("secret", str(response))
            count = collect.call_count
            schedule.run_once(self.root, now=local(at="09:10:00"))
            self.assertEqual(collect.call_count, count)

    def test_bad_state_and_interrupted_attempt_fail_closed(self, collect):
        self.root.mkdir()
        path = self.root / "bccr-schedule.json"
        for raw in ("bad secret", "{}", '{"version":1,"version":2}'):
            path.write_text(raw)
            with self.assertRaises(schedule.ScheduleError) as caught:
                schedule.run_once(self.root, now=local())
            self.assertNotIn("secret", str(caught.exception))
        collect.assert_not_called()
        path.unlink()
        collect.side_effect = RuntimeError("crash")
        with self.assertRaises(RuntimeError):
            schedule.run_once(self.root, now=local())
        self.assertEqual(self.state()["status"], "started")
        collect.reset_mock()
        with self.assertRaisesRegex(schedule.ScheduleError, "did not finish"):
            schedule.run_once(self.root, now=local(at="09:30:00"))
        collect.assert_not_called()

    def test_existing_lock_does_not_connect(self, collect):
        self.root.mkdir()
        lock = self.root / "bccr-schedule.lock"; lock.write_text("")
        with self.assertRaises(schedule.ScheduleError):
            schedule.run_once(self.root, now=local())
        self.assertTrue(lock.exists())
        collect.assert_not_called()

    def test_state_write_failure_before_request(self, collect):
        with patch("fx_lag.scheduled_bccr.os.replace", side_effect=OSError("secret")):
            with self.assertRaises(schedule.ScheduleError) as caught:
                schedule.run_once(self.root, now=local())
        self.assertNotIn("secret", str(caught.exception))
        collect.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_cannot_persist_429_leaves_started_state_and_no_next_request(self, collect):
        real_write = schedule.write_state
        def write(path, state):
            if state["status"] == "rate_limited":
                raise schedule.ScheduleError("persistence failed")
            real_write(path, state)
        collect.side_effect = sdde.RateLimitError("limited")
        with patch("fx_lag.scheduled_bccr.write_state", side_effect=write), self.assertRaises(schedule.ScheduleError):
            schedule.run_once(self.root, now=local())
        self.assertEqual(self.state()["status"], "started")
        collect.reset_mock()
        with self.assertRaises(schedule.ScheduleError):
            schedule.run_once(self.root, now=local(at="09:30:00"))
        collect.assert_not_called()

    def test_storage_failure_and_clock_rollback(self, collect):
        collect.return_value = result(local(at="09:30:00"))
        with patch("fx_lag.scheduled_bccr.save_observations", side_effect=HistoryError("secret")):
            self.assertEqual(schedule.run_once(self.root, now=local(at="09:30:00"))["status"], "error")
        collect.reset_mock()
        with self.assertRaisesRegex(schedule.ScheduleError, "Clock moved"):
            schedule.run_once(self.root, now=local(at="09:10:00"))
        collect.assert_not_called()


class CliTests(unittest.TestCase):
    def test_status_exit_codes_and_sanitized_output(self):
        for status, expected in (("saved", 0), ("paused", 0), ("outside_window", 0), ("already_attempted", 0), ("too_soon", 0), ("rate_limited", 2), ("error", 1), ("partial", 1)):
            with patch("fx_lag.scheduled_bccr.run_once", return_value={"status": status}):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(schedule.main([]), expected)
                self.assertEqual(json.loads(out.getvalue()), {"status": status})

    def test_state_error_is_safe_cli_failure(self):
        with patch("fx_lag.scheduled_bccr.run_once", side_effect=schedule.ScheduleError("State needs inspection")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(schedule.main([]), 1)
            self.assertIn("State needs inspection", err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())


class RateLimitTransportTests(unittest.TestCase):
    @patch.dict("os.environ", {"BCCR_SDDE_TOKEN": "fake-secret"}, clear=True)
    @patch("fx_lag.bccr_sdde.build_opener")
    def test_http_429_becomes_typed_error_and_retains_retry_after(self, opener):
        opener.return_value.open.side_effect = HTTPError(sdde.ENDPOINT, 429, "secret", {"Retry-After": "3600"}, io.BytesIO(b"secret"))
        with self.assertRaises(sdde.RateLimitError) as caught:
            sdde.collect(local().date(), local().date())
        self.assertEqual(caught.exception.retry_after, "3600")
        self.assertNotIn("secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
