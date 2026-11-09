from datetime import datetime, timezone
from typing import Mapping
from uuid import uuid4


import psycopg

from config import SOURCE_NAME


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS job_postings (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    company_name TEXT,
    job_title TEXT,
    remote BOOLEAN,
    location TEXT,
    "type" TEXT[],
    created_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, source_id)
)
"""

CREATE_PIPELINE_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    records_fetched INTEGER NOT NULL,
    records_new INTEGER NOT NULL,
    records_loaded INTEGER NOT NULL,
    snapshot_location TEXT,
    run_type TEXT NOT NULL DEFAULT 'ingestion'
)
"""

ADD_RUN_TYPE_COLUMN = """
ALTER TABLE pipeline_runs
ADD COLUMN IF NOT EXISTS run_type TEXT NOT NULL DEFAULT 'ingestion'
"""

ADD_SNAPSHOT_LOCATION_COLUMN = """
ALTER TABLE pipeline_runs
ADD COLUMN IF NOT EXISTS snapshot_location TEXT
"""

INSERT_PIPELINE_RUN = """
INSERT INTO pipeline_runs (
    run_id,
    started_at,
    completed_at,
    status,
    records_fetched,
    records_new,
    records_loaded,
    snapshot_location,
    run_type
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

INSERT_JOB = """
INSERT INTO job_postings (
    source,
    source_id,
    company_name,
    job_title,
    remote,
    location,
    "type",
    created_at
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (source, source_id) 
DO UPDATE SET
    company_name = EXCLUDED.company_name,
    job_title = EXCLUDED.job_title,
    remote = EXCLUDED.remote,
    location = EXCLUDED.location,
    "type" = EXCLUDED."type",
    created_at = EXCLUDED.created_at,
    ingested_at = CURRENT_TIMESTAMP;
"""


def _job_data(job: Mapping[str, object], index: int) -> tuple[object, ...]:
    try:
        source = SOURCE_NAME
        source_id = job["slug"]
        company_name = job["company_name"]
        job_title = job["title"]
        remote = job["remote"]
        location = job["location"]
        tags = job["tags"]
        created_at = job["created_at"]

        if not isinstance(source, str):
            raise TypeError("'source' must be a string")
        if not isinstance(source_id, str):
            raise TypeError("'slug' must be a string")
        if not isinstance(company_name, str):
            raise TypeError("'company_name' must be a string")
        if not isinstance(job_title, str):
            raise TypeError("'title' must be a string")
        if not isinstance(remote, bool):
            raise TypeError("'remote' must be a boolean")
        if location is not None and not isinstance(location, str):
            raise TypeError("'location' must be a string or null")
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) for tag in tags
        ):
            raise TypeError("'tags' must be a list of strings")
        if not isinstance(created_at, (int, float)) or isinstance(created_at, bool):
            raise TypeError("'created_at' must be a Unix timestamp")

        return (
            source,
            source_id,
            company_name,
            job_title,
            remote,
            location,
            tags,
            datetime.fromtimestamp(created_at, tz=timezone.utc),
        )
    except (KeyError, OverflowError, OSError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid job record at index {index}: {error}") from error


def load_jobs(
    jobs: list[Mapping[str, object]],
    database_url: str,
    records_fetched: int | None = None,
    run_type: str = "ingestion",
    snapshot_location: str | None = None,
) -> int:
    rows = [_job_data(job, index) for index, job in enumerate(jobs, start=1)]
    records_fetched = len(jobs) if records_fetched is None else records_fetched
    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(CREATE_TABLE)
            cursor.execute(CREATE_PIPELINE_RUNS_TABLE)
            cursor.execute(ADD_RUN_TYPE_COLUMN)
            cursor.execute(ADD_SNAPSHOT_LOCATION_COLUMN)

            if records_fetched == 0:
                completed_at = datetime.now(timezone.utc)
                cursor.execute(
                    INSERT_PIPELINE_RUN,
                    (
                        run_id,
                        started_at,
                        completed_at,
                        "failed",
                        records_fetched,
                        len(rows),
                        0,
                        snapshot_location,
                        run_type,
                    ),
                )
                connection.commit()
                raise ValueError(
                    "Ingestion returned 0 records; refusing to treat the run as successful."
                )

            cursor.executemany(INSERT_JOB, rows)
            cursor.execute(
                INSERT_PIPELINE_RUN,
                (
                    run_id,
                    started_at,
                    datetime.now(timezone.utc),
                    "success",
                    records_fetched,
                    len(rows),
                    len(rows),
                    snapshot_location,
                    run_type,
                ),
            )

    return len(rows)

