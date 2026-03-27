"""Tests for the implementation checker module."""

import pytest
from unittest.mock import MagicMock

import httpx

from arxiv_to_code.impl_checker import (
    check_github,
    check_paperswithcode,
    has_implementation,
    _extract_keywords,
    _titles_match,
    ImplResult,
)


class TestExtractKeywords:
    def test_removes_stopwords(self):
        kw = _extract_keywords("A Novel Framework for the Analysis of Deep Learning")
        assert "a" not in kw.split()
        assert "for" not in kw.split()
        assert "the" not in kw.split()
        assert "novel" in kw
        assert "framework" in kw
        assert "deep" in kw

    def test_limits_keywords(self):
        kw = _extract_keywords(
            "Very Long Title With Many Words About Deep Learning "
            "Transformers Attention Mechanisms Neural Networks"
        )
        assert len(kw.split()) <= 6

    def test_empty_title(self):
        assert _extract_keywords("") == ""

    def test_short_words_filtered(self):
        kw = _extract_keywords("An AI ML DL Approach")
        # "an" is stopword, "ai", "ml", "dl" are <=2 chars
        assert "approach" in kw


class TestTitlesMatch:
    def test_exact_match(self):
        assert _titles_match("deep learning for nlp", "deep learning for nlp")

    def test_similar_titles(self):
        assert _titles_match(
            "a novel framework for secure computation",
            "novel framework for secure multi-party computation",
        )

    def test_different_titles(self):
        assert not _titles_match(
            "deep learning for images",
            "reinforcement learning for robotics",
        )

    def test_empty_titles(self):
        assert not _titles_match("", "")
        assert not _titles_match("test", "")


class TestCheckGitHub:
    def test_finds_impl(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "name": "secure-computation-framework",
                    "description": "Implementation of novel secure computation",
                    "html_url": "https://github.com/user/secure-computation-framework",
                    "stargazers_count": 50,
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_resp

        result = check_github(
            "A Novel Framework for Secure Computation", client=mock_client
        )
        assert result.has_impl
        assert len(result.impl_urls) > 0
        assert result.source == "github"

    def test_no_impl_low_stars(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "name": "random-repo",
                    "description": "some computation stuff",
                    "html_url": "https://github.com/user/random-repo",
                    "stargazers_count": 1,  # Too few stars
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_resp

        result = check_github("Novel Secure Computation Framework", client=mock_client)
        assert not result.has_impl

    def test_no_impl_no_results(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"items": []}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_resp

        result = check_github("Completely Unique Paper Title", client=mock_client)
        assert not result.has_impl
        assert result.impl_urls == []

    def test_rate_limited(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_resp

        result = check_github("Test Paper", client=mock_client)
        assert not result.has_impl

    def test_http_error(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.HTTPError("timeout")

        result = check_github("Test Paper", client=mock_client)
        assert not result.has_impl


class TestCheckPapersWithCode:
    def test_finds_paper(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "title": "A Novel Framework for Secure Computation",
                    "repositories": [
                        {"url": "https://github.com/user/impl"},
                    ],
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_resp

        result = check_paperswithcode(
            "A Novel Framework for Secure Computation", client=mock_client
        )
        assert result.has_impl
        assert "https://github.com/user/impl" in result.impl_urls
        assert result.source == "paperswithcode"

    def test_paper_without_repos(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "title": "A Novel Framework for Secure Computation",
                    "repositories": [],
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_resp

        result = check_paperswithcode(
            "A Novel Framework for Secure Computation", client=mock_client
        )
        assert not result.has_impl

    def test_no_matching_paper(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_resp

        result = check_paperswithcode("Unique Paper", client=mock_client)
        assert not result.has_impl

    def test_http_error(self):
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.HTTPError("timeout")

        result = check_paperswithcode("Test Paper", client=mock_client)
        assert not result.has_impl


class TestHasImplementation:
    def test_github_has_impl(self):
        """If GitHub finds impl, should return early without checking PWC."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "name": "secure-computation-framework",
                    "description": "Implementation of novel secure computation framework",
                    "html_url": "https://github.com/user/repo",
                    "stargazers_count": 100,
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_resp

        result = has_implementation(
            "Novel Secure Computation Framework", client=mock_client
        )
        assert result.has_impl
        assert result.source == "github"

    def test_neither_has_impl(self):
        """If neither source has impl, return False."""
        # GitHub returns no results
        gh_resp = MagicMock()
        gh_resp.status_code = 200
        gh_resp.json.return_value = {"items": []}
        gh_resp.raise_for_status = MagicMock()

        # PWC returns no results
        pwc_resp = MagicMock()
        pwc_resp.status_code = 200
        pwc_resp.json.return_value = {"results": []}
        pwc_resp.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = [gh_resp, pwc_resp]

        result = has_implementation("Unique Paper Title", client=mock_client)
        assert not result.has_impl
