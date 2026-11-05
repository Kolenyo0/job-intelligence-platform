# Airflow local runbook

Airflow is orchestrated locally through Docker Compose. The existing `jobs_db`
PostgreSQL service remains the application and dbt database. Airflow uses the
separate `airflow_db` PostgreSQL service for its operational metadata.

## Start the environment

```powershell
docker compose up -d --build airflow-init airflow-webserver airflow-scheduler
```

Open http://localhost:8080 and sign in with `admin` / `admin`. The
`job_intelligence_pipeline` DAG should be visible and unpaused. The final DAG
configuration runs automatically once per day (`@daily`), but the validation
below starts with manual runs.

## Ingestion retry policy

The `ingestion` task retries transient failures up to **2 times**, waiting **5
minutes** between attempts. This allows short-lived dependency or network
failures to recover without creating a long retry loop. If all three attempts
(the initial attempt plus two retries) fail, the task is marked failed and
`dbt_build` remains `upstream_failed` for that DAG run.

Each ingestion run is recorded in the PostgreSQL `pipeline_runs` table with
its run ID, start and completion timestamps, status, and fetched/new/loaded
record counts. The `run_type` column distinguishes normal `ingestion` runs
from `replay` runs. A run that fetches zero records is marked failed and
raises an error so Airflow can retry it.

## Recovery replay

To recover from a saved snapshot, run the recovery entry point with the JSON
path from inside the application or Airflow container:

```bash
PYTHONPATH=/opt/airflow/project/src python src/replay.py data/raw/jobs_20261102_120000.json
```

Replay reads only the supplied snapshot, validates and UPSERTs every record,
does not call Arbeitnow, does not consult the watermark, and does not update
the watermark. Its logs identify the snapshot and report records in and
records processed.

## Manual validation

Trigger a normal run from the Airflow UI. Confirm `ingestion` succeeds, then
`dbt_build` succeeds. The downstream task cannot start until ingestion has
completed successfully; the task logs show the existing pipeline and dbt
commands running in order.

To deliberately fail ingestion, trigger a run with this JSON configuration in
the UI's **Trigger DAG** dialog:

```json
{"force_ingestion_failure": true}
```

Confirm the ingestion task retries after five minutes (or inspect the task
instance's retry count and logs), then confirm that after the final failed
attempt `ingestion` is red and `dbt_build` is shown as `upstream_failed` (and
has no task log for that run). Trigger one more run without configuration to
restore the successful path and confirm both task logs are successful.
