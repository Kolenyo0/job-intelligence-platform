"""Airflow orchestration for the Job Intelligence Platform."""

import os
import subprocess
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


PROJECT_DIR = "/opt/airflow/project"


def _run_command(command: list[str], task_name:str) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "/opt/airflow/project/src"
    subprocess.run(command, cwd=PROJECT_DIR, env=env, check=True)


def run_ingestion(**context: object) -> None:
    _run_command([sys.executable, "src/pipeline.py"], "ingestion")


def run_dbt_build() -> None:
    _run_command([sys.executable, "scripts/run_dbt.py", "build"], "dbt build")


with DAG(
    dag_id="job_intelligence_pipeline",
    description="Ingest job postings, then build the dbt models.",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["job-intelligence", "ingestion", "dbt"],
) as dag:
    ingestion = PythonOperator(
        task_id="ingestion",
        python_callable=run_ingestion,
        retries=2,
        retry_delay=timedelta(minutes=5),
    )
    dbt_build = PythonOperator(
        task_id="dbt_build",
        python_callable=run_dbt_build,
    )

    ingestion >> dbt_build
