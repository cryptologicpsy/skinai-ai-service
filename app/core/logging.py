"""Logging configuration."""

from __future__ import annotations

import logging
import sys

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure root logging once, at process startup.

    Uses plain stdlib logging to stdout. This is intentionally simple:
    no external logging services are contacted, so it is safe to call at
    import time.
    """

    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
