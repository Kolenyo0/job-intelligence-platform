# Airflow on Linux: Deployment and Operations Runbook

Project: Job Intelligence Platform  
Scope: Single Ubuntu EC2 host, Docker Compose, Airflow 2.10.5 with LocalExecutor, PostgreSQL, Python ingestion, and dbt.  
This documents the deployment used in this project. Check service names and mounts against your repository before using it elsewhere. It is a single-host learning deployment, not a high-availability architecture.

## 1. Quick start: return to an existing deployment

### On your Windows laptop — PowerShell

Connect to the server (replace the IP with the current EC2 public IP):

```powershell
ssh -i "C:\Users\peter\Downloads\job-intelligence-key.pem" ubuntu@YOUR_EC2_PUBLIC_IP
```

### On EC2 — Ubuntu terminal

```bash
cd ~/job-intelligence-platform
sudo docker compose ps -a
sudo docker compose up -d
```

Do not rebuild on every visit. `up -d` starts or reconciles services in the background.

### On your laptop — second PowerShell window

Open both tunnels:

```powershell
ssh -i "C:\Users\peter\Downloads\job-intelligence-key.pem" -o ExitOnForwardFailure=yes -N -L 18080:127.0.0.1:8080 -L 15433:127.0.0.1:5433 ubuntu@YOUR_EC2_PUBLIC_IP
```

Keep this window open; no output normally means the tunnel is waiting for connections. Close existing tunnels on these ports before opening another.

- Airflow: http://localhost:18080
- pgAdmin: host `127.0.0.1`, port `15433`, and the EC2 database credentials.
- Closing the tunnel stops laptop access, not the pipeline.
- EC2 and the required containers must stay running for scheduled execution.

## 2. Understand what runs where

| Component | Responsibility |
| --- | --- |
| EC2 Ubuntu host | Remote computer holding Docker, the repository, and persistent storage |
| Dockerfile | Build instructions for an image |
| Image | Software and dependencies used to create a container |
| Compose | Defines services, networks, mounts, environment, and ports |
| `jobs_db` | Job records, pipeline run metrics, and dbt analytical relations |
| `app` | Standalone environment for manual project execution |
| `airflow_db` | Airflow metadata: schedules, users, task and DAG states |
| `airflow-init` | Database initialization/migration and initial user setup |
| `airflow-webserver` | Airflow browser interface |
| `airflow-scheduler` | Schedules and executes tasks using LocalExecutor |

In this deployment, scheduled ingestion runs in the scheduler container, not in the `app` container. The DAG starts Python subprocesses there.

The dependency `ingestion >> dbt_build` establishes order. The subprocess exit code establishes success or failure. Docker supplies the runtime; Airflow supplies scheduling and task orchestration.

## 3. Provision the EC2 host

1. Choose a supported Ubuntu release and an architecture compatible with your images. Ubuntu LTS is a sensible baseline for a fresh deployment.
2. Allocate enough memory and disk for Airflow, two PostgreSQL services, image builds, and raw snapshots. Review EC2 pricing before launching.
3. Create/download an SSH key pair and retain the private key locally.
4. Permit inbound SSH TCP 22 from your current public IP.
5. With the tunnel approach, do not add public inbound rules for PostgreSQL or Airflow.
6. Confirm the instance is running and status checks have passed.
7. Record its current public IP. A stop/start can change a non-static public IP.

### First SSH connection

Compare the host fingerprint before accepting. In the EC2 console, select the instance, then **Actions → Monitor and troubleshoot → Get system log**. Find `BEGIN SSH HOST KEY FINGERPRINTS` and compare the same algorithm and complete SHA256 fingerprint shown by SSH. This is not the fingerprint on the Key pairs page.

### Windows private-key permissions error

If OpenSSH reports `UNPROTECTED PRIVATE KEY FILE`, use local PowerShell:

```powershell
$key = "C:\Users\peter\Downloads\job-intelligence-key.pem"
$me = whoami
icacls $key /grant:r "${me}:(R)"
icacls $key /inheritance:r
icacls $key
```

Remove any remaining unauthorized account/group named in the error. In this session, it was:

```powershell
icacls $key /remove "HPG7\CodexSandboxUsers"
```

Do not remove your own access. Never paste or commit the private key contents.

## 4. Install Docker and Git — EC2 terminal

Check first:

```bash
docker --version
sudo docker compose version
```

If Docker is already installed, skip installation. For a fresh supported Ubuntu host, use Docker's official apt repository:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<DOCKER_REPO
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
DOCKER_REPO
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

If the Ubuntu release is unsupported or the host has conflicting Docker packages, follow the official installation prerequisites instead of forcing a different distribution repository.

## 5. Clone the repository — EC2 terminal

```bash
cd ~
git clone https://github.com/Kolenyo0/job-intelligence-platform.git
cd job-intelligence-platform
ls
```

There must be a space after `clone`.

For a private repository, GitHub account passwords do not work for HTTPS Git operations. Create a short-lived fine-grained token scoped to this repository with Contents read-only. Enter your username at the username prompt and the token at the password prompt. Do not embed the token in the clone URL. A read-only deploy key is another option for ongoing server access.

## 6. Configure the EC2 environment

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Only copy the example when creating a new `.env`; do not overwrite an existing deployment configuration.

Replace placeholders using the variable names expected by your Compose file. Example:

```dotenv
POSTGRES_DB=job_market
POSTGRES_USER=jobs_user
POSTGRES_PASSWORD=REPLACE_WITH_EC2_PASSWORD
DATABASE_URL=postgresql://jobs_user:REPLACE_WITH_EC2_PASSWORD@jobs_db:5432/job_market
DBT_SCHEMA=analytics
```

| URL part | Must match |
| --- | --- |
| Username | `POSTGRES_USER` |
| Password | `POSTGRES_PASSWORD` (URL-encode special characters in the URL) |
| Host `jobs_db` | PostgreSQL Compose service name |
| Port `5432` | Internal PostgreSQL port |
| Final path `job_market` | `POSTGRES_DB` |

`POSTGRES_DB` does not need to equal the service name. Use a separate EC2 password. This database is separate from the laptop database.

PostgreSQL initialization variables create the initial database/user only when its data directory is empty. Editing `.env` later does not change existing database passwords.

Review Airflow admin credentials and webserver secret configuration too. If these are hardcoded in Compose, adding unused variables to `.env` will not change them. Keep `.env` out of Git.

Save nano with Ctrl+O, Enter; exit with Ctrl+X.

```bash
sudo docker compose config --quiet
git check-ignore .env
```

Do not publish resolved Compose output: it can include credentials.

## 7. Build images and prepare Linux permissions

The following steps assume the project's bind mounts expose the repository as `/opt/airflow/project` and `dags/` as `/opt/airflow/dags`.

```bash
sudo docker compose build
sudo docker compose run --rm --no-deps --entrypoint id airflow-scheduler
```

Record the reported UID and GID. Our container used UID `50000`, GID `0`. Use the actual values if different.

### Permission setup for the current trusted project mount

Run from `~/job-intelligence-platform`. These variables are shell variables, not required `.env` entries:

```bash
AIRFLOW_RUN_UID=50000
AIRFLOW_RUN_GID=0

sudo mkdir -p data/raw logs target dbt_packages

# Preserve the host user's ownership; grant the container group access.
sudo chgrp "$AIRFLOW_RUN_GID" .
sudo chmod g+rwx .

sudo chgrp "$AIRFLOW_RUN_GID" .env
chmod 640 .env

sudo chgrp -R "$AIRFLOW_RUN_GID" data logs target dbt_packages
sudo chmod -R g+rwX data logs target dbt_packages

# New subdirectories inherit the shared group.
sudo find data logs target dbt_packages -type d -exec chmod g+s {} +
```

The project root needs group write permission because `dbt deps` deletes/recreates `dbt_packages` and may write its lock file. This grants the trusted Airflow process write access at the project root; a more restrictive deployment would separate read-only source code from writable runtime directories.

The `.env` group-read setting is needed by this whole-project mount because the installed dbt automatically discovers and reads `.env`. Compose also injects configured variables into containers. Do not use `chmod 777` or recursively loosen permissions across the entire repository.

### What each folder needs

| Path | Access needed | Reason |
| --- | --- | --- |
| `data/` and `data/raw/` | Write | Snapshots and watermark |
| `.env` | Read | dbt dotenv discovery in this setup |
| `logs/` | Write | dbt diagnostic logs |
| `target/` | Write | Compiled SQL and result artifacts |
| `dbt_packages/` | Write | Downloaded dbt packages |
| Project directory | Write for dependency installation | Replace package directory/create lock file |

Airflow's own `/opt/airflow/logs` named volume is separate from project `logs/`. Do not change PostgreSQL volume ownership to the Airflow UID.

## 8. Configure optional S3 raw snapshots

Local storage is the default and remains the rollback setting:

```dotenv
RAW_STORAGE=local
S3_BUCKET=
S3_PREFIX=raw/
AWS_DEFAULT_REGION=
```

For S3 storage, use an existing bucket and a dedicated prefix. Do not add AWS access keys to `.env`; boto3 uses its default credential provider chain. On EC2, prefer the instance profile/IAM role:

```dotenv
RAW_STORAGE=s3
S3_BUCKET=YOUR_BUCKET_NAME
S3_PREFIX=job-intelligence/raw/
AWS_DEFAULT_REGION=us-east-1
```

The role needs only `s3:PutObject` and `s3:GetObject` on `arn:aws:s3:::YOUR_BUCKET_NAME/job-intelligence/raw/*` for ingestion and replay. Add `s3:ListBucket` on the bucket only if an operational tool needs prefix listing; this application does not require it. If bucket encryption uses a customer-managed KMS key, grant the role the corresponding encryption/decryption permissions separately.

After changing `requirements.txt`, `Dockerfile`, or Compose configuration, rebuild and recreate the application and Airflow containers. Run from the checkout, with no ingestion active:

```bash
sudo docker compose build app airflow-init airflow-webserver airflow-scheduler
sudo docker compose up -d --force-recreate airflow-init airflow-webserver airflow-scheduler app
sudo docker compose ps -a
```

Check the attached identity from inside the scheduler without printing credentials:

```bash
sudo docker compose exec airflow-scheduler python -c 'import boto3; print(boto3.client("sts").get_caller_identity())'
```

This command prints only the account, ARN, and principal ID; it does not print credentials or environment variables.

Safe S3 smoke test: use a dedicated test prefix and synthetic JSON, never the production ingestion command. The following uploads and downloads an inline synthetic payload without running ingestion or loading PostgreSQL:

```bash
TEST_PREFIX=job-intelligence/smoke/$(date -u +%Y%m%dT%H%M%SZ)
sudo docker compose exec -e TEST_PREFIX="$TEST_PREFIX" airflow-scheduler bash -lc \
  'python - <<'PY'
import json, os, tempfile, boto3
from config import get_raw_storage_config

cfg = get_raw_storage_config()
key = os.environ["TEST_PREFIX"] + "/synthetic.json"
body = json.dumps([{"synthetic": True}]).encode()
client = boto3.client("s3", region_name=cfg.region)
client.put_object(Bucket=cfg.bucket, Key=key, Body=body, ContentType="application/json")
with tempfile.NamedTemporaryFile() as downloaded:
    client.download_file(cfg.bucket, key, downloaded.name)
    assert open(downloaded.name, "rb").read() == body
print(f"S3 smoke upload/download succeeded: s3://{cfg.bucket}/{key}")
PY'
```

For a download-only check without deleting the object, use an existing synthetic test key:

```bash
sudo docker compose exec airflow-scheduler python -u src/replay.py s3://YOUR_BUCKET_NAME/YOUR_TEST_PREFIX/synthetic.json
```

Do not run that replay command against production data unless a database load is intended. Remove only the dedicated smoke-test object later through the normal bucket lifecycle/operations process, never with a broad prefix deletion.

Troubleshooting:

- Missing credentials: verify the container can reach the EC2 instance metadata endpoint and that the instance profile is attached. Do not add static keys.
- `AccessDenied`: check the exact bucket and prefix ARN, role trust policy, bucket policy, KMS policy if applicable, and region; the configured prefix is part of the object key.
- EC2 metadata unavailable from Docker: inspect host/container networking and IMDS hop-limit settings. If the current setting blocks containers, the minimum infrastructure change is to raise the instance metadata `HttpPutResponseHopLimit` to `2` while keeping `HttpTokens=required` (IMDSv2). Make this change explicitly in AWS infrastructure; this application does not modify it automatically.
- Upload failure: the local snapshot remains in `data/raw/`, the Airflow task fails, and the watermark is not advanced. Retry after fixing access.

Rollback to local storage by setting `RAW_STORAGE=local` and clearing the S3-only values, then recreate the containers with the commands above. Existing S3 snapshots are not deleted; local ingestion resumes writing under `data/raw/`.

## 9. Start services and install dbt packages

```bash
sudo docker compose up -d
sudo docker compose ps -a
sudo docker compose logs --tail=100 airflow-init
```

Confirm both databases are healthy, the scheduler/webserver are running, and initialization completed successfully. An init container exiting with code 0 is normal. If the init shell command masks errors with `|| true`, inspect logs rather than trusting the exit code alone.

Install dbt packages in the mounted checkout:

```bash
sudo docker compose exec -w /opt/airflow/project airflow-scheduler python -u scripts/run_dbt.py deps
```

Wait for successful installation before building. Python requirements install dbt itself; `dbt deps` installs packages such as `dbt_utils`. An image's files at a bind-mounted path are hidden by the host checkout.

Validate permissions if necessary:

```bash
sudo docker compose exec airflow-scheduler id
sudo docker compose exec -w /opt/airflow/project airflow-scheduler python -c 'import os; from pathlib import Path; print("env readable:", os.access(".env", os.R_OK)); print("project writable:", os.access(".", os.W_OK)); print({p: os.access(p, os.W_OK) for p in ["data", "data/raw", "logs", "target", "dbt_packages"]})'
```

## 10. Test the DAG end to end

1. Open the laptop tunnel from section 1.
2. Log in at http://localhost:18080.
3. Confirm the DAG appears without import errors.
4. Unpause `job_intelligence_pipeline`.
5. Trigger one manual run; avoid overlapping ingestion runs.
6. Confirm `ingestion` succeeds, then `dbt_build` succeeds.
7. Inspect task logs and database records.

Manual diagnostics on EC2 (these execute work, not just inspect it):

```bash
sudo docker compose exec -w /opt/airflow/project airflow-scheduler python -u src/pipeline.py
sudo docker compose exec -w /opt/airflow/project airflow-scheduler python -u scripts/run_dbt.py build
```

Run them separately, with no overlapping matching Airflow task. After fixing dbt, clear only the failed `dbt_build` task in Airflow. Ensure the clear selection does not include upstream ingestion unless intended.

## 11. Preserve useful errors

In `scripts/run_dbt.py`, inspect the returned exception rather than silently converting every failure into exit code 1:

```python
result = dbtRunner().invoke(command)
if result.exception is not None:
    raise result.exception
return 0 if result.success else 1
```

In the DAG, forward subprocess output while preserving failure propagation:

```python
import logging
import os
import subprocess

PROJECT_DIR = "/opt/airflow/project"

def _run_command(command: list[str], task_name: str) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_DIR}/src"
    logging.info("Starting %s", task_name)
    with subprocess.Popen(
        command,
        cwd=PROJECT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            logging.info("%s", line.rstrip())
        return_code = process.wait()
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)
```

Use `sys.executable, "-u", ...` for ingestion and dbt Python commands. Forwarded lines have Airflow INFO level even if their text contains ERROR; the raised exception still makes the task fail. Avoid logging secrets. This wrapper does not itself implement full subprocess timeout/termination management.

## 12. Connect pgAdmin and verify persistence

With the laptop tunnel open, register an EC2 server in pgAdmin:

| Field | Value |
| --- | --- |
| Name | EC2 Job Platform |
| Host | `127.0.0.1` |
| Port | `15433` |
| Maintenance database | EC2 `POSTGRES_DB` |
| Username/password | EC2 credentials |

Port mapping: laptop `15433` → EC2 loopback `5433` → PostgreSQL container `5432`. Check Compose still publishes `127.0.0.1:5433:5432`.

Run in pgAdmin before and after recreation:

```sql
SELECT COUNT(*) FROM public.job_postings;
SELECT COUNT(*) FROM public.pipeline_runs;
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'analytics'
ORDER BY table_name;
```

Or count via EC2 terminal:

```bash
sudo docker compose exec jobs_db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT COUNT(*) FROM public.job_postings; SELECT COUNT(*) FROM public.pipeline_runs;"'
```

When no pipeline is active, note counts, then:

```bash
sudo docker compose down
sudo docker compose up -d
sudo docker compose ps -a
```

Reconnect pgAdmin and compare counts after PostgreSQL is healthy. Counts should remain unchanged unless another ingestion ran. Do not use `down -v`: it removes named volumes. Volumes surviving container recreation does not prove protection against host/disk loss; keep independent backups.

## 13. First load, watermark, and recovery

An empty EC2 database does not automatically reset a file-based watermark. A watermark copied from local development can cause records to be skipped even though they are absent from EC2.

Inspect before changing state:

```bash
cat data/watermark.json
git ls-files data/watermark.json
ls -lh data/raw
```

Compare fetched, filtered/new, and processed counts in successful ingestion logs. A 664-row table proves neither full history nor a bug by itself.

For a confirmed missing-history problem, replay an existing raw snapshot using the project's supported replay script, with no overlapping ingestion:

```bash
sudo docker compose exec -w /opt/airflow/project airflow-scheduler python -u src/replay.py data/raw/ACTUAL_SNAPSHOT_FILENAME.json
sudo docker compose exec -w /opt/airflow/project airflow-scheduler python -u scripts/run_dbt.py build
```

Verify replay's watermark behavior in the current code before using it. Replay can only restore records present in available snapshots. Do not casually delete the watermark or database volume. Runtime watermark state should be environment-specific, not shipped as production state in Git.

## 14. Deploy a code update

On the laptop: edit, commit, and push. On EC2:

```bash
cd ~/job-intelligence-platform
git status --short
git pull --ff-only
```

If Git reports local modifications or divergence, inspect them; do not discard server files blindly.

| Change | Action after pull |
| --- | --- |
| Mounted Python/dbt SQL | Next process reads updated files |
| Mounted DAG | Wait for scheduler parsing; check import errors |
| `packages.yml`/lock file | Run `scripts/run_dbt.py deps` |
| requirements or Dockerfile | `sudo docker compose up -d --build` |
| Compose environment or `.env` | `sudo docker compose up -d` |

A plain container restart does not inject changed environment variables. GitHub pushes do not update EC2 automatically. Mounts expose EC2's checkout, not your laptop checkout or GitHub directly.

Avoid updates while tasks are active. Record the deployed commit:

```bash
git rev-parse HEAD
```

## 15. Daily operations and troubleshooting

```bash
# Service state, including completed init containers
sudo docker compose ps -a

# Recent service logs
sudo docker compose logs --tail=100 airflow-scheduler
sudo docker compose logs --tail=100 airflow-webserver
sudo docker compose logs --tail=100 jobs_db

# DAG import errors
sudo docker compose exec airflow-scheduler airflow dags list-import-errors

# Check disk and memory
 df -h
 free -h

# Restart an existing scheduler (avoid interrupting active tasks)
sudo docker compose restart airflow-scheduler

# Stop/remove containers and networks, retain named volumes
sudo docker compose down
```

| Symptom | Check/action |
| --- | --- |
| `CalledProcessError` | Wrapper error; find earlier child-process output |
| Silent dbt failure | Print/raise `result.exception` |
| Cannot write snapshot | Permissions on `data` and `data/raw` |
| Cannot read `.env` | Group membership and mode 640 |
| Cannot create `logs`/`target` | Prepare writable output folders |
| Cannot remove `dbt_packages` | Parent directory write + execute permission |
| Missing `dbt_utils` | Run `deps` and inspect its output before `build` |
| DB password authentication fails | URL values and existing volume credentials; `.env` does not reset passwords |
| Laptop cannot resolve `jobs_db` | Docker-only hostname; use tunnel address on laptop |
| Tunnel says address already in use | Existing tunnel/local process owns laptop port |
| Browser unavailable | Tunnel open? EC2 running? Webserver up? Correct port? |
| Changes absent on EC2 | Pull correct commit; rebuild only when necessary |

## 16. Survive a host reboot and prove independent scheduling

`up -d` detaches containers from your terminal; it does not alone guarantee restart after a host reboot.

Ensure Docker is enabled:

```bash
sudo systemctl enable --now docker
```

Review Compose and add `restart: unless-stopped` to appropriate long-running services (databases, webserver, scheduler, and app if desired). Keep the init service one-shot. Apply with `sudo docker compose up -d`. Test planned reboot recovery when no tasks are active and verify service/dependency health afterward.

Leave the DAG unpaused. Close laptop SSH sessions and verify the next scheduled ingestion and dbt build succeed. Check the Airflow timezone before interpreting `@daily`; the supplied DAG uses Airflow's configured default timezone. Scheduling is not dependent on an open browser.

## 17. Handoff to another developer

Provide the repository, `.env.example`, this runbook, expected service names/mounts, supported versions, and verification queries. Give each developer their own authorized server access; do not share the private SSH key or commit secrets.

A separate clone/deployment has separate data and state. Recover history explicitly. Document backups for the jobs database, Airflow metadata, and raw snapshots. A successful build is distinct from complete data, persistence, successful scheduled execution, and a tested restore.

## References

- Docker Engine on Ubuntu: https://docs.docker.com/engine/install/ubuntu/
- Airflow Docker user/group behavior: https://airflow.apache.org/docs/docker-stack/entrypoint.html
- Airflow 2.10.5 Docker Compose guide: https://airflow.apache.org/docs/apache-airflow/2.10.5/howto/docker-compose/index.html
- dbt programmatic invocation result handling: https://docs.getdbt.com/reference/programmatic-invocations
- dbt dependency installation: https://docs.getdbt.com/reference/commands/deps
- EC2 SSH troubleshooting: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/TroubleshootingInstancesConnecting.html
- GitHub token management: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
