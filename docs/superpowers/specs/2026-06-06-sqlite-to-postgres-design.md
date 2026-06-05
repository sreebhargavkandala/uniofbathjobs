---
title: SQLite → PostgreSQL Migration
date: 2026-06-06
status: approved
---

## Problem

Render free tier uses an ephemeral filesystem. The `jobs.db` SQLite file is wiped every time the server restarts (after 15 min inactivity). Automated scrapes store data that is then lost before users visit the dashboard.

## Solution

Replace SQLite with a persistent Neon.tech PostgreSQL database. Only `db.py` changes meaningfully — the rest of the app is untouched.

## Provider

**Neon.tech** — free tier, serverless Postgres, single `DATABASE_URL` connection string, no expiry. User creates a project at neon.tech, copies the connection string, and sets it as an environment variable in Render and GitHub Actions.

---

## Architecture

No structural change. The same three-layer architecture (scraper → db → app) is preserved. `db.py` is the only layer that knows about the database driver.

```
scraper.py  ──┐
               ├──→  db.py  ──→  Neon PostgreSQL (via DATABASE_URL)
app.py      ──┘
```

`get_conn()` remains a context manager with the same interface. Callers are unchanged.

---

## File-by-File Changes

### `db.py` (rewrite)

- Import `psycopg2` instead of `sqlite3`
- `get_conn()`: connect via `psycopg2.connect(os.environ["DATABASE_URL"])`, commit on success, close in finally
- Placeholders: `?` → `%s` throughout
- Schema: `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`
- `init_db()`: replace `executescript()` with separate `execute()` calls; replace the `ALTER TABLE ADD COLUMN` try/except with a Postgres-compatible `DO $$ BEGIN ALTER TABLE ... EXCEPTION WHEN duplicate_column THEN NULL; END $$;` block
- All query logic (upsert, mark_stale, get_jobs, log_run, get_last_run) is functionally identical — only placeholder syntax changes

### `requirements.txt`

Add `psycopg2-binary`. No removals (sqlite3 is stdlib, just unused).

### `render.yaml`

Add `DATABASE_URL` env var entry with `sync: false` so the value is entered manually in the Render dashboard (never committed to git).

### `tests/test_db.py` (rewrite)

Replace in-memory SQLite fixture with mocks. Each test patches `db.get_conn()` with a `MagicMock` context manager that returns a mock connection/cursor. Tests verify that the correct SQL and parameters are passed — not that Postgres executes them correctly.

### `tests/test_app.py`

Patch `db.get_conn()` and `db.get_jobs()` / `db.get_last_run()` at the Flask route level so tests don't require a live database. Existing test logic (HTTP 200, HTML content, CSV export, 400 on bad type) is preserved.

### `tests/test_scraper.py`

No changes. These tests cover HTML parsing only, no DB involvement.

### `Dockerfile`, `app.py`, `scraper.py`, `templates/`, `static/`

No changes.

---

## Connection Handling

`get_conn()` opens a new connection per call and closes it in the `finally` block — same pattern as the SQLite version. For the current load (a handful of dashboard requests and twice-daily scrapes), this is sufficient. Neon's serverless architecture handles connection overhead well at this scale.

If connection volume grows, the pooled Neon connection string (PgBouncer endpoint) can be substituted without any code change.

---

## Schema

Identical columns to the current SQLite schema. Only DDL syntax changes:

```sql
-- jobs
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
);

-- scrape_log
CREATE TABLE IF NOT EXISTS scrape_log (
    id          SERIAL PRIMARY KEY,
    run_at      TIMESTAMP NOT NULL,
    jobs_found  INTEGER,
    status      TEXT,
    error_msg   TEXT
);
```

---

## Testing Strategy

- `test_db.py`: mock `db.get_conn()` — verify correct SQL strings and `%s` parameter tuples are passed to the mock cursor
- `test_app.py`: mock `db.get_conn()`, `db.get_jobs()`, `db.get_last_run()` — verify HTTP responses and rendered content
- `test_scraper.py`: unchanged — no DB interaction

Tests run fully offline with no external credentials required.

---

## Deployment Steps (manual, one-time)

1. Create a Neon project at neon.tech → copy the connection string
2. In Render dashboard: set `DATABASE_URL` environment variable
3. In GitHub repository settings: add `DATABASE_URL` as an Actions secret (for the scrape workflow if it ever needs direct DB access — currently it doesn't, so optional)
4. Deploy — `init_db()` runs on startup and creates tables automatically

---

## What Does Not Change

- All Flask routes and their behaviour
- The scraper's fetching and parsing logic
- The dashboard template and CSS
- The GitHub Actions scrape schedule and token auth
- The CSV export format
- The stale job cleanup logic (48h cutoff)
- The NEW badge logic (24h cutoff)
