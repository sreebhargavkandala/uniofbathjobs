import os
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import scraper


def test_scrape_jobs_returns_list_from_list_result():
    mock_graph = MagicMock()
    mock_graph.run.return_value = [
        {"title": "Lab Tech", "department": "Science", "type": "part-time",
         "salary": "£12/hr", "deadline": "2026-06-01", "url": "https://bath.ac.uk/job/1"}
    ]
    with patch("scraper.SmartScraperGraph", return_value=mock_graph):
        result = scraper.scrape_jobs()
    assert isinstance(result, list)
    assert result[0]["title"] == "Lab Tech"


def test_scrape_jobs_unwraps_dict_result():
    mock_graph = MagicMock()
    mock_graph.run.return_value = {"jobs": [
        {"title": "Admin", "type": "full-time", "url": "https://bath.ac.uk/job/2"}
    ]}
    with patch("scraper.SmartScraperGraph", return_value=mock_graph):
        result = scraper.scrape_jobs()
    assert isinstance(result, list)
    assert result[0]["title"] == "Admin"


def test_scrape_jobs_returns_empty_on_empty_dict():
    mock_graph = MagicMock()
    mock_graph.run.return_value = {}
    with patch("scraper.SmartScraperGraph", return_value=mock_graph):
        result = scraper.scrape_jobs()
    assert result == []
