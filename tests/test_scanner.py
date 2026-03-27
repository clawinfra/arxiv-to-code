"""Tests for the arXiv scanner module."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import httpx

from arxiv_to_code.scanner import (
    Paper,
    fetch_recent,
    _build_query,
    _parse_entry,
    DEFAULT_CATEGORIES,
)


class TestBuildQuery:
    def test_default_categories(self):
        q = _build_query(DEFAULT_CATEGORIES)
        assert "cat:cs.AI" in q
        assert "cat:cs.CR" in q
        assert "cat:cs.LG" in q
        assert "cat:cs.SE" in q
        assert " OR " in q

    def test_single_category(self):
        q = _build_query(["cs.CR"])
        assert q == "cat:cs.CR"

    def test_two_categories(self):
        q = _build_query(["cs.AI", "cs.LG"])
        assert q == "cat:cs.AI OR cat:cs.LG"


class TestParseEntry:
    def test_basic_entry(self):
        entry = {
            "id": "http://arxiv.org/abs/2403.12345v1",
            "title": "Test Paper\nTitle",
            "summary": "Test abstract\nwith newlines",
            "published": "2024-03-20T12:00:00Z",
            "authors": [{"name": "Alice"}, {"name": "Bob"}],
            "tags": [{"term": "cs.AI"}, {"term": "cs.LG"}],
            "links": [{"href": "http://arxiv.org/pdf/2403.12345v1", "type": "application/pdf"}],
        }
        paper = _parse_entry(entry)
        assert paper.arxiv_id == "2403.12345"
        assert paper.title == "Test Paper Title"
        assert "newlines" in paper.abstract
        assert paper.authors == ["Alice", "Bob"]
        assert paper.categories == ["cs.AI", "cs.LG"]
        assert paper.pdf_url == "http://arxiv.org/pdf/2403.12345v1"

    def test_entry_without_version(self):
        entry = {
            "id": "http://arxiv.org/abs/2403.12345",
            "title": "No Version Paper",
            "summary": "Abstract",
            "published": "2024-03-20T12:00:00Z",
            "authors": [],
            "tags": [],
            "links": [],
        }
        paper = _parse_entry(entry)
        assert paper.arxiv_id == "2403.12345"

    def test_entry_with_bad_date(self):
        entry = {
            "id": "http://arxiv.org/abs/2403.12345v1",
            "title": "Bad Date Paper",
            "summary": "Abstract",
            "published": "not-a-date",
            "authors": [],
            "tags": [],
            "links": [],
        }
        paper = _parse_entry(entry)
        # Should default to now
        assert (datetime.now(timezone.utc) - paper.submitted).total_seconds() < 10


class TestFetchRecent:
    def test_fetch_parses_xml(self, sample_arxiv_xml):
        mock_resp = MagicMock()
        mock_resp.text = sample_arxiv_xml
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_resp

        papers = fetch_recent(hours=48, client=mock_client)

        mock_client.get.assert_called_once()
        # Should get at least the fresh paper (12h < 48h cutoff)
        assert len(papers) >= 1
        assert all(isinstance(p, Paper) for p in papers)

    def test_fetch_filters_old_papers(self, sample_arxiv_xml):
        mock_resp = MagicMock()
        mock_resp.text = sample_arxiv_xml
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_resp

        # Use 24h window — the 72h-old paper should be excluded
        papers = fetch_recent(hours=24, client=mock_client)
        for p in papers:
            age_h = (datetime.now(timezone.utc) - p.submitted).total_seconds() / 3600
            assert age_h <= 24

    def test_fetch_handles_http_error(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.HTTPError("Connection failed")

        papers = fetch_recent(hours=48, client=mock_client)
        assert papers == []

    def test_fetch_sorted_newest_first(self, sample_arxiv_xml):
        mock_resp = MagicMock()
        mock_resp.text = sample_arxiv_xml
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_resp

        papers = fetch_recent(hours=200, client=mock_client)  # Wide window to get all
        if len(papers) > 1:
            for i in range(len(papers) - 1):
                assert papers[i].submitted >= papers[i + 1].submitted


class TestPaper:
    def test_to_dict_roundtrip(self, fresh_paper):
        d = fresh_paper.to_dict()
        assert d["arxiv_id"] == "2403.12345"
        assert d["title"] == fresh_paper.title
        assert isinstance(d["submitted"], str)

        # Roundtrip
        p2 = Paper.from_dict(d)
        assert p2.arxiv_id == fresh_paper.arxiv_id
        assert p2.title == fresh_paper.title

    def test_from_dict_with_datetime_string(self):
        d = {
            "arxiv_id": "test",
            "title": "Test",
            "abstract": "Abstract",
            "authors": [],
            "categories": [],
            "submitted": "2024-03-20T12:00:00+00:00",
        }
        p = Paper.from_dict(d)
        assert isinstance(p.submitted, datetime)
