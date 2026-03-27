#!/usr/bin/env python3
"""Rebuild structured metadata for an existing paper dataset."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config_loader import load_config
from scripts.paper_processing import PaperProcessor, paper_sort_key


def reindex_papers(
    data_path: str = "data/papers.json",
    config_path: str = "config.yaml",
) -> List[Dict[str, Any]]:
    config = load_config(config_path)
    processor = PaperProcessor(config)

    input_path = Path(data_path)
    with input_path.open("r", encoding="utf-8") as handle:
        papers = json.load(handle)

    reindexed = [processor.enrich_paper(paper) for paper in papers]
    reindexed.sort(key=paper_sort_key, reverse=True)

    with input_path.open("w", encoding="utf-8") as handle:
        json.dump(reindexed, handle, ensure_ascii=False, indent=2)

    return reindexed


def main() -> None:
    reindexed = reindex_papers()
    print(f"Reindexed {len(reindexed)} papers")


if __name__ == "__main__":
    main()
