import pytest
from datetime import datetime

import db
import app as flask_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db(db_path)
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Bath" in resp.data


def test_index_shows_both_tabs(client):
    resp = client.get("/")
    assert b"Full-time" in resp.data
    assert b"Part-time" in resp.data


def test_download_csv_full_time(client, tmp_path):
    db_path = str(tmp_path / "test.db")
    now = datetime.utcnow().isoformat()
    with db.get_conn(db_path) as conn:
        db.upsert_job(conn, {
            "title": "Admin", "department": "HR", "type": "full-time",
            "salary": "£30k", "deadline": "2026-07-01",
            "url": "https://bath.ac.uk/job/1"
        }, now)
    resp = client.get("/download/full-time")
    assert resp.status_code == 200
    assert b"Admin" in resp.data


def test_download_csv_invalid_type(client):
    resp = client.get("/download/invalid")
    assert resp.status_code == 400
