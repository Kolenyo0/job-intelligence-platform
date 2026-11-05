import json
import time
from datetime import datetime
from pathlib import Path

import requests

from config import API_URL, RAW_DATA_PATH, REQUEST_DELAY, REQUEST_TIMEOUT, WATERMARK_PATH


def fetch_page(page):
    response = requests.get(
        API_URL, params={"page": page}, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def fetch_all_jobs():
    all_jobs = []
    page = 1
    while True:
        data = fetch_page(page)
        all_jobs.extend(data["data"])
        if data["links"]["next"] is None:
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return all_jobs


def load_watermark(filepath=WATERMARK_PATH):
    if not filepath.exists():
        return None
    with filepath.open(encoding="utf-8") as file:
        return json.load(file)


def filter_new_jobs(jobs, watermark):
    if watermark is None:
        return jobs

    watermark_created_at = watermark["created_at"]
    watermark_slugs = set(watermark["slugs"])
    return [
        job
        for job in jobs
        if job["created_at"] > watermark_created_at
        or (
            job["created_at"] == watermark_created_at
            and job["slug"] not in watermark_slugs
        )
    ]


def save_raw_snapshot(jobs):
    RAW_DATA_PATH.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = RAW_DATA_PATH / f"jobs_{timestamp}.json"
    with filepath.open("w", encoding="utf-8") as file:
        json.dump(jobs, file, indent=2, ensure_ascii=False)
    return filepath


def load_raw_snapshot(filepath: str | Path):
    """Read a previously saved raw snapshot without contacting the source API."""
    path = Path(filepath)
    with path.open(encoding="utf-8") as file:
        snapshot = json.load(file)

    if isinstance(snapshot, list):
        jobs = snapshot
    elif isinstance(snapshot, dict) and isinstance(snapshot.get("data"), list):
        jobs = snapshot["data"]
    else:
        raise ValueError(
            "Raw snapshot must contain job records as a JSON array or under a 'data' key."
        )

    return jobs


def save_watermark(jobs, previous_watermark, filepath):
    if not jobs:
        return

    newest_created_at = max(job["created_at"] for job in jobs)
    if (
        previous_watermark is not None
        and newest_created_at == previous_watermark["created_at"]
    ):
        slugs = set(previous_watermark["slugs"])
    else:
        slugs = set()

    slugs.update(
        job["slug"] for job in jobs if job["created_at"] == newest_created_at
    )
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("w", encoding="utf-8") as file:
        json.dump({"created_at": newest_created_at, "slugs": sorted(slugs)}, file)
