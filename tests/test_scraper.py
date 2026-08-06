import pytest
from unittest.mock import patch, MagicMock

import scraper

FAKE_HTML = """
<html><body>
<div class="vacancyCategoryDiv">
  <div class="vacancyCategoryHeader">Engineering</div>
  <div class="vacancyCategoryContainer">
    <div class="vacancyCategoryItem">
      <div class="vacancyCategoryItemTitle">
        <a href="Vacancy.aspx?ref=ENG001">Lab Technician</a>
      </div>
      <div class="vacancyCategoryItemSub"><b>Contract Type:</b> Part Time, Fixed Term</div>
      <div class="vacancyCategoryItemSub"><b>Closing Date:</b> 30/06/2026</div>
    </div>
  </div>
  <div class="vacancyCategoryHeader">Science</div>
  <div class="vacancyCategoryContainer">
    <div class="vacancyCategoryItem">
      <div class="vacancyCategoryItemTitle">
        <a href="Vacancy.aspx?ref=SCI002">Research Fellow</a>
      </div>
      <div class="vacancyCategoryItemSub"><b>Contract Type:</b> Full Time, Permanent</div>
      <div class="vacancyCategoryItemSub"><b>Closing Date:</b> 01/07/2026</div>
    </div>
  </div>
</div>
</body></html>
"""


def _mock_response(html=FAKE_HTML, status=200):
    mock = MagicMock()
    mock.status_code = status
    mock.text = html
    mock.raise_for_status = MagicMock()
    return mock


def test_scrape_jobs_returns_two_jobs():
    with patch("scraper.requests.get", return_value=_mock_response()):
        jobs = scraper.scrape_jobs()
    assert len(jobs) == 2


def test_scrape_jobs_part_time_detection():
    with patch("scraper.requests.get", return_value=_mock_response()):
        jobs = scraper.scrape_jobs()
    pt = [j for j in jobs if j["type"] == "part-time"]
    ft = [j for j in jobs if j["type"] == "full-time"]
    assert len(pt) == 1 and pt[0]["title"] == "Lab Technician"
    assert len(ft) == 1 and ft[0]["title"] == "Research Fellow"


def test_scrape_jobs_url_is_lowercase():
    with patch("scraper.requests.get", return_value=_mock_response()):
        jobs = scraper.scrape_jobs()
    for job in jobs:
        assert job["url"] == job["url"].lower()


def test_scrape_jobs_department_populated():
    with patch("scraper.requests.get", return_value=_mock_response()):
        jobs = scraper.scrape_jobs()
    assert jobs[0]["department"] == "Engineering"
    assert jobs[1]["department"] == "Science"


def test_scrape_jobs_deadline_populated():
    with patch("scraper.requests.get", return_value=_mock_response()):
        jobs = scraper.scrape_jobs()
    assert jobs[0]["deadline"] == "30/06/2026"


def test_scrape_jobs_returns_empty_on_blank_page():
    with patch("scraper.requests.get", return_value=_mock_response("<html><body></body></html>")):
        jobs = scraper.scrape_jobs()
    assert jobs == []


def test_run_fails_loudly_when_zero_jobs_scraped():
    """A layout change must log an error and exit non-zero, never 'success'."""
    logged = {}

    def fake_log_run(conn, run_at, jobs_found, status, error_msg=None):
        logged["status"] = status
        logged["error_msg"] = error_msg

    with patch("scraper.scrape_jobs", return_value=[]), \
         patch.object(scraper.db, "init_db", lambda: None), \
         patch.object(scraper.db, "log_run", fake_log_run), \
         patch.object(scraper.db, "get_conn", MagicMock()), \
         pytest.raises(SystemExit) as exc:
        scraper.run()

    assert exc.value.code == 1
    assert logged["status"] == "error"
    assert "0 jobs" in logged["error_msg"]
