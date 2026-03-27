"""Tests for the scoring module."""

import pytest
from datetime import datetime, timezone, timedelta

from arxiv_to_code.scanner import Paper
from arxiv_to_code.scorer import (
    score,
    _has_algorithm_indicators,
    _has_code_available,
    _is_security_paper,
    BUILD_THRESHOLD,
    NO_IMPL_BONUS,
    SECURITY_DOMAIN_BONUS,
    ALGORITHM_BONUS,
    FRESHNESS_BONUS,
    CODE_AVAILABLE_PENALTY,
)


class TestAlgorithmIndicators:
    def test_has_algorithm(self):
        assert _has_algorithm_indicators("We propose a novel algorithm for sorting")
        assert _has_algorithm_indicators("The pseudocode is shown in Figure 1")
        assert _has_algorithm_indicators("Step 1: initialize the parameters")
        assert _has_algorithm_indicators("We introduce a model for classification")
        assert _has_algorithm_indicators("A novel framework for detection")
        assert _has_algorithm_indicators("Our pipeline processes data in three stages")

    def test_no_algorithm(self):
        assert not _has_algorithm_indicators("We study the problem of classification")
        assert not _has_algorithm_indicators("Results show improvement on benchmarks")
        assert not _has_algorithm_indicators("This is a simple survey paper")


class TestCodeAvailable:
    def test_has_code(self):
        assert _has_code_available("We release all code and models")
        assert _has_code_available("Code is available at github.com/example")
        assert _has_code_available("Our open-source implementation")
        assert _has_code_available("Code available at our project page")
        assert _has_code_available("We released the code")

    def test_no_code(self):
        assert not _has_code_available("We propose a novel method")
        assert not _has_code_available("Experiments show strong results")
        assert not _has_code_available("We train on standard benchmarks")


class TestSecurityPaper:
    def test_security_categories(self):
        assert _is_security_paper(["cs.CR"])
        assert _is_security_paper(["cs.CY"])
        assert _is_security_paper(["cs.AI", "cs.CR"])

    def test_non_security(self):
        assert not _is_security_paper(["cs.AI"])
        assert not _is_security_paper(["cs.LG", "cs.SE"])
        assert not _is_security_paper([])


class TestScoring:
    def test_fresh_security_paper_no_impl(self, fresh_paper):
        """Fresh security paper with no impl should score high."""
        result = score(fresh_paper, has_impl=False)

        assert result.no_impl == NO_IMPL_BONUS  # 40
        assert result.security_domain == SECURITY_DOMAIN_BONUS  # 20 (cs.CR)
        assert result.algorithm_present == ALGORITHM_BONUS  # 15 (has "algorithm", "protocol", "step 1")
        assert result.freshness == FRESHNESS_BONUS  # 15 (12h ago)
        assert result.code_available_penalty == 0
        assert result.total == 90
        assert result.passes_threshold

    def test_stale_paper(self, stale_paper):
        """Stale paper with no special traits should score low."""
        result = score(stale_paper, has_impl=False)

        assert result.no_impl == NO_IMPL_BONUS  # 40
        assert result.security_domain == 0
        assert result.freshness == 0  # 72h ago > 48h
        assert result.total < BUILD_THRESHOLD  # Should be 40 or slightly more

    def test_paper_with_existing_impl(self, fresh_paper):
        """Paper with existing impl loses 40 points."""
        result = score(fresh_paper, has_impl=True)

        assert result.no_impl == 0
        assert result.total == 50  # 0 + 20 + 15 + 15 = 50
        assert not result.passes_threshold  # 50 < 60

    def test_paper_with_code_available(self, paper_with_code):
        """Paper that mentions code available gets penalty."""
        result = score(paper_with_code, has_impl=False)

        assert result.code_available_penalty == CODE_AVAILABLE_PENALTY  # -30
        # 40 (no impl) + 0 (not security) + 0 (no algorithm) + 15 (fresh) - 30 (code avail) = 25
        assert result.total == 25
        assert not result.passes_threshold

    def test_score_never_negative(self):
        """Score should never go below 0."""
        paper = Paper(
            arxiv_id="test",
            title="Test",
            abstract="We release our open-source code at github.com/example",
            authors=[],
            categories=[],
            submitted=datetime.now(timezone.utc) - timedelta(hours=100),
        )
        result = score(paper, has_impl=True)
        assert result.total >= 0

    def test_score_breakdown_details(self, fresh_paper):
        """Breakdown should contain human-readable details."""
        result = score(fresh_paper, has_impl=False)
        assert "no existing impl" in result.details
        assert "security domain" in result.details
        assert "algorithm indicators" in result.details
        assert "fresh" in result.details

    def test_max_possible_score(self):
        """A perfect paper should score 90."""
        paper = Paper(
            arxiv_id="perfect",
            title="A Novel Protocol for Zero-Knowledge Proofs",
            abstract="We propose a novel algorithm and protocol. Step 1 is key generation.",
            authors=["Test"],
            categories=["cs.CR"],
            submitted=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        result = score(paper, has_impl=False)
        assert result.total == 90  # 40 + 20 + 15 + 15
