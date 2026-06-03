"""Persistent storage for the Manager Bot — SQLite with WAL, indexed, FTS search."""

from db.connection import db_path, init_db
from db.store import VacancyStore

__all__ = ["VacancyStore", "db_path", "init_db"]
