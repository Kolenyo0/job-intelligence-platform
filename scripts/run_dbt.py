import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from dbt.cli.main import dbtRunner
import yaml


PROJECT_DIR = Path(__file__).resolve().parent.parent
SUPPORTED_QUERY_PARAMETERS = {
    "application_name",
    "connect_timeout",
    "options",
    "sslcert",
    "sslkey",
    "sslmode",
    "sslrootcert",
}


def _profile_from_database_url(database_url: str) -> dict[str, object]:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use the postgres or postgresql scheme.")
    if not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("DATABASE_URL must include a host and database name.")
    if parsed.username is None:
        raise ValueError("DATABASE_URL must include a database username.")

    credentials: dict[str, object] = {
        "type": "postgres",
        "host": parsed.hostname,
        "user": unquote(parsed.username),
        "password": unquote(parsed.password or ""),
        "port": parsed.port or 5432,
        "dbname": unquote(parsed.path.lstrip("/")),
        "schema": os.environ.get("DBT_SCHEMA", "analytics"),
        "threads": 4,
    }

    query_parameters = parse_qs(parsed.query)
    for name in SUPPORTED_QUERY_PARAMETERS:
        if name in query_parameters:
            credentials[name] = query_parameters[name][-1]

    return {"job_intelligence": {"target": "dev", "outputs": {"dev": credentials}}}


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("Set DATABASE_URL to the PostgreSQL URL used by ingestion.")
    if not sys.argv[1:]:
        raise ValueError("Pass a dbt command, for example: run or test.")

    profile = _profile_from_database_url(database_url)
    with tempfile.TemporaryDirectory(prefix="job-intelligence-dbt-") as temp_dir:
        profile_path = Path(temp_dir) / "profiles.yml"
        profile_path.write_text(yaml.safe_dump(profile), encoding="utf-8")
        command = [
            *sys.argv[1:],
            "--project-dir",
            str(PROJECT_DIR),
            "--profiles-dir",
            temp_dir,
        ]
        result = dbtRunner().invoke(command)
        return 0 if result.success else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"dbt setup failed: {error}", file=sys.stderr)
        raise SystemExit(2) from error
