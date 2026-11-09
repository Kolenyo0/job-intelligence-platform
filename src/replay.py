"""Replay a saved raw snapshot through the normal validation and load path."""

import argparse
import logging
from pathlib import Path

from config import DATABASE_URL
from extract import load_raw_snapshot
from load import load_jobs


logger = logging.getLogger(__name__)


def replay_snapshot(snapshot_path: str | Path, database_url: str | None = DATABASE_URL) -> int:
    """Replay every record in *snapshot_path* without API or watermark access."""
    snapshot_value = str(snapshot_path)
    logger.info("Recovery replay started")
    logger.info("Snapshot: %s", snapshot_value.rsplit("/", 1)[-1])

    jobs = load_raw_snapshot(snapshot_value)
    logger.info("Records in snapshot: %d", len(jobs))

    if not database_url:
        raise ValueError("Set DATABASE_URL to the PostgreSQL connection string.")

    count = load_jobs(
        jobs,
        database_url,
        records_fetched=len(jobs),
        run_type="replay",
        snapshot_location=snapshot_value,
    )
    logger.info("Records processed: %d", count)
    logger.info("Recovery replay completed")
    return count


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Replay a saved raw job snapshot.")
    parser.add_argument("snapshot", help="Path or s3://bucket/key for a saved raw snapshot JSON")
    args = parser.parse_args()
    replay_snapshot(args.snapshot)


if __name__ == "__main__":
    main()
