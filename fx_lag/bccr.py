"""Collector for BCCR's documented legacy indicator 317 XML service."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.client import HTTPException
import json
import math
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
import xml.etree.ElementTree as ET

ENDPOINT = "https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/wsindicadoreseconomicos.asmx"
METHOD = "ObtenerIndicadoresEconomicosXML"
NAMESPACE = "http://ws.sdde.bccr.fi.cr"
SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
MAX_RESPONSE_BYTES = 2_000_000


class CollectorError(Exception):
    """A safe, user-facing collection failure (never includes remote bodies)."""


class AuthenticationError(CollectorError):
    """Credentials are missing or the service explicitly rejected authentication."""


class NoDataError(CollectorError):
    """No observations were returned; this alone does not prove invalid credentials."""


class ResponseError(CollectorError):
    """The response cannot be interpreted safely as indicator 317 data."""


class NetworkError(CollectorError):
    """Transport, HTTP, or service availability failure."""


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def auth_message(text: str) -> bool:
    # Heuristic only: BCCR's current fault vocabulary is not verified.
    return any(word in text.casefold() for word in (
        "token", "autentic", "authentication", "unauthorized", "credencial",
        "correo", "suscripci", "subscription", "access denied"))


def xml_root(raw: bytes | str) -> ET.Element:
    # Disallow DTD/entity declarations, including UTF-16/32 encodings.
    scan = raw.replace(b"\x00", b"") if isinstance(raw, bytes) else raw
    upper = scan.upper()
    declarations = (b"<!DOCTYPE", b"<!ENTITY") if isinstance(upper, bytes) else ("<!DOCTYPE", "<!ENTITY")
    if any(marker in upper for marker in declarations):
        raise ResponseError("BCCR XML contains unsupported DTD/entity declarations.")
    try:
        return ET.fromstring(raw)
    except (ET.ParseError, ValueError):
        raise ResponseError("BCCR returned invalid XML.") from None


def parse_response(raw: bytes, start: date, end: date, retrieved_at: str) -> dict:
    """Parse SOAP escaped XML or direct XML; report gaps without fabricating rates."""
    root = xml_root(raw)
    fault = next((e for e in root.iter() if local_name(e.tag) == "Fault"), None)
    if fault is not None:
        if auth_message(" ".join(fault.itertext())):
            raise AuthenticationError("BCCR rejected authentication; check BCCR_EMAIL and BCCR_TOKEN.")
        raise ResponseError("BCCR returned a SOAP fault; service or request may be unsupported.")
    wrapper = next((e for e in root.iter() if local_name(e.tag) in (METHOD + "Result", "string")), None)
    if wrapper is not None:
        if len(wrapper):
            root = wrapper
        else:
            text = (wrapper.text or "").strip()
            if not text or text.casefold() == "nothing":
                raise NoDataError("BCCR returned no data; check dates, subscription, and service availability.")
            if not text.startswith("<"):
                if auth_message(text):
                    raise AuthenticationError("BCCR rejected authentication; check BCCR_EMAIL and BCCR_TOKEN.")
                raise ResponseError("BCCR returned an unexpected non-XML result.")
            root = xml_root(text)
    rows = [e for e in root.iter() if local_name(e.tag) == "INGC011_CAT_INDICADORECONOMIC"]
    if not rows:
        if local_name(root.tag) not in ("Datos_de_INGC011_CAT_INDICADORECONOMIC", "NewDataSet", METHOD + "Result", "string"):
            raise ResponseError("BCCR response has an unrecognized data schema.")
        raise NoDataError("BCCR returned no observations; no rate has been inferred.")
    observations = {}
    for row in rows:
        fields = {local_name(e.tag): (e.text or "").strip() for e in row}
        try:
            if fields["COD_INDICADORINTERNO"] != "317":
                raise ValueError
            raw_date = fields["DES_FECHA"]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?", raw_date):
                raise ValueError
            effective = datetime.fromisoformat(raw_date).date() if "T" in raw_date else date.fromisoformat(raw_date)
            rate = Decimal(fields["NUM_VALOR"])
            if not rate.is_finite() or rate <= 0 or not start <= effective <= end or effective.isoformat() in observations:
                raise ValueError
        except (KeyError, ValueError, InvalidOperation):
            raise ResponseError("BCCR returned invalid, duplicate, out-of-range, or non-317 observations.") from None
        observations[effective.isoformat()] = {
            "source": "BCCR", "source_url": ENDPOINT, "indicator": 317,
            "rate": str(rate), "units": "CRC/USD", "effective_date": effective.isoformat(),
            "retrieved_at": retrieved_at,
        }
    # Publication time is intentionally omitted: DES_FECHA is an effective date.
    missing = []
    day = start
    while day <= end:
        if day.isoformat() not in observations:
            missing.append(day.isoformat())
        if day == end:
            break
        day += timedelta(days=1)
    return {"observations": [observations[k] for k in sorted(observations)], "missing_dates": missing}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward subscription credentials to a redirected destination.
        raise NetworkError("BCCR redirected the request; endpoint support needs verification.")


def collect(start: date, end: date, name: str, timeout: float = 30) -> dict:
    if start > end:
        raise CollectorError("Start date must be on or before end date.")
    if not name.strip():
        raise CollectorError("Provide a representative user name with --name.")
    if not math.isfinite(timeout) or timeout <= 0:
        raise CollectorError("Timeout must be a finite positive number.")
    email, token = (os.environ.get(k, "").strip() for k in ("BCCR_EMAIL", "BCCR_TOKEN"))
    if not email or not token:
        raise AuthenticationError("Set BCCR_EMAIL and BCCR_TOKEN environment variables before collecting.")
    envelope = ET.Element(f"{{{SOAP}}}Envelope")
    body = ET.SubElement(envelope, f"{{{SOAP}}}Body")
    method = ET.SubElement(body, f"{{{NAMESPACE}}}{METHOD}")
    for key, value in {
        "Indicador": "317", "FechaInicio": start.strftime("%d/%m/%Y"),
        "FechaFinal": end.strftime("%d/%m/%Y"), "Nombre": name,
        "SubNiveles": "N", "CorreoElectronico": email, "Token": token,
    }.items():
        ET.SubElement(method, f"{{{NAMESPACE}}}{key}").text = value
    request = Request(ENDPOINT, data=ET.tostring(envelope, encoding="utf-8", xml_declaration=True), headers={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{NAMESPACE}/{METHOD}"',
    }, method="POST")
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise AuthenticationError(f"HTTP {exc.code}: access rejected; check subscription credentials and access policy.") from None
        if exc.code == 500:
            # SOAP 1.1 faults commonly arrive with HTTP 500.
            try:
                raw = exc.read(MAX_RESPONSE_BYTES + 1)
            except (OSError, HTTPException):
                raise NetworkError("BCCR response was interrupted while reading an HTTP fault.") from None
            try:
                parse_response(raw, start, end, "")
            except AuthenticationError:
                raise
            except CollectorError:
                pass
        raise NetworkError(f"BCCR HTTP {exc.code}; request failed (legacy service may be unavailable).") from None
    except (URLError, OSError, HTTPException):
        raise NetworkError("Cannot reach BCCR: network, TLS, connection, or timeout failure.") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ResponseError("BCCR response exceeds the 2 MB safety limit; request a smaller date range.")
    retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return parse_response(raw, start, end, retrieved)


def iso_date(value: str) -> date:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Use a valid date in YYYY-MM-DD format.") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Retrieve BCCR USD compra (317) from the documented legacy XML service.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", type=iso_date, help="One effective date, YYYY-MM-DD")
    group.add_argument("--start", type=iso_date, help="First effective date, YYYY-MM-DD")
    parser.add_argument("--end", type=iso_date, help="Last effective date (inclusive); required with --start")
    parser.add_argument("--name", required=True, help="Representative name of the service user")
    parser.add_argument("--timeout", type=float, default=30, help="Network timeout in seconds (default: 30)")
    args = parser.parse_args(argv)
    if bool(args.start) != bool(args.end):
        parser.error("Use --start and --end together, or --date alone.")
    try:
        result = collect(args.date or args.start, args.date or args.end, args.name, args.timeout)
    except CollectorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["missing_dates"]:
        print("Warning: some requested dates are missing; see missing_dates. No values were filled.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
