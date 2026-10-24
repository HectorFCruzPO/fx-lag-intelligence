"""Read-only descriptive report for three distinct local rate histories."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException, localcontext
import json
from pathlib import Path
import sys

from . import bccr_sdde, monex, promerica
from .csv_history import HistoryError, read_history
from .scheduled_bccr import COSTA_RICA

SOURCES = (
    ("bccr", "BCCR reference compra", bccr_sdde.ENDPOINT, 317),
    ("monex", "MONEX closing average", monex.ENDPOINT, 3323),
    ("promerica", "Promerica public branch compra", promerica.URL, promerica.SERIES),
)
LIMITATIONS = [
    "Distinct reference, wholesale and public branch series; not interchangeable executable quotes.",
    "Source publication time and freshness are unverified. Retrieval time is not publication time.",
    "Observation-check windows do not establish exact update times, causal order or a predictive lag.",
    "Gaps describe absent successful observations, including schedule breaks; they do not prove failed requests.",
    "Historical/backfilled rows are shown by effective date, not treated as intraday observations of past changes.",
]


class ReportError(Exception):
    """Safe report failure; no raw CSV records or underlying errors exposed."""


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def stamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError
    return result.astimezone(timezone.utc)


def minutes(start: datetime, end: datetime) -> str:
    delta = end - start
    micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    return str((Decimal(micros) / Decimal(60_000_000)).quantize(Decimal("0.01")))


def difference(current: str, previous: str) -> str:
    a, b = Decimal(current), Decimal(previous)
    precision = max(a.adjusted(), b.adjusted()) - min(a.as_tuple().exponent, b.as_tuple().exponent) + 2
    if precision > 10_000:
        raise ReportError("Rate precision exceeds report arithmetic limits; no histories changed.")
    try:
        with localcontext() as ctx:
            ctx.prec = max(28, precision)
            delta = a - b
            return "0" if delta.is_zero() else str(delta)
    except DecimalException:
        raise ReportError("Rate arithmetic could not be represented safely; no histories changed.") from None


def comparison(previous: dict, current: dict, *, historical: bool = False) -> dict:
    delta = difference(current["rate"], previous["rate"])
    changed_period = previous["effective_date"] != current["effective_date"]
    kind = ("daily_period_change" if historical or changed_period else
            "same_effective_date_revision" if current["effective_date"] else "public_quote_observation")
    # For period changes/backfills, do not manufacture an intraday update window.
    window = None if historical or changed_period else {
        "previous_check_at": previous["retrieved_at"], "current_check_at": current["retrieved_at"],
        "elapsed_minutes": minutes(stamp(previous["retrieved_at"]), stamp(current["retrieved_at"])),
        "publication_transition_verified": False,
    }
    return {
        "direction": "increase" if Decimal(delta) > 0 else "decrease" if Decimal(delta) < 0 else "unchanged",
        "delta_crc_per_usd": delta, "previous_rate": previous["rate"], "rate": current["rate"],
        "previous_effective_date": previous["effective_date"], "effective_date": current["effective_date"],
        "observed_at": current["retrieved_at"], "comparison_kind": kind,
        "observation_check_window": window,
    }


def summarize(key: str, label: str, rows: list[dict], as_of: datetime, gap_minutes: int) -> dict:
    future_retrievals = sum(stamp(row["retrieved_at"]) > as_of for row in rows)
    rows = [dict(row, effective_date=row["effective_date"] or None,
                 retrieved_at=utc(stamp(row["retrieved_at"])))
            for row in rows if stamp(row["retrieved_at"]) <= as_of]
    rows.sort(key=lambda row: (stamp(row["retrieved_at"]), row["effective_date"] or ""))
    # Detect ambiguous conflicting values rather than invent an observation order.
    seen = set()
    for row in rows:
        identity = (row["retrieved_at"], row["effective_date"])
        if identity in seen:
            raise ReportError("Conflicting observations share a series, effective date and retrieval timestamp.")
        seen.add(identity)
    daily = {}
    polls = []
    future_effective = historical = 0
    for row in rows:
        effective = row["effective_date"]
        local_date = stamp(row["retrieved_at"]).astimezone(COSTA_RICA).date().isoformat()
        if effective is not None:
            if effective not in daily:
                daily[effective] = {"effective_date": effective, "rate": row["rate"],
                                    "first_retrieved_at": row["retrieved_at"], "last_retrieved_at": row["retrieved_at"],
                                    "retrieval_count": 0, "revision_count": 0}
            entry = daily[effective]
            entry["revision_count"] += Decimal(entry["rate"]) != Decimal(row["rate"])
            entry.update(rate=row["rate"], last_retrieved_at=row["retrieved_at"],
                         retrieval_count=entry["retrieval_count"] + 1)
            if effective > local_date:
                future_effective += 1
                continue
            if effective < local_date:
                historical += 1
                continue
        polls.append(row)
    daily = [daily[day] for day in sorted(daily) if day <= as_of.astimezone(COSTA_RICA).date().isoformat()]
    daily_comparisons = []
    for previous, current in zip(daily, daily[1:]):
        left = dict(previous, retrieved_at=previous["last_retrieved_at"])
        right = dict(current, retrieved_at=current["last_retrieved_at"])
        daily_comparisons.append(comparison(left, right, historical=True))
    comparisons, gaps = [], []
    for previous, current in zip(polls, polls[1:]):
        comparisons.append(comparison(previous, current))
        start, end = stamp(previous["retrieved_at"]), stamp(current["retrieved_at"])
        elapsed = minutes(start, end)
        if end - start > timedelta(minutes=gap_minutes):
            gaps.append({"from": previous["retrieved_at"], "to": current["retrieved_at"],
                         "elapsed_minutes": elapsed,
                         "spans_local_dates": start.astimezone(COSTA_RICA).date() != end.astimezone(COSTA_RICA).date()})
    latest = polls[-1] if polls else None
    last_success = max((stamp(row["retrieved_at"]) for row in rows), default=None)
    return {
        "source_key": key, "label": label, "status": "observed" if polls else "historical_only" if historical else "no_eligible_polls" if rows else "no_observations",
        "observation_count": len(rows), "eligible_poll_count": len(polls),
        "historical_row_count": historical, "future_effective_row_count": future_effective,
        "future_retrieval_rows_excluded": future_retrievals,
        "last_successful_retrieval_at": utc(last_success) if last_success else None,
        "minutes_since_last_retrieval": minutes(last_success, as_of) if last_success else None,
        "freshness": "unverified", "latest_observation": latest,
        "latest_poll_from_prior_local_date": (
            stamp(latest["retrieved_at"]).astimezone(COSTA_RICA).date() < as_of.astimezone(COSTA_RICA).date()
            if latest else None),
        "comparisons": comparisons, "daily_history": daily, "daily_comparisons": daily_comparisons,
        "observation_gaps": gaps,
    }


def build_report(data_dir: str | Path = "data", *, as_of: datetime | None = None, gap_minutes: int = 45) -> dict:
    current = as_of if as_of is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ReportError("Report time must include a timezone.")
    if type(gap_minutes) is not int or not 1 <= gap_minutes <= 525600:
        raise ReportError("Gap threshold must be a whole number from 1 through 525600 minutes.")
    result = {"as_of": utc(current), "display_timezone": "America/Costa_Rica (UTC-06:00)",
              "units": "CRC/USD", "gap_threshold_minutes": gap_minutes, "sources": [],
              "movement_timeline": [], "limitations": LIMITATIONS}
    for key, label, url, indicator in SOURCES:
        path = Path(data_dir) / f"{key}-history.csv"
        try:
            rows = read_history(path, url, indicator)
        except (HistoryError, OSError, UnicodeError, csv.Error, ValueError):
            raise ReportError(f"Cannot read valid {key} history; check its format, identity and permissions. No histories changed.") from None
        source = summarize(key, label, rows, current, gap_minutes)
        source.update(source_url=url, indicator=indicator)
        if not path.exists():
            source["status"] = "missing_file"
        result["sources"].append(source)
        result["movement_timeline"].extend(dict(item, source_key=key) for item in source["comparisons"] if item["direction"] != "unchanged")
    result["movement_timeline"].sort(key=lambda event: (stamp(event["observed_at"]), event["source_key"]))
    return result


def local_time(value: str | None) -> str:
    return stamp(value).astimezone(COSTA_RICA).isoformat() if value else "unknown"


def markdown(report: dict, limit: int = 10) -> str:
    lines = ["# Three-source observation report", "",
             f"As of {local_time(report['as_of'])}. Times below: Costa Rica (UTC-06:00). Rates: CRC/USD.", "",
             f"Showing up to {limit} recent entries per section; JSON output includes the full report.", "",
             "| Series | Latest eligible poll rate | Effective date | Retrieved at | Status |",
             "| --- | --- | --- | --- | --- |"]
    for source in report["sources"]:
        row = source["latest_observation"]
        status = source['status'] + (" (prior local date)" if source['latest_poll_from_prior_local_date'] else "")
        lines.append(f"| {source['label']} | {row['rate'] if row else '—'} | {(row['effective_date'] or 'unknown') if row else '—'} | {local_time(row['retrieved_at']) if row else '—'} | {status} |")
    lines += ["", "Each latest value has its own retrieval time; these are not a simultaneous snapshot."]
    for source in report["sources"]:
        lines += ["", f"## {source['label']}", "",
                  f"Rows: {source['observation_count']}; eligible polls: {source['eligible_poll_count']}; historical rows: {source['historical_row_count']}; future-effective rows excluded from polls: {source['future_effective_row_count']}.",
                  f"Future retrievals excluded: {source['future_retrieval_rows_excluded']}. Minutes since last successful retrieval: {source['minutes_since_last_retrieval'] or 'unknown'}. Source freshness: unverified.", "",
                  "### Recent poll comparisons", "",
                  "| Observed at | Direction | Previous → current | Delta CRC/USD | Check window | Kind |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for item in source["comparisons"][-limit:]:
            window = item["observation_check_window"]
            interval = f"{local_time(window['previous_check_at'])} to {local_time(window['current_check_at'])}" if window else "different effective periods; no intraday window"
            lines.append(f"| {local_time(item['observed_at'])} | {item['direction']} | {item['previous_rate']} → {item['rate']} | {item['delta_crc_per_usd']} | {interval} | {item['comparison_kind']} |")
        if not source["comparisons"]:
            lines += ["", "No comparable pair of eligible polls yet."]
        lines += ["", "### Daily history (latest retrieved value per effective date)", "",
                  "| Effective date | Rate | Daily change CRC/USD | First retrieved | Last retrieved | Revisions observed |",
                  "| --- | --- | --- | --- | --- | --- |"]
        daily_changes = {item["effective_date"]: item for item in source["daily_comparisons"]}
        for row in source["daily_history"][-limit:]:
            change = daily_changes.get(row["effective_date"])
            delta = f"{change['direction']} {change['delta_crc_per_usd']}" if change else "no baseline"
            lines.append(f"| {row['effective_date']} | {row['rate']} | {delta} | {local_time(row['first_retrieved_at'])} | {local_time(row['last_retrieved_at'])} | {row['revision_count']} |")
        if not source["daily_history"]:
            lines += ["", "No dated daily history; an unknown date is not filled from retrieval time."]
        lines += ["", f"Observation gaps over {report['gap_threshold_minutes']} minutes: {len(source['observation_gaps'])}. Schedule breaks may be included."]
        for gap in source["observation_gaps"][-limit:]:
            lines.append(f"- {local_time(gap['from'])} to {local_time(gap['to'])}: {gap['elapsed_minutes']} minutes; spans local dates: {gap['spans_local_dates']}.")
    lines += ["", "## Changed observations across sources", "", "Chronological retrieval order only; movements are not matched into causal episodes.", ""]
    for event in report["movement_timeline"][-limit:]:
        lines.append(f"- {local_time(event['observed_at'])}: {event['source_key']} {event['direction']} {event['delta_crc_per_usd']} CRC/USD ({event['comparison_kind']}).")
    if not report["movement_timeline"]:
        lines.append("No eligible changed observations yet.")
    lines += ["", "## Interpretation limits", ""] + [f"- {item}" for item in report["limitations"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only comparison of BCCR, MONEX and Promerica local CSV histories. No network requests.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--as-of", help="Optional timezone-aware ISO timestamp; exclude later retrievals")
    parser.add_argument("--gap-minutes", type=int, default=45, help="Diagnostic observation-gap threshold, not a freshness rule")
    parser.add_argument("--limit", type=int, default=10, help="Recent rows per Markdown section (JSON contains all)")
    args = parser.parse_args(argv)
    if args.limit <= 0 or args.gap_minutes <= 0:
        parser.error("Limit and gap minutes must be positive.")
    try:
        try:
            as_of = stamp(args.as_of) if args.as_of else None
        except (ValueError, OverflowError):
            raise ReportError("Use a valid timezone-aware ISO timestamp for --as-of.") from None
        report = build_report(args.data_dir, as_of=as_of, gap_minutes=args.gap_minutes)
    except ReportError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2) if args.format == "json" else markdown(report, args.limit), end="\n" if args.format == "json" else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
