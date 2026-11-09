import os
from dataclasses import dataclass
from pathlib import Path


DATABASE_URL = os.environ.get("DATABASE_URL")
SOURCE_NAME = "arbeitnow"
API_URL = "https://www.arbeitnow.com/api/job-board-api"
REQUEST_TIMEOUT = 10
REQUEST_DELAY = 5
RAW_DATA_PATH = Path("data/raw")
WATERMARK_PATH = Path("data/watermark.json")


@dataclass(frozen=True)
class RawStorageConfig:
    mode: str
    bucket: str | None
    prefix: str
    region: str | None


def get_raw_storage_config() -> RawStorageConfig:
    """Read and validate raw snapshot storage settings without contacting AWS."""
    mode = os.environ.get("RAW_STORAGE", "local").strip().lower()
    if mode not in {"local", "s3"}:
        raise ValueError("RAW_STORAGE must be either 'local' or 's3'.")

    prefix = os.environ.get("S3_PREFIX", "raw/").strip().strip("/")
    prefix = f"{prefix}/" if prefix else ""
    bucket = os.environ.get("S3_BUCKET", "").strip() or None
    region = os.environ.get("AWS_DEFAULT_REGION", "").strip() or None

    if mode == "s3":
        missing = [name for name, value in (("S3_BUCKET", bucket), ("AWS_DEFAULT_REGION", region)) if not value]
        if missing:
            raise ValueError(
                "RAW_STORAGE=s3 requires: " + ", ".join(missing) + "."
            )

    return RawStorageConfig(mode=mode, bucket=bucket, prefix=prefix, region=region)
