"""State management for the arxiv-to-code pipeline.

Manages three JSON state files:
- processed.json: Papers already seen (arxiv IDs → status)
- queue.json: Scored papers pending build (sorted by score)
- published.json: Shipped repos with metrics
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .scanner import Paper

logger = logging.getLogger(__name__)

DEFAULT_STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state")


@dataclass
class QueuedPaper:
    """A paper in the build queue with its score."""

    paper: Paper
    score: int
    queued_at: str = ""
    status: str = "queued"  # queued, building, built, failed

    def to_dict(self) -> dict:
        return {
            "paper": self.paper.to_dict(),
            "score": self.score,
            "queued_at": self.queued_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QueuedPaper":
        return cls(
            paper=Paper.from_dict(d["paper"]),
            score=d["score"],
            queued_at=d.get("queued_at", ""),
            status=d.get("status", "queued"),
        )


@dataclass
class PublishedRepo:
    """A published implementation."""

    arxiv_id: str
    repo_url: str
    title: str
    published_at: str = ""
    tweet_url: str = ""
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "arxiv_id": self.arxiv_id,
            "repo_url": self.repo_url,
            "title": self.title,
            "published_at": self.published_at,
            "tweet_url": self.tweet_url,
            "metrics": self.metrics,
        }


class StateManager:
    """Manages pipeline state across JSON files."""

    def __init__(self, state_dir: str | None = None):
        self.state_dir = Path(state_dir or DEFAULT_STATE_DIR)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self._processed_path = self.state_dir / "processed.json"
        self._queue_path = self.state_dir / "queue.json"
        self._published_path = self.state_dir / "published.json"

    def _load_json(self, path: Path) -> Any:
        if not path.exists():
            return {}
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load %s: %s", path, e)
            return {}

    def _save_json(self, path: Path, data: Any) -> None:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    # --- Processed papers ---

    def already_processed(self, arxiv_id: str) -> bool:
        """Check if a paper has already been processed."""
        processed = self._load_json(self._processed_path)
        return arxiv_id in processed

    def mark_processed(self, arxiv_id: str, reason: str) -> None:
        """Mark a paper as processed with a reason."""
        processed = self._load_json(self._processed_path)
        processed[arxiv_id] = {
            "reason": reason,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_json(self._processed_path, processed)
        logger.info("Marked %s as processed: %s", arxiv_id, reason)

    def get_processed(self) -> Dict[str, dict]:
        """Get all processed papers."""
        return self._load_json(self._processed_path)

    # --- Build queue ---

    def add_to_queue(self, paper: Paper, score: int) -> None:
        """Add a paper to the build queue."""
        queue = self._load_queue()
        entry = QueuedPaper(
            paper=paper,
            score=score,
            queued_at=datetime.now(timezone.utc).isoformat(),
        )
        queue.append(entry)
        self._save_queue(queue)
        self.mark_processed(paper.arxiv_id, "queued_for_build")
        logger.info("Queued %s (score=%d): %s", paper.arxiv_id, score, paper.title)

    def get_top_queued(self) -> Optional[QueuedPaper]:
        """Get the highest-scored queued paper."""
        queue = self._load_queue()
        queued = [q for q in queue if q.status == "queued"]
        if not queued:
            return None
        return max(queued, key=lambda q: q.score)

    def mark_building(self, arxiv_id: str, task_prompt: str) -> None:
        """Mark a queued paper as currently being built."""
        queue = self._load_queue()
        for item in queue:
            if item.paper.arxiv_id == arxiv_id:
                item.status = "building"
                break
        self._save_queue(queue)
        logger.info("Marked %s as building", arxiv_id)

    def mark_built(self, arxiv_id: str) -> None:
        """Mark a queued paper as successfully built."""
        queue = self._load_queue()
        for item in queue:
            if item.paper.arxiv_id == arxiv_id:
                item.status = "built"
                break
        self._save_queue(queue)

    def mark_failed(self, arxiv_id: str) -> None:
        """Mark a queued paper as failed to build."""
        queue = self._load_queue()
        for item in queue:
            if item.paper.arxiv_id == arxiv_id:
                item.status = "failed"
                break
        self._save_queue(queue)

    def get_queue(self) -> List[QueuedPaper]:
        """Get the full build queue."""
        return self._load_queue()

    def _load_queue(self) -> List[QueuedPaper]:
        data = self._load_json(self._queue_path)
        if isinstance(data, list):
            return [QueuedPaper.from_dict(d) for d in data]
        return []

    def _save_queue(self, queue: List[QueuedPaper]) -> None:
        self._save_json(self._queue_path, [q.to_dict() for q in queue])

    # --- Published repos ---

    def add_published(self, repo: PublishedRepo) -> None:
        """Record a published implementation."""
        published = self._load_published()
        published.append(repo)
        self._save_json(self._published_path, [p.to_dict() for p in published])
        logger.info("Published %s → %s", repo.arxiv_id, repo.repo_url)

    def get_published(self) -> List[PublishedRepo]:
        """Get all published repos."""
        return self._load_published()

    def _load_published(self) -> List[PublishedRepo]:
        data = self._load_json(self._published_path)
        if isinstance(data, list):
            return [
                PublishedRepo(
                    arxiv_id=d["arxiv_id"],
                    repo_url=d["repo_url"],
                    title=d["title"],
                    published_at=d.get("published_at", ""),
                    tweet_url=d.get("tweet_url", ""),
                    metrics=d.get("metrics", {}),
                )
                for d in data
            ]
        return []

    # --- Stats ---

    def stats(self) -> dict:
        """Get pipeline statistics."""
        processed = self._load_json(self._processed_path)
        queue = self._load_queue()
        published = self._load_published()
        return {
            "total_processed": len(processed),
            "queued": len([q for q in queue if q.status == "queued"]),
            "building": len([q for q in queue if q.status == "building"]),
            "built": len([q for q in queue if q.status == "built"]),
            "failed": len([q for q in queue if q.status == "failed"]),
            "published": len(published),
        }
