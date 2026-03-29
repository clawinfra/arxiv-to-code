"""Fetch recent papers from arXiv API across target categories."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List
from urllib.parse import quote

import feedparser
import httpx

logger = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
DEFAULT_CATEGORIES = ["cs.AI", "cs.CR", "cs.LG", "cs.SE"]
DEFAULT_MAX_RESULTS = 100


@dataclass
class Paper:
    """Represents a single arXiv paper."""

    arxiv_id: str
    title: str
    abstract: str
    authors: List[str]
    categories: List[str]
    submitted: datetime
    pdf_url: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "categories": self.categories,
            "submitted": self.submitted.isoformat(),
            "pdf_url": self.pdf_url,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Paper":
        submitted = d["submitted"]
        if isinstance(submitted, str):
            submitted = datetime.fromisoformat(submitted)
        return cls(
            arxiv_id=d["arxiv_id"],
            title=d["title"],
            abstract=d["abstract"],
            authors=d["authors"],
            categories=d["categories"],
            submitted=submitted,
            pdf_url=d.get("pdf_url", ""),
        )


def _build_query(categories: List[str]) -> str:
    """Build an arXiv API search query for given categories."""
    cat_parts = [f"cat:{cat}" for cat in categories]
    return " OR ".join(cat_parts)


def _parse_entry(entry: dict) -> Paper:
    """Parse a single feedparser entry into a Paper."""
    # Extract arxiv ID from the entry id URL
    arxiv_id = entry.get("id", "").split("/abs/")[-1]
    # Remove version suffix if present
    if arxiv_id and "v" in arxiv_id:
        base = arxiv_id.rsplit("v", 1)
        if base[1].isdigit():
            arxiv_id = base[0]

    title = entry.get("title", "").replace("\n", " ").strip()
    abstract = entry.get("summary", "").replace("\n", " ").strip()
    authors = [a.get("name", "") for a in entry.get("authors", [])]

    # Categories
    tags = entry.get("tags", [])
    categories = [t.get("term", "") for t in tags if t.get("term")]

    # Submitted date
    published = entry.get("published", "")
    try:
        submitted = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        submitted = datetime.now(timezone.utc)

    # PDF link
    pdf_url = ""
    for link in entry.get("links", []):
        if link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
            break

    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        abstract=abstract,
        authors=authors,
        categories=categories,
        submitted=submitted,
        pdf_url=pdf_url,
    )


def fetch_recent(
    hours: int = 48,
    categories: List[str] | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    client: httpx.Client | None = None,
) -> List[Paper]:
    """Fetch papers from arXiv published in the last `hours` hours.

    Args:
        hours: Look-back window in hours (default 48).
        categories: arXiv categories to search (default: cs.AI, cs.CR, cs.LG, cs.SE).
        max_results: Maximum number of results to fetch.
        client: Optional httpx.Client for testing/injection.

    Returns:
        List of Paper objects sorted by submission date (newest first).
    """
    cats = categories or DEFAULT_CATEGORIES
    query = _build_query(cats)
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    logger.info("Fetching arXiv papers: query=%s max_results=%d", query, max_results)

    should_close = False
    if client is None:
        client = httpx.Client(timeout=30)
        should_close = True

    # Retry with exponential backoff — arXiv returns 429 during peak hours
    import time as _time
    max_retries = 4
    base_delay = 15  # seconds
    resp = None
    last_exc = None
    for attempt in range(max_retries):
        try:
            resp = client.get(ARXIV_API, params=params)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", base_delay * (2 ** attempt)))
                logger.warning("arXiv rate limited (429). Waiting %ds before retry %d/%d",
                               retry_after, attempt + 1, max_retries)
                _time.sleep(retry_after)
                continue
            resp.raise_for_status()
            break
        except httpx.HTTPError as e:
            last_exc = e
            if attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt)
                logger.warning("arXiv request failed (%s). Retrying in %ds (%d/%d)",
                               e, wait, attempt + 1, max_retries)
                _time.sleep(wait)
            else:
                logger.error("arXiv API request failed after %d retries: %s", max_retries, e)
        finally:
            pass  # close handled below

    if should_close:
        client.close()

    if resp is None or not resp.is_success:
        logger.error("arXiv API unavailable after retries (last error: %s)", last_exc)
        return []

    feed = feedparser.parse(resp.text)
    papers: List[Paper] = []
    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)

    for entry in feed.entries:
        paper = _parse_entry(entry)
        if paper.submitted.timestamp() >= cutoff:
            papers.append(paper)

    logger.info("Fetched %d papers within %dh window", len(papers), hours)
    return sorted(papers, key=lambda p: p.submitted, reverse=True)
