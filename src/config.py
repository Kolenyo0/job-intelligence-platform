import os
from pathlib import Path


DATABASE_URL = os.environ.get("DATABASE_URL")
SOURCE_NAME = "arbeitnow"
API_URL = "https://www.arbeitnow.com/api/job-board-api"
REQUEST_TIMEOUT = 10
REQUEST_DELAY = 5
RAW_DATA_PATH = Path("data/raw")
WATERMARK_PATH = Path("data/watermark.json")