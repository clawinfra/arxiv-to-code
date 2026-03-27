"""Tests for the pipeline orchestrator and state management."""

import json
import pytest
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from arxiv_to_code.scanner import Paper
from arxiv_to_code.state import StateManager, QueuedPaper, PublishedRepo
from arxiv_to_code.builder import generate_task, generate_repo_name, _sanitize_repo_name
from arxiv_to_code.publisher import (
    generate_tweet_thread,
    generate_devto_draft,
    record_publication,
)
from arxiv_to_code.pipeline import run, PipelineResult


class TestStateManager:
    @pytest.fixture
    def state(self, tmp_path):
        return StateManager(str(tmp_path / "state"))

    def test_processed_lifecycle(self, state):
        assert not state.already_processed("2403.12345")
        state.mark_processed("2403.12345", "has_impl")
        assert state.already_processed("2403.12345")

        processed = state.get_processed()
        assert "2403.12345" in processed
        assert processed["2403.12345"]["reason"] == "has_impl"

    def test_queue_lifecycle(self, state, fresh_paper):
        # Initially empty
        assert state.get_top_queued() is None

        # Add to queue
        state.add_to_queue(fresh_paper, 85)
        top = state.get_top_queued()
        assert top is not None
        assert top.paper.arxiv_id == "2403.12345"
        assert top.score == 85
        assert top.status == "queued"

        # Mark as building
        state.mark_building("2403.12345", "task prompt here")
        top = state.get_top_queued()
        # Should not return building papers
        assert top is None

        # Mark as built
        state.mark_built("2403.12345")
        queue = state.get_queue()
        assert queue[0].status == "built"

    def test_queue_returns_highest_score(self, state, fresh_paper, stale_paper):
        state.add_to_queue(stale_paper, 45)
        state.add_to_queue(fresh_paper, 85)

        top = state.get_top_queued()
        assert top.score == 85
        assert top.paper.arxiv_id == fresh_paper.arxiv_id

    def test_mark_failed(self, state, fresh_paper):
        state.add_to_queue(fresh_paper, 70)
        state.mark_failed("2403.12345")
        queue = state.get_queue()
        assert queue[0].status == "failed"

    def test_published_lifecycle(self, state):
        pub = PublishedRepo(
            arxiv_id="2403.12345",
            repo_url="https://github.com/clawinfra/test-repo",
            title="Test Paper",
            published_at=datetime.now(timezone.utc).isoformat(),
        )
        state.add_published(pub)

        published = state.get_published()
        assert len(published) == 1
        assert published[0].repo_url == "https://github.com/clawinfra/test-repo"

    def test_stats(self, state, fresh_paper, stale_paper):
        state.add_to_queue(fresh_paper, 85)
        state.add_to_queue(stale_paper, 45)
        state.mark_building("2403.12345", "task")

        stats = state.stats()
        assert stats["queued"] == 1
        assert stats["building"] == 1
        assert stats["total_processed"] == 2  # Both get marked processed when queued

    def test_corrupted_json(self, state):
        """Should handle corrupted JSON gracefully."""
        # Write invalid JSON
        (Path(state.state_dir) / "processed.json").write_text("{invalid")
        assert not state.already_processed("test")

    def test_queued_paper_roundtrip(self, fresh_paper):
        qp = QueuedPaper(
            paper=fresh_paper,
            score=85,
            queued_at="2024-03-20T12:00:00+00:00",
            status="queued",
        )
        d = qp.to_dict()
        qp2 = QueuedPaper.from_dict(d)
        assert qp2.score == 85
        assert qp2.paper.arxiv_id == fresh_paper.arxiv_id
        assert qp2.status == "queued"


class TestBuilder:
    def test_sanitize_repo_name(self):
        assert _sanitize_repo_name("A Novel Framework for NLP") == "a-novel-framework-for-nlp"
        assert _sanitize_repo_name("Test: Special (Chars)!") == "test-special-chars"
        assert len(_sanitize_repo_name("a" * 100)) <= 60

    def test_generate_repo_name(self, fresh_paper):
        name = generate_repo_name(fresh_paper)
        assert isinstance(name, str)
        assert len(name) > 0
        assert " " not in name

    def test_generate_task(self, fresh_paper):
        queued = QueuedPaper(paper=fresh_paper, score=85)
        task = generate_task(queued)

        assert "2403.12345" in task
        assert fresh_paper.title in task
        assert "≥90%" in task
        assert "sessions_send" in task
        assert "clawinfra" in task
        assert "pyproject.toml" in task

    def test_generate_task_custom_org(self, fresh_paper):
        queued = QueuedPaper(paper=fresh_paper, score=70)
        task = generate_task(queued, org="myorg")
        assert "myorg" in task


class TestPublisher:
    def test_generate_tweet_thread(self, fresh_paper):
        tweets = generate_tweet_thread(
            fresh_paper, "https://github.com/clawinfra/test-repo"
        )
        assert len(tweets) >= 3
        assert all(isinstance(t, str) for t in tweets)
        # Check tweet lengths (Twitter limit)
        for tweet in tweets:
            assert len(tweet) <= 400  # Some slack for URLs

    def test_tweet_thread_contains_repo_url(self, fresh_paper):
        url = "https://github.com/clawinfra/test-repo"
        tweets = generate_tweet_thread(fresh_paper, url)
        # At least one tweet should have the repo URL
        assert any(url in t for t in tweets)

    def test_generate_devto_draft(self, fresh_paper):
        draft = generate_devto_draft(
            fresh_paper, "https://github.com/clawinfra/test-repo"
        )
        assert "---" in draft  # Front matter
        assert fresh_paper.title in draft
        assert "2403.12345" in draft
        assert "https://github.com/clawinfra/test-repo" in draft
        assert "bibtex" in draft.lower() or "@article" in draft

    def test_record_publication(self, tmp_path, fresh_paper):
        state = StateManager(str(tmp_path / "state"))
        pub = record_publication(
            state,
            fresh_paper,
            "https://github.com/clawinfra/test-repo",
            tweet_url="https://twitter.com/user/status/123",
            metrics={"stars": 10},
        )
        assert pub.arxiv_id == "2403.12345"
        assert pub.repo_url == "https://github.com/clawinfra/test-repo"

        published = state.get_published()
        assert len(published) == 1


class TestPipeline:
    @patch("arxiv_to_code.pipeline.scanner")
    @patch("arxiv_to_code.pipeline.impl_checker")
    def test_full_run(self, mock_impl, mock_scanner, fresh_paper, stale_paper, tmp_path):
        """Test full pipeline run with mocked external APIs."""
        from arxiv_to_code.impl_checker import ImplResult

        mock_scanner.fetch_recent.return_value = [fresh_paper, stale_paper]
        mock_impl.has_implementation.return_value = ImplResult(
            has_impl=False, impl_urls=[]
        )
        mock_impl.ImplResult = ImplResult

        result = run(state_dir=str(tmp_path / "state"), hours=48)

        assert result.papers_scanned == 2
        assert result.papers_queued >= 1
        assert result.top_paper_title != ""
        assert result.top_paper_score > 0
        assert result.task_prompt != ""
        assert not result.error

    @patch("arxiv_to_code.pipeline.scanner")
    @patch("arxiv_to_code.pipeline.impl_checker")
    def test_dry_run(self, mock_impl, mock_scanner, fresh_paper, tmp_path):
        from arxiv_to_code.impl_checker import ImplResult

        mock_scanner.fetch_recent.return_value = [fresh_paper]
        mock_impl.has_implementation.return_value = ImplResult(
            has_impl=False, impl_urls=[]
        )
        mock_impl.ImplResult = ImplResult

        state_dir = str(tmp_path / "state")
        result = run(state_dir=state_dir, dry_run=True)

        assert result.papers_queued >= 1
        # State should NOT be modified in dry run
        state = StateManager(state_dir)
        assert not state.already_processed(fresh_paper.arxiv_id)

    @patch("arxiv_to_code.pipeline.scanner")
    @patch("arxiv_to_code.pipeline.impl_checker")
    def test_skips_papers_with_impl(
        self, mock_impl, mock_scanner, fresh_paper, paper_with_code, tmp_path
    ):
        from arxiv_to_code.impl_checker import ImplResult

        mock_scanner.fetch_recent.return_value = [fresh_paper, paper_with_code]

        def check_impl(title, **kwargs):
            if "FastDiff" in title:
                return ImplResult(
                    has_impl=True, impl_urls=["https://github.com/example/fastdiff"]
                )
            return ImplResult(has_impl=False, impl_urls=[])

        mock_impl.has_implementation.side_effect = check_impl
        mock_impl.ImplResult = ImplResult

        result = run(state_dir=str(tmp_path / "state"), hours=48)

        assert result.papers_with_impl == 1

    @patch("arxiv_to_code.pipeline.scanner")
    def test_scanner_failure(self, mock_scanner, tmp_path):
        mock_scanner.fetch_recent.side_effect = Exception("Network error")

        result = run(state_dir=str(tmp_path / "state"))
        assert result.error != ""
        assert "Scanner failed" in result.error

    @patch("arxiv_to_code.pipeline.scanner")
    @patch("arxiv_to_code.pipeline.impl_checker")
    def test_skips_already_processed(
        self, mock_impl, mock_scanner, fresh_paper, tmp_path
    ):
        from arxiv_to_code.impl_checker import ImplResult

        state_dir = str(tmp_path / "state")
        # Pre-mark as processed
        state = StateManager(state_dir)
        state.mark_processed(fresh_paper.arxiv_id, "test")

        mock_scanner.fetch_recent.return_value = [fresh_paper]
        mock_impl.ImplResult = ImplResult

        result = run(state_dir=state_dir)
        assert result.papers_skipped == 1

    def test_pipeline_result_summary(self):
        result = PipelineResult(
            papers_scanned=50,
            papers_skipped=10,
            papers_with_impl=15,
            papers_queued=3,
            top_paper_title="Test Paper",
            top_paper_score=85,
            top_paper_arxiv_id="2403.12345",
        )
        summary = result.summary()
        assert "50" in summary
        assert "Test Paper" in summary
        assert "85" in summary

    def test_pipeline_result_to_dict(self):
        result = PipelineResult(papers_scanned=10, top_paper_title="Test")
        d = result.to_dict()
        assert d["papers_scanned"] == 10
        assert d["top_paper_title"] == "Test"
        assert isinstance(d["has_task"], bool)
