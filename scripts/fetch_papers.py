#!/usr/bin/env python3
"""Fetch and normalize DailyPaper records from ArXiv."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config_loader import load_config
from scripts.paper_processing import PaperProcessor, paper_sort_key, strip_arxiv_version


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class PaperFetcher:
    """ArXiv-backed paper fetcher with structured enrichment."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = load_config(config_path)
        self.processor = PaperProcessor(self.config)

    def fetch_arxiv_papers(self) -> List[Dict[str, Any]]:
        """Fetch papers from configured ArXiv categories."""

        try:
            import arxiv  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "The `arxiv` package is required for fetching new papers. "
                "Install dependencies from requirements.txt first."
            ) from exc

        arxiv_config = self.config["sources"]["arxiv"]
        if not arxiv_config.get("enabled", True):
            logger.info("ArXiv source is disabled")
            return []

        primary_categories = list(arxiv_config.get("primary_categories", []))
        secondary_categories = list(arxiv_config.get("secondary_categories", []))
        tracked_categories = primary_categories + secondary_categories
        secondary_category_set = set(secondary_categories)

        max_results = int(arxiv_config.get("max_results", 100))
        days_back = int(arxiv_config.get("days_back", 7))
        start_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        papers_by_key: Dict[str, Dict[str, Any]] = {}

        logger.info("Fetching ArXiv papers from %s categories", len(tracked_categories))
        for category in tracked_categories:
            logger.info("Fetching category: %s", category)
            search = arxiv.Search(
                query=f"cat:{category}",
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )

            category_count = 0
            for result in search.results():
                paper_date = (result.updated or result.published).astimezone(timezone.utc)
                if paper_date < start_date:
                    continue

                paper = self._result_to_paper(result, category)
                paper = self.processor.enrich_paper(paper)

                if category in secondary_category_set and not self.processor.should_keep_secondary_category_paper(paper):
                    continue

                dedup_key = paper.get("arxiv_id") or paper["id"]
                existing = papers_by_key.get(dedup_key)
                if existing is None:
                    papers_by_key[dedup_key] = paper
                else:
                    papers_by_key[dedup_key] = self._merge_duplicate(existing, paper)

                category_count += 1

            logger.info("Collected %s recent papers from %s", category_count, category)

        papers = list(papers_by_key.values())
        papers.sort(key=paper_sort_key, reverse=True)
        logger.info("ArXiv fetch complete: %s unique papers", len(papers))
        return papers

    def _result_to_paper(self, result: Any, category: str) -> Dict[str, Any]:
        arxiv_id = result.entry_id.split("/")[-1]
        return {
            "id": arxiv_id,
            "arxiv_id": strip_arxiv_version(arxiv_id),
            "title": result.title,
            "authors": [author.name for author in result.authors],
            "abstract": result.summary,
            "published": result.published.strftime("%Y-%m-%d"),
            "updated": result.updated.strftime("%Y-%m-%d"),
            "categories": list(result.categories),
            "primary_category": result.primary_category,
            "pdf_url": result.pdf_url,
            "arxiv_url": result.entry_id,
            "source": "ArXiv",
            "venue": category,
            "source_category": category,
            "comment": result.comment if getattr(result, "comment", None) else None,
            "journal_ref": (
                result.journal_ref if getattr(result, "journal_ref", None) else None
            ),
        }

    def _merge_duplicate(
        self, existing: Dict[str, Any], candidate: Dict[str, Any]
    ) -> Dict[str, Any]:
        merged = dict(existing)
        merged["categories"] = sorted(
            dict.fromkeys((existing.get("categories") or []) + (candidate.get("categories") or []))
        )

        if candidate.get("relevance_score", 0) > existing.get("relevance_score", 0):
            preferred = dict(candidate)
            preferred["categories"] = merged["categories"]
            return preferred

        merged["tags"] = list(
            dict.fromkeys((existing.get("tags") or []) + (candidate.get("tags") or []))
        )
        for field in ("topic_tags", "method_tags", "scenario_tags", "match_reasons"):
            merged[field] = list(
                dict.fromkeys((existing.get(field) or []) + (candidate.get(field) or []))
            )
        if not merged.get("venue_name") and candidate.get("venue_name"):
            for field in (
                "venue_name",
                "venue_acronym",
                "venue_type",
                "venue_tier",
                "conference",
                "publication_status",
            ):
                merged[field] = candidate.get(field)
        return merged

    def save_papers(self, papers: List[Dict[str, Any]], output_path: str = "data/papers.json") -> None:
        """Merge fetched papers into the local dataset."""

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        existing_papers = []
        if output_file.exists():
            with output_file.open("r", encoding="utf-8") as handle:
                existing_papers = json.load(handle)

        existing_by_key = {
            (paper.get("arxiv_id") or strip_arxiv_version(paper.get("id")) or paper.get("id")): paper
            for paper in existing_papers
        }

        new_count = 0
        for paper in papers:
            key = paper.get("arxiv_id") or strip_arxiv_version(paper.get("id")) or paper["id"]
            if key in existing_by_key:
                existing_by_key[key] = self._merge_duplicate(existing_by_key[key], paper)
            else:
                existing_by_key[key] = paper
                new_count += 1

        merged_papers = list(existing_by_key.values())
        merged_papers.sort(key=paper_sort_key, reverse=True)

        with output_file.open("w", encoding="utf-8") as handle:
            json.dump(merged_papers, handle, ensure_ascii=False, indent=2)

        logger.info("Saved %s new papers, %s total", new_count, len(merged_papers))

    def run(self) -> None:
        logger.info("=" * 60)
        logger.info("Starting paper fetch")
        logger.info("=" * 60)

        papers = self.fetch_arxiv_papers()
        if papers:
            self.save_papers(papers)
            logger.info("Fetch complete: %s papers", len(papers))
        else:
            logger.warning("No papers fetched")

        logger.info("=" * 60)


def main() -> None:
    fetcher = PaperFetcher()
    fetcher.run()


if __name__ == "__main__":
    main()
