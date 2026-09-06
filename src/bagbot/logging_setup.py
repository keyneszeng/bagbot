"""Logging setup: tee to file + stderr."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(log_file: str, level: str = "INFO") -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )
