**Job Intelligence Platform**

An end-to-end data engineering project that turns job-board API data into a tested PostgreSQL analytics layer and a Power BI executive dashboard. The platform runs on AWS EC2 using Docker Compose, with Apache Airflow coordinating daily ingestion and dbt transformations.

**Status:** Deployed on AWS EC2; deployed end-to-end pipeline test completed successfully on November 5, 2026. Supports local or private S3 raw-snapshot storage, authenticates through an EC2 IAM role, preserves local snapshots on upload failure, and supports replay from local files or S3.

**Purpose**

Job postings arrive as operational API records. Analyzing them consistently requires repeatable extraction, stable identifiers, standardized fields, and clear relationships between postings, companies, locations, and roles.

This project implements that workflow and the operational controls needed to maintain it: incremental ingestion, safe reruns, raw snapshots, data-quality tests, execution logs, and recovery through snapshot replay.

**Raw snapshot storage**

Local development uses `RAW_STORAGE=local` by default and needs no AWS credentials. Snapshots are written to `data/raw/`. To use durable S3 snapshots, set `RAW_STORAGE=s3`, `S3_BUCKET`, `S3_PREFIX` (default `raw/`), and `AWS_DEFAULT_REGION`. The application writes the complete JSON file locally, closes it, uploads it with `Content-Type: application/json`, records the resulting `s3://bucket/key` in `pipeline_runs.snapshot_location`, and removes the local copy only after a successful upload. An upload failure leaves the local file in place, fails the task, and prevents watermark advancement.

Replay accepts either a local JSON path or `s3://bucket/key`. S3 replay downloads to a temporary file, uses the same validation and UPSERT path, then removes the temporary file; it never deletes the S3 object. Replay does not read or update the ingestion watermark, preserving the existing recovery behavior.

**Architecture**

<img width="1736" height="1696" alt="mermaid-diagram" src="https://github.com/user-attachments/assets/bc2447c5-cd64-4930-ac31-209e03bdb433" />

The ingestion and transformation services run on an Ubuntu EC2 host. PostgreSQL holds the application data and analytics models; Airflow uses a separate metadata database. Power BI consumes the curated analytics layer. Dashboard refresh is a separate step from a successful Airflow run.

**Technology stack**

Component	Technology	Responsibility
Extraction and loading	Python	API pagination, snapshots, incremental processing, database writes
Storage	PostgreSQL	Job postings, pipeline run records, analytics views
Transformation	dbt	SQL models and automated data-quality tests
Orchestration	Apache Airflow	Daily execution and ingestion-to-build dependency
Packaging	Docker and Docker Compose	Reproducible services and persistent storage
Deployment	AWS EC2, Ubuntu	Cloud execution environment
Reporting	Power BI	Executive job-market analysis



**Pipeline workflow**
1. Fetch paginated job postings from the Arbeitnow API.
2. Save the fetched payload to a timestamped raw JSON snapshot before transformation.
3. Use a created_at watermark to identify newly eligible records.
4. Load records into PostgreSQL with transactional writes and a unique (source, source_id) identity to support safe reruns.
5. Record execution information and emit logs for extraction, loading, and failures.
6. Run dbt build after ingestion succeeds to create the analytics models and execute their tests.
7. Refresh Power BI to consume the latest successful analytics output.
Snapshots are stored under data/raw/, and incremental state is maintained in data/watermark.json. PostgreSQL data and required pipeline files must persist across container recreation.

**Data model**

The analytics layer contains six dbt models:


_stg_job_postings_ -	Standardize source fields and normalize blank values

_int_job_postings_ -	Resolve duplicate identities using deterministic ordering

_dim_company_ -	Company descriptions and surrogate keys

_dim_location_ -	Location descriptions and surrogate keys

_dim_role_ -	Job-title descriptions and surrogate keys

_fact_job_posting_ -	One row per posting identity, linked to company, location, and role


The fact grain is **one job posting per (source, source_id)**. Saved raw snapshots provide extraction history; the fact model is not a daily snapshot of whether each posting remains active.


**Reliability and data quality**

**1. Safe reruns**: Source identity constraints and UPSERT-based loading prevent repeated ingestion from creating duplicate posting identities.

**2. Incremental state**: A watermark avoids repeatedly processing the entire fetched dataset as new data.

**3. Transaction handling**: Failed database work is rolled back rather than committed partially.

**4. Recovery**: Saved raw snapshots support replay without depending on the current API response.

**5. Failure propagation**: Subprocesses use nonzero exit codes to fail their Airflow tasks. A failed ingestion blocks the dependent dbt build.

**6. Visibility**: Airflow task status, Python logs, and pipeline_runs records support troubleshooting. An ingestion success record alone does not prove that the downstream dbt build succeeded.

**7. Automated validation**: 31 dbt data tests cover required values, unique identities and keys, dimension relationships, timestamp validity, and fact-row preservation.


**Validation results**


 **- Local** - ingestion run	4,666 records processed

 **- Subsequent incremental run**	- 0 new records processed; watermark unchanged

 **- dbt build**	- 6 models and 31 data tests completed successfully

 **- dbt summary**	- PASS=37 WARN=0 ERROR=0

 **- Deployed end-to-end test**	- Successful on AWS EC2, November 5, 2026


The record counts describe individual validation runs, not total warehouse size or daily throughput. The dbt summary includes model builds as well as tests.

**Run the project**

**Prerequisites**
- Git, Docker, and Docker Compose.
- Access to the Arbeitnow API.
- A local .env configured for the database and Airflow services defined in docker-compose.yml.
- Power BI Desktop for opening and refreshing the dashboard.

**Clone and configure**
git clone https://github.com/Kolenyo0/job-intelligence-platform.git
cd job-intelligence-platform
Use .env.example as the configuration reference. Set DATABASE_URL to the application database and supply the credentials required by Compose. Container-to-container database connections use the Compose service hostname and internal PostgreSQL port; a desktop client uses the host's published port.

Before the first run, initialize the application schema and Airflow metadata/admin account using the repository's database setup and Airflow initialization configuration. Ensure the mounted project directories are writable by the container user, including data/ and the dbt-generated output locations.

**Start services**

docker compose up -d --build
docker compose ps

**Run ingestion and transformations manually**

docker compose exec app python src/pipeline.py
docker compose exec app python scripts/run_dbt.py build

**Run through Airflow**

Open the Airflow UI, enable job_intelligence_pipeline, and trigger a run. The DAG is scheduled daily with catchup=False and executes ingestion before dbt_build.

Inspect both tasks and their logs when verifying a run. A successful ingestion task followed by a failed dbt task requires investigation before refreshing the dashboard.

**Deployment and access**

The deployed environment uses Docker Compose on an AWS EC2 Ubuntu instance. Keep credentials in environment configuration, preserve database and snapshot storage, and use SSH tunneling to access services bound to localhost.

Example Airflow tunnel, with placeholders for your own SSH key and host:
ssh -i /path/to/key.pem -L 18080:127.0.0.1:8080 ubuntu@EC2_HOST
Then open http://localhost:18080. Keep .env, private keys, raw data, and generated runtime files out of version control.

See the [Airflow Linux deployment runbook](docs/airflow-linux-deployment-runbook.md)
for EC2 setup, permissions, SSH tunnels, troubleshooting, and recovery.

**Power BI**

The executive dashboard uses curated fact and dimension models for analysis by company, location, role, and remote status. Refresh an imported Power BI dataset after the pipeline succeeds to retrieve updated data.

A completed cloud pipeline run does not automatically refresh a Power BI import. A secure connection to the deployed database and Power BI Service scheduled refresh require separate configuration.

**Troubleshooting**

Symptom	What to check
PermissionError saving a snapshot	Ownership and write permissions on the mounted data/ directory
dbt task fails after ingestion succeeds	dbt logs, database connection, dependencies, and generated-file permissions
PostgreSQL data appears missing in a desktop client	Host, published port, database name, and schema; confirm local versus EC2 environment
Airflow appears successful but dashboard is stale	dbt task result, Power BI data-source connection, and last dashboard refresh
Rerun finds no new records	Compare source timestamps with the watermark; zero new records can be expected


**Limitations and next steps**

The platform covers one API source and runs on a single EC2 instance. It demonstrates deployed orchestration and recovery controls; high availability and sustained uptime have not been measured.

A creation-time watermark primarily captures new postings. Updates to older postings, late-arriving records, and listing removals need a reconciliation strategy. Retained postings should not be interpreted as a current inventory of open jobs, and this source is not representative of the entire labor market.

Planned improvements include automated failure notifications, CI checks,  backup-and-restore validation, and additional sources with explicit reconciliation rules.
Author
Peter Kolenyo · LinkedIn
