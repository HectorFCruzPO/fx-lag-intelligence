"""Public branch USD compra observation; no login, private API or app quote."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from html.parser import HTMLParser
from http.client import HTTPException
import json
import math
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import bccr_sdde as sdde
from .csv_history import HistoryError, save_observations

URL = "https://www.promerica.fi.cr/tipo-de-cambio-sucursales/"
SERIES = "promerica_branch_usd_compra"  # Local identity, not a BCCR indicator.
MAX_BYTES = 1_000_000


class PageText(HTMLParser):
    """Read text only, ignoring executable/template content and explicit hiding."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        style = re.sub(r"\s+", "", attrs.get("style", "").lower())
        hidden = (tag in ("script", "style", "template", "noscript", "head") or
                  "hidden" in attrs or attrs.get("aria-hidden", "").lower() == "true" or
                  "display:none" in style or "visibility:hidden" in style)
        if tag not in ("br", "hr", "img", "input", "meta", "link", "source", "wbr", "area", "base", "embed", "param", "track", "col"):
            self.stack.append((tag, hidden or any(item[1] for item in self.stack)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if not any(item[1] for item in self.stack):
            self.parts.append(data)


def parse_page(raw: bytes, retrieved_at: str) -> dict:
    try:
        parser = PageText()
        parser.feed(raw.decode("utf-8-sig"))
        parser.close()
        text = " ".join(" ".join(parser.parts).split())
    except (UnicodeError, ValueError, RecursionError):
        raise sdde.ResponseError("Promerica page could not be decoded safely.") from None
    # Require the observed labels, pair, currency symbols and two numeric cells.
    # Do not search globally for a plausible price or consume accounting rates.
    sections = re.split(r"Referencia\s+contable", text, flags=re.IGNORECASE)
    if len(sections) != 2:
        raise sdde.ResponseError("Promerica page layout changed: accounting boundary missing or ambiguous.")
    number = r"([0-9]+(?:\.[0-9]{2}))"
    pattern = (r"Tipo de cambio\s+Compra\s+Venta\s+USD\s*/\s*CRC\s+"
               r"[¢₡]\s*" + number + r"\s+[¢₡]\s*" + number + r"\s+Precios sujetos")
    matches = re.findall(pattern, sections[0], flags=re.IGNORECASE)
    if len(matches) != 1:
        raise sdde.ResponseError("Promerica USD/CRC branch quote is missing or ambiguous; no rate saved.")
    compra, venta = (Decimal(value) for value in matches[0])
    if not 0 < compra <= venta:
        raise sdde.ResponseError("Promerica returned invalid compra/venta values; no rate saved.")
    return {"observations": [{
        "source": "Promerica", "interface": "PUBLIC_WEB", "source_url": URL,
        "indicator": SERIES, "rate": str(compra), "units": "CRC/USD",
        "effective_date": None, "retrieved_at": retrieved_at,
    }], "missing_dates": []}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise sdde.NetworkError("Promerica page redirect rejected; verify the public URL.") from None


def collect(timeout: float = 30) -> dict:
    if not math.isfinite(timeout) or timeout <= 0:
        raise sdde.CollectorError("Timeout must be a finite positive number.")
    # Fixed public URL, explicit identity, no Authorization or cookies.
    request = Request(URL, headers={"Accept": "text/html", "User-Agent": "FXLagIntelligence/0.1 (public-rate research)"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            if response.status != 200 or response.headers.get_content_type() != "text/html":
                raise sdde.ResponseError("Promerica did not return a successful HTML page.")
            raw = response.read(MAX_BYTES + 1)
    except HTTPError as error:
        code = error.code
        retry_after = error.headers.get("Retry-After") if error.headers else None
        error.close()
        if code == 429:
            raise sdde.RateLimitError("Promerica HTTP 429: stop requests until the cooldown expires.", retry_after) from None
        if code in (401, 403):
            raise sdde.AuthenticationError("Promerica public-page access rejected; do not retry with login credentials.") from None
        raise sdde.NetworkError(f"Promerica HTTP {code}: public-page request failed.") from None
    except (URLError, OSError, HTTPException, ValueError):
        raise sdde.NetworkError("Promerica public page unavailable: connection, TLS or timeout failure.") from None
    if len(raw) > MAX_BYTES:
        raise sdde.ResponseError("Promerica page exceeds the response-size limit.")
    return parse_page(raw, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Observe Promerica public branch USD compra; not an executable app quote.")
    parser.add_argument("--csv", help="Separate public-rate CSV, e.g. data/promerica-history.csv")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    try:
        result = collect(args.timeout)
        saved = None
        if args.csv:
            saved = save_observations(args.csv, result["observations"], source_url=URL, indicator=SERIES)
    except (sdde.CollectorError, HistoryError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    if saved:
        print(f"CSV history: {saved['added']} added, {saved['skipped']} already saved.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
