import pytest
from datetime import datetime, timedelta
import db


@pytest.fixture
def tmp_db(tmp_path):
    path = str(tmp_path / "test.db")
    db.init_db(path)
    return path


def test_init_creates_tables(tmp_db):
    with db.get_conn(tmp_db) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    names = {t["name"] for t in tables}
    assert "jobs" in names
    assert "scrape_log" in names


def test_upsert_new_job_returns_true(tmp_db):
    job = {
        "title": "Lab Assistant", "department": "Chemistry",
        "type": "part-time", "salary": "£12/hr",
        "deadline": "2026-06-01", "url": "https://bath.ac.uk/job/1"
    }
    now = datetime.utcnow().isoformat()
    with db.get_conn(tmp_db) as conn:
        is_new = db.upsert_job(conn, job, now)
    assert is_new is True


def test_upsert_existing_job_returns_false(tmp_db):
    job = {
        "title": "Lab Assistant", "department": "Chemistry",
        "type": "part-time", "salary": "£12/hr",
        "deadline": "2026-06-01", "url": "https://bath.ac.uk/job/1"
    }
    now = datetime.utcnow().isoformat()
    with db.get_conn(tmp_db) as conn:
        db.upsert_job(conn, job, now)
        is_new = db.upsert_job(conn, job, now)
    assert is_new is False


def test_get_jobs_filters_by_type(tmp_db):
    now = datetime.utcnow().isoformat()
    with db.get_conn(tmp_db) as conn:
        db.upsert_job(conn, {"title": "A", "type": "full-time", "url": "https://bath.ac.uk/1"}, now)
        db.upsert_job(conn, {"title": "B", "type": "part-time", "url": "https://bath.ac.uk/2"}, now)
        full = db.get_jobs(conn, "full-time")
        part = db.get_jobs(conn, "part-time")
    assert len(full) == 1 and full[0]["title"] == "A"
    assert len(part) == 1 and part[0]["title"] == "B"


def test_mark_stale_deactivates_old_jobs(tmp_db):
    old_ts = (datetime.utcnow() - timedelta(hours=50)).isoformat()
    cutoff = (datetime.utcnow() - timedelta(hours=48)).isoformat()
    with db.get_conn(tmp_db) as conn:
        db.upsert_job(conn, {"title": "Old", "type": "part-time", "url": "https://bath.ac.uk/old"}, old_ts)
        conn.execute("UPDATE jobs SET last_seen = ? WHERE url = ?", (old_ts, "https://bath.ac.uk/old"))
        db.mark_stale(conn, cutoff)
        jobs = db.get_jobs(conn, "part-time")
    assert len(jobs) == 0


def test_log_run_and_get_last_run(tmp_db):
    now = datetime.utcnow().isoformat()
    with db.get_conn(tmp_db) as conn:
        db.log_run(conn, now, 5, "success")
        last = db.get_last_run(conn)
    assert last["jobs_found"] == 5
    assert last["status"] == "success"
