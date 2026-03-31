#!/usr/bin/env python3
"""Generate the static DailyPaper site and monthly data index."""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config_loader import load_config
from scripts.paper_processing import now_utc_timestamp


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HTMLGenerator:
    """Static site generator for the refactored DailyPaper UI."""

    def __init__(
        self,
        data_path: str = "data/papers.json",
        output_dir: str = "docs",
        config_path: str = "config.yaml",
    ):
        self.data_path = Path(data_path)
        self.output_dir = Path(output_dir)
        self.config = load_config(config_path)
        self.papers: List[Dict[str, Any]] = []
        self.papers_by_month: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def load_papers(self) -> None:
        if not self.data_path.exists():
            logger.warning("Data file does not exist: %s", self.data_path)
            return

        with self.data_path.open("r", encoding="utf-8") as handle:
            self.papers = json.load(handle)

        logger.info("Loaded %s papers", len(self.papers))
        self.papers_by_month.clear()
        for paper in self.papers:
            published = paper.get("published", "")
            year_month = published[:7] if len(published) >= 7 else "unknown"
            self.papers_by_month[year_month].append(paper)

    def generate_monthly_data_files(self) -> None:
        data_dir = self.output_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        months_index = []
        for year_month in sorted(self.papers_by_month.keys(), reverse=True):
            papers = self.papers_by_month[year_month]
            file_path = data_dir / f"{year_month}.json"
            with file_path.open("w", encoding="utf-8") as handle:
                json.dump(papers, handle, ensure_ascii=False, indent=2)

            months_index.append(
                {
                    "month": year_month,
                    "count": len(papers),
                    "track_counts": dict(Counter(p.get("interest_track", "other") for p in papers)),
                    "status_counts": dict(
                        Counter(p.get("publication_status", "unknown") for p in papers)
                    ),
                }
            )
            logger.info("Generated monthly data file: %s", file_path)

        index_payload = {
            "generated_at": now_utc_timestamp(),
            "defaults": {
                "interest_track": self.config["filter_policy"]["default_track"],
                "sort": self.config["filter_policy"]["default_sort"],
            },
            "months": months_index,
            "filters": self._build_filter_metadata(),
        }

        with (data_dir / "index.json").open("w", encoding="utf-8") as handle:
            json.dump(index_payload, handle, ensure_ascii=False, indent=2)

        logger.info("Generated metadata index: %s", data_dir / "index.json")

    def _build_filter_metadata(self) -> Dict[str, List[Dict[str, Any]]]:
        filter_policy = self.config["filter_policy"]
        track_labels = filter_policy["track_labels"]
        status_labels = filter_policy["status_labels"]
        paper_type_labels = filter_policy["paper_type_labels"]
        venue_tier_labels = filter_policy["venue_tier_labels"]

        topic_counts = Counter()
        method_counts = Counter()
        scenario_counts = Counter()
        track_counts = Counter()
        status_counts = Counter()
        paper_type_counts = Counter()
        venue_tier_counts = Counter()
        venue_counts = Counter()
        venue_meta: Dict[str, Dict[str, str]] = {}

        for paper in self.papers:
            topic_counts.update(paper.get("topic_tags", []))
            method_counts.update(paper.get("method_tags", []))
            scenario_counts.update(paper.get("scenario_tags", []))
            track_counts.update([paper.get("interest_track", "other")])
            status_counts.update([paper.get("publication_status", "unknown")])
            paper_type_counts.update([paper.get("paper_type", "other")])
            venue_tier_counts.update([paper.get("venue_tier") or "other"])

            venue_value = paper.get("venue_filter_value")
            if venue_value:
                venue_counts.update([venue_value])
                venue_meta.setdefault(
                    venue_value,
                    {
                        "label": paper.get("venue_filter_label") or venue_value,
                        "title": paper.get("venue_name") or venue_value,
                    },
                )

        return {
            "interest_track": [
                {"value": value, "label": label, "count": track_counts.get(value, 0)}
                for value, label in track_labels.items()
            ],
            "publication_status": [
                {"value": value, "label": label, "count": status_counts.get(value, 0)}
                for value, label in status_labels.items()
                if value != "all"
            ],
            "paper_type": [
                {"value": value, "label": label, "count": paper_type_counts.get(value, 0)}
                for value, label in paper_type_labels.items()
                if value != "all"
            ],
            "venue_tier": [
                {"value": value, "label": label, "count": venue_tier_counts.get(value, 0)}
                for value, label in venue_tier_labels.items()
                if value != "all"
            ],
            "venues": self._build_venue_items(venue_counts, venue_meta),
            "topic_tags": self._facet_items(topic_counts),
            "method_tags": self._facet_items(method_counts),
            "scenario_tags": self._facet_items(scenario_counts),
        }

    def _build_venue_items(
        self,
        venue_counts: Counter,
        venue_meta: Dict[str, Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen = set()

        registry_entries = self.config.get("venue_registry", {}).get("entries", {})
        for canonical_name, entry in registry_entries.items():
            value = entry.get("acronym") or canonical_name
            if value in seen or venue_counts.get(value, 0) == 0:
                continue
            items.append(
                {
                    "value": value,
                    "label": value,
                    "count": venue_counts.get(value, 0),
                    "title": canonical_name,
                }
            )
            seen.add(value)

        dynamic_items = sorted(
            (
                {
                    "value": value,
                    "label": meta["label"],
                    "count": venue_counts.get(value, 0),
                    "title": meta["title"],
                }
                for value, meta in venue_meta.items()
                if value not in seen
            ),
            key=lambda item: (-item["count"], item["label"]),
        )
        items.extend(dynamic_items)
        return items

    @staticmethod
    def _facet_items(counter: Counter) -> List[Dict[str, Any]]:
        return [
            {"value": value, "label": value, "count": count}
            for value, count in counter.most_common()
        ]

    def generate_index_html(self) -> None:
        updated_time = now_utc_timestamp()
        total_papers = len(self.papers)
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DailyPaperZWJ | RL+通信 与 LLM/多模态论文雷达</title>
    <link rel="stylesheet" href="css/style.css">
</head>
<body>
    <header class="hero">
        <div class="container hero-inner">
            <div class="hero-copy">
                <p class="eyebrow">DailyPaperZWJ</p>
                <h1>RL+通信主线，兼顾 LLM、多模态与神经网络更新</h1>
                <p class="hero-summary">按文献类型、Venue、topic、method、scenario 和发表状态筛选最新论文，默认聚焦高相关的 RL+通信结果。</p>
            </div>
            <div class="hero-stats">
                <div class="stat-card">
                    <span class="stat-label">总论文数</span>
                    <strong class="stat-value">{total_papers}</strong>
                </div>
                <div class="stat-card">
                    <span class="stat-label">最后生成</span>
                    <strong class="stat-value small">{updated_time}</strong>
                </div>
            </div>
        </div>
    </header>

    <main class="container page-shell">
        <section class="control-panel">
            <div class="panel-head">
                <h2>筛选面板</h2>
                <p>默认只显示 RL+通信主线结果，可切换到次级兴趣轨并按正式 Venue 精筛。</p>
            </div>

            <div class="filter-grid">
                <section class="filter-group">
                    <div class="filter-title-row">
                        <h3>月份</h3>
                    </div>
                    <div id="monthFilters" class="filters"></div>
                </section>

                <section class="filter-group">
                    <div class="filter-title-row">
                        <h3>兴趣轨</h3>
                    </div>
                    <div id="trackFilters" class="filters"></div>
                </section>

                <section class="filter-group">
                    <div class="filter-title-row">
                        <h3>发表状态</h3>
                    </div>
                    <div id="statusFilters" class="filters"></div>
                </section>

                <section class="filter-group">
                    <div class="filter-title-row">
                        <h3>文献类型</h3>
                    </div>
                    <div id="paperTypeFilters" class="filters"></div>
                </section>

                <section class="filter-group">
                    <div class="filter-title-row">
                        <h3>Venue</h3>
                    </div>
                    <div id="venueFilters" class="filters"></div>
                </section>

                <section class="filter-group">
                    <div class="filter-title-row">
                        <h3>Venue 层级</h3>
                    </div>
                    <div id="venueTierFilters" class="filters"></div>
                </section>

                <section class="filter-group">
                    <div class="filter-title-row">
                        <h3>研究主题</h3>
                    </div>
                    <div id="topicFilters" class="filters"></div>
                </section>

                <section class="filter-group">
                    <div class="filter-title-row">
                        <h3>方法标签</h3>
                    </div>
                    <div id="methodFilters" class="filters"></div>
                </section>

                <section class="filter-group">
                    <div class="filter-title-row">
                        <h3>应用场景</h3>
                    </div>
                    <div id="scenarioFilters" class="filters"></div>
                </section>

                <section class="filter-group">
                    <div class="filter-title-row">
                        <h3>排序</h3>
                    </div>
                    <div id="sortFilters" class="filters">
                        <button class="filter-btn sort-btn active" data-sort="relevance-desc">相关性优先</button>
                        <button class="filter-btn sort-btn" data-sort="date-desc">最新优先</button>
                        <button class="filter-btn sort-btn" data-sort="date-asc">最早优先</button>
                    </div>
                </section>
            </div>

            <div class="search-row">
                <input id="searchInput" type="text" placeholder="搜索标题、作者、摘要、venue、标签">
            </div>

            <div class="result-row">
                <div id="resultsCount" class="results-count">加载中...</div>
                <div class="export-controls">
                    <button id="selectAllBtn" class="ghost-btn">全选当前结果</button>
                    <button id="clearAllBtn" class="ghost-btn">清空选择</button>
                    <button id="exportBtn" class="solid-btn">导出 BibTeX (<span id="selectedCount">0</span>)</button>
                </div>
            </div>
        </section>

        <section class="paper-section">
            <div id="papersContainer" class="paper-list"></div>
            <div class="load-more-wrap">
                <button id="loadMoreBtn" class="solid-btn">加载更多</button>
            </div>
        </section>
    </main>

    <footer class="site-footer">
        <div class="container">
            <p>数据源: ArXiv、Crossref、DBLP、OpenReview。当前版本已支持正式 Venue 归一化、多源去重，以及文献类型 / Venue 筛选。</p>
        </div>
    </footer>

    <script src="js/main.js"></script>
</body>
</html>
"""

        output_file = self.output_dir / "index.html"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding="utf-8") as handle:
            handle.write(html)
        logger.info("Generated index page: %s", output_file)

    def generate_css(self) -> None:
        logger.info("Static CSS is maintained in docs/css/style.css")

    def generate_js(self) -> None:
        logger.info("Static JS is maintained in docs/js/main.js")

    def run(self) -> None:
        logger.info("Generating static site...")
        self.load_papers()
        self.generate_monthly_data_files()
        self.generate_css()
        self.generate_js()
        self.generate_index_html()
        logger.info("Site generation complete: %s", self.output_dir)


def main() -> None:
    generator = HTMLGenerator()
    generator.run()


if __name__ == "__main__":
    main()
