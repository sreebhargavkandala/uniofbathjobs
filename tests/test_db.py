import pytest
from unittest.mock import MagicMock
import db


def _mock_conn(fetchone_return=None, fetchall_return=None):
    """Return (conn, cursor) mocks. cursor.fetchone/fetchall return given values."""
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_return
    cursor.fetchall.return_value = fetchall_return or []
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def test_upsert_new_job_returns_true():
    conn, cursor = _mock_conn(fetchone_return=None)
    job = {
        "title": "Lab Assistant", "department": "Chemistry",
        "type": "part-time", "salary": "£12/hr",
        "deadline": "2026-06-01", "url": "https://bath.ac.uk/job/1",
    }
    result = db.upsert_job(conn, job, "2026-06-01T10:00:00")
    assert result is True


def test_upsert_existing_job_returns_false():
    conn, cursor = _mock_conn(fetchone_return={"id": 1, "placed_on": None})
    job = {
        "title": "Lab Assistant", "department": "Chemistry",
        "type": "part-time", "url": "https://bath.ac.uk/job/1",
    }
    result = db.upsert_job(conn, job, "2026-06-01T10:00:00")
    assert result is False


def test_get_jobs_queries_correct_type():
    conn, cursor = _mock_conn(fetchall_return=[])
    db.get_jobs(conn, "full-time")
    sql, params = cursor.execute.call_args[0]
    assert "%s" in sql
    assert params == ("full-time",)


def test_mark_stale_uses_cutoff():
    conn, cursor = _mock_conn()
    cutoff = "2026-06-01T00:00:00"
    db.mark_stale(conn, cutoff)
    sql, params = cursor.execute.call_args[0]
    assert "active" in sql.lower()
    assert params == (cutoff,)


def test_log_run_inserts_record():
    conn, cursor = _mock_conn()
    db.log_run(conn, "2026-06-01T10:00:00", 42, "success")
    sql, params = cursor.execute.call_args[0]
    assert "scrape_log" in sql.lower()
    assert 42 in params
    assert "success" in params


def test_get_last_run_returns_row():
    expected = {"id": 1, "jobs_found": 5, "status": "success",
                "run_at": "2026-06-01T10:00:00", "error_msg": None}
    conn, cursor = _mock_conn(fetchone_return=expected)
    result = db.get_last_run(conn)
    assert result["jobs_found"] == 5
    assert result["status"] == "success"


def test_count_active_jobs_returns_integer():
    conn, cursor = _mock_conn(fetchone_return={"cnt": 7})
    result = db.count_active_jobs(conn)
    assert result == 7