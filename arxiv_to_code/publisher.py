"""Publish built implementations: push to GitHub, generate tweet threads and dev.to drafts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from .scanner import Paper
from .state import PublishedRepo, StateManager

logger = logging.getLogger(__name__)


def generate_tweet_thread(paper: Paper, repo_url: str) -> list[str]:
    """Generate a tweet thread announcing the implementation.

    Args:
        paper: The implemented paper.
        repo_url: URL to the GitHub repo.

    Returns:
        List of tweet strings (each ≤280 chars).
    """
    tweets = []

    # Tweet 1: Hook
    title_short = paper.title[:120]
    tweet1 = (
        f"🧵 Just shipped an implementation of \"{title_short}\"\n\n"
        f"Paper dropped on arXiv, had no code — so I built it.\n\n"
        f"Thread 🔽"
    )
    tweets.append(tweet1)

    # Tweet 2: What the paper does
    abstract_short = paper.abstract[:220].rsplit(" ", 1)[0]
    tweet2 = f"📄 What the paper does:\n\n{abstract_short}..."
    tweets.append(tweet2)

    # Tweet 3: Implementation details
    tweet3 = (
        f"⚙️ Implementation highlights:\n\n"
        f"• Python 3.10+, fully typed\n"
        f"• Unit tests with ≥90% coverage\n"
        f"• Clean API, ready to use\n"
        f"• MIT licensed"
    )
    tweets.append(tweet3)

    # Tweet 4: Repo link
    tweet4 = (
        f"🔗 Code: {repo_url}\n"
        f"📄 Paper: https://arxiv.org/abs/{paper.arxiv_id}\n\n"
        f"Star it if useful! Contributions welcome."
    )
    tweets.append(tweet4)

    return tweets


def generate_devto_draft(paper: Paper, repo_url: str) -> str:
    """Generate a dev.to article draft in markdown.

    Args:
        paper: The implemented paper.
        repo_url: URL to the GitHub repo.

    Returns:
        Markdown string for a dev.to draft.
    """
    authors = ", ".join(paper.authors[:5])
    if len(paper.authors) > 5:
        authors += f" et al. ({len(paper.authors)} authors)"

    draft = f"""---
title: "Implementing '{paper.title}' from arXiv"
published: false
description: "A clean Python implementation of a recent arXiv paper with no existing code."
tags: machinelearning, python, research, opensource
---

## The Paper

**{paper.title}**
*{authors}*

- arXiv: [https://arxiv.org/abs/{paper.arxiv_id}](https://arxiv.org/abs/{paper.arxiv_id})
- PDF: [https://arxiv.org/pdf/{paper.arxiv_id}](https://arxiv.org/pdf/{paper.arxiv_id})

### Abstract

{paper.abstract}

## Why I Built This

This paper was published on arXiv with no accompanying code. The algorithm looked
implementable and the results were promising, so I decided to build it.

## Implementation

The full implementation is available on GitHub: [{repo_url}]({repo_url})

### Key Features

- **Python 3.10+** with full type annotations
- **≥90% test coverage** on core logic
- **Clean API** — import and use in your own projects
- **MIT Licensed** — use it however you want

## Getting Started

```bash
git clone {repo_url}
cd $(basename {repo_url})
pip install -e .
```

## Contributing

Found a bug? Want to improve the implementation? PRs welcome!

## Citation

If you use this implementation in your research, please cite the original paper:

```bibtex
@article{{{paper.arxiv_id.replace('.', '_')},
    title={{{paper.title}}},
    author={{{authors}}},
    year={{{paper.submitted.year}}},
    journal={{arXiv preprint arXiv:{paper.arxiv_id}}}
}}
```
"""
    return draft


def notify(message: str) -> None:
    """Log a notification message (integration point for external notifications)."""
    logger.info("[Publisher] %s", message)


def record_publication(
    state: StateManager,
    paper: Paper,
    repo_url: str,
    tweet_url: str = "",
    metrics: dict | None = None,
) -> PublishedRepo:
    """Record a successful publication in state.

    Args:
        state: StateManager instance.
        paper: The published paper.
        repo_url: GitHub repo URL.
        tweet_url: Optional tweet thread URL.
        metrics: Optional metrics (stars, forks, etc).

    Returns:
        PublishedRepo record.
    """
    pub = PublishedRepo(
        arxiv_id=paper.arxiv_id,
        repo_url=repo_url,
        title=paper.title,
        published_at=datetime.now(timezone.utc).isoformat(),
        tweet_url=tweet_url,
        metrics=metrics or {},
    )
    state.add_published(pub)
    logger.info("Recorded publication: %s → %s", paper.arxiv_id, repo_url)
    return pub
