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
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _normalize_url(url):
    if not url:
        return url
    return url.strip().lower()


def upsert_job(conn, job, now):
    url = _normalize_url(job.get("url"))
    cur = conn.cursor()
    # One statement, so concurrent scrapes can't both pass a SELECT then collide
    # on the url index. Refreshes mutable fields so extended deadlines don't stick.
    cur.execute(
        """INSERT INTO jobs
               (title, department, type, salary, deadline, placed_on, url, first_seen, last_seen, active)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
           ON CONFLICT (url) DO UPDATE SET
               title      = EXCLUDED.title,
               department = EXCLUDED.department,
               type       = EXCLUDED.type,
               deadline   = EXCLUDED.deadline,
               placed_on  = COALESCE(EXCLUDED.placed_on, jobs.placed_on),
               last_seen  = EXCLUDED.last_seen,
               active     = TRUE
           RETURNING (xmax = 0) AS inserted""",  # xmax = 0 only on a real insert
        (
            job.get("title"), job.get("department"), job.get("type"),
            job.get("salary"), job.get("deadline"), job.get("placed_on"),
            url, now, now,
        ),
    )
    return cur.fetchone()["inserted"]


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