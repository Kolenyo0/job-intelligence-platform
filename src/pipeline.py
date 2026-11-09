import logging

from extract import fetch_all_jobs, save_raw_snapshot, save_watermark, load_watermark, filter_new_jobs
from load import load_jobs
from config import DATABASE_URL, WATERMARK_PATH, get_raw_storage_config

logger = logging.getLogger(__name__)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",)
    try:
        logger.info("Normal ingestion started")
        get_raw_storage_config()
        all_jobs = fetch_all_jobs()
        logger.info("Fetched %d job records.", len(all_jobs))

        raw_snapshot_path = save_raw_snapshot(all_jobs)
        logger.info("Saved raw snapshot to %s.", raw_snapshot_path)

        watermark = load_watermark()
        new_jobs = filter_new_jobs(all_jobs, watermark)
        if new_jobs is None:
            logger.info("Found 0 new jobs")
        else:
            logger.info("Found %d new job records.", len(new_jobs))

        if not DATABASE_URL:
            raise ValueError("Set DATABASE_URL to the PostgreSQL connection string.")

        count = load_jobs(
            new_jobs,
            DATABASE_URL,
            records_fetched=len(all_jobs),
            snapshot_location=str(raw_snapshot_path),
        )
        logger.info("Processed %d job records.", count)

        save_watermark(new_jobs, watermark, WATERMARK_PATH)
        if new_jobs:
            logger.info("Updated watermark at %s.", WATERMARK_PATH)
        else:
            logger.info("Watermark unchanged; there are no new records.")
        logger.info("Normal ingestion completed")
    except Exception:
        logger.exception("Pipeline run failed.")
        raise


if __name__ == "__main__":
    main()
