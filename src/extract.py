import json
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import boto3
import requests

from config import (
    API_URL,
    RAW_DATA_PATH,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    WATERMARK_PATH,
    get_raw_storage_config,
)


logger = logging.getLogger(__name__)


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
    storage = get_raw_storage_config()
    RAW_DATA_PATH.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    filepath = RAW_DATA_PATH / f"jobs_{timestamp}.json"
    with filepath.open("w", encoding="utf-8") as file:
        json.dump(jobs, file, indent=2, ensure_ascii=False)

    if storage.mode == "local":
        return filepath

    key = f"{storage.prefix}jobs_{timestamp}_{uuid4().hex}.json"
    location = f"s3://{storage.bucket}/{key}"
    try:
        client = boto3.client("s3", region_name=storage.region)
        with filepath.open("rb") as file:
            client.upload_fileobj(
                file,
                storage.bucket,
                key,
                ExtraArgs={"ContentType": "application/json"},
            )
    except Exception:
        logger.exception("Raw snapshot upload failed; local snapshot preserved at %s", filepath)
        raise

    try:
        filepath.unlink()
    except OSError:
        logger.exception("Uploaded raw snapshot to %s, but local cleanup failed at %s", location, filepath)
    return location


def load_raw_snapshot(filepath: str | Path):
    """Read a previously saved raw snapshot without contacting the source API."""
    path_value = str(filepath)
    temporary_path = None
    if path_value.startswith("s3://"):
        bucket, separator, key = path_value[5:].partition("/")
        if not bucket or not separator or not key:
            raise ValueError("S3 snapshot paths must use the form s3://bucket/key.")
        storage = get_raw_storage_config()
        temporary_file = tempfile.NamedTemporaryFile(
            mode="wb", suffix=".json", prefix="job-snapshot-", delete=False
        )
        temporary_path = Path(temporary_file.name)
        temporary_file.close()
        try:
            boto3.client("s3", region_name=storage.region).download_file(
                bucket, key, str(temporary_path)
            )
            path = temporary_path
            with path.open(encoding="utf-8") as file:
                snapshot = json.load(file)
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("S3 replay temporary-file cleanup failed at %s", temporary_path)
    else:
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
