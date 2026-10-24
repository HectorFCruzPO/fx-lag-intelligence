"""BCCR MONEX daily closing-average collector (SDDE indicator 3323).

This wholesale statistic is distinct from BCCR reference compra and bank quotes.
Uses the shared SDDE transport/validation; no scheduler or intraday feed implied.
"""
from __future__ import annotations

from datetime import date
import sys

from . import bccr_sdde as sdde

INDICATOR = 3323
ENDPOINT = sdde.series_endpoint(INDICATOR)


def collect(start: date, end: date, timeout: float = 30) -> dict:
    """Retrieve daily MONEX closing averages without filling missing dates."""
    return sdde.collect(start, end, timeout, indicator=INDICATOR)


def main(argv=None) -> int:
    return sdde.main(argv, indicator=INDICATOR)


if __name__ == "__main__":
    sys.exit(main())
