"""
db/database.py
--------------
Database engine setup and session management.
Supports PostgreSQL (cloud) and SQLite (local dev).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path

from core.logger import get_logger
from db.models import Base

logger = get_logger(__name__)

import os as _os
from pathlib import Path as _Path

# ── Database URL ──────────────────────────────────────────────────────────────
_PG_URL = _os.environ.get("DATABASE_URL", "")

if _PG_URL:
    DATABASE_URL = _PG_URL
    logger.info("Using PostgreSQL database")
    engine = create_engine(DATABASE_URL, echo=False)
else:
    _DATA_DIR = _Path(_os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent.parent.parent)))
    DB_PATH = _DATA_DIR / "studyrag.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    logger.info("Using SQLite database at: %s", DB_PATH)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
        echo=False,
    )

# ── Session factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db() -> None:
    logger.info("Initialising database...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database ready ✓")


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
