import sqlite3
import os
from contextlib import contextmanager

_data_dir = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_data_dir, "jobs.db")


def init_db(db_path=None):
    if db_path is None:
        db_path = DB_PATH
    with get_conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                department  TEXT,
                type        TEXT NOT NULL,
                salary      TEXT,
                deadline    TEXT,
                placed_on   TEXT,
                url         TEXT UNIQUE NOT NULL,
                first_seen  DATETIME NOT NULL,
                last_seen   DATETIME NOT NULL,
                active      BOOLEAN NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS scrape_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at      DATETIME NOT NULL,
                jobs_found  INTEGER,
                status      TEXT,
                error_msg   TEXT
            );
        """)
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN placed_on TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists


@contextmanager
def get_conn(db_path=None):
    if db_path is None:
        db_path = DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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
    existing = conn.execute(
        "SELECT id, placed_on FROM jobs WHERE url = ?", (url,)
    ).fetchone()
    if existing:
        placed_on = job.get("placed_on") or (existing["placed_on"] if existing else None)
        conn.execute(
            "UPDATE jobs SET last_seen = ?, active = 1, placed_on = ? WHERE url = ?",
            (now, placed_on, url)
        )
        return False
    conn.execute(
        """INSERT INTO jobs (title, department, type, salary, deadline, placed_on, url, first_seen, last_seen, active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (
            job.get("title"), job.get("department"), job.get("type"),
            job.get("salary"), job.get("deadline"), job.get("placed_on"), url, now, now
        )
    )
    return True


def mark_stale(conn, cutoff):
    conn.execute("UPDATE jobs SET active = 0 WHERE last_seen < ?", (cutoff,))


def log_run(conn, run_at, jobs_found, status, error_msg=None):
    conn.execute(
        "INSERT INTO scrape_log (run_at, jobs_found, status, error_msg) VALUES (?, ?, ?, ?)",
        (run_at, jobs_found, status, error_msg)
    )


def get_jobs(conn, job_type):
    return conn.execute(
        """SELECT * FROM jobs WHERE type = ? AND active = 1
           ORDER BY placed_on IS NULL, placed_on DESC, first_seen DESC""",
        (job_type,)
    ).fetchall()


def get_last_run(conn):
    return conn.execute(
        "SELECT * FROM scrape_log ORDER BY run_at DESC LIMIT 1"
    ).fetchone()
