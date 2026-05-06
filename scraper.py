import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

import db

BATH_JOBS_URL = "https://www.bath.ac.uk/jobs/AdvancedSearch.aspx?search="
BASE_URL = "https://www.bath.ac.uk/jobs/"
STALE_HOURS = 48


def scrape_jobs():
    resp = requests.get(
        BATH_JOBS_URL,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    jobs = []
    for cat_div in soup.select("div.vacancyCategoryDiv"):
        dept = ""
        for child in cat_div.children:
            if not hasattr(child, "get"):
                continue
            classes = child.get("class", [])
            if "vacancyCategoryHeader" in classes:
                dept = child.get_text(strip=True)
            elif "vacancyCategoryContainer" in classes:
                for item in child.select("div.vacancyCategoryItem"):
                    title_tag = item.find(class_="vacancyCategoryItemTitle")
                    title = title_tag.get_text(strip=True) if title_tag else ""

                    link = item.find("a", href=lambda h: h and "vacancy" in h.lower())
                    href = link["href"].split("/")[-1] if link else ""
                    url = (BASE_URL + href).lower() if href else ""

                    contract = deadline = ""
                    for sub in item.select("div.vacancyCategoryItemSub"):
                        text = sub.get_text(separator=" ", strip=True)
                        if "Contract Type" in text:
                            contract = text.split(":", 1)[-1].strip()
                        elif "Closing Date" in text:
                            deadline = text.split(":", 1)[-1].strip()

                    job_type = "part-time" if "part" in contract.lower() else "full-time"

                    jobs.append({
                        "title": title,
                        "department": dept,
                        "type": job_type,
                        "deadline": deadline,
                        "url": url,
                    })
    return jobs


def _parse_placed_on(text):
    if not text:
        return None
    parts = text.strip().split()
    # "Tuesday 28 April 2026" → strip day name; "28 April 2026" → use as-is
    date_str = " ".join(parts[1:]) if len(parts) == 4 else text.strip()
    try:
        return datetime.strptime(date_str, "%d %B %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def fetch_placed_on(url):
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for span in soup.find_all("span", class_="vacancyAdvertWidgetTitle"):
            if "Placed on" in span.get_text():
                raw = span.parent.get_text(strip=True).replace("Placed on", "").strip()
                return _parse_placed_on(raw)
    except Exception:
        pass
    return None


def _notify(new_jobs):
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic or not new_jobs:
        return
    titles = [j.get("title", "Unknown") for j in new_jobs[:5]]
    body = "\n".join(titles)
    if len(new_jobs) > 5:
        body += f"\n…and {len(new_jobs) - 5} more"
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={
                "Title": f"{len(new_jobs)} new Bath job{'s' if len(new_jobs) > 1 else ''} posted",
                "Priority": "default",
                "Tags": "mortar_board",
            },
            timeout=10,
        )
    except Exception:
        pass


def run():
    db.init_db()
    now = datetime.utcnow().isoformat()
    cutoff = (datetime.utcnow() - timedelta(hours=STALE_HOURS)).isoformat()

    try:
        jobs = scrape_jobs()
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_idx = {executor.submit(fetch_placed_on, job["url"]): i
                             for i, job in enumerate(jobs)}
            for future, idx in future_to_idx.items():
                jobs[idx]["placed_on"] = future.result()
        with db.get_conn() as conn:
            results = [(job, db.upsert_job(conn, job, now)) for job in jobs]
            new_jobs = [job for job, is_new in results if is_new]
            db.mark_stale(conn, cutoff)
            db.log_run(conn, now, len(jobs), "success")
        _notify(new_jobs)
        print(f"[{now}] Scraped {len(jobs)} jobs ({len(new_jobs)} new)")
    except Exception as e:
        with db.get_conn() as conn:
            db.log_run(conn, now, 0, "error", str(e))
        print(f"[{now}] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
