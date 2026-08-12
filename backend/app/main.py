from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .database import db_cursor, init_db, news_count
from .rewriter import MOOD_PROMPTS, get_or_create_rewrite
from .rss_fetcher import fetch_and_store_news

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if news_count() < 10:
        try:
            n = fetch_and_store_news(limit=15)
            print(f"[startup] Загружено новостей: {n}")
        except Exception as e:
            print(f"[startup] Не удалось загрузить новости из Google RSS: {e}")
    yield


app = FastAPI(title="News Mood API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RewriteRequest(BaseModel):
    mood: str


@app.get("/api/moods")
def list_moods():
    return {"moods": list(MOOD_PROMPTS.keys())}


@app.get("/api/news")
def list_news():
    with db_cursor() as conn:
        rows = conn.execute(
            "SELECT id, title, source, link, published_at, original_text "
            "FROM news ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/news/{news_id}")
def get_news(news_id: int):
    with db_cursor() as conn:
        row = conn.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    return dict(row)


@app.post("/api/news/{news_id}/rewrite")
def rewrite_news(news_id: int, body: RewriteRequest):
    with db_cursor() as conn:
        row = conn.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    if not body.mood or not body.mood.strip():
        raise HTTPException(status_code=400, detail="Не указано настроение")

    try:
        result = get_or_create_rewrite(news_id, row["title"], row["original_text"], body.mood)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"OpenRouter вернул ошибку: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка обращения к OpenRouter: {e}")

    return result


@app.post("/api/news/refresh")
def refresh_news():
    try:
        inserted = fetch_and_store_news()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Не удалось получить новости: {e}")
    return {"inserted": inserted}


# Отдаём фронтенд (чистый html/css/js) как статику той же FastAPI-аппликацией.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
