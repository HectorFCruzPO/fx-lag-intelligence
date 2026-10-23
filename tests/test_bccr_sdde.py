"""Offline SDDE contract tests. Fixtures are synthetic, not live responses.

The shape follows the official SDDE guide pp.19–20; nulls exercise our explicit
missing-data policy. No SOAP or legacy response wrappers are assumed.
"""
import contextlib
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from http.client import IncompleteRead
import io
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

from fx_lag import bccr_sdde as sdde

FIXTURES = Path(__file__).parent / "fixtures" / "sdde"
START, END = date(2026, 1, 1), date(2026, 1, 3)
STAMP = "2026-01-04T12:00:00Z"
SECRET = "fake-secret-never-display"


def fixture(name):
    return (FIXTURES / name).read_bytes()


def payload():
    return {
        "estado": True, "mensaje": "Consulta exitosa",
        "datos": [{"codigoIndicador": "317", "nombreIndicador": "Tipo cambio compra", "series": [
            {"fecha": "2026-01-01", "valorDatoPorPeriodo": 502},
        ]}],
    }


class ParseTests(unittest.TestCase):
    def parse(self, raw):
        return sdde.parse_response(raw, START, END, STAMP)

    def encode(self, data):
        return json.dumps(data).encode()

    def test_documented_shape_decimal_precision_sorting_provenance(self):
        result = self.parse(fixture("series.json"))
        self.assertEqual(result["missing_dates"], ["2026-01-02"])
        first, last = result["observations"]
        self.assertEqual(first, {
            "source": "BCCR", "interface": "SDDE", "source_url": sdde.ENDPOINT,
            "indicator": 317, "rate": "502.12000", "units": "CRC/USD",
            "effective_date": "2026-01-01", "retrieved_at": STAMP,
        })
        self.assertEqual(last["rate"], "500.12345678901234567890")
        self.assertEqual(Decimal(last["rate"]), Decimal("500.12345678901234567890"))
        self.assertNotIn("published_at", first)
        self.assertEqual(last["effective_date"], "2026-01-03")

    def test_integer_json_rate(self):
        result = self.parse(self.encode(payload()))
        self.assertEqual(result["observations"][0]["rate"], "502")
        self.assertEqual(result["missing_dates"], ["2026-01-02", "2026-01-03"])

    def test_one_date_and_maximum_calendar_date(self):
        raw = self.encode(payload())
        result = sdde.parse_response(raw, START, START, STAMP)
        self.assertEqual(result["missing_dates"], [])
        data = payload();data["datos"][0]["series"][0]["fecha"] = "9999-12-31"
        result = sdde.parse_response(self.encode(data), date.max, date.max, STAMP)
        self.assertEqual(result["observations"][0]["effective_date"], "9999-12-31")

    def test_no_data_variants(self):
        empty_series = payload();empty_series["datos"][0]["series"] = []
        null_series = payload();null_series["datos"][0]["series"][0]["valorDatoPorPeriodo"] = None
        for raw in (fixture("empty.json"), self.encode(empty_series), self.encode(null_series)):
            with self.subTest(raw=raw), self.assertRaises(sdde.NoDataError):
                self.parse(raw)

    def test_invalid_json(self):
        for raw in (b"{broken", b"<soap:Envelope/>", b"\xff", b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1,"x":2}', b'{"x":{"a":1,"a":2}}'):
            with self.subTest(raw=raw), self.assertRaises(sdde.ResponseError):
                self.parse(raw)

    def test_unexpected_schema(self):
        cases = [[], None, {}, {"estado": "true", "mensaje":"x", "datos":[]},
                 {"estado": 1, "mensaje":"x", "datos":[]},
                 {"estado": True, "datos":[]}, {"estado": True, "mensaje":None, "datos":[]}]
        for value in (None, {}, "", [None]):
            data = payload();data["datos"] = value;cases.append(data)
        for key, value in (("codigoIndicador", "318"), ("codigoIndicador", 317), ("nombreIndicador", None), ("series", {}), ("series", [None]), ("series", [{}])):
            data = payload();data["datos"][0][key] = value;cases.append(data)
        data=payload();data["datos"].append(deepcopy(data["datos"][0]));cases.append(data)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(sdde.ResponseError):
                self.parse(self.encode(data))

    def test_dates_are_strict_unique_and_in_range(self):
        for value in ("2026-02-30", "2026-01-04", "2025-12-31", "20260101", "2026-1-1", "2026-01-01T00:00:00Z", None, 20260101):
            data=payload();data["datos"][0]["series"][0]["fecha"] = value
            with self.subTest(value=value), self.assertRaises(sdde.ResponseError):
                self.parse(self.encode(data))
        for value in (None, 500):
            data=payload();row=deepcopy(data["datos"][0]["series"][0]);row["valorDatoPorPeriodo"]=value
            data["datos"][0]["series"].append(row)
            with self.assertRaises(sdde.ResponseError):
                self.parse(self.encode(data))

    def test_invalid_rates_fail_whole_batch(self):
        for value in ("500.12", True, False, 0, -1, [], {}):
            data=payload();row={"fecha":"2026-01-02","valorDatoPorPeriodo":value}
            data["datos"][0]["series"].append(row)
            with self.subTest(value=value), self.assertRaises(sdde.ResponseError):
                self.parse(self.encode(data))
        data=payload();del data["datos"][0]["series"][0]["valorDatoPorPeriodo"]
        with self.assertRaises(sdde.ResponseError):
            self.parse(self.encode(data))

    def test_api_failure_messages_are_not_echoed_or_guessed_as_auth(self):
        for raw in (fixture("error.json"), self.encode({"estado": False,"mensaje":SECRET,"datos":[]})):
            with self.assertRaises(sdde.ServiceError) as caught:
                self.parse(raw)
            self.assertNotIn(SECRET, str(caught.exception))

    def test_unknown_publication_fields_are_not_assumed_to_be_timestamps(self):
        data=payload();data["datos"][0]["ultimaPublicacion"] = "2026-01-01"
        result=self.parse(self.encode(data))
        self.assertEqual(set(result["observations"][0]), {"source","interface","source_url","indicator","rate","units","effective_date","retrieved_at"})


@patch.dict("os.environ", {"BCCR_SDDE_TOKEN": SECRET}, clear=True)
class TransportTests(unittest.TestCase):
    def response(self, opener, raw=None, status=200):
        response=MagicMock();response.status=status
        response.read.return_value=fixture("series.json") if raw is None else raw
        opener.return_value.open.return_value.__enter__.return_value=response
        return response

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_documented_get_request_and_header_only_auth(self, opener):
        self.response(opener)
        before=datetime.now(timezone.utc)
        result=sdde.collect(START, END, 12)
        after=datetime.now(timezone.utc)
        request=opener.return_value.open.call_args.args[0]
        self.assertEqual(request.method,"GET")
        self.assertIsNone(request.data)
        self.assertEqual(urlsplit(request.full_url).path, "/SDDE/api/Bccr.GE.SDDE.Publico.Indicadores.API/indicadoresEconomicos/317/series")
        self.assertEqual(parse_qs(urlsplit(request.full_url).query),{"fechaInicio":["2026/01/01"],"fechaFin":["2026/01/03"],"idioma":["ES"]})
        self.assertEqual(request.get_header("Authorization"),"Bearer "+SECRET)
        self.assertEqual(request.get_header("Accept"),"application/json")
        self.assertEqual(request.get_header("User-agent"), "Mozilla/5.0")
        self.assertNotIn(SECRET,request.full_url)
        self.assertEqual(opener.return_value.open.call_args.kwargs,{"timeout":12})
        self.assertIsInstance(opener.call_args.args[0],sdde.NoRedirect)
        stamp=result["observations"][0]["retrieved_at"]
        self.assertTrue(stamp.endswith("Z"))
        self.assertTrue(before <= datetime.fromisoformat(stamp.replace("Z","+00:00")) <= after)

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_invalid_credentials_do_not_connect(self, opener):
        for token in ("", " ", " abc", "abc\n", "abc\r\nX-Evil: injected", "é", "abc def"):
            with patch.dict("os.environ", {"BCCR_SDDE_TOKEN":token}, clear=True):
                with self.subTest(token=repr(token)), self.assertRaises(sdde.AuthenticationError) as caught:
                    sdde.collect(START,END)
                self.assertNotIn("injected",str(caught.exception))
        with patch.dict("os.environ", {"BCCR_TOKEN":SECRET}, clear=True), self.assertRaises(sdde.AuthenticationError):
            sdde.collect(START,END)
        opener.assert_not_called()

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_invalid_options_do_not_connect(self, opener):
        for start,end,timeout in ((END,START,30),(START,END,0),(START,END,-1),(START,END,float("nan")),(START,END,float("inf"))):
            with self.assertRaises(sdde.CollectorError):
                sdde.collect(start,end,timeout)
        opener.assert_not_called()

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_http_errors_sanitized_without_reading_body(self, opener):
        for code in (301,302,307,308,400,401,403,404,429,500,503):
            body=MagicMock();body.read.return_value=fixture("error.json")
            opener.return_value.open.side_effect=HTTPError(sdde.ENDPOINT,code,SECRET,{},body)
            expected=sdde.AuthenticationError if code in (401,403) else sdde.NetworkError
            with self.subTest(code=code), self.assertRaises(expected) as caught:
                sdde.collect(START,END)
            self.assertNotIn(SECRET,str(caught.exception))
            body.read.assert_not_called();body.close.assert_called_once()
            self.assertTrue(caught.exception.__suppress_context__)

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_network_failures(self, opener):
        for error in (URLError(SECRET),TimeoutError(SECRET),OSError(SECRET),IncompleteRead(SECRET.encode())):
            opener.return_value.open.side_effect=error
            with self.subTest(error=type(error)), self.assertRaises(sdde.NetworkError) as caught:
                sdde.collect(START,END)
            self.assertNotIn(SECRET,str(caught.exception))

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_interrupted_response_read(self, opener):
        response=self.response(opener);response.read.side_effect=IncompleteRead(SECRET.encode())
        with self.assertRaises(sdde.NetworkError) as caught:
            sdde.collect(START,END)
        self.assertNotIn(SECRET,str(caught.exception))

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_unexpected_success_status_is_not_data(self, opener):
        for code in (204,206):
            response=self.response(opener,status=code)
            with self.assertRaises(sdde.NetworkError):
                sdde.collect(START,END)
            response.read.assert_not_called()

    @patch("fx_lag.bccr_sdde.build_opener")
    def test_size_limit(self, opener):
        response=self.response(opener,b"x"*(sdde.MAX_RESPONSE_BYTES+1))
        with self.assertRaises(sdde.ResponseError):
            sdde.collect(START,END)
        response.read.assert_called_once_with(sdde.MAX_RESPONSE_BYTES+1)

    def test_all_redirects_reject_without_followup_request(self):
        for code in (301,302,303,307,308):
            for destination in (sdde.ENDPOINT+"/other","https://example.invalid/", "http://apim.bccr.fi.cr/"):
                handler=sdde.NoRedirect();handler.parent=MagicMock()
                req=Request(sdde.ENDPOINT,headers={"Authorization":"Bearer "+SECRET})
                with self.subTest(code=code,destination=destination), self.assertRaises(sdde.NetworkError) as caught:
                    handler.http_error_302(req,MagicMock(),code,"moved",{"location":destination})
                self.assertNotIn(SECRET,str(caught.exception))
                handler.parent.open.assert_not_called()


class CliTests(unittest.TestCase):
    @patch("fx_lag.bccr_sdde.collect")
    def test_date_and_range_json_output(self, collect):
        collect.return_value={"observations":[{"rate":"502.12000"}],"missing_dates":[]}
        for args,expected in ((["--date","2026-01-01"],(START,START,30)),(["--start","2026-01-01","--end","2026-01-03","--timeout","12"],(START,END,12))):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(sdde.main(args),0)
            self.assertEqual(json.loads(output.getvalue()),collect.return_value)
            self.assertEqual(collect.call_args.args,expected)

    @patch("fx_lag.bccr_sdde.collect")
    def test_invalid_arguments(self, collect):
        for args in ([],["--date","2026-02-30"],["--date","20260101"],["--start","2026-01-01"],["--date","2026-01-01","--end","2026-01-03"],["--date","2026-01-01","--start","2026-01-01"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                sdde.main(args)
            self.assertEqual(caught.exception.code,2)
        collect.assert_not_called()

    @patch("fx_lag.bccr_sdde.collect",return_value={"observations":[{"rate":"502"}],"missing_dates":["2026-01-02"]})
    def test_partial_range_warning(self, collect):
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            self.assertEqual(sdde.main(["--date","2026-01-01"]),0)
        self.assertIn("missing",err.getvalue());self.assertEqual(json.loads(out.getvalue()),collect.return_value)

    @patch.dict("os.environ",{"BCCR_SDDE_TOKEN":SECRET},clear=True)
    @patch("fx_lag.bccr_sdde.build_opener")
    def test_actual_cli_http_error_is_sanitized(self, opener):
        for code in (401,500):
            opener.return_value.open.side_effect=HTTPError(sdde.ENDPOINT,code,SECRET,{},io.BytesIO(fixture("error.json")))
            out,err=io.StringIO(),io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                self.assertEqual(sdde.main(["--date","2026-01-01"]),1)
            self.assertEqual(out.getvalue(),"")
            self.assertNotIn(SECRET,err.getvalue());self.assertNotIn("Traceback",err.getvalue())

    @patch("fx_lag.bccr_sdde.collect",side_effect=sdde.NoDataError("No observations"))
    def test_no_data_failure(self, collect):
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            self.assertEqual(sdde.main(["--date","2026-01-01"]),1)
        self.assertEqual(out.getvalue(),"");self.assertIn("No observations",err.getvalue())


if __name__ == "__main__":
    unittest.main()
