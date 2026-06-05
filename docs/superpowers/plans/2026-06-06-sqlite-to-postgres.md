# SQLite → PostgreSQL Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ephemeral SQLite `jobs.db` with a persistent Neon.tech PostgreSQL database so scraped jobs survive Render server restarts.

**Architecture:** `db.py` is the only file that knows about the database driver. It is rewritten to use `psycopg2-binary` with a `DATABASE_URL` environment variable. All other files (`scraper.py`, templates, Dockerfile) are unchanged except for two raw SQL calls in `app.py` that are replaced with a new `db.count_active_jobs()` helper. Tests are rewritten to mock `db.get_conn()` so they run offline with no credentials.

**Tech Stack:** Python 3.11, psycopg2-binary, Neon.tech PostgreSQL, pytest + unittest.mock

---

## File Map

| File | Action | Reason |
|------|--------|--------|
| `requirements.txt` | Modify | Add `psycopg2-binary` |
| `db.py` | Rewrite | Replace sqlite3 with psycopg2; `%s` placeholders; `SERIAL` PK; `DATABASE_URL` |
| `app.py` | Modify (2 lines) | Replace `conn.execute("SELECT count(*)")` with `db.count_active_jobs(conn)` |
| `tests/test_db.py` | Rewrite | Mock `conn.cursor()` instead of using in-memory SQLite |
| `tests/test_app.py` | Rewrite | Mock `db.get_conn()`, `db.get_jobs()`, `db.get_last_run()` |
| `render.yaml` | Modify | Add `DATABASE_URL` env var |
| `tests/test_scraper.py` | No change | HTML parsing only, no DB |
| `Dockerfile` | No change | psycopg2-binary has no system build deps |
| `scraper.py` | No change | Calls `db.init_db()` and `db.get_conn()` — interface unchanged |

---

## Task 1: Add psycopg2-binary to requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add psycopg2-binary**

Edit `requirements.txt` to read:

```
flask
requests
beautifulsoup4
gunicorn
tzdata
pytest
psycopg2-binary
```

- [ ] **Step 2: Install it locally**

```bash
pip install psycopg2-binary
```

Expected: installs without errors.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add psycopg2-binary dependency"
```

---

## Task 2: Write failing tests for the new db.py interface

**Files:**
- Rewrite: `tests/test_db.py`

The new `db.py` will use `conn.cursor().execute()` instead of `conn.execute()`. Writing tests that mock at the cursor level ensures they fail with the current sqlite3-based `db.py` (which calls `conn.execute()` directly) and pass only after the rewrite.

- [ ] **Step 1: Replace tests/test_db.py entirely**

```python
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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_db.py -v
```

Expected: several FAILED (current `db.py` calls `conn.execute()` directly, not `conn.cursor().execute()`).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_db.py
git commit -m "test: replace test_db with mock-based psycopg2 interface tests"
```

---

## Task 3: Rewrite db.py with psycopg2

**Files:**
- Rewrite: `db.py`

- [ ] **Step 1: Replace db.py entirely**

```python
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

_DATABASE_URL = os.environ.get("DATABASE_URL", "")


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          SERIAL PRIMARY KEY,
                title       TEXT NOT NULL,
                department  TEXT,
                type        TEXT NOT NULL,
                salary      TEXT,
                deadline    TEXT,
                placed_on   TEXT,
                url         TEXT UNIQUE NOT NULL,
                first_seen  TIMESTAMP NOT NULL,
                last_seen   TIMESTAMP NOT NULL,
                active      BOOLEAN NOT NULL DEFAULT TRUE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scrape_log (
                id          SERIAL PRIMARY KEY,
                run_at      TIMESTAMP NOT NULL,
                jobs_found  INTEGER,
                status      TEXT,
                error_msg   TEXT
            )
        """)
        cur.execute("""
            DO $$
            BEGIN
                ALTER TABLE jobs ADD COLUMN placed_on TEXT;
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
        """)


@contextmanager
def get_conn():
    conn = psycopg2.connect(
        _DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _normalize_url(url):
    if not url:
        return url
    return url.strip().lower()


def upsert_job(conn, job, now):
    url = _normalize_url(job.get("url"))
    cur = conn.cursor()
    cur.execute("SELECT id, placed_on FROM jobs WHERE url = %s", (url,))
    existing = cur.fetchone()
    if existing:
        placed_on = job.get("placed_on") or (existing["placed_on"] if existing else None)
        cur.execute(
            "UPDATE jobs SET last_seen = %s, active = TRUE, placed_on = %s WHERE url = %s",
            (now, placed_on, url),
        )
        return False
    cur.execute(
        """INSERT INTO jobs
               (title, department, type, salary, deadline, placed_on, url, first_seen, last_seen, active)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)""",
        (
            job.get("title"), job.get("department"), job.get("type"),
            job.get("salary"), job.get("deadline"), job.get("placed_on"),
            url, now, now,
        ),
    )
    return True


def mark_stale(conn, cutoff):
    cur = conn.cursor()
    cur.execute("UPDATE jobs SET active = FALSE WHERE last_seen < %s", (cutoff,))


def log_run(conn, run_at, jobs_found, status, error_msg=None):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO scrape_log (run_at, jobs_found, status, error_msg) VALUES (%s, %s, %s, %s)",
        (run_at, jobs_found, status, error_msg),
    )


def get_jobs(conn, job_type):
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM jobs WHERE type = %s AND active = TRUE
           ORDER BY placed_on IS NULL, placed_on DESC, first_seen DESC""",
        (job_type,),
    )
    return cur.fetchall()


def get_last_run(conn):
    cur = conn.cursor()
    cur.execute("SELECT * FROM scrape_log ORDER BY run_at DESC LIMIT 1")
    return cur.fetchone()


def count_active_jobs(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM jobs WHERE active = TRUE")
    return cur.fetchone()["cnt"]
```

- [ ] **Step 2: Run the db tests — expect all to pass**

```bash
pytest tests/test_db.py -v
```

Expected: 7 passed.

- [ ] **Step 3: Commit**

```bash
git add db.py
git commit -m "feat: rewrite db.py to use psycopg2 with DATABASE_URL"
```

---

## Task 4: Update app.py to use count_active_jobs

**Files:**
- Modify: `app.py:105-106` and `app.py:119-120`

psycopg2 connections have no `.execute()` method — only cursors do. The two raw `conn.execute("SELECT count(*)")` calls in `run_scraper` must be replaced.

- [ ] **Step 1: Update the before-count (app.py line 105-106)**

Find:
```python
    with db.get_conn() as conn:
        before = conn.execute("SELECT count(*) FROM jobs WHERE active=1").fetchone()[0]
```

Replace with:
```python
    with db.get_conn() as conn:
        before = db.count_active_jobs(conn)
```

- [ ] **Step 2: Update the after-count (app.py line 119-120)**

Find:
```python
        with db.get_conn() as conn:
            after = conn.execute("SELECT count(*) FROM jobs WHERE active=1").fetchone()[0]
            last = db.get_last_run(conn)
```

Replace with:
```python
        with db.get_conn() as conn:
            after = db.count_active_jobs(conn)
            last = db.get_last_run(conn)
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "fix: replace raw conn.execute() calls with db.count_active_jobs()"
```

---

## Task 5: Rewrite test_app.py with mocks

**Files:**
- Rewrite: `tests/test_app.py`

- [ ] **Step 1: Replace tests/test_app.py entirely**

```python
import pytest
from unittest.mock import MagicMock
from contextlib import contextmanager
import app as flask_app
import db


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
```

- [ ] **Step 2: Run the app tests — expect all to pass**

```bash
pytest tests/test_app.py -v
```

Expected: 4 passed.

- [ ] **Step 3: Run the full test suite**

```bash
pytest -v
```

Expected: 11 passed (7 test_db + 4 test_app + existing test_scraper).

- [ ] **Step 4: Commit**

```bash
git add tests/test_app.py
git commit -m "test: replace test_app with mock-based tests, remove sqlite fixture"
```

---

## Task 6: Update render.yaml

**Files:**
- Modify: `render.yaml`

- [ ] **Step 1: Add DATABASE_URL env var**

Replace the entire file with:

```yaml
services:
  - type: web
    name: uniofbathjobs
    runtime: docker
    plan: free
    envVars:
      - key: SCRAPE_TOKEN
        sync: false
      - key: DATABASE_URL
        sync: false
```

`sync: false` means the value is entered manually in the Render dashboard and is never committed to git.

- [ ] **Step 2: Commit**

```bash
git add render.yaml
git commit -m "chore: add DATABASE_URL env var to render.yaml"
```

---

## Task 7: One-time deployment setup (manual steps)

These are not code changes — perform once after pushing to Render.

- [ ] **Step 1: Create a Neon project**
  1. Sign in at https://neon.tech
  2. Create a new project — choose region `eu-west-2` (London) or `eu-central-1` (Frankfurt)
  3. Copy the **connection string**: `postgresql://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require`

- [ ] **Step 2: Set DATABASE_URL in Render**
  1. Render dashboard → `uniofbathjobs` web service → **Environment**
  2. Add `DATABASE_URL` = (paste Neon connection string)
  3. Render redeploys automatically — `init_db()` runs on startup and creates tables

- [ ] **Step 3: Verify tables in Neon console**

  In Neon SQL Editor:
  ```sql
  SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
  ```
  Expected: `jobs` and `scrape_log` listed.

- [ ] **Step 4: Trigger a manual scrape**

  Visit the live dashboard, click "Run scrape now", confirm jobs appear. Wait 20+ minutes (Render spin-down), revisit — jobs should still be there.