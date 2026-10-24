"""Local CSV history for validated BCCR SDDE observations (no credentials)."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import re
import tempfile

FIELDS = (
    "source", "interface", "source_url", "indicator", "rate", "units",
    "effective_date", "retrieved_at",
)


class HistoryError(Exception):
    """Safe storage failure; never includes raw row content or system errors."""


def validated_row(observation: dict, source_url: str, indicator: int | str = 317) -> dict:
    """Reject corrupt/foreign rows rather than silently changing a history file."""
    try:
        public = indicator == "promerica_branch_usd_compra"
        if not public and (type(indicator) is not int or indicator not in (317, 3323)):
            raise ValueError
        if public and source_url != "https://www.promerica.fi.cr/tipo-de-cambio-sucursales/":
            raise ValueError
        if not isinstance(observation, dict) or set(observation) != set(FIELDS):
            raise ValueError
        row = dict(observation)
        if public and row["effective_date"] is None:
            row["effective_date"] = ""
        if type(row["indicator"]) is int:
            row["indicator"] = str(row["indicator"])
        if any(not isinstance(value, str) for value in row.values()):
            raise ValueError
        if (row["source"], row["interface"], row["indicator"], row["units"], row["source_url"]) != (
            "Promerica" if public else "BCCR", "PUBLIC_WEB" if public else "SDDE",
            str(indicator), "CRC/USD", source_url,
        ):
            raise ValueError
        # Accept decimal/scientific notation emitted by Decimal, never formulas.
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:[Ee][+-]?[0-9]+)?", row["rate"]):
            raise ValueError
        rate = Decimal(row["rate"])
        if not rate.is_finite() or rate <= 0:
            raise ValueError
        if public:
            if row["effective_date"] != "":
                raise ValueError  # No source effective date is supplied by this page.
        elif date.fromisoformat(row["effective_date"]).isoformat() != row["effective_date"]:
            raise ValueError
        stamp = row["retrieved_at"]
        if "T" not in stamp:
            raise ValueError
        retrieved = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if retrieved.tzinfo is None or retrieved.utcoffset() != timedelta(0):
            raise ValueError
    except (ValueError, TypeError, InvalidOperation, OverflowError):
        raise HistoryError("CSV history contains an invalid or incompatible observation; no data was saved.") from None
    return row


def observation_key(row: dict) -> tuple:
    # Keep each retrieval, even for unchanged rates. Only exact observations dedupe.
    return (row["source"], row["interface"], row["indicator"],
            row["effective_date"], Decimal(row["rate"]),
            datetime.fromisoformat(row["retrieved_at"].replace("Z", "+00:00")))


def read_history(path: Path, source_url: str, indicator: int | str = 317) -> list[dict]:
    if path.is_symlink():
        raise HistoryError("CSV destination must not be a symbolic link.")
    if not path.exists():
        return []
    if not path.is_file():
        raise HistoryError("CSV destination must be a regular file, not a link or directory.")
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != list(FIELDS):
            raise HistoryError("CSV history has an incompatible header; choose a new file or restore a backup.")
        rows = [validated_row(row, source_url, indicator) for row in reader]
    keys = [observation_key(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise HistoryError("CSV history already contains duplicate observations; no data was saved.")
    return rows


def save_observations(path: str | Path, observations: list[dict], *, source_url: str, indicator: int | str = 317) -> dict:
    """Atomically add observations, retaining every distinct retrieval timestamp.

    Cooperating writers use an exclusive sidecar lock. This is a small local
    history of successful observations, not a scheduler or failed-query log.
    """
    destination = Path(path)
    temporary = None
    lock_fd = None
    lock_path = None
    try:
        lock_path = destination.with_name(destination.name + ".lock")
        incoming = [validated_row(row, source_url, indicator) for row in observations]
        if not incoming:
            raise HistoryError("No observations to save; CSV history was not changed.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise HistoryError("CSV history is locked. Close other collectors; see the guide for stale-lock recovery.") from None
        existing = read_history(destination, source_url, indicator)
        keys = {observation_key(row) for row in existing}
        added, skipped = 0, 0
        for row in incoming:
            key = observation_key(row)
            if key in keys:
                skipped += 1
                continue
            existing.append(row)
            keys.add(key)
            added += 1
        if added:
            # Same-directory temp + replace: a failed write cannot truncate history.
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=destination.parent,
                prefix="." + destination.name + ".", suffix=".tmp", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(existing)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            temporary = None
        return {"added": added, "skipped": skipped}
    except HistoryError:
        raise
    except (OSError, UnicodeError, csv.Error, ValueError):
        raise HistoryError("Could not save CSV history; check the path, file format and write permissions. Existing history was not replaced.") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        if lock_fd is not None:
            try:
                os.close(lock_fd)
                lock_path.unlink(missing_ok=True)
            except OSError:
                raise HistoryError("CSV lock cleanup failed; the CSV may already be saved. Check the lock before retrying.") from None
