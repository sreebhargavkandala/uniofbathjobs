import pytest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager
import db

# Patch db.init_db before importing app so the module-level call doesn't hit Postgres
with patch.object(db, "init_db", lambda: None):
    import app as flask_app


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


def _patch_db(monkeypatch, full_time=None, part_time=None, last_run=None):
    """Patch db layer so Flask routes never touch a real database."""
    full_time = full_time or []
    part_time = part_time or []

    @contextmanager
    def mock_get_conn():
        yield MagicMock()

    monkeypatch.setattr(db, "get_conn", mock_get_conn)
    monkeypatch.setattr(db, "get_jobs", lambda conn, t: full_time if t == "full-time" else part_time)
    monkeypatch.setattr(db, "get_last_run", lambda conn: last_run)


def test_index_returns_200(client, monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Bath" in resp.data


def test_index_shows_both_tabs(client, monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/")
    assert b"Full-time" in resp.data
    assert b"Part-time" in resp.data


def test_download_csv_full_time(client, monkeypatch):
    job = {
        "title": "Admin", "department": "HR", "type": "full-time",
        "salary": "£30k", "deadline": "2026-07-01", "placed_on": None,
        "url": "https://bath.ac.uk/job/1", "first_seen": "2026-06-01T10:00:00",
    }
    _patch_db(monkeypatch, full_time=[job])
    resp = client.get("/download/full-time")
    assert resp.status_code == 200
    assert b"Admin" in resp.data


def test_download_csv_invalid_type(client):
    resp = client.get("/download/invalid")
    assert resp.status_code == 400