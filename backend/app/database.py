"""Слой хранения: обычный sqlite3 из стандартной библиотеки Python.

Никакого ORM намеренно — база маленькая (новости + переписанные версии),
и явный SQL проще читать и объяснить в README, чем маппинги ORM.
"""
import sqlite3
from contextlib import contextmanager

from .config import settings


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor():
    """Контекстный менеджер: открывает соединение, коммитит при успехе, закрывает всегда."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db_cursor() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guid TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                link TEXT NOT NULL,
                source TEXT,
                published_at TEXT,
                original_text TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rewrites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER NOT NULL REFERENCES news(id) ON DELETE CASCADE,
                mood TEXT NOT NULL,
                rewritten_text TEXT NOT NULL,
                fact_check_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(news_id, mood)
            )
            """
        )


def news_count() -> int:
    with db_cursor() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM news").fetchone()
        return row["c"]
