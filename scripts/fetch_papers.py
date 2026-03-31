#!/usr/bin/env python3
"""Fetch and normalize DailyPaper records from ArXiv and formal venues."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config_loader import load_config
from scripts.paper_processing import (
    PaperProcessor,
    normalize_doi,
    normalize_lookup,
    normalize_title,
    paper_sort_key,
    pick_better_status,
    strip_arxiv_version,
)
from scripts.source_adapters import CrossrefAdapter, DBLPAdapter, OpenReviewAdapter


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

PROVIDER_PRIORITY = {
    "unknown": 0,
    "arxiv": 1,
    "openreview": 3,
    "dblp": 4,
    "crossref": 4,
}


def _is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _combine_unique(left: Iterable[Any] | None, right: Iterable[Any] | None) -> List[Any]:
    items: List[Any] = []
    for value in list(left or []) + list(right or []):
        if value in (None, "", [], {}):
            continue
        if value not in items:
            items.append(value)
    return items


def _first_author_key(paper: Dict[str, Any]) -> str | None:
    authors = paper.get("authors") or []
    if not authors:
        return None
    return normalize_lookup(str(authors[0]))


class PaperDeduper:
    """Merge papers by arXiv ID, DOI, or normalized title/author/year."""

    def __init__(self, merge_fn):
        self.merge_fn = merge_fn
        self.records: List[Dict[str, Any] | None] = []
        self.record_keys: List[set[Tuple[str, str]]] = []
        self.key_to_index: Dict[Tuple[str, str], int] = {}

    def add(self, paper: Dict[str, Any]) -> None:
        keys = self._keys_for(paper)
        matches = sorted({self.key_to_index[key] for key in keys if key in self.key_to_index})

        if not matches:
            index = len(self.records)
            self.records.append(paper)
            self.record_keys.append(set(keys))
            for key in keys:
                self.key_to_index[key] = index
            return

        target = matches[0]
        merged = self.records[target] or {}
        for other_index in matches[1:]:
            if self.records[other_index] is None:
                continue
            merged = self.merge_fn(merged, self.records[other_index] or {})
            for key in self.record_keys[other_index]:
                self.key_to_index[key] = target
            self.record_keys[target].update(self.record_keys[other_index])
            self.records[other_index] = None
            self.record_keys[other_index] = set()

        merged = self.merge_fn(merged, paper)
        self.records[target] = merged
        final_keys = self._keys_for(merged)
        self.record_keys[target].update(final_keys)
        for key in self.record_keys[target]:
            self.key_to_index[key] = target

    def values(self) -> List[Dict[str, Any]]:
        return [record for record in self.records if record is not None]

    @staticmethod
    def _keys_for(paper: Dict[str, Any]) -> List[Tuple[str, str]]:
        keys: List[Tuple[str, str]] = []
        arxiv_id = strip_arxiv_version(paper.get("arxiv_id") or paper.get("id"))
        if arxiv_id:
            keys.append(("arxiv_id", arxiv_id))

        doi = normalize_doi(paper.get("doi"))
        if doi:
            keys.append(("doi", doi))

        normalized_title = paper.get("normalized_title") or normalize_title(paper.get("title"))
        first_author = _first_author_key(paper)
        published = paper.get("published") or paper.get("updated") or ""
        year = str(published)[:4] if published else ""
        if normalized_title and first_author and year:
            keys.append(("title_author_year", f"{normalized_title}|{first_author}|{year}"))

        return keys


class PaperFetcher:
    """Multi-source fetcher with structured enrichment and deduplication."""

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

        deduper = PaperDeduper(self._merge_duplicate)

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

                deduper.add(paper)
                category_count += 1

            logger.info("Collected %s recent papers from %s", category_count, category)

        papers = deduper.values()
        papers.sort(key=paper_sort_key, reverse=True)
        logger.info("ArXiv fetch complete: %s unique papers", len(papers))
        return papers

    def fetch_external_papers(self) -> List[Dict[str, Any]]:
        """Fetch formal venue metadata from external adapters."""

        papers: List[Dict[str, Any]] = []
        for adapter_cls in (CrossrefAdapter, DBLPAdapter, OpenReviewAdapter):
            adapter = adapter_cls(self.config)
            if not adapter.enabled:
                continue

            logger.info("Fetching external source: %s", adapter.name)
            try:
                source_papers = adapter.fetch()
            except Exception:
                logger.exception("Source adapter %s failed", adapter.name)
                continue

            logger.info("Fetched %s records from %s", len(source_papers), adapter.name)
            papers.extend(self.processor.enrich_paper(paper) for paper in source_papers)

        deduper = PaperDeduper(self._merge_duplicate)
        for paper in papers:
            deduper.add(paper)

        deduped = deduper.values()
        deduped.sort(key=paper_sort_key, reverse=True)
        return deduped

    def fetch_all_papers(self) -> List[Dict[str, Any]]:
        deduper = PaperDeduper(self._merge_duplicate)
        for paper in self.fetch_arxiv_papers():
            deduper.add(paper)
        for paper in self.fetch_external_papers():
            deduper.add(paper)

        papers = deduper.values()
        papers.sort(key=paper_sort_key, reverse=True)
        logger.info("Unified fetch complete: %s unique papers", len(papers))
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
            "source_url": result.entry_id,
            "source": "ArXiv",
            "source_provider": "arxiv",
            "venue": category,
            "source_category": category,
            "comment": result.comment if getattr(result, "comment", None) else None,
            "journal_ref": (
                result.journal_ref if getattr(result, "journal_ref", None) else None
            ),
            "doi": normalize_doi(getattr(result, "doi", None)),
        }

    def _preferred_pair(
        self,
        left: Dict[str, Any],
        right: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        if self._quality(right) > self._quality(left):
            return right, left
        return left, right

    def _quality(self, paper: Dict[str, Any]) -> tuple[int, int, int, int, int, int]:
        provider = normalize_lookup(paper.get("source_provider") or "unknown")
        status = normalize_lookup(paper.get("publication_status") or "unknown")
        return (
            PROVIDER_PRIORITY.get(provider, 0),
            1 if paper.get("doi") else 0,
            1 if paper.get("venue_name") else 0,
            1 if paper.get("paper_type") and paper.get("paper_type") != "other" else 0,
            1 if paper.get("abstract") else 0,
            len(paper.get("authors") or []),
        )

    def _merge_duplicate(
        self,
        existing: Dict[str, Any],
        candidate: Dict[str, Any],
    ) -> Dict[str, Any]:
        preferred, fallback = self._preferred_pair(existing, candidate)
        merged: Dict[str, Any] = {}

        all_keys = set(existing) | set(candidate)
        for key in all_keys:
            preferred_value = preferred.get(key)
            fallback_value = fallback.get(key)

            if key in {
                "authors",
                "categories",
                "tags",
                "topic_tags",
                "method_tags",
                "scenario_tags",
                "match_reasons",
            } or isinstance(preferred_value, list) or isinstance(fallback_value, list):
                merged[key] = _combine_unique(
                    preferred_value if isinstance(preferred_value, list) else [preferred_value] if preferred_value else [],
                    fallback_value if isinstance(fallback_value, list) else [fallback_value] if fallback_value else [],
                )
                continue

            if key == "publication_status":
                merged[key] = pick_better_status(preferred_value, fallback_value)
                continue

            if key == "paper_type":
                if "review" in {preferred_value, fallback_value}:
                    merged[key] = "review"
                else:
                    merged[key] = preferred_value or fallback_value
                continue

            merged[key] = preferred_value if not _is_empty(preferred_value) else fallback_value

        merged["authors"] = _combine_unique(existing.get("authors"), candidate.get("authors"))
        merged["categories"] = _combine_unique(existing.get("categories"), candidate.get("categories"))
        merged["tags"] = _combine_unique(existing.get("tags"), candidate.get("tags"))
        merged["topic_tags"] = _combine_unique(existing.get("topic_tags"), candidate.get("topic_tags"))
        merged["method_tags"] = _combine_unique(existing.get("method_tags"), candidate.get("method_tags"))
        merged["scenario_tags"] = _combine_unique(existing.get("scenario_tags"), candidate.get("scenario_tags"))
        merged["match_reasons"] = _combine_unique(existing.get("match_reasons"), candidate.get("match_reasons"))

        merged["arxiv_id"] = strip_arxiv_version(
            merged.get("arxiv_id")
            or existing.get("arxiv_id")
            or candidate.get("arxiv_id")
            or merged.get("id")
        )
        merged["doi"] = normalize_doi(merged.get("doi") or existing.get("doi") or candidate.get("doi"))
        if not merged.get("id"):
            merged["id"] = (
                merged.get("arxiv_id")
                or (f"doi:{merged['doi']}" if merged.get("doi") else None)
                or existing.get("id")
                or candidate.get("id")
            )

        return self.processor.enrich_paper(merged)

    def _deduplicate_papers(self, papers: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduper = PaperDeduper(self._merge_duplicate)
        for paper in papers:
            deduper.add(self.processor.enrich_paper(paper))
        merged = deduper.values()
        merged.sort(key=paper_sort_key, reverse=True)
        return merged

    def save_papers(self, papers: List[Dict[str, Any]], output_path: str = "data/papers.json") -> None:
        """Merge fetched papers into the local dataset."""

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        existing_papers: List[Dict[str, Any]] = []
        if output_file.exists():
            with output_file.open("r", encoding="utf-8") as handle:
                existing_papers = json.load(handle)

        merged_papers = self._deduplicate_papers(existing_papers + papers)

        with output_file.open("w", encoding="utf-8") as handle:
            json.dump(merged_papers, handle, ensure_ascii=False, indent=2)

        logger.info("Saved %s total papers", len(merged_papers))

    def run(self) -> None:
        logger.info("=" * 60)
        logger.info("Starting multi-source paper fetch")
        logger.info("=" * 60)

        papers = self.fetch_all_papers()
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
