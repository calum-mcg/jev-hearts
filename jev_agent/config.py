"""Settings for the Jev API, read from the environment or a local `.env` file."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"


def load_env(path: str | Path = ".env") -> None:
    """Load KEY=value lines from `path` into os.environ (real env vars win)."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api_key() -> str | None:
    key = os.environ.get("JEV_API_KEY", "").strip()
    return None if not key or key.startswith("<") else key


def api_url() -> str:
    return os.environ.get("JEV_API_URL", "").strip() or DEFAULT_API_URL


def model() -> str:
    """Model id (required by the API). GET /v1/models lists them: jev-latest, jev-preview."""
    value = os.environ.get("JEV_MODEL", "").strip()
    return DEFAULT_MODEL if not value or value.startswith("<") else value
