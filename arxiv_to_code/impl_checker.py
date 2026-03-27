"""Check GitHub and PapersWithCode for existing implementations of a paper."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import List

import httpx

logger = logging.getLogger(__name__)

GITHUB_SEARCH_API = "https://api.github.com/search/repositories"
PAPERSWITHCODE_API = "https://paperswithcode.com/api/v1/papers/"


@dataclass
class ImplResult:
    """Result of an implementation check."""

    has_impl: bool
    impl_urls: List[str]
    source: str = ""  # "github", "paperswithcode", or ""


def _extract_keywords(title: str) -> str:
    """Extract meaningful keywords from a paper title for search."""
    # Remove common filler words
    stopwords = {
        "a", "an", "the", "of", "for", "in", "on", "to", "and", "or",
        "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "its", "their", "this", "that", "using", "via", "towards", "toward",
        "based", "through", "into",
    }
    words = re.findall(r"[a-zA-Z0-9]+", title.lower())
    keywords = [w for w in words if w not in stopwords and len(w) > 2]
    # Take first 6 meaningful keywords to avoid over-filtering
    return " ".join(keywords[:6])


def check_github(title: str, client: httpx.Client | None = None) -> ImplResult:
    """Search GitHub repositories for implementations matching the paper title.

    Args:
        title: Paper title to search for.
        client: Optional httpx.Client for testing/injection.

    Returns:
        ImplResult with has_impl=True if repos found with >5 stars.
    """
    keywords = _extract_keywords(title)
    if not keywords:
        return ImplResult(has_impl=False, impl_urls=[])

    headers = {"Accept": "application/vnd.github+json"}
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    should_close = False
    if client is None:
        client = httpx.Client(timeout=15)
        should_close = True

    try:
        resp = client.get(
            GITHUB_SEARCH_API,
            params={"q": keywords, "sort": "stars", "per_page": 5},
            headers=headers,
        )
        if resp.status_code == 403:
            logger.warning("GitHub API rate limited, assuming no impl")
            return ImplResult(has_impl=False, impl_urls=[], source="github")
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("GitHub search failed: %s", e)
        return ImplResult(has_impl=False, impl_urls=[])
    finally:
        if should_close:
            client.close()

    data = resp.json()
    items = data.get("items", [])

    # Filter for repos that likely implement the paper (>5 stars, name/desc match)
    title_lower = title.lower()
    title_words = set(re.findall(r"[a-z0-9]+", title_lower))

    matching_urls: List[str] = []
    for item in items:
        repo_name = (item.get("name", "") + " " + (item.get("description") or "")).lower()
        repo_words = set(re.findall(r"[a-z0-9]+", repo_name))
        overlap = title_words & repo_words
        stars = item.get("stargazers_count", 0)

        # At least 3 keyword matches and some stars → likely an impl
        if len(overlap) >= 3 and stars >= 5:
            matching_urls.append(item.get("html_url", ""))

    return ImplResult(
        has_impl=len(matching_urls) > 0,
        impl_urls=matching_urls,
        source="github",
    )


def check_paperswithcode(title: str, client: httpx.Client | None = None) -> ImplResult:
    """Search PapersWithCode for the paper.

    Args:
        title: Paper title to search for.
        client: Optional httpx.Client for testing/injection.

    Returns:
        ImplResult with has_impl=True if paper found with code repos.
    """
    should_close = False
    if client is None:
        client = httpx.Client(timeout=15)
        should_close = True

    try:
        resp = client.get(
            PAPERSWITHCODE_API,
            params={"title": title},
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("PapersWithCode search failed: %s", e)
        return ImplResult(has_impl=False, impl_urls=[])
    finally:
        if should_close:
            client.close()

    data = resp.json()
    results = data.get("results", [])

    for result in results:
        paper_title = result.get("title", "").lower().strip()
        if _titles_match(title.lower().strip(), paper_title):
            # Check if it has associated repos
            repos = result.get("repositories", [])
            if repos:
                urls = [r.get("url", "") for r in repos if r.get("url")]
                return ImplResult(has_impl=True, impl_urls=urls, source="paperswithcode")

    return ImplResult(has_impl=False, impl_urls=[], source="paperswithcode")


def _titles_match(t1: str, t2: str) -> bool:
    """Fuzzy title matching — check if titles are substantially similar."""
    # Normalize
    w1 = set(re.findall(r"[a-z0-9]+", t1))
    w2 = set(re.findall(r"[a-z0-9]+", t2))
    if not w1 or not w2:
        return False
    overlap = len(w1 & w2) / max(len(w1), len(w2))
    return overlap >= 0.7


def has_implementation(title: str, client: httpx.Client | None = None) -> ImplResult:
    """Check both GitHub and PapersWithCode for existing implementations.

    Args:
        title: Paper title to search for.
        client: Optional httpx.Client for testing/injection.

    Returns:
        ImplResult — has_impl=True if ANY source has an implementation.
    """
    gh = check_github(title, client)
    if gh.has_impl:
        logger.info("Found GitHub impl for: %s", title)
        return gh

    pwc = check_paperswithcode(title, client)
    if pwc.has_impl:
        logger.info("Found PapersWithCode impl for: %s", title)
        return pwc

    return ImplResult(has_impl=False, impl_urls=[])
