import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs.db")


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


def upsert_job(conn, job, now):
    existing = conn.execute(
        "SELECT id FROM jobs WHERE url = ?", (job["url"],)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE jobs SET last_seen = ?, active = 1 WHERE url = ?",
            (now, job["url"])
        )
        return False
    conn.execute(
        """INSERT INTO jobs (title, department, type, salary, deadline, url, first_seen, last_seen, active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (
            job.get("title"), job.get("department"), job.get("type"),
            job.get("salary"), job.get("deadline"), job.get("url"), now, now
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
        "SELECT * FROM jobs WHERE type = ? AND active = 1 ORDER BY first_seen DESC",
        (job_type,)
    ).fetchall()


def get_last_run(conn):
    return conn.execute(
        "SELECT * FROM scrape_log ORDER BY run_at DESC LIMIT 1"
    ).fetchone()
