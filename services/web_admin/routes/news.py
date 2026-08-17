"""
Раздел Новости — API для просмотра и удаления записей
из таблиц: posts, rss_news, web_news, generated_news.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, desc, asc, or_, and_

from services.database import get_database_service
from services.database.enums import DatabaseType
from services.search_db import (
    text_search_condition,
    apply_filter,
    search_morph,
)
from services.web_admin.auth_dependency import get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Posts (Telegram)
# =============================================================================

@router.get("/api/posts", tags=["News"])
async def list_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at", pattern="^(id|text|channel_id|category|urgency|rate|tags|created_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Получить список постов из Telegram с пагинацией и сортировкой."""
    from database.models import TelegramPost

    db_service = get_database_service()
    try:
        order_func = desc if sort_dir == "desc" else asc
        sort_col = getattr(TelegramPost, sort_by, TelegramPost.created_at)

        async with db_service.session_context() as session:
            total_result = await session.execute(
                select(func.count()).select_from(TelegramPost)
            )
            total = total_result.scalar() or 0

            items_result = await session.execute(
                select(TelegramPost)
                .order_by(order_func(sort_col))
                .offset((page - 1) * limit)
                .limit(limit)
            )
            items = items_result.scalars().all()

        rows = []
        for p in items:
            created = p.created_at.isoformat() if p.created_at else None
            rows.append({
                "id": p.id,
                "text": (p.text or '')[:150],
                "channel_id": p.channel_id,
                "category": p.category or '',
                "urgency": p.urgency or '',
                "rate": p.rate,
                "tags": p.tags or '[]',
                "checked_at": p.checked_at,
                "bypass_ara": p.bypass_ara,
                "publisher_channel_id": p.publisher_channel_id,
                "created_at": created,
            })

        return {
            "success": True,
            "items": rows,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit if limit else 1,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        }
    except Exception as e:
        logger.error(f"Ошибка получения постов: {e}", exc_info=True)
        return {"success": False, "error": str(e), "items": [], "total": 0, "page": page, "limit": limit, "pages": 1}


@router.delete("/api/posts/{post_id}", tags=["News"])
async def delete_post(
    post_id: int,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Удалить пост из Telegram."""
    from database.models import TelegramPost

    db_service = get_database_service()
    try:
        async with db_service.session_context() as session:
            stmt = select(TelegramPost).where(TelegramPost.id == post_id)
            result = await session.execute(stmt)
            post = result.scalar_one_or_none()

            if not post:
                return {"success": False, "error": f"Пост {post_id} не найден"}

            await session.delete(post)
            await session.commit()

        logger.info(f"Пост {post_id} удалён")
        return {"success": True, "id": post_id}
    except Exception as e:
        logger.error(f"Ошибка удаления поста {post_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# RSS News
# =============================================================================

@router.get("/api/rss-news", tags=["News"])
async def list_rss_news(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at", pattern="^(id|source_id|title|link|author|category|tags|processed|created_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Получить список RSS новостей с пагинацией и сортировкой."""
    from database.models import RSSNews

    db_service = get_database_service()
    try:
        order_func = desc if sort_dir == "desc" else asc
        sort_col = getattr(RSSNews, sort_by, RSSNews.created_at)

        async with db_service.session_context() as session:
            total_result = await session.execute(
                select(func.count()).select_from(RSSNews)
            )
            total = total_result.scalar() or 0

            items_result = await session.execute(
                select(RSSNews)
                .order_by(order_func(sort_col))
                .offset((page - 1) * limit)
                .limit(limit)
            )
            items = items_result.scalars().all()

        rows = []
        for n in items:
            pub = n.published_at.isoformat() if n.published_at else None
            cr = n.created_at.isoformat() if n.created_at else None
            rows.append({
                "id": n.id,
                "source_id": n.source_id,
                "title": (n.title or '')[:150],
                "link": n.link or '',
                "author": n.author or '',
                "category": n.category or '',
                "tags": n.tags or '[]',
                "processed": n.processed,
                "post_id": n.post_id,
                "published_at": pub,
                "created_at": cr,
            })

        return {
            "success": True,
            "items": rows,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit if limit else 1,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        }
    except Exception as e:
        logger.error(f"Ошибка получения RSS новостей: {e}", exc_info=True)
        return {"success": False, "error": str(e), "items": [], "total": 0, "page": page, "limit": limit, "pages": 1}


@router.delete("/api/rss-news/{news_id}", tags=["News"])
async def delete_rss_news(
    news_id: int,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Удалить RSS новость."""
    from database.models import RSSNews

    db_service = get_database_service()
    try:
        async with db_service.session_context() as session:
            stmt = select(RSSNews).where(RSSNews.id == news_id)
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()

            if not item:
                return {"success": False, "error": f"RSS новость {news_id} не найдена"}

            await session.delete(item)
            await session.commit()

        logger.info(f"RSS новость {news_id} удалена")
        return {"success": True, "id": news_id}
    except Exception as e:
        logger.error(f"Ошибка удаления RSS новости {news_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# Web News
# =============================================================================

@router.get("/api/web-news", tags=["News"])
async def list_web_news(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at", pattern="^(id|source_id|title|link|author|category|tags|processed|created_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Получить список Web новостей с пагинацией и сортировкой."""
    from database.models import WebNews

    db_service = get_database_service()
    try:
        order_func = desc if sort_dir == "desc" else asc
        sort_col = getattr(WebNews, sort_by, WebNews.created_at)

        async with db_service.session_context() as session:
            total_result = await session.execute(
                select(func.count()).select_from(WebNews)
            )
            total = total_result.scalar() or 0

            items_result = await session.execute(
                select(WebNews)
                .order_by(order_func(sort_col))
                .offset((page - 1) * limit)
                .limit(limit)
            )
            items = items_result.scalars().all()

        rows = []
        for n in items:
            pub = n.published_at.isoformat() if n.published_at else None
            cr = n.created_at.isoformat() if n.created_at else None
            rows.append({
                "id": n.id,
                "source_id": n.source_id,
                "title": (n.title or '')[:150],
                "link": n.link or '',
                "author": n.author or '',
                "category": n.category or '',
                "tags": n.tags or '[]',
                "processed": n.processed,
                "post_id": n.post_id,
                "published_at": pub,
                "created_at": cr,
            })

        return {
            "success": True,
            "items": rows,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit if limit else 1,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        }
    except Exception as e:
        logger.error(f"Ошибка получения Web новостей: {e}", exc_info=True)
        return {"success": False, "error": str(e), "items": [], "total": 0, "page": page, "limit": limit, "pages": 1}


@router.delete("/api/web-news/{news_id}", tags=["News"])
async def delete_web_news(
    news_id: int,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Удалить Web новость."""
    from database.models import WebNews

    db_service = get_database_service()
    try:
        async with db_service.session_context() as session:
            stmt = select(WebNews).where(WebNews.id == news_id)
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()

            if not item:
                return {"success": False, "error": f"Web новость {news_id} не найдена"}

            await session.delete(item)
            await session.commit()

        logger.info(f"Web новость {news_id} удалена")
        return {"success": True, "id": news_id}
    except Exception as e:
        logger.error(f"Ошибка удаления Web новости {news_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# Generated News
# =============================================================================

@router.get("/api/generated-news", tags=["News"])
async def list_generated_news(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at", pattern="^(id|text|category|tags|moderation_status|bypass_ara|published_at|created_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Получить список сгенерированных новостей с пагинацией и сортировкой."""
    from database.models import GeneratedNews

    db_service = get_database_service()
    try:
        order_func = desc if sort_dir == "desc" else asc
        sort_col = getattr(GeneratedNews, sort_by, GeneratedNews.created_at)

        async with db_service.session_context() as session:
            total_result = await session.execute(
                select(func.count()).select_from(GeneratedNews)
            )
            total = total_result.scalar() or 0

            items_result = await session.execute(
                select(GeneratedNews)
                .order_by(order_func(sort_col))
                .offset((page - 1) * limit)
                .limit(limit)
            )
            items = items_result.scalars().all()

        rows = []
        for n in items:
            cr = n.created_at.isoformat() if n.created_at else None
            pub = n.published_at.isoformat() if n.published_at else None
            rows.append({
                "id": n.id,
                "text": (n.text or '')[:200],
                "category": n.category or '',
                "tags": n.tags or '[]',
                "moderation_status": n.moderation_status or 'pending',
                "bypass_ara": n.bypass_ara,
                "publisher_channel_id": n.publisher_channel_id,
                "published_at": pub,
                "created_at": cr,
            })

        return {
            "success": True,
            "items": rows,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit if limit else 1,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        }
    except Exception as e:
        logger.error(f"Ошибка получения сгенерированных новостей: {e}", exc_info=True)
        return {"success": False, "error": str(e), "items": [], "total": 0, "page": page, "limit": limit, "pages": 1}


@router.delete("/api/generated-news/{news_id}", tags=["News"])
async def delete_generated_news(
    news_id: int,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Удалить сгенерированную новость."""
    from database.models import GeneratedNews

    db_service = get_database_service()
    try:
        async with db_service.session_context() as session:
            stmt = select(GeneratedNews).where(GeneratedNews.id == news_id)
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()

            if not item:
                return {"success": False, "error": f"Сгенерированная новость {news_id} не найдена"}

            await session.delete(item)
            await session.commit()

        logger.info(f"Сгенерированная новость {news_id} удалена")
        return {"success": True, "id": news_id}
    except Exception as e:
        logger.error(f"Ошибка удаления сгенерированной новости {news_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# Event Context
# =============================================================================

@router.get("/api/events", tags=["News"])
async def list_events(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at", pattern="^(id|post_id|event_category|tags|last_processed_at|created_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Получить список контекстов событий с пагинацией и сортировкой."""
    from database.models import EventContext

    db_service = get_database_service()
    try:
        order_func = desc if sort_dir == "desc" else asc
        sort_col = getattr(EventContext, sort_by, EventContext.created_at)

        async with db_service.session_context() as session:
            total_result = await session.execute(
                select(func.count()).select_from(EventContext)
            )
            total = total_result.scalar() or 0

            items_result = await session.execute(
                select(EventContext)
                .order_by(order_func(sort_col))
                .offset((page - 1) * limit)
                .limit(limit)
            )
            items = items_result.scalars().all()

        rows = []
        for e in items:
            cr = e.created_at.isoformat() if e.created_at else None
            lp = e.last_processed_at.isoformat() if e.last_processed_at else None
            rows.append({
                "id": e.id,
                "post_id": e.post_id,
                "context_data": (e.context_data or '')[:200],
                "event_category": e.event_category or '',
                "tags": e.tags or '[]',
                "last_processed_at": lp,
                "created_at": cr,
            })

        return {
            "success": True,
            "items": rows,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit if limit else 1,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        }
    except Exception as e:
        logger.error(f"Ошибка получения событий: {e}", exc_info=True)
        return {"success": False, "error": str(e), "items": [], "total": 0, "page": page, "limit": limit, "pages": 1}


@router.delete("/api/events/{event_id}", tags=["News"])
async def delete_event(
    event_id: int,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Удалить контекст события."""
    from database.models import EventContext

    db_service = get_database_service()
    try:
        async with db_service.session_context() as session:
            stmt = select(EventContext).where(EventContext.id == event_id)
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()

            if not item:
                return {"success": False, "error": f"Событие {event_id} не найдено"}

            await session.delete(item)
            await session.commit()

        logger.info(f"Событие {event_id} удалено")
        return {"success": True, "id": event_id}
    except Exception as e:
        logger.error(f"Ошибка удаления события {event_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# Векторный поиск + текстовый фильтр
# =============================================================================

@router.post("/api/search", tags=["News"])
async def search_news(
    request_body: dict,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Гибридный поиск: семантический (ChromaDB) + текстовый (LIKE) + морфологический (n-gram).

    Body: {
        "tab": "posts" | "rss" | "web" | "generated",
        "query": "текст для поиска",
        "filter_field": "category" | "channel_id" | "tags" | "moderation_status" | "urgency",
        "filter_value": "значение фильтра",
        "limit": 50
    }

    Стратегия:
    1. Семантический поиск через ChromaDB (если коллекция заполнена)
    2. SQL LIKE по 3 полям: text/title OR category OR tags
    3. Python-level морфологический поиск (n-gram, покрывает SQLite ограничения)
    4. Объединение результатов: сначала семантические, потом текстовые/морфологические
    """
    tab = request_body.get("tab", "posts")
    query = (request_body.get("query") or "").strip()
    filter_field = request_body.get("filter_field") or None
    filter_value = (request_body.get("filter_value") or "").strip() or None
    limit = min(request_body.get("limit", 50), 200)

    logger.debug(f"[search] tab={tab}, query={query!r}, filter_field={filter_field!r}, filter_value={filter_value!r}, limit={limit}")

    TAB_MAP = {
        "posts": {
            "model_name": "TelegramPost",
            "collection": "posts",
            "text_field": "text",
            "prefixes": ["post_"],
        },
        "rss": {
            "model_name": "RSSNews",
            "collection": "news",
            "text_field": "title",
            "prefixes": ["rss_"],
        },
        "web": {
            "model_name": "WebNews",
            "collection": "news",
            "text_field": "title",
            "prefixes": ["web_"],
        },
        "events": {
            "model_name": "EventContext",
            "collection": "events",
            "text_field": "context_data",
            "category_field": "event_category",
            "prefixes": ["event_"],
        },
        "generated": {
            "model_name": "GeneratedNews",
            "collection": "news",
            "text_field": "text",
            "prefixes": ["news_"],
        },
    }

    tab_cfg = TAB_MAP.get(tab)
    if not tab_cfg:
        logger.error(f"[search] Таб {tab!r} не найден в TAB_MAP. Доступные: {list(TAB_MAP.keys())}")
        return {"success": False, "error": f"Неизвестный таб: {tab}"}

    from database.models import TelegramPost, RSSNews, WebNews, GeneratedNews

    db_service = get_database_service()
    Model = _get_model(tab_cfg["model_name"])
    text_col = getattr(Model, tab_cfg["text_field"])
    # Маппинг поля категории: event_category для EventContext, category для остального
    cat_field = tab_cfg.get("category_field", "category")
    cat_col = getattr(Model, cat_field, None)
    tags_col = getattr(Model, "tags", None)
    prefixes = tab_cfg.get("prefixes", [])

    # Словарь для дедупликации результатов (id → row)
    all_results: dict[int, dict] = {}

    # ======================================================================
    # Этап 1: Семантический поиск через ChromaDB
    # ======================================================================
    semantic_ids: dict[int, float] = {}  # id → score
    if query and tab_cfg["collection"]:
        try:
            vector_service = _get_vector_search_service()
            if vector_service:
                enriched_query = query
                if (filter_field == "category" or filter_field == cat_field) and filter_value:
                    enriched_query = f"{query} {filter_value}"
                if filter_field == "tags" and filter_value:
                    enriched_query = f"{query} {filter_value}"

                cat_filter = filter_value if (filter_field == "category" or filter_field == cat_field) else ""

                if tab == "generated":
                    chroma_results = await vector_service.find_related_news(
                        text=enriched_query,
                        category=cat_filter,
                        limit=limit * 2,
                        min_score=0.3,
                    )
                else:
                    chroma_results = await vector_service.find_similar_posts(
                        text=enriched_query,
                        category=cat_filter,
                        limit=limit * 2,
                        min_score=0.3,
                    )

                # Фильтруем по префиксам (например, rss_ для RSS таба)
                for r in chroma_results:
                    rid = r.get("id", "")
                    if prefixes and not any(rid.startswith(p) for p in prefixes):
                        continue
                    try:
                        db_id = int(rid.split("_", 1)[1]) if "_" in rid else int(rid)
                    except (ValueError, IndexError):
                        continue
                    semantic_ids[db_id] = r.get("score", 0)
        except Exception as e:
            logger.warning(f"Семантический поиск не выполнен: {e}")

    # ======================================================================
    # Этап 2: SQL LIKE + морфологический поиск
    # ======================================================================
    text_ids: set[int] = set()

    if query:
        async with db_service.session_context() as session:
            # Текстовый поиск с учётом СУБД (ILIKE для PG, LIKE для MySQL,
            # множественные LIKE для SQLite)
            condition = text_search_condition(
                query=query,
                text_col=text_col,
                category_col=cat_col,
                tags_col=tags_col,
            )

            stmt = select(Model).where(condition)
            total_result = await session.execute(
                select(func.count()).select_from(stmt.subquery())
            )
            total_like = total_result.scalar() or 0

            if total_like > 0:
                stmt = stmt.limit(limit * 2)
                items_result = await session.execute(stmt)
                for item in items_result.scalars().all():
                    text_ids.add(item.id)
            else:
                # Fallback: морфологический поиск (Python-level, DB-agnostic)
                fallback_stmt = select(Model).order_by(desc(Model.created_at)).limit(limit * 10)
                all_items = (await session.execute(fallback_stmt)).scalars().all()
                for item in all_items:
                    text_val = getattr(item, text_col.key, "") or ""
                    cat_val = (getattr(item, cat_col.key, "") or "") if cat_col else ""
                    tags_val = (getattr(item, "tags", "") or "") if tags_col else ""
                    if (search_morph(text_val, query) or
                            search_morph(cat_val, query) or
                            search_morph(tags_val, query)):
                        text_ids.add(item.id)

    # ======================================================================
    # Объединение результатов
    # ======================================================================
    # Текстовые совпадения (LIKE/morph) получают score=1.0 — всегда в топе.
    # Семантические результаты добавляются как дополнение.
    #
    # Когда текстовый поиск нашёл хиты, семантика дополняет выдачу, но
    # не больше чем до `limit * 1.5` записей — чтобы шум с низким score
    # не засорял результаты. Когда текстовый поиск пуст, семантика
    # основной источник, порог пониже.
    merged_scores: dict[int, float] = {}

    if text_ids:
        # Текстовые совпадения — приоритет
        for tid in text_ids:
            merged_scores[tid] = 1.0

        # Семантические: только если score >= 0.4 и не дублируют текстовые
        semantic_additions = []
        for sid, score in semantic_ids.items():
            if sid in merged_scores:
                continue
            if score >= 0.4:
                semantic_additions.append((sid, score))

        # Сортируем по score desc; семантика занимает не больше половины
        # лимита, чтобы текстовые результаты (точное совпадение)
        # оставались доминирующими в выдаче.
        semantic_additions.sort(key=lambda x: -x[1])
        max_semantic = max(0, limit - len(text_ids))
        for sid, score in semantic_additions[:max_semantic]:
            merged_scores[sid] = score
    else:
        # Текстовый поиск ничего не нашёл — семантика основной источник
        for sid, score in semantic_ids.items():
            if score >= 0.3:
                merged_scores[sid] = score

    all_ids = set(merged_scores.keys())

    # Применяем filter
    if filter_value and all_ids:
        async with db_service.session_context() as session:
            stmt = select(Model).where(Model.id.in_(list(all_ids)))
            stmt = apply_filter(stmt, Model, filter_field, filter_value)
            filtered = (await session.execute(stmt)).scalars().all()
            all_ids = {item.id for item in filtered}

    # Загружаем записи
    rows = []
    if all_ids:
        async with db_service.session_context() as session:
            # Сортировка: текстовые совпадения (score=1.0) → семантические (по score)
            sorted_ids = sorted(
                all_ids,
                key=lambda iid: (-merged_scores.get(iid, 0), -iid),
            )
            stmt = select(Model).where(Model.id.in_(sorted_ids))
            items = (await session.execute(stmt)).scalars().all()

            items_by_id = {item.id: item for item in items}
            ordered_items = [items_by_id[iid] for iid in sorted_ids if iid in items_by_id]

            rows = _serialize_items(ordered_items[:limit], tab)

    search_type_parts = []
    if semantic_ids:
        search_type_parts.append("semantic")
    if text_ids:
        search_type_parts.append("text")

    # ======================================================================
    # Без запроса: просто фильтр
    # ======================================================================
    logger.debug(f"[search] search_type_parts={search_type_parts}, all_ids={len(all_ids)}, filter_value={filter_value!r}")
    if not semantic_ids and not text_ids and filter_value:
        async with db_service.session_context() as session:
            stmt = select(Model)
            stmt = apply_filter(stmt, Model, filter_field, filter_value)
            total_result = await session.execute(
                select(func.count()).select_from(stmt.subquery())
            )
            total = total_result.scalar() or 0
            stmt = stmt.limit(limit)
            items = (await session.execute(stmt)).scalars().all()

        # Fallback: морфологический n-gram если LIKE не нашёл
        if not items:
            async with db_service.session_context() as s2:
                fallback_result = await s2.execute(
                    select(Model).order_by(desc(Model.id)).limit(limit * 10)
                )
                fallback_items = fallback_result.scalars().all()
            col_name = filter_field
            morph_matches = [
                item for item in fallback_items
                if search_morph(getattr(item, col_name, "") or "", filter_value)
            ]
            if morph_matches:
                items = morph_matches[:limit]
                total = len(items)

        rows = _serialize_items(items, tab)
        return {
            "success": True,
            "items": rows,
            "total": total,
            "search_type": "filter",
        }

    if not query and filter_value:
        search_type_parts.append("filter")

    return {
        "success": True,
        "items": rows,
        "total": len(rows),
        "search_type": "+".join(search_type_parts) if search_type_parts else "none",
        "query": query,
    }

    # ======================================================================
    # ChromaDB индексация
    # ======================================================================


def _get_vector_search_service():
    """Получить VectorSearchService из DI контейнера."""
    import sys
    for mod_name in ("main", "__main__"):
        main_mod = sys.modules.get(mod_name)
        if main_mod:
            container = getattr(main_mod, "_global_container", None)
            if container:
                return container.get_vector_search_service()
    return None


def _get_model(name: str):
    """Получить SQLAlchemy модель по имени."""
    from database.models import TelegramPost, RSSNews, WebNews, GeneratedNews, EventContext
    return {
        "TelegramPost": TelegramPost,
        "RSSNews": RSSNews,
        "WebNews": WebNews,
        "GeneratedNews": GeneratedNews,
        "EventContext": EventContext,
    }[name]


def _serialize_items(items, tab):
    """Сериализовать записи для JSON ответа."""
    import json as json_mod

    rows = []
    for item in items:
        row = {
            "id": item.id,
        }
        if tab == "posts":
            row["text"] = (item.text or "")[:200]
            row["channel_id"] = item.channel_id
            row["category"] = item.category or ""
            row["urgency"] = item.urgency or ""
            row["rate"] = item.rate
            row["tags"] = item.tags or "[]"
            row["checked_at"] = item.checked_at
            row["bypass_ara"] = item.bypass_ara
            row["publisher_channel_id"] = item.publisher_channel_id
            row["created_at"] = item.created_at.isoformat() if item.created_at else None
        elif tab in ("rss", "web"):
            row["title"] = (item.title or "")[:200]
            row["link"] = item.link or ""
            row["category"] = item.category or ""
            row["tags"] = item.tags or "[]"
            row["processed"] = item.processed
            row["post_id"] = item.post_id
            row["created_at"] = item.created_at.isoformat() if item.created_at else None
        elif tab == "generated":
            row["text"] = (item.text or "")[:200]
            row["category"] = item.category or ""
            row["tags"] = item.tags or "[]"
            row["moderation_status"] = item.moderation_status or "pending"
            row["bypass_ara"] = item.bypass_ara
            row["publisher_channel_id"] = item.publisher_channel_id
            row["published_at"] = item.published_at.isoformat() if getattr(item, "published_at", None) else None
            row["created_at"] = item.created_at.isoformat() if item.created_at else None
        elif tab == "events":
            row["post_id"] = item.post_id
            row["context_data"] = (item.context_data or "")[:200]
            row["event_category"] = item.event_category or ""
            row["tags"] = item.tags or "[]"
            row["last_processed_at"] = item.last_processed_at.isoformat() if getattr(item, "last_processed_at", None) else None
            row["created_at"] = item.created_at.isoformat() if item.created_at else None

        rows.append(row)
    return rows


# =============================================================================
# ChromaDB индексация
# =============================================================================

_REINDEX_FLAG_FILE = "vector_store/.reindexed"

@router.get("/api/vector-index/status", tags=["News"])
async def vector_index_status():
    """Статус векторного индекса: количество записей в коллекциях и флаг первичной индексации."""
    import os
    from pathlib import Path

    stats = {"posts": 0, "news": 0, "events": 0}
    try:
        from services.vector_search.search_engine import VectorSearchEngine
        engine = VectorSearchEngine()
        s = engine.get_stats()
        stats = s
    except Exception as e:
        logger.warning(f"Не удалось получить статистику ChromaDB: {e}")

    reindexed = os.path.exists(_REINDEX_FLAG_FILE)

    return {
        "success": True,
        "stats": stats,
        "total": sum(stats.values()),
        "reindexed": reindexed,
    }


@router.post("/api/vector-index/reindex", tags=["News"])
async def trigger_reindex():
    """Запустить первичную индексацию всех записей в ChromaDB."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    # Проверяем, не запущена ли уже индексация
    lock_file = Path("vector_store/.reindexing")
    if lock_file.exists():
        return {"success": False, "error": "Индексация уже выполняется"}

    # Ставим lock
    lock_file.touch()

    try:
        # Запускаем скрипт в subprocess
        project_root = Path(__file__).parent.parent.parent.parent
        script = project_root / "scripts" / "reindex_chroma.py"

        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(project_root),
        )

        if result.returncode == 0:
            # Ставим флаг что индексация проведена
            Path(_REINDEX_FLAG_FILE).touch()

            stats = {"posts": 0, "news": 0, "events": 0}
            try:
                from services.vector_search.search_engine import VectorSearchEngine
                engine = VectorSearchEngine()
                stats = engine.get_stats()
            except Exception:
                pass

            return {
                "success": True,
                "message": f"Индексация завершена: {sum(stats.values())} записей",
                "stats": stats,
                "log": result.stdout[-500:] if len(result.stdout) > 500 else result.stdout,
            }
        else:
            return {
                "success": False,
                "error": f"Ошибка индексации: {result.stderr[-300:]}",
                "log": result.stderr[-1000:],
            }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Таймаут индексации (>5 мин)"}
    except Exception as e:
        logger.error(f"Ошибка запуска реиндексации: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        # Снимаем lock
        try:
            lock_file.unlink(missing_ok=True)
        except Exception:
            pass

