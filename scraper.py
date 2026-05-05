import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv
from scrapegraphai.graphs import SmartScraperGraph

import db

load_dotenv()

BATH_JOBS_URL = "https://www.bath.ac.uk/jobs/AdvancedSearch.aspx?search="
STALE_HOURS = 48
PROMPT = (
    "Extract all job listings from this page. For each job return a list of objects with these fields: "
    "title (string), department (string), type (string — must be exactly 'full-time' or 'part-time'), "
    "salary (string or null), deadline (string or null), url (string — full URL to the job posting)."
)


def build_graph_config():
    return {
        "llm": {
            "api_key": os.environ["OPENAI_API_KEY"],
            "model": "openai/gpt-4o-mini",
        },
        "verbose": False,
    }


def scrape_jobs():
    graph = SmartScraperGraph(
        prompt=PROMPT,
        source=BATH_JOBS_URL,
        config=build_graph_config(),
    )
    result = graph.run()
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for v in result.values():
            if isinstance(v, list):
                return v
    return []


def run():
    db.init_db()
    now = datetime.utcnow().isoformat()
    cutoff = (datetime.utcnow() - timedelta(hours=STALE_HOURS)).isoformat()

    try:
        jobs = scrape_jobs()
        with db.get_conn() as conn:
            new_count = sum(db.upsert_job(conn, job, now) for job in jobs)
            db.mark_stale(conn, cutoff)
            db.log_run(conn, now, len(jobs), "success")
        print(f"[{now}] Scraped {len(jobs)} jobs ({new_count} new)")
    except Exception as e:
        with db.get_conn() as conn:
            db.log_run(conn, now, 0, "error", str(e))
        print(f"[{now}] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
