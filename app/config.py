import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1/chat/completions"

    DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "news.db"))

    # Пусто -> топ новости Google News (ru/RU). Иначе -> поиск по теме.
    GOOGLE_NEWS_QUERY: str = os.getenv("GOOGLE_NEWS_QUERY", "")
    NEWS_FETCH_LIMIT: int = int(os.getenv("NEWS_FETCH_LIMIT", "15"))

    APP_URL: str = os.getenv("APP_URL", "http://localhost:8000")


settings = Settings()
