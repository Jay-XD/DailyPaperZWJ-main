#!/usr/bin/env python3
"""Future external source adapter interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseSourceAdapter(ABC):
    """Non-ArXiv source adapter contract for future multi-source expansion."""

    name = "base"

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def fetch(self) -> List[Dict[str, Any]]:
        """Fetch normalized paper records."""


class CrossrefAdapter(BaseSourceAdapter):
    name = "crossref"

    def fetch(self) -> List[Dict[str, Any]]:
        return []


class DBLPAdapter(BaseSourceAdapter):
    name = "dblp"

    def fetch(self) -> List[Dict[str, Any]]:
        return []


class OpenReviewAdapter(BaseSourceAdapter):
    name = "openreview"

    def fetch(self) -> List[Dict[str, Any]]:
        return []
