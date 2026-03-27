"""Generate builder task prompts for sessions_spawn to implement papers."""

from __future__ import annotations

import logging
import re
from typing import Optional

from .scanner import Paper
from .state import QueuedPaper

logger = logging.getLogger(__name__)


def _sanitize_repo_name(title: str) -> str:
    """Convert a paper title to a valid GitHub repo name."""
    # Remove special chars, keep alphanumeric and spaces
    clean = re.sub(r"[^a-zA-Z0-9\s-]", "", title.lower())
    # Replace spaces with hyphens
    clean = re.sub(r"\s+", "-", clean.strip())
    # Truncate
    return clean[:60].rstrip("-")


def _extract_key_concepts(abstract: str) -> str:
    """Extract key algorithmic concepts from the abstract for the builder."""
    # Look for sentences that describe the method/approach
    sentences = abstract.split(". ")
    key_sentences = []
    indicators = [
        "propose", "introduce", "present", "develop", "design",
        "novel", "approach", "method", "algorithm", "framework",
        "architecture", "pipeline", "technique",
    ]
    for sent in sentences:
        if any(ind in sent.lower() for ind in indicators):
            key_sentences.append(sent.strip())
    return ". ".join(key_sentences[:3]) if key_sentences else abstract[:500]


def generate_task(queued: QueuedPaper, org: str = "clawinfra") -> str:
    """Generate a complete task prompt for a builder sub-agent.

    The prompt instructs the builder to:
    1. Create a standard repo structure (src/, tests/, README)
    2. Implement the core algorithm from the paper
    3. Write tests with ≥90% coverage
    4. Report back via sessions_send

    Args:
        queued: The queued paper with score info.
        org: GitHub org to create the repo under.

    Returns:
        Task prompt string for sessions_spawn.
    """
    paper = queued.paper
    repo_name = _sanitize_repo_name(paper.title)
    key_concepts = _extract_key_concepts(paper.abstract)

    task = f"""Build a working implementation of the paper "{paper.title}".

## Paper Details
- **arXiv ID:** {paper.arxiv_id}
- **PDF:** https://arxiv.org/pdf/{paper.arxiv_id}
- **Authors:** {', '.join(paper.authors[:5])}
- **Categories:** {', '.join(paper.categories)}
- **Score:** {queued.score}/100

## Abstract
{paper.abstract}

## Key Concepts to Implement
{key_concepts}

## Requirements

### Repository Structure
```
{repo_name}/
  src/
    __init__.py
    core.py          — main algorithm implementation
    utils.py         — helper functions
  tests/
    test_core.py     — unit tests for core algorithm
    test_utils.py    — unit tests for utilities
  README.md          — paper citation, usage, results
  pyproject.toml     — project config with dependencies
  LICENSE            — MIT
```

### Implementation Standards
- Python 3.10+, type-annotated
- Core algorithm must be faithful to the paper
- Include docstrings referencing paper sections
- ≥90% test coverage on core logic
- README must cite the original paper
- Include example usage in README

### Build Steps
```bash
cd /tmp && rm -rf {repo_name}
mkdir {repo_name} && cd {repo_name}
git init
git config user.name "Alex Chen" && git config user.email "alex.chen31337@gmail.com"
# implement everything
uv run pytest tests/ -v --cov=src --cov-report=term-missing
gh repo create {org}/{repo_name} --public --description "Implementation of: {paper.title}"
GIT_SSH_COMMAND='ssh -i ~/.ssh/id_ed25519_alexchen' git remote add origin git@github.com:{org}/{repo_name}.git
git add -A && git commit -m "feat: implement {paper.title[:50]}"
GIT_SSH_COMMAND='ssh -i ~/.ssh/id_ed25519_alexchen' git push -u origin main
```

### Report Back
When done, report:
sessions_send(sessionKey="agent:main:main", message="[ArxivBuilder] Shipped {org}/{repo_name} — arXiv:{paper.arxiv_id} — <test_count> tests, <coverage>% coverage")
"""
    logger.info("Generated task for %s → %s/%s", paper.arxiv_id, org, repo_name)
    return task


def generate_repo_name(paper: Paper) -> str:
    """Generate a GitHub-friendly repo name from a paper title."""
    return _sanitize_repo_name(paper.title)
