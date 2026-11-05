# dbt

The dbt project models the ingestion pipeline's PostgreSQL `job_postings` table.
`scripts/run_dbt.py` reads the same `DATABASE_URL` as the ingestion pipeline,
creates a temporary dbt profile, and removes that profile when the command
finishes. Database credentials are not stored in the project.

Install the project requirements, then run dbt commands from the project root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\run_dbt.py debug
.\.venv\Scripts\python.exe scripts\run_dbt.py run
.\.venv\Scripts\python.exe scripts\run_dbt.py test
```

## Local Docker platform

Install Docker Desktop, then copy `.env.example` to `.env` and adjust the
local PostgreSQL credentials if needed. The example credentials are for local
development only. Keep `.env` private; for passwords with URL-reserved
characters, percent-encode the username and password in `DATABASE_URL`.

From the project root, start both services:

```powershell
docker compose up -d --build
```

Compose waits for PostgreSQL's health check before starting the application.
The application connects to the `postgres` service over the Compose network.
Run ingestion and dbt from the same application container:

```powershell
docker compose exec app python src/pipeline.py
docker compose exec app python scripts/run_dbt.py build
```

Raw snapshots and the ingestion watermark are stored in the host `data`
directory. PostgreSQL data is stored separately in the named `postgres_data`
volume, so recreating or stopping the application does not remove the database.
Stop the services with:

```powershell
docker compose down
```

This keeps the PostgreSQL volume. `docker compose down --volumes` also deletes
the database and should only be used when intentionally resetting local data.

The staging table is created in the `analytics` schema by default. Set
`DBT_SCHEMA` to change that schema. The source table is expected in `public`.

The warehouse models build on `stg_job_postings` through
`int_job_postings`, which keeps the latest staged record per `(source,
source_id)`. `dim_company`, `dim_role`, and `dim_location` each contain one
row per normalized entity and use deterministic MD5 surrogate keys.
`fact_job_posting` has one row per `(source, source_id)` and references each
dimension. Null or blank dimension values map to an `Unknown` entity.
