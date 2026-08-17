"""
Первичная индексация всех существующих записей в ChromaDB.

Запуск:
    python scripts/reindex_chroma.py

Индексирует:
- posts (TelegramPost) → коллекция posts
- generated_news → коллекция news
- rss_news → коллекция news (отдельный префикс)
- web_news → коллекция news (отдельный префикс)
"""

import asyncio
import json
import logging
import sys
import os

# Настройка логирования до импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    from services.database import get_database_service
    from services.vector_search.search_engine import VectorSearchEngine
    from sqlalchemy import select, func

    # Инициализация БД (lazy singleton)
    db = get_database_service()

    # Векторный поисковик
    engine = VectorSearchEngine()

    stats = {"posts": 0, "news": 0, "rss": 0, "web": 0, "errors": 0}

    async with db.session_context() as session:
        # === 1. Telegram Posts ===
        from database.models import TelegramPost
        r = await session.execute(select(func.count()).select_from(TelegramPost))
        total = r.scalar() or 0
        logger.info(f"📦 Индексация posts: {total} записей")

        r = await session.execute(select(TelegramPost))
        posts = r.scalars().all()
        for p in posts:
            try:
                text = p.text or ""
                category = p.category or ""
                tags_raw = p.tags or "[]"

                # Конкатенируем текст + категория + тэги для лучшего эмбеддинга
                search_text = text
                if category:
                    search_text = f"{text} {category}"
                try:
                    tags_list = json.loads(tags_raw) if tags_raw != "[]" else []
                    if tags_list:
                        search_text = f"{search_text} {' '.join(tags_list)}"
                except json.JSONDecodeError:
                    pass

                await engine.add_post(
                    id=f"post_{p.id}",
                    text=search_text,
                    channel_id=p.channel_id,
                    category=category,
                    urgency=int(p.urgency) if p.urgency else 1,
                )
                stats["posts"] += 1
            except Exception as e:
                logger.error(f"❌ Ошибка индексации post {p.id}: {e}")
                stats["errors"] += 1

        logger.info(f"✅ Posts: {stats['posts']} проиндексировано")

        # === 2. Generated News ===
        from database.models import GeneratedNews
        r = await session.execute(select(func.count()).select_from(GeneratedNews))
        total = r.scalar() or 0
        logger.info(f"📦 Индексация generated_news: {total} записей")

        r = await session.execute(select(GeneratedNews))
        news_items = r.scalars().all()
        for n in news_items:
            try:
                text = n.text or ""
                category = n.category or ""
                tags_raw = n.tags or "[]"

                search_text = text
                if category:
                    search_text = f"{text} {category}"
                try:
                    tags_list = json.loads(tags_raw) if tags_raw != "[]" else []
                    if tags_list:
                        search_text = f"{search_text} {' '.join(tags_list)}"
                except json.JSONDecodeError:
                    pass

                tags = []
                try:
                    tags = json.loads(tags_raw) if tags_raw != "[]" else []
                except json.JSONDecodeError:
                    pass

                await engine.add_news(
                    id=f"news_{n.id}",
                    text=search_text,
                    category=category,
                    tags=tags,
                )
                stats["news"] += 1
            except Exception as e:
                logger.error(f"❌ Ошибка индексации generated_news {n.id}: {e}")
                stats["errors"] += 1

        logger.info(f"✅ GeneratedNews: {stats['news']} проиндексировано")

        # === 3. RSS News ===
        from database.models import RSSNews
        r = await session.execute(select(func.count()).select_from(RSSNews))
        total = r.scalar() or 0
        logger.info(f"📦 Индексация rss_news: {total} записей")

        r = await session.execute(select(RSSNews))
        rss_items = r.scalars().all()
        for item in rss_items:
            try:
                text = (item.title or "") + " " + (item.description or "")
                category = item.category or ""
                tags_raw = item.tags or "[]"

                search_text = text
                if category:
                    search_text = f"{search_text} {category}"
                try:
                    tags_list = json.loads(tags_raw) if tags_raw != "[]" else []
                    if tags_list:
                        search_text = f"{search_text} {' '.join(tags_list)}"
                except json.JSONDecodeError:
                    pass

                tags = []
                try:
                    tags = json.loads(tags_raw) if tags_raw != "[]" else []
                except json.JSONDecodeError:
                    pass

                await engine.add_news(
                    id=f"rss_{item.id}",
                    text=search_text,
                    category=category,
                    tags=tags,
                )
                stats["rss"] += 1
            except Exception as e:
                logger.error(f"❌ Ошибка индексации rss_news {item.id}: {e}")
                stats["errors"] += 1

        logger.info(f"✅ RSSNews: {stats['rss']} проиндексировано")

        # === 4. Web News ===
        from database.models import WebNews
        r = await session.execute(select(func.count()).select_from(WebNews))
        total = r.scalar() or 0
        logger.info(f"📦 Индексация web_news: {total} записей")

        r = await session.execute(select(WebNews))
        web_items = r.scalars().all()
        for item in web_items:
            try:
                text = (item.title or "") + " " + (item.description or "")
                category = item.category or ""
                tags_raw = item.tags or "[]"

                search_text = text
                if category:
                    search_text = f"{search_text} {category}"
                try:
                    tags_list = json.loads(tags_raw) if tags_raw != "[]" else []
                    if tags_list:
                        search_text = f"{search_text} {' '.join(tags_list)}"
                except json.JSONDecodeError:
                    pass

                tags = []
                try:
                    tags = json.loads(tags_raw) if tags_raw != "[]" else []
                except json.JSONDecodeError:
                    pass

                await engine.add_news(
                    id=f"web_{item.id}",
                    text=search_text,
                    category=category,
                    tags=tags,
                )
                stats["web"] += 1
            except Exception as e:
                logger.error(f"❌ Ошибка индексации web_news {item.id}: {e}")
                stats["errors"] += 1

        logger.info(f"✅ WebNews: {stats['web']} проиндексировано")

    # Статистика
    engine.log_stats()
    logger.info(f"📊 Итого: posts={stats['posts']}, news={stats['news']}, "
                f"rss={stats['rss']}, web={stats['web']}, errors={stats['errors']}")

    # Очистка БД
    from services.core.database import dispose_database_service
    await dispose_database_service()


if __name__ == "__main__":
    asyncio.run(main())
