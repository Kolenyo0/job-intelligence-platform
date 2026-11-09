import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import extract  # noqa: E402
import pipeline  # noqa: E402
import replay  # noqa: E402


JOB = {
    "slug": "synthetic-job",
    "company_name": "Synthetic Co",
    "title": "Tester",
    "remote": True,
    "location": "Anywhere",
    "tags": ["test"],
    "created_at": 1_700_000_000,
}


def test_local_snapshot_does_not_need_aws_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_STORAGE", "local")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setattr(extract, "RAW_DATA_PATH", tmp_path)
    client = Mock()
    monkeypatch.setattr(extract.boto3, "client", client)

    snapshot = extract.save_raw_snapshot([JOB])

    assert snapshot.exists()
    assert json.loads(snapshot.read_text(encoding="utf-8")) == [JOB]
    client.assert_not_called()


def test_s3_upload_returns_location_and_removes_local_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_STORAGE", "s3")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_PREFIX", "test-prefix/")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setattr(extract, "RAW_DATA_PATH", tmp_path)
    client = Mock()
    monkeypatch.setattr(extract.boto3, "client", Mock(return_value=client))

    location = extract.save_raw_snapshot([JOB])

    assert location.startswith("s3://test-bucket/test-prefix/jobs_")
    assert list(tmp_path.glob("*.json")) == []
    client.upload_fileobj.assert_called_once()
    assert client.upload_fileobj.call_args.kwargs["ExtraArgs"] == {
        "ContentType": "application/json"
    }


def test_failed_s3_upload_preserves_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_STORAGE", "s3")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setattr(extract, "RAW_DATA_PATH", tmp_path)
    client = Mock()
    client.upload_fileobj.side_effect = RuntimeError("AccessDenied")
    monkeypatch.setattr(extract.boto3, "client", Mock(return_value=client))

    with pytest.raises(RuntimeError, match="AccessDenied"):
        extract.save_raw_snapshot([JOB])

    snapshots = list(tmp_path.glob("*.json"))
    assert len(snapshots) == 1


def test_pipeline_does_not_advance_watermark_when_snapshot_upload_fails(monkeypatch):
    watermark = Mock()
    monkeypatch.setattr(pipeline, "fetch_all_jobs", Mock(return_value=[JOB]))
    monkeypatch.setattr(
        pipeline,
        "save_raw_snapshot",
        Mock(side_effect=RuntimeError("upload failed")),
    )
    monkeypatch.setattr(pipeline, "load_watermark", Mock(return_value=watermark))
    save_watermark = Mock()
    monkeypatch.setattr(pipeline, "save_watermark", save_watermark)
    monkeypatch.setattr(pipeline, "DATABASE_URL", "postgresql://test")

    with pytest.raises(RuntimeError, match="upload failed"):
        pipeline.main()

    save_watermark.assert_not_called()


def test_local_replay_uses_existing_loader(monkeypatch, tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps([JOB]), encoding="utf-8")
    load_jobs = Mock(return_value=1)
    monkeypatch.setattr(replay, "load_jobs", load_jobs)

    assert replay.replay_snapshot(snapshot, database_url="postgresql://test") == 1
    load_jobs.assert_called_once()
    assert load_jobs.call_args.kwargs["run_type"] == "replay"
    assert load_jobs.call_args.kwargs["snapshot_location"] == str(snapshot)


def test_s3_replay_downloads_then_uses_existing_loader(monkeypatch):
    client = Mock()

    def download_file(bucket, key, filename):
        Path(filename).write_text(json.dumps([JOB]), encoding="utf-8")

    client.download_file.side_effect = download_file
    monkeypatch.setattr(extract.boto3, "client", Mock(return_value=client))
    monkeypatch.setenv("RAW_STORAGE", "local")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    load_jobs = Mock(return_value=1)
    monkeypatch.setattr(replay, "load_jobs", load_jobs)

    assert replay.replay_snapshot("s3://test-bucket/test-prefix/snapshot.json", "postgresql://test") == 1
    client.download_file.assert_called_once()
    downloaded_path = Path(client.download_file.call_args.args[2])
    assert not downloaded_path.exists()
    load_jobs.assert_called_once()
    assert load_jobs.call_args.kwargs["snapshot_location"] == "s3://test-bucket/test-prefix/snapshot.json"
