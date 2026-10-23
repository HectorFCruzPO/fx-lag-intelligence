"""Offline MONEX tests: synthetic JSON and mocked transport only."""
import contextlib
import csv
from datetime import date
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from fx_lag import bccr_sdde as sdde, csv_history as history, monex

START, END = date(2026, 10, 20), date(2026, 10, 23)
STAMP = "2026-10-23T23:00:00Z"
SECRET = "synthetic-secret-not-a-real-token"
FIXTURE = Path(__file__).parent / "fixtures/sdde/monex_closing.json"


def parsed(raw=None, stamp=STAMP):
    return sdde.parse_response(raw or FIXTURE.read_bytes(), START, END, stamp, indicator=3323)


class ParserTests(unittest.TestCase):
    def test_precision_identity_and_missing_date(self):
        result = parsed()
        row = result["observations"][0]
        self.assertEqual(row, {
            "source": "BCCR", "interface": "SDDE", "source_url": monex.ENDPOINT,
            "indicator": 3323, "rate": "456.12345678", "units": "CRC/USD",
            "effective_date": "2026-10-20", "retrieved_at": STAMP,
        })
        self.assertEqual(result["observations"][1]["rate"], "454.99000000")
        self.assertEqual(result["missing_dates"], ["2026-10-22"])

    def test_indicators_cannot_be_substituted(self):
        for code in ("317", "3439", 3323):
            payload = json.loads(FIXTURE.read_bytes())
            payload["datos"][0]["codigoIndicador"] = code
            with self.subTest(code=code), self.assertRaises(sdde.ResponseError):
                parsed(json.dumps(payload).encode())
        with self.assertRaises(sdde.ResponseError):
            sdde.parse_response(FIXTURE.read_bytes(), START, END, STAMP)

    def test_invalid_values_and_dates_rejected(self):
        for field, value in (("valorDatoPorPeriodo", 0), ("valorDatoPorPeriodo", -1),
                             ("valorDatoPorPeriodo", True), ("valorDatoPorPeriodo", "454.3"),
                             ("fecha", "2026-10-24"), ("fecha", "invalid")):
            payload = json.loads(FIXTURE.read_bytes())
            payload["datos"][0]["series"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(sdde.ResponseError):
                parsed(json.dumps(payload).encode())

    def test_duplicate_dates_and_unexpected_schema_rejected(self):
        payload = json.loads(FIXTURE.read_bytes())
        payload["datos"][0]["series"].append(payload["datos"][0]["series"][0])
        for raw in (json.dumps(payload).encode(), b"[]", b'{"estado":true}', b"invalid JSON",
                    b'{"estado":true,"estado":true}'):
            with self.subTest(raw=raw), self.assertRaises(sdde.ResponseError):
                parsed(raw)

    def test_empty_data_and_service_errors_are_sanitized(self):
        for payload, error in (({"estado": True, "mensaje": SECRET, "datos": []}, sdde.NoDataError),
                               ({"estado": False, "mensaje": SECRET}, sdde.ServiceError)):
            with self.assertRaises(error) as caught:
                parsed(json.dumps(payload).encode())
            self.assertNotIn(SECRET, str(caught.exception))


@patch.dict("os.environ", {"BCCR_SDDE_TOKEN": SECRET}, clear=True)
class TransportTests(unittest.TestCase):
    @patch("fx_lag.bccr_sdde.build_opener")
    def test_request_uses_closing_indicator_and_inclusive_dates(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = FIXTURE.read_bytes()
        result = monex.collect(START, END, timeout=12)
        request = opener.return_value.open.call_args.args[0]
        self.assertTrue(request.full_url.startswith(monex.ENDPOINT + "?"))
        self.assertIn("fechaInicio=2026%2F10%2F20", request.full_url)
        self.assertIn("fechaFin=2026%2F10%2F23", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer " + SECRET)
        self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 12)
        self.assertNotIn(SECRET, request.full_url)
        self.assertTrue(result["observations"][0]["retrieved_at"].endswith("Z"))
        self.assertIsInstance(opener.call_args.args[0], sdde.NoRedirect)

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_http_failures_never_read_or_expose_body(self, opener):
        for code, kind in ((401, sdde.AuthenticationError), (403, sdde.AuthenticationError),
                           (429, sdde.RateLimitError), (500, sdde.NetworkError),
                           (302, sdde.NetworkError)):
            body = MagicMock()
            opener.return_value.open.side_effect = HTTPError(monex.ENDPOINT, code, SECRET,
                                                             {"Retry-After": "120"}, body)
            with self.subTest(code=code), self.assertRaises(kind) as caught:
                monex.collect(START, END)
            self.assertNotIn(SECRET, str(caught.exception))
            body.read.assert_not_called()
            body.close.assert_called_once()
            if code == 429:
                self.assertEqual(caught.exception.retry_after, "120")

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_network_and_timeout_failures(self, opener):
        for error in (URLError(SECRET), TimeoutError(SECRET)):
            opener.return_value.open.side_effect = error
            with self.assertRaises(sdde.NetworkError) as caught:
                monex.collect(START, END)
            self.assertNotIn(SECRET, str(caught.exception))

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_missing_credentials_and_invalid_parameters_make_no_request(self, opener):
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(sdde.AuthenticationError):
            monex.collect(START, END)
        for token in ("has space", "bad\r\nheader"):
            with patch.dict("os.environ", {"BCCR_SDDE_TOKEN": token}), self.assertRaises(sdde.AuthenticationError):
                monex.collect(START, END)
        for timeout in (0, float("inf"), float("nan")):
            with self.assertRaises(sdde.CollectorError):
                monex.collect(START, END, timeout)
        with self.assertRaises(sdde.CollectorError):
            monex.collect(END, START)
        opener.assert_not_called()

    def test_redirects_are_rejected_before_forwarding(self):
        request = Request(monex.ENDPOINT, headers={"Authorization": "Bearer " + SECRET})
        for destination in (monex.ENDPOINT + "/other", "https://example.invalid", "http://apim.bccr.fi.cr"):
            with self.assertRaises(sdde.NetworkError):
                sdde.NoRedirect().redirect_request(request, None, 302, SECRET, {}, destination)

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_response_size_and_status_checked(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.status = 204
        with self.assertRaises(sdde.NetworkError):
            monex.collect(START, END)
        response.status = 200
        response.read.return_value = b"x" * (sdde.MAX_RESPONSE_BYTES + 1)
        with self.assertRaises(sdde.ResponseError):
            monex.collect(START, END)


class HistoryAndCLITests(unittest.TestCase):
    @patch.dict("os.environ", {"BCCR_SDDE_TOKEN": SECRET}, clear=True)
    @patch("fx_lag.bccr_sdde.build_opener")
    def test_cli_transport_parse_and_save_together(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = FIXTURE.read_bytes()
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            path = Path(folder) / "monex.csv"
            code = monex.main(["--start", "2026-10-20", "--end", "2026-10-23", "--csv", str(path)])
            self.assertEqual(code, 0)
            row = json.loads(out.getvalue())["observations"][0]
            self.assertEqual(row["rate"], "456.12345678")
            self.assertEqual(row["indicator"], 3323)
            self.assertNotIn(SECRET, path.read_text())
            self.assertNotIn(SECRET, out.getvalue())
            with path.open(newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["rate"], "456.12345678")
        self.assertTrue(opener.return_value.open.call_args.args[0].full_url.startswith(monex.ENDPOINT))

    def test_separate_history_retains_unchanged_retrievals(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "monex-history.csv"
            first = parsed()["observations"]
            later = parsed(stamp="2026-10-23T23:30:00Z")["observations"]
            for rows, added in ((first, 3), (later, 3), (first, 0)):
                result = history.save_observations(path, rows, source_url=monex.ENDPOINT, indicator=3323)
                self.assertEqual(result["added"], added)
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 6)
            self.assertTrue(all(row["indicator"] == "3323" for row in rows))

    def test_foreign_history_cannot_be_mixed_or_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.csv"
            rows = parsed()["observations"]
            history.save_observations(path, rows, source_url=monex.ENDPOINT, indicator=3323)
            original = path.read_bytes()
            compra = dict(rows[0], indicator=317, source_url=sdde.ENDPOINT)
            with self.assertRaises(history.HistoryError):
                history.save_observations(path, [compra], source_url=sdde.ENDPOINT)
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(history.HistoryError):
                history.save_observations(path, rows, source_url=sdde.ENDPOINT, indicator=3323)

    @patch("fx_lag.bccr_sdde.collect")
    def test_cli_range_saves_correct_identity(self, collect):
        collect.return_value = parsed()
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            path = Path(folder) / "monex.csv"
            code = monex.main(["--start", "2026-10-20", "--end", "2026-10-23", "--csv", str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())["observations"][0]["indicator"], 3323)
            self.assertIn("3 added", err.getvalue())
            self.assertIn("missing", err.getvalue())
            self.assertTrue(path.exists())
        collect.assert_called_once_with(START, END, 30, indicator=3323)

    @patch("fx_lag.bccr_sdde.collect")
    def test_cli_single_date(self, collect):
        collect.return_value = {"observations": [], "missing_dates": []}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(monex.main(["--date", "2026-10-23"]), 0)
        collect.assert_called_once_with(END, END, 30, indicator=3323)

    @patch("fx_lag.bccr_sdde.collect")
    def test_cli_invalid_date_arguments_make_no_request(self, collect):
        for args in ([], ["--start", "2026-10-20"], ["--date", "not-a-date"],
                     ["--date", "2026-10-23", "--end", "2026-10-23"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                monex.main(args)
            self.assertEqual(caught.exception.code, 2)
        collect.assert_not_called()

    @patch("fx_lag.bccr_sdde.collect", side_effect=sdde.NetworkError("Safe network error"))
    def test_cli_failure_does_not_create_history(self, collect):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            path = Path(folder) / "monex.csv"
            self.assertEqual(monex.main(["--date", "2026-10-23", "--csv", str(path)]), 1)
            self.assertFalse(path.exists())
            self.assertEqual(out.getvalue(), "")
            self.assertIn("Safe network error", err.getvalue())

    def test_unsupported_indicator_is_not_a_generic_fetch_escape(self):
        for indicator in (3439, True, "3323"):
            with self.assertRaises(sdde.CollectorError):
                sdde.collect(START, END, indicator=indicator)


if __name__ == "__main__":
    unittest.main()
