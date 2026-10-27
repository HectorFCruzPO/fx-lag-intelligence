
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "dashboard" / "rates.json"

SOURCES = [
    ("monex", "monex-history.csv"),
    ("bccr", "bccr-history.csv"),
    ("promerica", "promerica-history.csv"),
]


def read_observations(filename):
    path = DATA / filename

    if not path.exists():
        return []

    observations = []

    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            try:
                rate = float(row["rate"])
                if not math.isfinite(rate) or rate <= 0:
                    continue

                retrieved = datetime.fromisoformat(
                    row["retrieved_at"].replace("Z", "+00:00")
                )

                if retrieved.tzinfo is None:
                    continue

                effective_date = row.get("effective_date") or None

                if effective_date:
                    datetime.strptime(effective_date, "%Y-%m-%d")

                observations.append({
                    "rate": rate,
                    "effective_date": effective_date,
                    "retrieved_at": retrieved.isoformat(),
                    "units": row.get("units", "CRC/USD"),
                })

            except (ValueError, KeyError, TypeError):
                continue

    return observations


def build_source(name, filename):
    observations = read_observations(filename)

    if not observations:
        return None, []

    latest = max(
        observations,
        key=lambda item: item["retrieved_at"]
    )

    # MONEX and BCCR: one observation per effective date.
    # Promerica: retain timestamped observations.
    history = {}

    for observation in observations:
        if name == "promerica":
            key = observation["retrieved_at"]
        else:
            key = observation["effective_date"]

        if not key:
            continue

        previous = history.get(key)

        if (
            previous is None
            or observation["retrieved_at"] > previous["retrieved_at"]
        ):
            history[key] = observation

    ordered = sorted(
        history.values(),
        key=lambda item: (
            item["effective_date"] or item["retrieved_at"]
        )
    )

    return latest, ordered


def main():
    sources = {}
    history = {}

    for name, filename in SOURCES:
        latest, observations = build_source(name, filename)
        sources[name] = latest
        history[name] = observations

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "history": history,
    }

    OUTPUT.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8"
    )

    print(f"Exported dashboard data to {OUTPUT}")

    for name in sources:
        print(f"{name}: {len(history[name])} historical points")


if __name__ == "__main__":
    main()
