"""Main pipeline orchestrator for arxiv-to-code.

Runs the full loop:
1. Scan arXiv for recent papers
2. Filter out processed papers
3. Check for existing implementations
4. Score remaining papers
5. Queue top papers for building
6. Generate builder task for the top paper
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import scanner, scorer, impl_checker, builder, publisher
from .state import StateManager

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of a pipeline run."""

    papers_scanned: int = 0
    papers_skipped: int = 0
    papers_with_impl: int = 0
    papers_queued: int = 0
    top_paper_title: str = ""
    top_paper_score: int = 0
    top_paper_arxiv_id: str = ""
    task_prompt: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "papers_scanned": self.papers_scanned,
            "papers_skipped": self.papers_skipped,
            "papers_with_impl": self.papers_with_impl,
            "papers_queued": self.papers_queued,
            "top_paper_title": self.top_paper_title,
            "top_paper_score": self.top_paper_score,
            "top_paper_arxiv_id": self.top_paper_arxiv_id,
            "has_task": bool(self.task_prompt),
            "error": self.error,
        }

    def summary(self) -> str:
        lines = [
            f"Scanned {self.papers_scanned} papers",
            f"  Skipped (already processed): {self.papers_skipped}",
            f"  Had existing impl: {self.papers_with_impl}",
            f"  Queued for build: {self.papers_queued}",
        ]
        if self.top_paper_title:
            lines.append(
                f"  Top paper: \"{self.top_paper_title}\" "
                f"(score={self.top_paper_score}, arxiv={self.top_paper_arxiv_id})"
            )
        if self.error:
            lines.append(f"  ERROR: {self.error}")
        return "\n".join(lines)


def run(
    state_dir: str | None = None,
    hours: int = 48,
    max_results: int = 100,
    dry_run: bool = False,
) -> PipelineResult:
    """Run the arxiv-to-code pipeline.

    Args:
        state_dir: Path to state directory. Uses default if None.
        hours: Look-back window for arXiv papers.
        max_results: Maximum papers to fetch from arXiv.
        dry_run: If True, don't modify state or generate tasks.

    Returns:
        PipelineResult with summary of what happened.
    """
    result = PipelineResult()
    state = StateManager(state_dir)

    # 1. Scan for new papers
    logger.info("Step 1: Scanning arXiv (last %dh, max %d results)", hours, max_results)
    try:
        papers = scanner.fetch_recent(hours=hours, max_results=max_results)
    except Exception as e:
        result.error = f"Scanner failed: {e}"
        logger.error(result.error)
        return result

    result.papers_scanned = len(papers)
    logger.info("Found %d papers", len(papers))

    # 2. Filter and score
    logger.info("Step 2: Filtering and scoring papers")
    for paper in papers:
        # Skip if already processed
        if state.already_processed(paper.arxiv_id):
            result.papers_skipped += 1
            continue

        # Check for existing implementations
        try:
            impl_result = impl_checker.has_implementation(paper.title)
        except Exception as e:
            logger.warning("Impl check failed for %s: %s", paper.arxiv_id, e)
            impl_result = impl_checker.ImplResult(has_impl=False, impl_urls=[])

        if impl_result.has_impl:
            result.papers_with_impl += 1
            if not dry_run:
                state.mark_processed(
                    paper.arxiv_id,
                    f"has_impl:{impl_result.source}:{','.join(impl_result.impl_urls[:3])}",
                )
            continue

        # Score the paper
        score_result = scorer.score(paper, has_impl=impl_result.has_impl)

        if score_result.passes_threshold:
            result.papers_queued += 1
            if not dry_run:
                state.add_to_queue(paper, score_result.total)
            logger.info(
                "Queued: %s (score=%d) — %s",
                paper.arxiv_id,
                score_result.total,
                paper.title,
            )
        else:
            if not dry_run:
                state.mark_processed(
                    paper.arxiv_id,
                    f"below_threshold:score={score_result.total}",
                )

    # 3. Get top paper and generate build task
    logger.info("Step 3: Selecting top paper for build")
    top = state.get_top_queued()
    if top:
        result.top_paper_title = top.paper.title
        result.top_paper_score = top.score
        result.top_paper_arxiv_id = top.paper.arxiv_id

        task_prompt = builder.generate_task(top)
        result.task_prompt = task_prompt

        if not dry_run:
            state.mark_building(top.paper.arxiv_id, task_prompt)
            publisher.notify(f"Building: {top.paper.title} (score={top.score})")

        logger.info(
            "Top paper: %s (score=%d)", top.paper.title, top.score
        )
    else:
        logger.info("No papers in queue above threshold")

    logger.info("Pipeline complete: %s", result.summary())
    return result


def main() -> None:
    """CLI entry point for the pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    import argparse

    parser = argparse.ArgumentParser(description="arxiv-to-code pipeline")
    parser.add_argument("--state-dir", help="State directory path")
    parser.add_argument("--hours", type=int, default=48, help="Look-back window in hours")
    parser.add_argument("--max-results", type=int, default=100, help="Max arXiv results")
    parser.add_argument("--dry-run", action="store_true", help="Don't modify state")
    args = parser.parse_args()

    result = run(
        state_dir=args.state_dir,
        hours=args.hours,
        max_results=args.max_results,
        dry_run=args.dry_run,
    )

    print("\n" + "=" * 60)
    print("PIPELINE RESULT")
    print("=" * 60)
    print(result.summary())
    print()
    print(json.dumps(result.to_dict(), indent=2))

    if result.error:
        sys.exit(1)


if __name__ == "__main__":
    main()
