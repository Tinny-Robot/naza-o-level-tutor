"""Shared logging helper so every module logs with a consistent format."""

from __future__ import annotations

import logging

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_configured = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the project-wide format configured once.

    Args:
        name: Usually ``__name__`` of the calling module.

    Returns:
        A configured :class:`logging.Logger`.
    """
    global _configured
    if not _configured:
        logging.basicConfig(level=logging.INFO, format=_FORMAT)
        _configured = True
    return logging.getLogger(name)
