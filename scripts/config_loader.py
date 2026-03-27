#!/usr/bin/env python3
"""Configuration loading helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_config(config_path: str | Path) -> Dict[str, Any]:
    """Load a YAML/JSON configuration file.

    The project keeps `config.yaml` JSON-compatible so the runtime still works
    even when `PyYAML` is not available on the server.
    """

    path = Path(config_path)
    text = path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None

    if yaml is not None:
        return yaml.safe_load(text)

    return json.loads(text)
