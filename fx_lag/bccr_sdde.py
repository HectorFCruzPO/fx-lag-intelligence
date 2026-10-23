"""USD compra (317) adapter for BCCR's documented SDDE REST API.

The wire contract comes from the official SDDE guide, pages 19-20.
Synthetic tests verify the implementation; authenticated behavior is unverified.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from http.client import HTTPException
import json
import math
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

# Section 1.3 base URL; its Ge/GE capitalization varies elsewhere in the guide.
BASE_URL = "https://apim.bccr.fi.cr/SDDE/api/Bccr.GE.SDDE.Publico.Indicadores.API"
ENDPOINT = BASE_URL + "/indicadoresEconomicos/317/series"
MAX_RESPONSE_BYTES = 2_000_000
TOKEN_VARIABLE = "BCCR_SDDE_TOKEN"


class CollectorError(Exception):
    """Safe user-facing error; messages contain no remote body or credentials."""


class AuthenticationError(CollectorError):
    """Missing/invalid local credentials or HTTP authentication/access rejection."""


class NetworkError(CollectorError):
    """Transport, HTTP, or redirect failure."""


class ResponseError(CollectorError):
    """Invalid JSON, unexpected schema, or invalid observation."""


class ServiceError(CollectorError):
    """The API reported failure without a reliable authentication classification."""


class NoDataError(CollectorError):
    """No usable observations; no rate has been inferred."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Reject all redirects, including same-host, before another request is made.
        raise NetworkError("SDDE redirected the request; verify the documented endpoint. Redirects are disabled.") from None


def iso_date(value: str) -> date:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Use a valid date in YYYY-MM-DD format.") from None


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value: str):
    raise ValueError("Nonstandard JSON number")


def parse_response(raw: bytes, start: date, end: date, retrieved_at: str) -> dict:
    """Validate the documented indicator-series JSON, never a legacy XML shape."""
    if start > end:
        raise CollectorError("Start date must be on or before end date.")
    try:
        payload = json.loads(
            raw.decode("utf-8-sig"), parse_float=Decimal,
            parse_constant=reject_constant, object_pairs_hook=unique_object,
        )
    except (UnicodeError, ValueError, RecursionError):
        raise ResponseError("SDDE returned invalid JSON.") from None
    if not isinstance(payload, dict):
        raise ResponseError("SDDE response must be a JSON object.")
    if "CodigoError" in payload:
        # The guide documents CodigoError/Mensaje errors. Never echo their text.
        raise ServiceError("SDDE reported an API error; verify the request and service availability.") from None
    if type(payload.get("estado")) is not bool or not isinstance(payload.get("mensaje"), str):
        raise ResponseError("SDDE response has an unexpected status envelope.")
    if payload["estado"] is False:
        raise ServiceError("SDDE reported an unsuccessful query; verify access, dates, and service availability.") from None
    groups = payload.get("datos")
    if not isinstance(groups, list):
        raise ResponseError("SDDE response is missing the documented datos array.")
    if not groups:
        raise NoDataError("SDDE returned no observations; no rate has been inferred.") from None
    if len(groups) != 1 or not isinstance(groups[0], dict):
        raise ResponseError("SDDE returned unexpected indicator groups.")
    group = groups[0]
    if group.get("codigoIndicador") != "317" or not isinstance(group.get("nombreIndicador"), str):
        raise ResponseError("SDDE returned an unexpected indicator identity.")
    rows = group.get("series")
    if not isinstance(rows, list):
        raise ResponseError("SDDE response is missing the documented series array.")
    seen = set()
    observations = {}
    for row in rows:
        if not isinstance(row, dict) or "fecha" not in row or "valorDatoPorPeriodo" not in row:
            raise ResponseError("SDDE series contains an unexpected record schema.")
        try:
            effective = iso_date(row["fecha"]) if isinstance(row["fecha"], str) else None
        except argparse.ArgumentTypeError:
            raise ResponseError("SDDE returned an invalid effective date.") from None
        if effective is None or not start <= effective <= end or effective in seen:
            raise ResponseError("SDDE returned duplicate or out-of-range effective dates.")
        seen.add(effective)
        value = row["valorDatoPorPeriodo"]
        if value is None:
            # Null is missing, never zero; its date remains in missing_dates.
            continue
        if type(value) not in (int, Decimal):
            raise ResponseError("SDDE rate must be a JSON number or null.")
        rate = Decimal(value)
        if not rate.is_finite() or rate <= 0:
            raise ResponseError("SDDE rate must be finite and positive.")
        observations[effective] = {
            "source": "BCCR", "interface": "SDDE", "source_url": ENDPOINT,
            "indicator": 317, "rate": str(rate), "units": "CRC/USD",
            "effective_date": effective.isoformat(), "retrieved_at": retrieved_at,
        }
    if not observations:
        raise NoDataError("SDDE returned no usable observations; no rate has been inferred.") from None
    missing = []
    day = start
    while True:
        if day not in observations:
            missing.append(day.isoformat())
        if day == end:
            break
        day += timedelta(days=1)
    return {
        "observations": [observations[d] for d in sorted(observations)],
        "missing_dates": missing,
    }


def collect(start: date, end: date, timeout: float = 30) -> dict:
    if start > end:
        raise CollectorError("Start date must be on or before end date.")
    if not math.isfinite(timeout) or timeout <= 0:
        raise CollectorError("Timeout must be a finite positive number.")
    token = os.environ.get(TOKEN_VARIABLE, "")
    if not token:
        raise AuthenticationError("Set BCCR_SDDE_TOKEN in the environment before collecting.")
    # RFC 6750 bearer syntax; reject controls/whitespace before header construction.
    if not re.fullmatch(r"[A-Za-z0-9._~+/\-]+=*", token):
        raise AuthenticationError("BCCR_SDDE_TOKEN has invalid Bearer-token syntax.") from None
    query = urlencode({
        "fechaInicio": start.isoformat().replace("-", "/"),
        "fechaFin": end.isoformat().replace("-", "/"), "idioma": "ES",
    })
    request = Request(ENDPOINT + "?" + query, headers={
        "Authorization": "Bearer " + token, "Accept": "application/json", "User-Agent": "Mozilla/5.0",
    }, method="GET")
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            # urllib normally raises HTTPError for errors. Also require HTTP 200
            # explicitly so 204/206 or custom handlers cannot be treated as success.
            if response.status != 200:
                raise NetworkError("SDDE returned an unexpected HTTP success status; no data accepted.")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        code = exc.code
        exc.close()  # Do not read/log potentially sensitive HTTP error bodies.
        if code in (401, 403):
            raise AuthenticationError(f"SDDE HTTP {code}: access rejected; check the SDDE token and subscription.") from None
        if code == 404:
            message = "SDDE HTTP 404: verify the documented endpoint and authentication."
        elif code == 429:
            message = "SDDE HTTP 429: request limit reached; reduce query frequency."
        elif 300 <= code < 400:
            message = "SDDE HTTP redirect rejected; credentials were not forwarded."
        else:
            message = f"SDDE HTTP {code}: request failed; verify parameters and service availability."
        raise NetworkError(message) from None
    except (URLError, OSError, HTTPException, ValueError):
        raise NetworkError("Cannot reach SDDE: network, TLS, connection, timeout, or interrupted response failure.") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ResponseError("SDDE response exceeds the 2 MB limit; request a smaller date range.")
    retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return parse_response(raw, start, end, retrieved)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BCCR SDDE USD compra (317) collector; authenticated live operation remains unverified.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", type=iso_date, help="One effective date, YYYY-MM-DD")
    group.add_argument("--start", type=iso_date, help="First effective date, YYYY-MM-DD")
    parser.add_argument("--end", type=iso_date, help="Last effective date, inclusive; required with --start")
    parser.add_argument("--timeout", type=float, default=30, help="Socket timeout in seconds (default: 30)")
    args = parser.parse_args(argv)
    if bool(args.start) != bool(args.end):
        parser.error("Use --start and --end together, or --date alone.")
    try:
        result = collect(args.date or args.start, args.date or args.end, args.timeout)
    except CollectorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    if result["missing_dates"]:
        print("Warning: requested dates are missing; see missing_dates. No rates were filled.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

