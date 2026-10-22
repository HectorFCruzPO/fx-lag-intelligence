"""Offline tests. All XML fixtures are synthetic, not captured BCCR responses."""
import contextlib
from datetime import date
import io
from http.client import IncompleteRead
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

from fx_lag import bccr

FIXTURES = Path(__file__).parent / "fixtures"
START, END = date(2026, 1, 1), date(2026, 1, 2)
STAMP = "2026-01-03T12:00:00Z"


def fixture(name):
    return (FIXTURES / name).read_bytes()


def soap(data):
    root = ET.Element(f"{{{bccr.SOAP}}}Envelope")
    body = ET.SubElement(root, f"{{{bccr.SOAP}}}Body")
    response = ET.SubElement(body, f"{{{bccr.NAMESPACE}}}{bccr.METHOD}Response")
    ET.SubElement(response, f"{{{bccr.NAMESPACE}}}{bccr.METHOD}Result").text = data.decode()
    return ET.tostring(root)


class ParseTests(unittest.TestCase):
    def parse(self, raw):
        return bccr.parse_response(raw, START, END, STAMP)

    def test_direct_and_escaped_soap_xml(self):
        for raw in (fixture("rates.xml"), soap(fixture("rates.xml"))):
            with self.subTest(raw=raw[:20]):
                result = self.parse(raw)
                first = result["observations"][0]
                self.assertEqual(first, {
                    "source": "BCCR", "source_url": bccr.ENDPOINT, "indicator": 317,
                    "rate": "502.12000", "units": "CRC/USD", "effective_date": "2026-01-01",
                    "retrieved_at": STAMP,
                })
                self.assertNotIn("source_publication_time", first)
                self.assertEqual(result["missing_dates"], [])

    def test_namespace_and_date_offset(self):
        raw = fixture("rates.xml")
        raw = raw.replace(b"<Datos_de_INGC011_CAT_INDICADORECONOMIC>", b'<Datos_de_INGC011_CAT_INDICADORECONOMIC xmlns="urn:test">')
        raw = raw.replace(b"T00:00:00", b"T00:00:00-06:00")
        self.assertEqual(self.parse(raw)["observations"][0]["effective_date"], "2026-01-01")

    def test_partial_range_exposes_missing_dates(self):
        result = bccr.parse_response(fixture("rates.xml"), START, date(2026, 1, 3), STAMP)
        self.assertEqual(result["missing_dates"], ["2026-01-03"])
        self.assertEqual(len(result["observations"]), 2)

    def test_empty_results(self):
        for raw in (fixture("empty.xml"), soap(b""), soap(b"Nothing")):
            with self.subTest(raw=raw), self.assertRaises(bccr.NoDataError):
                self.parse(raw)

    def test_invalid_xml_and_unknown_schema(self):
        for raw in (b"<broken", b"<html>Unavailable</html>", soap(b"<broken"), soap(b"unexpected")):
            with self.subTest(raw=raw), self.assertRaises(bccr.ResponseError):
                self.parse(raw)

    def test_unsafe_xml(self):
        for raw in (b'<!DOCTYPE x [<!ENTITY y "a">]><x>&y;</x>', '<!DOCTYPE x><x/>'.encode('utf-16')):
            with self.subTest(raw=raw), self.assertRaises(bccr.ResponseError):
                self.parse(raw)

    def test_faults_and_auth_text(self):
        for raw in (fixture("auth_fault.xml"), soap(b"Token invalido secret-never-display")):
            with self.assertRaises(bccr.AuthenticationError) as caught:
                self.parse(raw)
            self.assertNotIn("secret-never-display", str(caught.exception))
        with self.assertRaises(bccr.ResponseError):
            self.parse(fixture("auth_fault.xml").replace(b"Token", b"Service"))

    def test_invalid_records_fail_whole_batch(self):
        raw = fixture("rates.xml")
        for old, new in (
            (b"501.23000", b"NaN"), (b"501.23000", b"Infinity"), (b"501.23000", b"0"),
            (b"501.23000", b"-1"), (b"501.23000", b"501,23"), (b"317", b"318"),
            (b"2026-01-02", b"2026-02-30"), (b"2026-01-02", b"2026-01-03"),
            (b"2026-01-02", b"2026-01-01"), (b"NUM_VALOR", b"OTHER"),
        ):
            with self.subTest(new=new), self.assertRaises(bccr.ResponseError):
                self.parse(raw.replace(old, new))


@patch.dict("os.environ", {"BCCR_EMAIL": "synthetic@example.invalid", "BCCR_TOKEN": "fake-secret"}, clear=True)
class TransportTests(unittest.TestCase):
    def response(self, opener, raw=None):
        response = MagicMock()
        response.read.return_value = raw if raw is not None else soap(fixture("rates.xml"))
        opener.return_value.open.return_value.__enter__.return_value = response
        return response

    @patch("fx_lag.bccr.build_opener")
    def test_request_contract_and_timestamp(self, opener):
        self.response(opener)
        result = bccr.collect(START, END, "Example & Name", 12)
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, bccr.ENDPOINT)
        self.assertEqual(request.method, "POST")
        self.assertNotIn("fake-secret", request.full_url)
        self.assertEqual(request.get_header("Soapaction"), f'"{bccr.NAMESPACE}/{bccr.METHOD}"')
        fields = {bccr.local_name(e.tag): e.text for e in ET.fromstring(request.data).iter()}
        for k, v in {"Indicador":"317", "FechaInicio":"01/01/2026", "FechaFinal":"02/01/2026", "SubNiveles":"N", "Nombre":"Example & Name", "Token":"fake-secret", "CorreoElectronico":"synthetic@example.invalid"}.items():
            self.assertEqual(fields[k], v)
        self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 12)
        self.assertTrue(result["observations"][0]["retrieved_at"].endswith("Z"))

    @patch("fx_lag.bccr.build_opener")
    def test_transport_failures(self, opener):
        for error in (URLError("fake-secret"), TimeoutError("fake-secret"), OSError("fake-secret"), IncompleteRead(b"fake-secret")):
            opener.return_value.open.side_effect = error
            with self.subTest(error=error), self.assertRaises(bccr.NetworkError) as caught:
                bccr.collect(START, END, "Example")
            self.assertNotIn("fake-secret", str(caught.exception))

    @patch("fx_lag.bccr.build_opener")
    def test_http_failures(self, opener):
        for code in (401, 403, 429, 500, 503):
            opener.return_value.open.side_effect = HTTPError(bccr.ENDPOINT, code, "secret", {}, io.BytesIO(b"bad"))
            expected = bccr.AuthenticationError if code in (401,403) else bccr.NetworkError
            with self.subTest(code=code), self.assertRaises(expected):
                bccr.collect(START, END, "Example")

    @patch("fx_lag.bccr.build_opener")
    def test_http_500_auth_fault(self, opener):
        opener.return_value.open.side_effect = HTTPError(bccr.ENDPOINT, 500, "fault", {}, io.BytesIO(fixture("auth_fault.xml")))
        with self.assertRaises(bccr.AuthenticationError):
            bccr.collect(START, END, "Example")

    @patch("fx_lag.bccr.build_opener")
    def test_size_limit(self, opener):
        response = self.response(opener, b"x" * (bccr.MAX_RESPONSE_BYTES + 1))
        with self.assertRaises(bccr.ResponseError):
            bccr.collect(START, END, "Example")
        response.read.assert_called_once_with(bccr.MAX_RESPONSE_BYTES + 1)

    def test_redirect_rejected(self):
        with self.assertRaises(bccr.NetworkError):
            bccr.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid")

    @patch("fx_lag.bccr.build_opener")
    def test_invalid_inputs_do_not_connect(self, opener):
        for start, end, name, timeout in ((END,START,"Example",30), (START,END," ",30), (START,END,"Example",float("nan")), (START,END,"Example",0)):
            with self.assertRaises(bccr.CollectorError):
                bccr.collect(start,end,name,timeout)
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(bccr.AuthenticationError):
            bccr.collect(START, END, "Example")
        opener.assert_not_called()


class CliTests(unittest.TestCase):
    @patch("fx_lag.bccr.collect")
    def test_date_and_range(self, collect):
        collect.return_value = {"observations": [], "missing_dates": []}
        for args in (["--date","2026-01-01"], ["--start","2026-01-01","--end","2026-01-02"]):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(bccr.main(args+["--name","Example"]), 0)
            self.assertEqual(json.loads(output.getvalue()), collect.return_value)
        self.assertEqual(collect.call_args.args[:2], (START, END))

    @patch("fx_lag.bccr.collect")
    def test_invalid_cli(self, collect):
        for args in (["--date","2026-02-30"], ["--start","2026-01-01"], ["--date","2026-01-01","--end","2026-01-02"], ["--date","20260101"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                bccr.main(args+["--name","Example"])
            self.assertEqual(caught.exception.code, 2)
        collect.assert_not_called()

    @patch("fx_lag.bccr.collect", side_effect=bccr.NetworkError("Cannot reach BCCR"))
    def test_error_exit_and_no_stdout(self, collect):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            self.assertEqual(bccr.main(["--date","2026-01-01","--name","Example"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("Cannot reach BCCR", error.getvalue())

    @patch("fx_lag.bccr.collect", return_value={"observations":[],"missing_dates":["2026-01-01"]})
    def test_partial_result_warning(self, collect):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(bccr.main(["--date","2026-01-01","--name","Example"]), 0)
        self.assertIn("missing", error.getvalue())


if __name__ == "__main__":
    unittest.main()
