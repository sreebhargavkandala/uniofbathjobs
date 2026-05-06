import io
import csv
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from flask import Flask, render_template, send_file, redirect, url_for, flash

import db

app = Flask(__name__)
app.secret_key = "bathjobs-local"


@app.template_filter("fmt_date")
def fmt_date(value):
    if not value:
        return "—"
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        return value

SCRAPER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper.py")


def _next_scrape():
    now = datetime.now()
    candidates = [
        now.replace(hour=6, minute=0, second=0, microsecond=0),
        now.replace(hour=18, minute=0, second=0, microsecond=0),
    ]
    future = [t for t in candidates if t > now]
    target = future[0] if future else candidates[0] + timedelta(days=1)
    return target.strftime("%H:%M, %d %b")


def _fmt_time(iso_str):
    if not iso_str:
        return "—"
    try:
        # stored as naive UTC — attach UTC tzinfo before converting to local
        dt_local = datetime.fromisoformat(iso_str).replace(tzinfo=timezone.utc).astimezone()
        return dt_local.strftime("%d %b %Y, %H:%M")
    except Exception:
        return iso_str


@app.route("/")
def index():
    cutoff_24h = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    with db.get_conn() as conn:
        full_time = db.get_jobs(conn, "full-time")
        part_time = db.get_jobs(conn, "part-time")
        last_run = db.get_last_run(conn)

    new_full = sum(1 for j in full_time if j["first_seen"] > cutoff_24h)
    new_part = sum(1 for j in part_time if j["first_seen"] > cutoff_24h)

    return render_template(
        "index.html",
        full_time=full_time,
        part_time=part_time,
        last_run=last_run,
        last_run_time=_fmt_time(last_run["run_at"]) if last_run else None,
        next_scrape=_next_scrape(),
        cutoff_24h=cutoff_24h,
        new_full=new_full,
        new_part=new_part,
    )


@app.route("/download/<job_type>")
def download_csv(job_type):
    if job_type not in ("full-time", "part-time"):
        return "Invalid type", 400
    with db.get_conn() as conn:
        jobs = db.get_jobs(conn, job_type)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title", "Department", "Type", "Deadline", "Placed On", "URL", "First Seen"])
    for job in jobs:
        writer.writerow([
            job["title"], job["department"], job["type"],
            job["deadline"], job["placed_on"] or "", job["url"], job["first_seen"]
        ])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{job_type}-jobs.csv",
    )


@app.route("/run-scraper", methods=["POST"])
def run_scraper():
    project_dir = os.path.dirname(SCRAPER_PATH)

    with db.get_conn() as conn:
        before = conn.execute("SELECT count(*) FROM jobs WHERE active=1").fetchone()[0]

    try:
        result = subprocess.run(
            [sys.executable, SCRAPER_PATH],
            capture_output=True, text=True,
            cwd=project_dir, timeout=180,
        )
    except subprocess.TimeoutExpired:
        flash("Scrape timed out after 3 minutes — check your network connection.", "error")
        return redirect(url_for("index"))

    if result.returncode == 0:
        with db.get_conn() as conn:
            after = conn.execute("SELECT count(*) FROM jobs WHERE active=1").fetchone()[0]
            last = db.get_last_run(conn)
        total = last["jobs_found"] if last else 0
        new_count = max(0, after - before)
        if new_count:
            flash(f"Scrape complete — {total} jobs found, {new_count} new added.", "success")
        else:
            flash(f"Scrape complete — {total} jobs found, no new additions.", "success")
    else:
        last_line = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
        flash(f"Scrape failed: {last_line}", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    db.init_db()
    app.run(debug=False, port=5000)
