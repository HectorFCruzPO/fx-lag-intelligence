
import argparse
import json
import msvcrt
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLISH_REPO = Path.home() / "fx-lag-publisher" / "repo"
PUBLISH_JSON = PUBLISH_REPO / "dashboard" / "rates.json"

sys.path.insert(0, str(ROOT / "dashboard"))
from export_rates import SOURCES, build_source
@contextmanager
def publisher_lock():
    lock_path = PUBLISH_REPO.parent / "publisher.lock"

    with open(lock_path, "a+b") as lock_file:
        lock_file.seek(0)
        lock_file.write(b"\0")
        lock_file.flush()
        lock_file.seek(0)

        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError(
                "Another publisher process is already running."
            ) from None

        try:
            yield
        finally:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


def git(*args):
    command = ["git", "-C", str(PUBLISH_REPO), *args]

    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or "").strip()
        raise RuntimeError(
            f"Git operation '{args[0]}' failed: {details}"
        ) from error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check for updates without changing files or pushing to GitHub.",
    )
    args = parser.parse_args()
    if not (PUBLISH_REPO / ".git").exists():
        raise RuntimeError("Publishing repository not found.")

    status = git("status", "--porcelain").stdout.strip()
    if status:
        raise RuntimeError(
            "Publishing repository has uncommitted changes. "
            "Resolve them before publishing."
        )

    branch = git("branch", "--show-current").stdout.strip()
    if branch != "main":
        raise RuntimeError("Publishing repository must be on main.")

        # Recover commits left behind by a previous failed push.
    if not args.dry_run:
        git("fetch", "origin", "main")

        unpublished = git(
            "rev-list", "--count", "origin/main..HEAD"
        ).stdout.strip()

        if int(unpublished) > 0:
            # Recover only when the remote is an ancestor.
            # Otherwise stop safely for manual review.
            remote_is_ancestor = subprocess.run(
                [
                    "git", "-C", str(PUBLISH_REPO),
                    "merge-base", "--is-ancestor",
                    "origin/main", "HEAD",
                ],
                capture_output=True,
            )

            if remote_is_ancestor.returncode != 0:
                raise RuntimeError(
                    "Publishing stopped: local and remote Git "
                    "history require manual review."
                )

            git("push", "origin", "main")
            print(f"Recovered {unpublished} unpublished commit(s).")

        git("pull", "--ff-only", "origin", "main")

    sources = {}
    history = {}

    for name, filename in SOURCES:
        latest, observations = build_source(name, filename)

        if latest is None or not observations:
            raise RuntimeError(
                f"No valid historical data for {name}. "
                "Publishing stopped to protect existing rates."
            )

        sources[name] = latest
        history[name] = observations

    # Keep the previous generated_at when observations have
    # not changed, avoiding timestamp-only Git commits.
    existing = json.loads(PUBLISH_JSON.read_text(encoding="utf-8"))
    # Prevent incomplete collector data from replacing
    # historical observations already published.
    for name in history:
        previous = existing.get("history", {}).get(name, [])

        if len(history[name]) < len(previous):
            raise RuntimeError(
                f"Historical data protection: {name} has "
                f"{len(history[name])} observations, but the "
                f"published dashboard has {len(previous)}. "
                "Publishing stopped to prevent data loss."
             )
        # Protect historical observation dates and timestamps.
        # Existing observations may be corrected, but their
        # identifying dates or timestamps must not disappear.
        def observation_key(item):
            if name == "promerica":
                return item.get("retrieved_at")
            return item.get("effective_date")

        previous_keys = {
            observation_key(item) for item in previous
        }
        current_keys = {
            observation_key(item) for item in history[name]
        }

        missing_keys = previous_keys - current_keys

        if missing_keys:
            raise RuntimeError(
                f"Historical data protection: {name} is missing "
                f"{len(missing_keys)} previously published "
                "observation(s). Publishing stopped."
            )

    if (
        existing.get("sources") == sources
        and existing.get("history") == history
    ):
        print("No new observations. Nothing to publish.")
        return
    if args.dry_run:
        print("DRY RUN: New observations detected.")
        print("No files changed. No commits or pushes performed.")
        return

    from datetime import datetime, timezone

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "history": history,
    }

    PUBLISH_JSON.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    git("add", "--", "dashboard/rates.json")
    git("commit", "-m", "data: update published exchange rates")
    git("push", "origin", "main")

    print("Exchange-rate data published successfully.")


if __name__ == "__main__":
    with publisher_lock():
        main()
