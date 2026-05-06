# University of Bath Jobs Tracker

Automatically scrapes the [University of Bath jobs board](https://www.bath.ac.uk/jobs/AdvancedSearch.aspx?search=) twice daily and presents results in a web dashboard. Separates full-time and part-time roles, tracks when each job was placed, and marks new listings.

## Live Dashboard

Hosted on Render: **https://uniofbathjobs.onrender.com**

## Features

- Full-time / part-time tabs
- Placed On date column, sorted newest first
- NEW badge on jobs added in the last 24 hours
- CSV export for each job type
- Manual "Run scrape now" trigger in the dashboard
- Automatic scraping via GitHub Actions (6am and 5pm UTC daily)

## Stack

| Layer | Technology |
|---|---|
| Scraper | Python · requests · BeautifulSoup4 |
| Database | SQLite |
| Dashboard | Flask · gunicorn |
| Hosting | Render (free tier) |
| Scheduler | GitHub Actions cron |

## How It Works

1. GitHub Actions fires at `0 6 * * *` and `0 17 * * *` UTC
2. It POSTs to the Render app's `/api/scrape` endpoint (protected by `SCRAPE_TOKEN`)
3. The app runs the scraper: fetches the Bath jobs listing, then fetches each job's detail page in parallel to get the Placed On date
4. New jobs are inserted, existing ones refreshed, jobs missing for 48h are marked inactive
5. The dashboard reflects the updated data immediately

## Local Setup

```bash
git clone https://github.com/sreebhargavkandala/uniofbathjobs.git
cd uniofbathjobs
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Dashboard runs at `http://localhost:5000`.

To run a scrape manually:

```bash
python scraper.py
```

To install the local macOS scheduler (6am and 6pm daily via launchd):

```bash
./setup.sh
```

## Deployment (Render)

1. Connect this repo to [Render](https://render.com) as a new Web Service — it will detect `render.yaml` automatically
2. Set the following environment variables in the Render dashboard:
   - `SCRAPE_TOKEN` — any secret string, used to authenticate the GitHub Actions trigger

## GitHub Actions Setup

Add these secrets to the repository (`Settings → Secrets and variables → Actions`):

| Secret | Value |
|---|---|
| `SCRAPE_TOKEN` | Same value set in Render |
| `RENDER_URL` | `https://uniofbathjobs.onrender.com` |

The workflow can also be triggered manually from the Actions tab.

## Running Tests

```bash
source venv/bin/activate
pytest
```
