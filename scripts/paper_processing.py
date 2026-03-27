#!/usr/bin/env python3
"""Paper normalization, venue parsing, and structured tagging."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
ARXIV_VERSION_RE = re.compile(r"v\d+$", re.IGNORECASE)

STATUS_PATTERNS = {
    "published": [
        re.compile(r"\bpublished\s+(?:in|at|by|with)\b", re.IGNORECASE),
        re.compile(r"\bappeared\s+in\b", re.IGNORECASE),
        re.compile(r"\bpresented\s+at\b", re.IGNORECASE),
    ],
    "accepted": [
        re.compile(r"\baccepted\s+(?:at|to|by|for)\b", re.IGNORECASE),
        re.compile(r"\baccepted\s+for\s+publication\b", re.IGNORECASE),
        re.compile(r"\bto\s+appear\s+in\b", re.IGNORECASE),
    ],
    "submitted": [
        re.compile(r"\bsubmitted\s+(?:to|for)\b", re.IGNORECASE),
        re.compile(r"\bunder\s+review\b", re.IGNORECASE),
        re.compile(r"\bunder\s+submission\b", re.IGNORECASE),
        re.compile(r"\bfor\s+review\b", re.IGNORECASE),
        re.compile(r"\bunder\s+consideration\b", re.IGNORECASE),
    ],
    "preprint": [
        re.compile(r"\bpreprint\b", re.IGNORECASE),
        re.compile(r"\barxiv\s+version\b", re.IGNORECASE),
    ],
}

VENUE_FALLBACK_PATTERNS = [
    (
        "journal",
        re.compile(
            r"\b(IEEE(?:/[A-Z]+)?\s+(?:Transactions on|Journal of|Journal on)"
            r"[^.;\n]{0,140})",
            re.IGNORECASE,
        ),
    ),
    (
        "journal",
        re.compile(
            r"\b(IEEE\s+Wireless\s+Communications\s+Letters)\b",
            re.IGNORECASE,
        ),
    ),
]


def _collapse_spaces(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_lookup(text: str) -> str:
    return _collapse_spaces(NON_ALNUM_RE.sub(" ", text.lower()))


def compile_phrase_pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(normalize_lookup(phrase))
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)


def sanitize_venue_text(text: str) -> str:
    cleaned = URL_RE.sub(" ", text or "")
    cleaned = re.sub(
        r"\b\d+\s*(?:pages?|figures?|tables?|appendices?)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.replace("\n", " ")
    return _collapse_spaces(cleaned)


def strip_arxiv_version(arxiv_id: str | None) -> str | None:
    if not arxiv_id:
        return None
    return ARXIV_VERSION_RE.sub("", arxiv_id)


def normalize_title(title: str | None) -> str:
    return normalize_lookup(title or "")


def build_text_blob(paper: Dict[str, Any]) -> str:
    parts = [
        paper.get("title", ""),
        paper.get("abstract", ""),
        paper.get("comment", ""),
        paper.get("journal_ref", ""),
        " ".join(paper.get("categories", []) or []),
        paper.get("primary_category", ""),
        paper.get("venue_name", ""),
    ]
    return _collapse_spaces(" ".join(str(part) for part in parts if part))


def extract_first_url(text: str | None, domain: str | None = None) -> Optional[str]:
    if not text:
        return None
    for match in URL_RE.findall(text):
        if domain and domain.lower() not in match.lower():
            continue
        return match.rstrip(".,;)")
    return None


@dataclass(frozen=True)
class VenueEntry:
    canonical_name: str
    acronym: str
    venue_type: str
    tier: str
    aliases: tuple[str, ...]


class VenueRegistry:
    """Canonical venue registry with alias matching."""

    def __init__(self, config: Dict[str, Any]):
        registry_config = config.get("venue_registry", {})
        self.noise_tokens = set(registry_config.get("noise_tokens", []))
        self.entries: List[VenueEntry] = []
        self.alias_patterns: List[tuple[int, re.Pattern[str], VenueEntry]] = []

        for canonical_name, entry in registry_config.get("entries", {}).items():
            aliases = [canonical_name, entry.get("acronym", "")]
            aliases.extend(entry.get("aliases", []))
            deduped_aliases = tuple(dict.fromkeys(alias for alias in aliases if alias))
            venue_entry = VenueEntry(
                canonical_name=canonical_name,
                acronym=entry.get("acronym", canonical_name),
                venue_type=entry.get("type", "conference"),
                tier=entry.get("tier", "other"),
                aliases=deduped_aliases,
            )
            self.entries.append(venue_entry)
            for alias in deduped_aliases:
                normalized = normalize_lookup(alias)
                if not normalized:
                    continue
                self.alias_patterns.append(
                    (len(normalized), compile_phrase_pattern(alias), venue_entry)
                )

        self.alias_patterns.sort(key=lambda item: item[0], reverse=True)

    def match(self, journal_ref: str | None, comment: str | None) -> Dict[str, Optional[str]]:
        candidates = []
        if journal_ref:
            candidates.append(("journal_ref", sanitize_venue_text(journal_ref)))
        if comment:
            candidates.append(("comment", sanitize_venue_text(comment)))

        for source_name, text in candidates:
            for _, pattern, entry in self.alias_patterns:
                if pattern.search(normalize_lookup(text)):
                    return {
                        "venue_name": entry.canonical_name,
                        "venue_acronym": entry.acronym,
                        "venue_type": entry.venue_type,
                        "venue_tier": entry.tier,
                        "matched_from": source_name,
                    }

        for source_name, text in candidates:
            fallback = self._fallback_match(text)
            if fallback:
                fallback["matched_from"] = source_name
                return fallback

        return {
            "venue_name": None,
            "venue_acronym": None,
            "venue_type": None,
            "venue_tier": None,
            "matched_from": None,
        }

    def _fallback_match(self, text: str) -> Optional[Dict[str, Optional[str]]]:
        normalized = normalize_lookup(text)
        if not normalized or normalized in self.noise_tokens:
            return None

        for venue_type, pattern in VENUE_FALLBACK_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue

            venue_name = _collapse_spaces(match.group(1).strip(" ,.;"))
            lowered = normalize_lookup(venue_name)
            if not lowered or lowered in self.noise_tokens:
                continue

            return {
                "venue_name": venue_name,
                "venue_acronym": venue_name,
                "venue_type": venue_type,
                "venue_tier": "other",
            }

        return None


class KeywordTaxonomy:
    """Compiled keyword groups for structured tagging."""

    def __init__(self, taxonomy_config: Dict[str, Any]):
        self.topic_patterns = self._compile_group(taxonomy_config.get("topic_tags", {}))
        self.method_patterns = self._compile_group(taxonomy_config.get("method_tags", {}))
        self.scenario_patterns = self._compile_group(
            taxonomy_config.get("scenario_tags", {})
        )
        self.negative_patterns = self._compile_group(
            taxonomy_config.get("negative_rules", {})
        )

    @staticmethod
    def _compile_group(group: Dict[str, List[str]]) -> Dict[str, List[re.Pattern[str]]]:
        compiled: Dict[str, List[re.Pattern[str]]] = {}
        for label, keywords in group.items():
            compiled[label] = [compile_phrase_pattern(keyword) for keyword in keywords]
        return compiled

    @staticmethod
    def _match_group(
        patterns: Dict[str, List[re.Pattern[str]]], text: str
    ) -> List[str]:
        matches = []
        normalized = normalize_lookup(text)
        for label, regexes in patterns.items():
            if any(regex.search(normalized) for regex in regexes):
                matches.append(label)
        return matches

    def classify(self, text: str) -> Dict[str, List[str]]:
        return {
            "topic_tags": self._match_group(self.topic_patterns, text),
            "method_tags": self._match_group(self.method_patterns, text),
            "scenario_tags": self._match_group(self.scenario_patterns, text),
            "negative_hits": self._match_group(self.negative_patterns, text),
        }


class PaperProcessor:
    """Enrich papers with normalized venue metadata and structured tags."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.registry = VenueRegistry(config)
        self.taxonomy = KeywordTaxonomy(config.get("taxonomy", {}))
        self.policy = config.get("filter_policy", {})
        self.primary_categories = set(self.policy.get("primary_categories", []))
        self.secondary_categories = set(self.policy.get("secondary_categories", []))
        self.comm_categories = set(self.policy.get("comm_categories", []))
        self.secondary_network_topics = set(
            self.policy.get("secondary_network_topics", [])
        )
        self.communication_topics = {
            "Wireless Communications",
            "Network Optimization",
            "Resource Allocation",
            "Scheduling & Control",
            "Edge Intelligence",
            "Federated Learning",
            "Semantic Communications",
            "Signal Processing",
            "Networked Systems",
            "IoT Systems",
        }
        self.rl_topics = {"Reinforcement Learning", "Multi-Agent RL"}
        self.ai_anchor_tiers = {"core_ai"}
        self.comm_tiers = {"core_comms", "related_comms"}

    def enrich_paper(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(paper)
        enriched["authors"] = self._normalize_authors(enriched.get("authors", []))
        enriched["categories"] = sorted(
            dict.fromkeys(enriched.get("categories", []) or [])
        )
        enriched["arxiv_id"] = strip_arxiv_version(enriched.get("id"))
        enriched["normalized_title"] = normalize_title(enriched.get("title"))

        venue_meta = self.registry.match(
            enriched.get("journal_ref"),
            enriched.get("comment"),
        )
        enriched.update(venue_meta)
        enriched["publication_status"] = self._infer_status(
            enriched.get("journal_ref"),
            enriched.get("comment"),
            has_venue=bool(enriched.get("venue_name")),
        )
        enriched["conference"] = enriched.get("venue_name")
        if not enriched.get("venue_name"):
            enriched["venue_tier"] = None

        text_blob = build_text_blob(enriched)
        classified = self.taxonomy.classify(text_blob)
        topic_tags = classified["topic_tags"]
        method_tags = classified["method_tags"]
        scenario_tags = classified["scenario_tags"]
        negative_hits = classified["negative_hits"]

        relevance_score, interest_track, match_reasons = self._score_and_track(
            enriched,
            topic_tags,
            method_tags,
            scenario_tags,
            negative_hits,
        )

        enriched["topic_tags"] = topic_tags
        enriched["method_tags"] = method_tags
        enriched["scenario_tags"] = scenario_tags
        enriched["interest_track"] = interest_track
        enriched["relevance_score"] = relevance_score
        enriched["match_reasons"] = match_reasons
        enriched["tags"] = list(dict.fromkeys(topic_tags + method_tags + scenario_tags))

        enriched["code_link"] = (
            extract_first_url(enriched.get("comment"), "github.com")
            or extract_first_url(enriched.get("abstract"), "github.com")
        )
        enriched["project_link"] = (
            extract_first_url(enriched.get("comment"))
            or extract_first_url(enriched.get("abstract"))
        )

        if not enriched.get("arxiv_url") and enriched.get("arxiv_id"):
            enriched["arxiv_url"] = f"https://arxiv.org/abs/{enriched['arxiv_id']}"
        if not enriched.get("pdf_url") and enriched.get("arxiv_id"):
            enriched["pdf_url"] = f"https://arxiv.org/pdf/{enriched['arxiv_id']}.pdf"

        return enriched

    def should_keep_secondary_category_paper(self, paper: Dict[str, Any]) -> bool:
        return bool(paper.get("method_tags")) or paper.get("venue_tier") in self.ai_anchor_tiers

    def _normalize_authors(self, authors: Iterable[str] | str) -> List[str]:
        if isinstance(authors, str):
            if not authors.strip():
                return []
            if " and " in authors:
                return [part.strip() for part in authors.split(" and ") if part.strip()]
            if "," in authors:
                return [part.strip() for part in authors.split(",") if part.strip()]
            return [authors.strip()]
        return [str(author).strip() for author in authors if str(author).strip()]

    def _infer_status(
        self,
        journal_ref: str | None,
        comment: str | None,
        has_venue: bool,
    ) -> str:
        combined = sanitize_venue_text(" ".join(part for part in [journal_ref, comment] if part))
        if not combined:
            return "preprint"

        for status in ("submitted", "accepted", "published", "preprint"):
            if any(pattern.search(combined) for pattern in STATUS_PATTERNS[status]):
                return status

        if journal_ref and has_venue:
            return "published"
        if has_venue:
            return "accepted"
        return "preprint"

    def _score_and_track(
        self,
        paper: Dict[str, Any],
        topic_tags: List[str],
        method_tags: List[str],
        scenario_tags: List[str],
        negative_hits: List[str],
    ) -> tuple[int, str, List[str]]:
        relevance = 0
        reasons: List[str] = []

        for tag in topic_tags:
            boost = 8 if tag in self.rl_topics else 6
            relevance += boost
            reasons.append(f"topic:{tag}")

        for tag in method_tags:
            relevance += 3
            reasons.append(f"method:{tag}")

        for tag in scenario_tags:
            relevance += 4
            reasons.append(f"scenario:{tag}")

        category_hits = set(paper.get("categories", []) or [])
        primary_category = paper.get("primary_category")
        if primary_category:
            category_hits.add(primary_category)

        if category_hits & self.primary_categories:
            relevance += 4
            reasons.append("signal:primary_category")
        if category_hits & self.comm_categories:
            relevance += 5
            reasons.append("signal:comm_category")

        venue_tier = paper.get("venue_tier")
        if venue_tier == "core_comms":
            relevance += 8
            reasons.append("signal:core_comms_venue")
        elif venue_tier == "related_comms":
            relevance += 6
            reasons.append("signal:related_comms_venue")
        elif venue_tier == "core_ai":
            relevance += 5
            reasons.append("signal:core_ai_venue")
        elif venue_tier == "other":
            relevance += 2
            reasons.append("signal:other_venue")

        status = paper.get("publication_status")
        if status == "published":
            relevance += 2
            reasons.append("signal:published")
        elif status == "accepted":
            relevance += 1
            reasons.append("signal:accepted")

        comm_or_rl_topic = any(tag in self.communication_topics | self.rl_topics for tag in topic_tags)
        has_support_signal = bool(
            (category_hits & self.primary_categories)
            or venue_tier in self.comm_tiers | self.ai_anchor_tiers
            or scenario_tags
        )
        communication_context = bool(
            (category_hits & self.comm_categories)
            or venue_tier in self.comm_tiers
            or scenario_tags
            or any(tag in self.communication_topics for tag in topic_tags)
        )

        disqualified_core = self._disqualify_core(topic_tags, communication_context, negative_hits)

        if comm_or_rl_topic and has_support_signal and not disqualified_core:
            interest_track = "core_rl_comms"
            relevance += 12
            reasons.append("track:core_rl_comms")
        elif method_tags and (
            venue_tier in self.ai_anchor_tiers
            or any(tag in self.secondary_network_topics for tag in topic_tags)
            or primary_category in self.secondary_categories
        ):
            interest_track = "secondary_llm_mm_nn"
            relevance += 8
            reasons.append("track:secondary_llm_mm_nn")
        else:
            interest_track = "other"

        return relevance, interest_track, reasons

    def _disqualify_core(
        self,
        topic_tags: List[str],
        communication_context: bool,
        negative_hits: List[str],
    ) -> bool:
        if communication_context:
            return False
        if "pure_cv_exclusions" in negative_hits:
            return True
        if "biomedical_exclusions" in negative_hits and not topic_tags:
            return True
        return False


def paper_sort_key(paper: Dict[str, Any]) -> tuple[int, str, str]:
    return (
        int(paper.get("relevance_score", 0)),
        paper.get("published", ""),
        paper.get("title", ""),
    )


def now_utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
