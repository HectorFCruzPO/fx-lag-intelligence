"""One guarded market collection attempt for Windows Task Scheduler.

Collection window: Monday–Friday, 09:00 through the 17:00 slot, Costa Rica time.
The window is a user preference, not a verified market/publication calendar.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from datetime import datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import sys
import tempfile

from . import bccr_sdde as sdde, monex, promerica
from .csv_history import HistoryError, save_observations

# Costa Rica currently uses UTC-06:00 year-round; no Windows tzdata dependency.
COSTA_RICA = timezone(timedelta(hours=-6), "America/Costa_Rica")
UTC = timezone.utc
STATE_FIELDS = {"version", "last_slot", "last_attempt", "status", "blocked_until"}
STATUSES = {"started", "saved", "partial", "error", "rate_limited", "access_blocked"}


class ScheduleError(Exception):
    """Safe local scheduling/state failure; requests must fail closed."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise ValueError
    return result


def collection_slot(now: datetime) -> str | None:
    """Return a half-hour slot only in the configured local window.

    17:00 gets a one-minute launch grace, not a 17:30 slot. Other delayed starts
    are assigned to the current half-hour; missed slots are never backfilled.
    """
    local = now.astimezone(COSTA_RICA)
    if local.weekday() >= 5 or not time(9) <= local.time() < time(17, 1):
        return None
    return local.replace(minute=(local.minute // 30) * 30, second=0, microsecond=0).isoformat()


def next_weekday_open(now: datetime) -> datetime:
    local = now.astimezone(COSTA_RICA)
    following = (local + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    while following.weekday() >= 5:
        following += timedelta(days=1)
    return following.astimezone(UTC)


def cooldown_until(now: datetime, retry_after: str | None) -> datetime:
    """Pause to the next weekday 09:00, or longer when Retry-After requires it."""
    resume = next_weekday_open(now)
    if retry_after:
        try:
            if retry_after.isascii() and retry_after.isdigit():
                required = now + timedelta(seconds=int(retry_after))
            else:
                required = parsedate_to_datetime(retry_after)
                if required.tzinfo is None:
                    raise ValueError
                required = required.astimezone(UTC)
            resume = max(resume, required)
        except (TypeError, ValueError, OverflowError, IndexError):
            pass  # Unusable header never shortens the next-weekday pause.
    return resume


def read_state(path: Path) -> dict | None:
    if path.is_symlink():
        raise ScheduleError("Schedule state must not be a symbolic link.")
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=sdde.unique_object)
        if not isinstance(value, dict) or set(value) != STATE_FIELDS:
            raise ValueError
        if type(value["version"]) is not int or value["version"] != 1 or value["status"] not in STATUSES:
            raise ValueError
        parse_utc(value["last_attempt"])
        slot = datetime.fromisoformat(value["last_slot"])
        if slot.utcoffset() != timedelta(hours=-6) or collection_slot(slot) != value["last_slot"]:
            raise ValueError
        blocked = value["blocked_until"]
        if blocked is not None:
            parse_utc(blocked)
        if value["status"] == "rate_limited" and blocked is None:
            raise ValueError
        return value
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        raise ScheduleError("Schedule state is unreadable or invalid; no request sent. Restore a trusted state before resuming.") from None


def write_state(path: Path, value: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".bccr-state-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError:
        raise ScheduleError("Could not persist schedule state. Collection stopped; inspect state before resuming.") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


@contextmanager
def runner_lock(path: Path):
    handle = None
    try:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ScheduleError("Another scheduled runner or a stale schedule lock is present; no request sent.") from None
        yield
    finally:
        if handle is not None:
            try:
                os.close(handle)
                path.unlink(missing_ok=True)
            except OSError:
                raise ScheduleError("Schedule lock cleanup failed; inspect the lock before resuming.") from None


def run_once(data_dir: str | Path = "data", timeout: float = 30, *, now: datetime | None = None, source: str = "bccr") -> dict:
    """One guarded source poll; dated BCCR series use the current local date."""
    if source not in ("bccr", "monex", "promerica"):
        raise ScheduleError("Unsupported scheduled source.")
    current = now if now is not None else utc_now()
    if current.tzinfo is None or current.utcoffset() is None:
        raise ScheduleError("The schedule clock must include a timezone.")
    slot = collection_slot(current)
    if slot is None:
        return {"status": "outside_window"}
    root = Path(data_dir)
    try:
        root.mkdir(parents=True, exist_ok=True)
        api_lock = runner_lock(root / "sdde-schedule.lock") if source in ("bccr", "monex") else nullcontext()
        with runner_lock(root / f"{source}-schedule.lock"), api_lock:
            path = root / f"{source}-schedule.json"
            # Both BCCR-hosted collectors use the same token and must honor a
            # persisted pause from either series, even after restarting.
            if source in ("bccr", "monex"):
                other = "monex" if source == "bccr" else "bccr"
                peer = read_state(root / f"{other}-schedule.json")
                if peer and peer["status"] == "started":
                    raise ScheduleError("A BCCR-hosted peer attempt did not finish safely; inspect its state before resuming.")
                if peer and peer["blocked_until"] and current < parse_utc(peer["blocked_until"]):
                    return {"status": "paused", "resume_at": peer["blocked_until"]}
            state = read_state(path)
            if state is not None:
                if state["status"] == "access_blocked":
                    return {"status": "access_blocked"}
                if state["status"] == "started":
                    raise ScheduleError("A previous attempt did not finish safely; no request sent. Inspect state before resuming.")
                if state["blocked_until"] is not None and current < parse_utc(state["blocked_until"]):
                    return {"status": "paused", "resume_at": state["blocked_until"]}
                if current < parse_utc(state["last_attempt"]):
                    raise ScheduleError("Clock moved behind the last attempt; no request sent.")
                if state["last_slot"] == slot:
                    return {"status": "already_attempted"}
                if current - parse_utc(state["last_attempt"]) < timedelta(minutes=29):
                    return {"status": "too_soon"}
            state = {
                "version": 1, "last_slot": slot, "last_attempt": timestamp(current),
                "status": "started", "blocked_until": None,
            }
            # Write before contacting BCCR. An interrupted attempt fails closed.
            write_state(path, state)
            try:
                effective = current.astimezone(COSTA_RICA).date()
                if source == "bccr":
                    result = sdde.collect(effective, effective, timeout)
                    saved = save_observations(root / "bccr-history.csv", result["observations"], source_url=sdde.ENDPOINT)
                elif source == "monex":
                    result = monex.collect(effective, effective, timeout)
                    saved = save_observations(root / "monex-history.csv", result["observations"], source_url=monex.ENDPOINT, indicator=3323)
                else:
                    result = promerica.collect(timeout)
                    saved = save_observations(root / "promerica-history.csv", result["observations"], source_url=promerica.URL, indicator=promerica.SERIES)
            except sdde.RateLimitError as error:
                finished = current if now is not None else utc_now()
                state["status"] = "rate_limited"
                state["blocked_until"] = timestamp(cooldown_until(finished, error.retry_after))
                write_state(path, state)
                return {"status": "rate_limited", "resume_at": state["blocked_until"]}
            except sdde.AuthenticationError:
                if source == "promerica":
                    state["status"] = "access_blocked"
                    write_state(path, state)
                    return {"status": "access_blocked"}
                state["status"] = "error"
                write_state(path, state)
                return {"status": "error", "message": "SDDE access rejected; check token and subscription."}
            except (sdde.CollectorError, HistoryError):
                state["status"] = "error"
                write_state(path, state)
                # Never serialize underlying exceptions, bodies, headers or tokens.
                return {"status": "error", "message": "Collection or CSV saving failed; next eligible slot may try again."}
            state["status"] = "partial" if result["missing_dates"] else "saved"
            write_state(path, state)
            return {"status": state["status"], **saved}
    except OSError:
        raise ScheduleError("Schedule files could not be accessed; no further request attempted.") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="One source run: weekdays 09:00–17:00 Costa Rica time, 30-minute slots, durable 429 pause.")
    parser.add_argument("--data-dir", default="data", help="Persistent schedule state and CSV directory (default: data)")
    parser.add_argument("--timeout", type=float, default=30, help="Network socket timeout (seconds)")
    parser.add_argument("--source", choices=("bccr", "monex", "promerica"), default="bccr")
    args = parser.parse_args(argv)
    try:
        result = run_once(args.data_dir, args.timeout) if args.source == "bccr" else run_once(args.data_dir, args.timeout, source=args.source)
    except ScheduleError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 1 if result["status"] in ("error", "partial", "access_blocked") else (2 if result["status"] == "rate_limited" else 0)


if __name__ == "__main__":
    sys.exit(main())
