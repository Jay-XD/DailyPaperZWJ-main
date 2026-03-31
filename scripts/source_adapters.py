#!/usr/bin/env python3
"""External source adapter implementations for formal venue metadata."""

from __future__ import annotations

import html
import logging
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List

import requests

from scripts.paper_processing import SOURCE_PROVIDER_LABELS, VenueRegistry, normalize_doi


logger = logging.getLogger(__name__)

TAG_RE = re.compile(r"<[^>]+>")


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _strip_markup(text: str | None) -> str | None:
    if not text:
        return None
    stripped = TAG_RE.sub(" ", text)
    return html.unescape(re.sub(r"\s+", " ", stripped)).strip() or None


def _date_from_parts(parts: Any) -> str | None:
    if not parts:
        return None
    date_parts = parts[0] if isinstance(parts, list) and parts else parts
    if not isinstance(date_parts, list) or not date_parts:
        return None
    year = int(date_parts[0])
    month = int(date_parts[1]) if len(date_parts) > 1 else 1
    day = int(date_parts[2]) if len(date_parts) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _date_from_crossref(item: Dict[str, Any], *fields: str) -> str | None:
    for field in fields:
        payload = item.get(field) or {}
        date = _date_from_parts(payload.get("date-parts"))
        if date:
            return date
    return None


def _date_from_epoch_millis(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        timestamp = int(value) / 1000
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _extract_openreview_content(content: Dict[str, Any], key: str) -> Any:
    value = content.get(key)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


class BaseSourceAdapter(ABC):
    """Non-ArXiv source adapter contract for multi-source expansion."""

    name = "base"

    def __init__(
        self,
        config: Dict[str, Any],
        session: requests.Session | None = None,
        now: datetime | None = None,
    ):
        self.config = config
        self.registry = VenueRegistry(config)
        self.adapter_config = config.get("sources", {}).get("adapters", {}).get(self.name, {})
        self.session = session or requests.Session()
        self.now = now or datetime.now(timezone.utc)
        self.base_url = self.adapter_config.get("base_url", "").rstrip("/")
        self.timeout = int(self.adapter_config.get("timeout", 30))
        self.headers = {
            "User-Agent": "DailyPaperZWJ/1.0 (+https://github.com/Jay-XD/DailyPaperZWJ-main)",
            "Accept": "application/json",
        }

    @property
    def enabled(self) -> bool:
        return bool(self.adapter_config.get("enabled", False))

    @abstractmethod
    def fetch(self) -> List[Dict[str, Any]]:
        """Fetch normalized paper records."""

    def _request_json(
        self,
        path: str,
        *,
        params: Dict[str, Any] | None = None,
        json_body: Dict[str, Any] | None = None,
        headers: Dict[str, str] | None = None,
        method: str = "GET",
    ) -> Dict[str, Any]:
        response = self.session.request(
            method=method,
            url=f"{self.base_url}{path}",
            params=params,
            json=json_body,
            headers={**self.headers, **(headers or {})},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _build_paper(
        self,
        *,
        record_id: str,
        title: str,
        authors: Iterable[str],
        abstract: str | None,
        published: str | None,
        updated: str | None,
        source_provider: str,
        venue_name: str | None = None,
        venue_acronym: str | None = None,
        venue_text: str | None = None,
        venue_type: str | None = None,
        venue_tier: str | None = None,
        publication_status: str | None = None,
        doi: str | None = None,
        source_url: str | None = None,
        pdf_url: str | None = None,
        comment: str | None = None,
        journal_ref: str | None = None,
    ) -> Dict[str, Any]:
        venue_meta = self.registry.normalize(
            venue_name=venue_name,
            venue_acronym=venue_acronym,
            venue_text=venue_text,
        )
        normalized_venue_name = venue_meta["venue_name"] or venue_name
        normalized_venue_acronym = venue_meta["venue_acronym"] or venue_acronym or normalized_venue_name
        normalized_venue_type = venue_meta["venue_type"] or venue_type
        normalized_venue_tier = venue_meta["venue_tier"] or venue_tier

        return {
            "id": record_id,
            "arxiv_id": None,
            "title": title,
            "authors": list(authors),
            "abstract": abstract,
            "published": published or updated or self.now.strftime("%Y-%m-%d"),
            "updated": updated or published or self.now.strftime("%Y-%m-%d"),
            "categories": [],
            "primary_category": None,
            "pdf_url": pdf_url,
            "arxiv_url": None,
            "source_url": source_url,
            "source": SOURCE_PROVIDER_LABELS.get(source_provider, source_provider),
            "source_provider": source_provider,
            "venue": normalized_venue_name or venue_text,
            "venue_name": normalized_venue_name,
            "venue_acronym": normalized_venue_acronym,
            "venue_type": normalized_venue_type,
            "venue_tier": normalized_venue_tier,
            "comment": comment,
            "journal_ref": journal_ref,
            "publication_status": publication_status,
            "doi": normalize_doi(doi),
            "doi_url": f"https://doi.org/{normalize_doi(doi)}" if normalize_doi(doi) else None,
        }


class CrossrefAdapter(BaseSourceAdapter):
    name = "crossref"

    def fetch(self) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        papers: List[Dict[str, Any]] = []
        from_date = (self.now - timedelta(days=int(self.adapter_config.get("days_back", 365)))).date().isoformat()
        rows = int(self.adapter_config.get("rows_per_request", 100))
        max_pages = int(self.adapter_config.get("max_pages", 2))
        select_fields = ",".join(
            [
                "DOI",
                "URL",
                "title",
                "author",
                "abstract",
                "container-title",
                "short-container-title",
                "issued",
                "published-online",
                "published-print",
                "indexed",
                "created",
                "link",
            ]
        )

        for venue in self.adapter_config.get("venues", []):
            cursor = "*"
            for _ in range(max_pages):
                params = {
                    "filter": f"from-pub-date:{from_date},type:journal-article",
                    "rows": rows,
                    "cursor": cursor,
                    "select": select_fields,
                    "query.container-title": venue,
                }
                mailto = self.adapter_config.get("mailto")
                if mailto:
                    params["mailto"] = mailto

                try:
                    payload = self._request_json("/works", params=params)
                except requests.RequestException:
                    logger.exception("Crossref request failed for venue %s", venue)
                    break

                message = payload.get("message", {})
                items = message.get("items", [])
                if not items:
                    break

                target_venue = self.registry.normalize(venue_name=venue).get("venue_name") or venue
                for item in items:
                    normalized = self._normalize_item(item, target_venue)
                    if normalized:
                        papers.append(normalized)

                next_cursor = message.get("next-cursor")
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor

        return papers

    def _normalize_item(
        self,
        item: Dict[str, Any],
        target_venue: str,
    ) -> Dict[str, Any] | None:
        container_title = _first_nonempty(*_ensure_list(item.get("container-title")))
        short_title = _first_nonempty(*_ensure_list(item.get("short-container-title")))
        venue_meta = self.registry.normalize(
            venue_name=container_title,
            venue_acronym=short_title,
        )
        if venue_meta.get("venue_name") != target_venue:
            return None

        doi = normalize_doi(item.get("DOI"))
        title = _first_nonempty(*_ensure_list(item.get("title")))
        if not title or not doi:
            return None

        authors = []
        for author in item.get("author", []):
            given = author.get("given", "").strip()
            family = author.get("family", "").strip()
            full_name = " ".join(part for part in [given, family] if part).strip()
            if full_name:
                authors.append(full_name)

        published = _date_from_crossref(
            item,
            "published-online",
            "published-print",
            "issued",
            "created",
        )
        updated = _date_from_crossref(item, "indexed", "created") or published
        pdf_url = None
        for link in item.get("link", []):
            if "pdf" in str(link.get("content-type", "")).lower():
                pdf_url = link.get("URL")
                break

        return self._build_paper(
            record_id=f"doi:{doi}",
            title=title,
            authors=authors,
            abstract=_strip_markup(item.get("abstract")),
            published=published,
            updated=updated,
            source_provider="crossref",
            venue_name=venue_meta.get("venue_name"),
            venue_acronym=venue_meta.get("venue_acronym"),
            venue_type=venue_meta.get("venue_type"),
            venue_tier=venue_meta.get("venue_tier"),
            publication_status="published",
            doi=doi,
            source_url=item.get("URL"),
            pdf_url=pdf_url,
            journal_ref=container_title,
        )


class DBLPAdapter(BaseSourceAdapter):
    name = "dblp"

    def fetch(self) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        papers: List[Dict[str, Any]] = []
        rows = int(self.adapter_config.get("rows_per_request", 200))
        max_pages = int(self.adapter_config.get("max_pages", 2))
        min_year = self.now.year - int(self.adapter_config.get("years_back", 2))

        for venue in self.adapter_config.get("venues", []):
            venue_meta = self.registry.normalize(venue_name=venue)
            query = venue_meta.get("venue_acronym") or venue
            for page in range(max_pages):
                params = {
                    "q": query,
                    "format": "json",
                    "h": rows,
                    "f": page * rows,
                }
                try:
                    payload = self._request_json("/search/publ/api", params=params)
                except requests.RequestException:
                    logger.exception("DBLP request failed for venue %s", venue)
                    break

                hits = payload.get("result", {}).get("hits", {}).get("hit", [])
                if isinstance(hits, dict):
                    hits = [hits]
                if not hits:
                    break

                target_venue = venue_meta.get("venue_name") or venue
                for hit in hits:
                    normalized = self._normalize_hit(hit.get("info", {}), target_venue, min_year)
                    if normalized:
                        papers.append(normalized)

        return papers

    def _normalize_hit(
        self,
        info: Dict[str, Any],
        target_venue: str,
        min_year: int,
    ) -> Dict[str, Any] | None:
        try:
            year = int(info.get("year"))
        except (TypeError, ValueError):
            return None
        if year < min_year:
            return None

        venue_text = _first_nonempty(info.get("venue"), info.get("booktitle"))
        venue_meta = self.registry.normalize(venue_name=venue_text)
        if venue_meta.get("venue_name") != target_venue:
            return None

        title = _strip_markup(info.get("title"))
        if not title:
            return None

        author_entries = info.get("authors", {}).get("author", [])
        authors = []
        for author in _ensure_list(author_entries):
            if isinstance(author, dict):
                text = author.get("text")
            else:
                text = str(author)
            if text:
                authors.append(text.strip())

        doi = normalize_doi(info.get("doi"))
        ee_entries = _ensure_list(info.get("ee"))
        pdf_url = None
        source_url = info.get("url")
        for entry in ee_entries:
            if not isinstance(entry, str):
                continue
            if entry.endswith(".pdf"):
                pdf_url = entry
            if not source_url:
                source_url = entry
        if not source_url and info.get("key"):
            source_url = f"https://dblp.org/rec/{info['key']}.html"

        return self._build_paper(
            record_id=f"dblp:{info.get('key') or doi or title}",
            title=title,
            authors=authors,
            abstract=None,
            published=f"{year:04d}-01-01",
            updated=f"{year:04d}-01-01",
            source_provider="dblp",
            venue_name=venue_meta.get("venue_name"),
            venue_acronym=venue_meta.get("venue_acronym"),
            venue_type=venue_meta.get("venue_type"),
            venue_tier=venue_meta.get("venue_tier"),
            publication_status="published",
            doi=doi,
            source_url=source_url,
            pdf_url=pdf_url,
            journal_ref=venue_text if venue_meta.get("venue_type") == "journal" else None,
            comment=venue_text if venue_meta.get("venue_type") == "conference" else None,
        )


class OpenReviewAdapter(BaseSourceAdapter):
    name = "openreview"

    def __init__(
        self,
        config: Dict[str, Any],
        session: requests.Session | None = None,
        now: datetime | None = None,
    ):
        super().__init__(config, session=session, now=now)
        self.access_token = self._normalize_token(
            os.environ.get("OPENREVIEW_ACCESS_TOKEN")
            or os.environ.get("OPENREVIEW_TOKEN")
            or self.adapter_config.get("access_token")
        )
        self.username = os.environ.get("OPENREVIEW_USERNAME") or self.adapter_config.get("username")
        self.password = os.environ.get("OPENREVIEW_PASSWORD") or self.adapter_config.get("password")
        self.token_expires_in = int(self.adapter_config.get("token_expires_in", 3600))
        self.submission_invitation_suffix = self.adapter_config.get(
            "submission_invitation_suffix",
            "/-/Submission",
        )
        self.notes_details = self.adapter_config.get("notes_details", "directReplies")
        self._auth_mode = "token" if self.access_token else "anonymous"
        self._login_attempted = False
        self._warned_public_access = False

    def fetch(self) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        papers: List[Dict[str, Any]] = []
        limit = int(self.adapter_config.get("limit_per_request", 200))
        max_pages = int(self.adapter_config.get("max_pages", 2))
        years_back = int(self.adapter_config.get("years_back", 2))
        current_year = self.now.year
        templates = self.adapter_config.get("venue_id_templates", {})

        for venue in self.adapter_config.get("venues", []):
            template = templates.get(venue)
            if not template:
                continue

            target_venue = self.registry.normalize(venue_name=venue).get("venue_name") or venue
            for year in range(current_year, current_year - years_back - 1, -1):
                venue_id = template.format(year=year)
                invitation = f"{venue_id}{self.submission_invitation_suffix}"
                for page in range(max_pages):
                    params = {
                        "invitation": invitation,
                        "details": self.notes_details,
                        "limit": limit,
                        "offset": page * limit,
                    }
                    try:
                        payload = self._request_notes(params)
                    except requests.HTTPError as exc:
                        status_code = exc.response.status_code if exc.response is not None else None
                        if status_code in {401, 403}:
                            self._warn_access_denied(venue_id)
                            return papers
                        logger.exception("OpenReview request failed for venue %s", venue_id)
                        break
                    except requests.RequestException:
                        logger.exception("OpenReview request failed for venue %s", venue_id)
                        break

                    notes = payload.get("notes", [])
                    if not notes:
                        break

                    for note in notes:
                        normalized = self._normalize_note(note, target_venue)
                        if normalized:
                            papers.append(normalized)

        return papers

    @staticmethod
    def _normalize_token(token: str | None) -> str | None:
        if not token:
            return None
        return str(token).replace("Bearer ", "").strip() or None

    def _auth_headers(self) -> Dict[str, str]:
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    def _ensure_authenticated(self) -> bool:
        if self.access_token:
            return True
        if self._login_attempted:
            return False
        self._login_attempted = True

        if not (self.username and self.password):
            return False

        try:
            payload = self._request_json(
                "/login",
                json_body={
                    "id": self.username,
                    "password": self.password,
                    "expiresIn": self.token_expires_in,
                },
                method="POST",
            )
        except requests.RequestException:
            logger.exception("OpenReview login failed for user %s", self.username)
            return False

        token = self._normalize_token(payload.get("token"))
        if not token:
            logger.warning("OpenReview login succeeded but no token was returned")
            return False

        self.access_token = token
        self._auth_mode = "password"
        logger.info("OpenReview authenticated via %s", self._auth_mode)
        return True

    def _request_notes(self, params: Dict[str, Any]) -> Dict[str, Any]:
        request_headers = self._auth_headers()
        try:
            return self._request_json("/notes", params=params, headers=request_headers or None)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code not in {401, 403}:
                raise

            if request_headers:
                raise

            if self._ensure_authenticated():
                return self._request_json("/notes", params=params, headers=self._auth_headers())

            raise

    def _warn_access_denied(self, venue_id: str) -> None:
        if self._warned_public_access:
            return
        self._warned_public_access = True
        if self._auth_headers():
            logger.warning(
                "OpenReview denied API access for %s even with configured authentication. "
                "Check OPENREVIEW_ACCESS_TOKEN or OPENREVIEW_USERNAME/OPENREVIEW_PASSWORD.",
                venue_id,
            )
            return
        logger.warning(
            "OpenReview denied anonymous API access for %s. "
            "Set OPENREVIEW_ACCESS_TOKEN or OPENREVIEW_USERNAME/OPENREVIEW_PASSWORD to enable authenticated fetching.",
            venue_id,
        )

    def _normalize_note(
        self,
        note: Dict[str, Any],
        target_venue: str,
    ) -> Dict[str, Any] | None:
        content = note.get("content", {})
        details = note.get("details", {})
        venue_value = _extract_openreview_content(content, "venue")
        venue_id = _extract_openreview_content(content, "venueid")
        venue_meta = self.registry.normalize(
            venue_name=venue_value or target_venue,
            venue_text=target_venue,
        )
        if venue_meta.get("venue_name") != target_venue:
            return None

        title = _extract_openreview_content(content, "title")
        if not title:
            return None

        authors = _ensure_list(_extract_openreview_content(content, "authors"))
        doi = normalize_doi(_extract_openreview_content(content, "doi"))
        abstract = _extract_openreview_content(content, "abstract")
        decision = _first_nonempty(
            _extract_openreview_content(content, "decision"),
            self._extract_decision_from_replies(details),
        )
        published = _first_nonempty(
            _date_from_epoch_millis(note.get("pdate")),
            _date_from_epoch_millis(note.get("odate")),
            _date_from_epoch_millis(note.get("cdate")),
        )
        updated = _first_nonempty(
            _date_from_epoch_millis(note.get("tmdate")),
            _date_from_epoch_millis(note.get("mdate")),
            published,
        )
        publication_status = self._infer_status(venue_value, decision, published)
        forum_id = note.get("forum") or note.get("id")

        return self._build_paper(
            record_id=f"openreview:{note.get('id')}",
            title=title,
            authors=[str(author).strip() for author in authors if str(author).strip()],
            abstract=abstract,
            published=published,
            updated=updated,
            source_provider="openreview",
            venue_name=venue_meta.get("venue_name"),
            venue_acronym=venue_meta.get("venue_acronym"),
            venue_type=venue_meta.get("venue_type") or "conference",
            venue_tier=venue_meta.get("venue_tier"),
            publication_status=publication_status,
            doi=doi,
            source_url=f"https://openreview.net/forum?id={forum_id}",
            pdf_url=f"https://openreview.net/pdf?id={forum_id}",
            comment=_first_nonempty(decision, venue_value, venue_id),
        )

    def _extract_decision_from_replies(self, details: Dict[str, Any]) -> str | None:
        replies = _ensure_list(details.get("directReplies"))
        for reply in replies:
            if not isinstance(reply, dict):
                continue
            content = reply.get("content", {})
            decision = _first_nonempty(
                _extract_openreview_content(content, "decision"),
                _extract_openreview_content(content, "recommendation"),
                _extract_openreview_content(content, "final_decision"),
            )
            if decision:
                return str(decision)
        return None

    @staticmethod
    def _infer_status(
        venue_value: str | None,
        decision: str | None,
        published: str | None,
    ) -> str:
        normalized_venue = str(venue_value or "").lower()
        normalized_decision = str(decision or "").lower()
        if "reject" in normalized_decision or "withdraw" in normalized_decision:
            return "submitted"
        if published:
            return "published"
        if "accept" in normalized_decision:
            return "accepted"
        if normalized_venue.startswith("submitted to"):
            return "submitted"
        return "accepted"
