"""Переписывание новости под настроение через OpenRouter (модель DeepSeek)."""
import json
import re
from datetime import datetime, timezone

import httpx

from .config import settings
from .database import db_cursor
from .fact_checker import check_facts

MOOD_PROMPTS = {
    "радостно": "с радостной, воодушевлённой и позитивной интонацией",
    "грустно": "с грустной, меланхоличной интонацией",
    "нейтрально": "в подчёркнуто нейтральном, сухом информационном стиле, как в официальной сводке",
    "иронично": "с лёгкой иронией и сарказмом, но без перехода на оскорбления и без искажения сути",
}

SYSTEM_PROMPT = (
    "Ты — редактор новостей. Тебе дают текст новости и требуемую эмоциональную "
    "тональность. Перепиши текст в этой тональности, но СТРОГО сохрани все факты: "
    "имена людей и организаций, даты, числа, статистику, географические названия "
    "и содержание прямых цитат должны остаться неизменными по сути. Разрешено "
    "только менять грамматическую форму слов (падеж, число), стиль изложения и "
    "порядок предложений. ЗАПРЕЩЕНО: придумывать новые факты, убирать существующие "
    "факты, менять числа, даты, имена или суть цитат. "
    "Ответь ТОЛЬКО переписанным текстом на русском языке, без пояснений от себя "
    "и без кавычек вокруг всего ответа."
)


def _mood_instruction(mood: str) -> str:
    key = mood.strip().lower()
    if key in MOOD_PROMPTS:
        return MOOD_PROMPTS[key]
    # Свой вариант настроения, введённый пользователем вручную
    return f"в стиле: {mood.strip()}"


def _call_openrouter(title: str, original_text: str, mood: str) -> str:
    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY не задан. Добавьте ключ в backend/.env (см. README.md)."
        )

    style = _mood_instruction(mood)
    user_prompt = (
        f"Заголовок новости: {title}\n"
        f"Текст новости: {original_text}\n\n"
        f"Перепиши этот текст {style}. Сохрани все факты без изменений."
    )

    payload = {
        "model": settings.OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.APP_URL,
        "X-Title": "News Mood",
    }

    with httpx.Client(timeout=60) as client:
        resp = client.post(settings.OPENROUTER_BASE_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    text = data["choices"][0]["message"]["content"].strip()
    text = re.sub(r'^[«"]|[»"]$', "", text).strip()
    return text


def get_or_create_rewrite(news_id: int, title: str, original_text: str, mood: str) -> dict:
    """Возвращает переписанный текст: из кэша (SQLite), если для этой пары
    (новость, настроение) он уже есть, иначе — запрашивает у OpenRouter и
    сохраняет результат вместе с отчётом о проверке фактов."""
    mood_key = mood.strip()

    with db_cursor() as conn:
        row = conn.execute(
            "SELECT rewritten_text, fact_check_json FROM rewrites WHERE news_id = ? AND mood = ?",
            (news_id, mood_key),
        ).fetchone()
    if row:
        return {
            "mood": mood_key,
            "rewritten_text": row["rewritten_text"],
            "fact_check": json.loads(row["fact_check_json"]),
            "cached": True,
        }

    rewritten_text = _call_openrouter(title, original_text, mood_key)
    fact_check = check_facts(original_text, rewritten_text)
    now = datetime.now(timezone.utc).isoformat()

    with db_cursor() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO rewrites
               (news_id, mood, rewritten_text, fact_check_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (news_id, mood_key, rewritten_text, json.dumps(fact_check, ensure_ascii=False), now),
        )

    return {
        "mood": mood_key,
        "rewritten_text": rewritten_text,
        "fact_check": fact_check,
        "cached": False,
    }
