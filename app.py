import io
import csv
import subprocess
import sys
from datetime import datetime, timedelta

from flask import Flask, render_template, send_file, redirect, url_for

import db

app = Flask(__name__)


def _next_scrape():
    now = datetime.now()
    candidates = [
        now.replace(hour=6, minute=0, second=0, microsecond=0),
        now.replace(hour=18, minute=0, second=0, microsecond=0),
    ]
    future = [t for t in candidates if t > now]
    target = future[0] if future else candidates[0] + timedelta(days=1)
    return target.strftime("%H:%M, %d %b")


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
    writer.writerow(["Title", "Department", "Type", "Salary", "Deadline", "URL", "First Seen"])
    for job in jobs:
        writer.writerow([
            job["title"], job["department"], job["type"],
            job["salary"], job["deadline"], job["url"], job["first_seen"]
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
    subprocess.Popen([sys.executable, "scraper.py"])
    return redirect(url_for("index"))


if __name__ == "__main__":
    db.init_db()
    app.run(debug=False, port=5000)
