"""Получение реальных новостей из Google News RSS (на русском)."""
import html
import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from .config import settings
from .database import db_cursor

TOP_STORIES_URL = "https://news.google.com/rss?hl=ru&gl=RU&ceid=RU:ru"
SEARCH_URL_TMPL = "https://news.google.com/rss/search?q={query}&hl=ru&gl=RU&ceid=RU:ru"

# Google отдаёт RSS только клиентам с "браузерным" User-Agent.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _build_url() -> str:
    query = settings.GOOGLE_NEWS_QUERY.strip()
    if query:
        return SEARCH_URL_TMPL.format(query=quote(query))
    return TOP_STORIES_URL


def _clean_description(raw_html: str) -> str:
    """<description> в Google News RSS — это HTML-фрагмент со списком ссылок
    на источники. Достаём из него чистый текст."""
    soup = BeautifulSoup(raw_html or "", "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_google_news_rss(limit: Optional[int] = None) -> list[dict]:
    """Скачивает и парсит RSS-ленту Google News. Возвращает список словарей
    с реальными новостями (заголовок, ссылка, источник, дата, текст)."""
    limit = limit or settings.NEWS_FETCH_LIMIT
    url = _build_url()

    with httpx.Client(timeout=15, headers=HEADERS, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        xml_text = resp.text

    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        pub_date = (item.findtext("pubDate") or "").strip()

        source_el = item.find("source")
        source = (
            source_el.text.strip()
            if source_el is not None and source_el.text
            else "Источник не указан"
        )

        summary = _clean_description(item.findtext("description") or "")
        # Google часто дублирует заголовок в description — тогда используем
        # только заголовок, чтобы не переписывать пустоту.
        original_text = summary if summary and summary != title else title

        if not title or not link:
            continue

        items.append(
            {
                "guid": guid,
                "title": title,
                "link": link,
                "source": source,
                "published_at": pub_date,
                "original_text": original_text,
            }
        )
        if len(items) >= limit:
            break

    return items


def fetch_and_store_news(limit: Optional[int] = None) -> int:
    """Фетчит свежие новости и сохраняет только новые (по guid) в SQLite.
    Возвращает количество реально добавленных строк."""
    items = fetch_google_news_rss(limit=limit)
    inserted = 0
    now = datetime.now(timezone.utc).isoformat()

    with db_cursor() as conn:
        for it in items:
            try:
                conn.execute(
                    """INSERT INTO news
                       (guid, title, link, source, published_at, original_text, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        it["guid"],
                        it["title"],
                        it["link"],
                        it["source"],
                        it["published_at"],
                        it["original_text"],
                        now,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                # такая новость (guid) уже есть в базе — пропускаем
                continue

    return inserted
