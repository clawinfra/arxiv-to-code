"""Score papers for buildability, novelty, and impact."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from .scanner import Paper

logger = logging.getLogger(__name__)

# Score thresholds
BUILD_THRESHOLD = 60

# Scoring weights
NO_IMPL_BONUS = 40
SECURITY_DOMAIN_BONUS = 20
ALGORITHM_BONUS = 15
FRESHNESS_BONUS = 15
CODE_AVAILABLE_PENALTY = -30

# Algorithm/pseudocode indicators in abstracts
ALGORITHM_INDICATORS = [
    r"\balgorithm\b",
    r"\bpseudocode\b",
    r"\bprocedure\b",
    r"\bstep\s*\d",
    r"\bprotocol\b",
    r"\bmethod\b.*\bpropose\b",
    r"\bpropose\b.*\bmethod\b",
    r"\barchitecture\b",
    r"\bframework\b.*\bnovel\b",
    r"\bnovel\b.*\bframework\b",
    r"\bmodel\b.*\bintroduce\b",
    r"\bintroduce\b.*\bmodel\b",
    r"\bpipeline\b",
]

# Patterns that suggest code is already available
CODE_AVAILABLE_PATTERNS = [
    r"\bwe\s+release\b",
    r"\bcode\s+(is\s+)?available\b",
    r"\bopen[\s-]?source[d]?\b",
    r"\bgithub\.com\b",
    r"\bcode\s+at\b",
    r"\bimplementation\s+(is\s+)?available\b",
    r"\breleased\s+(the\s+)?code\b",
    r"\bour\s+code\b",
]

# Security/crypto categories
SECURITY_CATEGORIES = {"cs.CR", "cs.CY"}


@dataclass
class ScoreBreakdown:
    """Detailed scoring breakdown for a paper."""

    total: int
    no_impl: int = 0
    security_domain: int = 0
    algorithm_present: int = 0
    freshness: int = 0
    code_available_penalty: int = 0
    details: str = ""

    @property
    def passes_threshold(self) -> bool:
        return self.total >= BUILD_THRESHOLD


def _has_algorithm_indicators(abstract: str) -> bool:
    """Check if the abstract mentions algorithms or pseudocode."""
    text = abstract.lower()
    return any(re.search(pat, text) for pat in ALGORITHM_INDICATORS)


def _has_code_available(abstract: str) -> bool:
    """Check if the abstract mentions that code is already available."""
    text = abstract.lower()
    return any(re.search(pat, text) for pat in CODE_AVAILABLE_PATTERNS)


def _is_security_paper(categories: List[str]) -> bool:
    """Check if the paper is in a security/crypto category."""
    return bool(SECURITY_CATEGORIES & set(categories))


def _freshness_hours(submitted: datetime) -> float:
    """Calculate hours since submission."""
    now = datetime.now(timezone.utc)
    delta = now - submitted
    return delta.total_seconds() / 3600


def score(paper: Paper, has_impl: bool = False) -> ScoreBreakdown:
    """Score a paper for buildability and impact.

    Scoring heuristics (0-100):
    - No existing GitHub impl → +40pts
    - cs.CR / security domain → +20pts
    - Has algorithm/pseudocode in abstract → +15pts
    - Submitted <48h ago → +15pts (first-mover bonus)
    - Abstract mentions "we release" or "code available" → -30pts

    Args:
        paper: The paper to score.
        has_impl: Whether an implementation was found externally.

    Returns:
        ScoreBreakdown with total score and component details.
    """
    breakdown = ScoreBreakdown(total=0)
    details = []

    # 1. No existing implementation bonus
    if not has_impl:
        breakdown.no_impl = NO_IMPL_BONUS
        details.append(f"+{NO_IMPL_BONUS} no existing impl")
    else:
        details.append("+0 impl exists")

    # 2. Security domain bonus
    if _is_security_paper(paper.categories):
        breakdown.security_domain = SECURITY_DOMAIN_BONUS
        details.append(f"+{SECURITY_DOMAIN_BONUS} security domain")

    # 3. Algorithm/pseudocode in abstract
    if _has_algorithm_indicators(paper.abstract):
        breakdown.algorithm_present = ALGORITHM_BONUS
        details.append(f"+{ALGORITHM_BONUS} algorithm indicators")

    # 4. Freshness bonus (submitted within 48h)
    hours = _freshness_hours(paper.submitted)
    if hours <= 48:
        breakdown.freshness = FRESHNESS_BONUS
        details.append(f"+{FRESHNESS_BONUS} fresh ({hours:.0f}h ago)")
    else:
        details.append(f"+0 stale ({hours:.0f}h ago)")

    # 5. Code available penalty
    if _has_code_available(paper.abstract):
        breakdown.code_available_penalty = CODE_AVAILABLE_PENALTY
        details.append(f"{CODE_AVAILABLE_PENALTY} code already available")

    # Calculate total
    breakdown.total = max(0, (
        breakdown.no_impl
        + breakdown.security_domain
        + breakdown.algorithm_present
        + breakdown.freshness
        + breakdown.code_available_penalty
    ))
    breakdown.details = "; ".join(details)

    logger.info(
        "Scored paper %s: %d (%s)", paper.arxiv_id, breakdown.total, breakdown.details
    )
    return breakdown
