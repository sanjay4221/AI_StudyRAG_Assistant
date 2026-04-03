"""
core/logger.py
--------------
Centralized logger for the entire application.

Design decisions (think of these as your AI engineering patterns):
  - ONE logger setup, imported everywhere — avoids duplicate handlers
  - Rotating file handler — logs never blow up your disk on a laptop
  - Structured format — timestamp | level | module | message
    makes it easy to grep, tail, or later ship to a log aggregator (ELK, Datadog)
  - Console + file simultaneously — console for dev, file for audit trail
  - Each module gets its OWN named logger via get_logger(__name__)
    so you always know which file produced a log line

Usage (in any module):
    from core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Ingesting PDF: %s", filename)
    logger.error("Vectorstore failed", exc_info=True)   # includes traceback
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ── Log file location ─────────────────────────────────────────────────────────
# Goes two levels up from backend/core/ → project root → logs/
LOG_DIR  = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# ── Format ────────────────────────────────────────────────────────────────────
# Example output:
#   2024-12-01 14:23:05,123 | INFO     | rag.ingestion   | Ingesting lecture_notes.pdf
LOG_FORMAT  = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── Root logger level (DEBUG in dev, INFO in prod) ───────────────────────────
ROOT_LEVEL = logging.DEBUG


def _build_root_logger() -> None:
    """
    Configure the root logger exactly once.
    Called automatically when this module is first imported.
    """
    root = logging.getLogger()

    # Avoid adding duplicate handlers if the module is somehow re-imported
    if root.handlers:
        return

    root.setLevel(ROOT_LEVEL)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # ── Handler 1: stdout (colour-friendly, great in VS Code terminal) ────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)

    # ── Handler 2: rotating file (max 5 MB × 3 backups = 15 MB max) ──────────
    # When app.log hits 5 MB it rolls to app.log.1, app.log.2, app.log.3
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Silence overly chatty third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "chromadb", "sentence_transformers",
                  "chromadb.telemetry", "chromadb.telemetry.product.posthog",
                  "transformers", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.CRITICAL)


# Run once on import
_build_root_logger()


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger for the calling module.

    Best practice — always call with __name__:
        logger = get_logger(__name__)

    This makes every log line self-identifying:
        2024-12-01 14:23:05 | INFO | rag.ingestion | ...
    """
    return logging.getLogger(name)
