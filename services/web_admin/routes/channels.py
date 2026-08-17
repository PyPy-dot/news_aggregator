"""
Web Admin — Каналы.

Единый список каналов: источники мониторинга (channels) + каналы публикации (publishers).
Каждая запись содержит type: "channel" | "publisher" для различения.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, desc, asc, or_

from database.models import Channel, Publisher
from services.database import get_database_service
from services.search_db import search_morph
from services.web_admin.auth_dependency import get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialize_channel(ch: Channel) -> dict:
    """Сериализовать запись channels с type=channel."""
    return {
        "id": ch.id,
        "db_id": ch.id,
        "type": "channel",
        "channel_id": ch.channel_id,
        "title": ch.title or "",
        "description": ch.description or "",
        "trust_rating": ch.trust_rating,
        "is_trusted": ch.is_trusted,
        "tags": ch.tags or "[]",
        "category": "",
        "is_active": None,
        "created_at": None,
    }


def _serialize_publisher(pub: Publisher) -> dict:
    """Сериализовать запись publishers с type=publisher."""
    return {
        "id": pub.id,
        "db_id": pub.id,
        "type": "publisher",
        "channel_id": pub.channel_id,
        "title": pub.title or "",
        "description": pub.description or "",
        "trust_rating": None,
        "is_trusted": None,
        "tags": "[]",
        "category": pub.category or "",
        "is_active": pub.is_active,
        "created_at": pub.created_at.isoformat() if pub.created_at else None,
    }


# =============================================================================
# GET /api/channels — объединённый список с пагинацией
# =============================================================================

@router.get("/api/channels", tags=["Channels"])
async def list_channels_merged(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("title", pattern="^(id|title|channel_id|type|created_at)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    channel_type: Optional[str] = Query(None, description='Фильтр по типу: "channel" или "publisher"'),
    search_ids: Optional[str] = Query(None, description="Комма-разделённые ID из поискового запроса"),
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Получить объединённый список каналов (источники + публикация).

    Каждая запись содержит type: "channel" | "publisher".
    """
    db_service = get_database_service()

    try:
        # Разбираем search_ids
        id_filter: Optional[list[int]] = None
        if search_ids:
            if search_ids == "__empty__":
                return {
                    "success": True,
                    "items": [],
                    "total": 0,
                    "page": page,
                    "limit": limit,
                    "pages": 0,
                    "sort_by": sort_by,
                    "sort_dir": sort_dir,
                }
            try:
                id_filter = [int(x.strip()) for x in search_ids.split(",") if x.strip()]
            except ValueError:
                pass

        all_items: list[dict] = []

        async with db_service.session_context() as session:
            # Загружаем каналы мониторинга
            if not channel_type or channel_type == "channel":
                ch_stmt = select(Channel).order_by(Channel.id)
                ch_items = (await session.execute(ch_stmt)).scalars().all()
                all_items.extend(_serialize_channel(c) for c in ch_items)

            # Загружаем каналы публикации
            if not channel_type or channel_type == "publisher":
                pub_stmt = select(Publisher).order_by(Publisher.id)
                pub_items = (await session.execute(pub_stmt)).scalars().all()
                all_items.extend(_serialize_publisher(p) for p in pub_items)

        # Фильтр по search_ids (результаты поиска)
        if id_filter:
            id_set = set(id_filter)
            all_items = [i for i in all_items if i["db_id"] in id_set]

        # Считаем total до сортировки/пагинации
        total = len(all_items)

        # Сортировка на Python-уровне (обе таблицы вместе)
        order_reverse = sort_dir == "desc"
        if sort_by == "title":
            all_items.sort(key=lambda x: (x.get("title") or "").lower(), reverse=order_reverse)
        elif sort_by == "id":
            all_items.sort(key=lambda x: x.get("id", 0), reverse=order_reverse)
        elif sort_by == "channel_id":
            all_items.sort(key=lambda x: x.get("channel_id") or 0, reverse=order_reverse)
        elif sort_by == "type":
            all_items.sort(key=lambda x: x.get("type", ""), reverse=order_reverse)
        elif sort_by == "created_at":
            all_items.sort(key=lambda x: x.get("created_at") or "", reverse=order_reverse)

        # Пагинация
        start = (page - 1) * limit
        end = start + limit
        paged = all_items[start:end]
        pages = (total + limit - 1) // limit if limit else 1

        return {
            "success": True,
            "items": paged,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": pages,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        }

    except Exception as e:
        logger.error(f"Ошибка получения списка каналов: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "items": [],
            "total": 0,
            "page": page,
            "limit": limit,
            "pages": 1,
        }


# =============================================================================
# GET /api/channels/detail/{id}?type=... — детальная запись для модалки
# =============================================================================

@router.get("/api/channels/detail/{db_id}", tags=["Channels"])
async def get_channel_detail(
    db_id: int,
    channel_type: str = Query(..., description='type: "channel" или "publisher"'),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Получить полные данные канала для модалки редактирования."""
    db_service = get_database_service()

    try:
        async with db_service.session_context() as session:
            if channel_type == "channel":
                result = await session.execute(select(Channel).where(Channel.id == db_id))
                ch = result.scalar_one_or_none()
                if not ch:
                    return JSONResponse(status_code=404, content={"success": False, "error": f"Источник #{db_id} не найден"})
                return {
                    "success": True,
                    "type": "channel",
                    "id": ch.id,
                    "channel_id": ch.channel_id,
                    "title": ch.title or "",
                    "description": ch.description or "",
                    "trust_rating": ch.trust_rating,
                    "is_trusted": ch.is_trusted,
                    "tags": ch.tags or "[]",
                }
            elif channel_type == "publisher":
                result = await session.execute(select(Publisher).where(Publisher.id == db_id))
                pub = result.scalar_one_or_none()
                if not pub:
                    return JSONResponse(status_code=404, content={"success": False, "error": f"Публикатор #{db_id} не найден"})
                return {
                    "success": True,
                    "type": "publisher",
                    "id": pub.id,
                    "channel_id": pub.channel_id,
                    "title": pub.title or "",
                    "description": pub.description or "",
                    "is_active": pub.is_active,
                    "category": pub.category or "",
                }
            else:
                return JSONResponse(status_code=400, content={"success": False, "error": "Неизвестный тип"})
    except Exception as e:
        logger.error(f"Ошибка получения деталей: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =============================================================================
# GET /api/categories — список категорий из справочника (для dropdown)
# =============================================================================

@router.get("/api/categories", tags=["Channels"])
async def list_categories(
    user: Optional[dict] = Depends(get_optional_user),
):
    """Получить список категорий из справочника + из publishers (для dropdown)."""
    from database.models import NewsCategory
    from sqlalchemy import distinct

    db_service = get_database_service()

    try:
        async with db_service.session_context() as session:
            # Категории из справочника
            result = await session.execute(
                select(NewsCategory).where(NewsCategory.is_active == True)
                .order_by(NewsCategory.name)
            )
            cats = result.scalars().all()

            # Уникальные категории из publishers
            pub_result = await session.execute(
                select(distinct(Publisher.category)).where(
                    Publisher.category.isnot(None),
                    Publisher.category != "",
                ).order_by(Publisher.category)
            )
            pub_cats = pub_result.scalars().all()

        all_names = {c.name for c in cats if c.name}
        for c in pub_cats:
            all_names.add(c)

        return {
            "success": True,
            "categories": [{"value": c, "label": c} for c in sorted(all_names)],
        }

    except Exception as e:
        logger.error(f"Ошибка получения категорий: {e}", exc_info=True)
        return {"success": False, "error": str(e), "categories": []}


# =============================================================================
# Поиск каналов — по названию/описанию
# =============================================================================

@router.post("/api/search", tags=["Channels"])
async def search_channels(
    body: dict,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Поиск каналов по названию/описанию через SQL LIKE + морфологический n-gram.

    Body: { "query": "...", "channel_type": "channel" | "publisher" | null, "limit": 100 }
    """
    query = (body.get("query") or "").strip()
    channel_type = body.get("channel_type") or None
    limit = min(body.get("limit", 100), 500)

    if not query:
        return {"success": True, "ids": [], "types": {}, "search_type": "none"}

    db_service = get_database_service()

    try:
        found: dict[int, str] = {}  # id -> type

        async with db_service.session_context() as session:
            # Поиск в channels
            if not channel_type or channel_type == "channel":
                like_variants = [f"%{query}%", f"%{query.lower()}%", f"%{query.upper()}%"]
                conditions = []
                for lv in like_variants:
                    conditions.append(Channel.title.like(lv))
                    conditions.append(Channel.description.like(lv))

                total_result = await session.execute(
                    select(func.count()).select_from(
                        select(Channel.id).where(or_(*conditions)).subquery()
                    )
                )
                total_like = total_result.scalar() or 0

                if total_like > 0:
                    items = (await session.execute(
                        select(Channel.id).where(or_(*conditions)).limit(limit)
                    )).scalars().all()
                    for cid in items:
                        found[cid] = "channel"
                else:
                    fallback = (await session.execute(
                        select(Channel).order_by(desc(Channel.id)).limit(limit * 10)
                    )).scalars().all()
                    for ch in fallback:
                        if (search_morph(ch.title or "", query) or
                                search_morph(ch.description or "", query)):
                            found[ch.id] = "channel"

            # Поиск в publishers
            if not channel_type or channel_type == "publisher":
                like_variants = [f"%{query}%", f"%{query.lower()}%", f"%{query.upper()}%"]
                conditions = []
                for lv in like_variants:
                    conditions.append(Publisher.title.like(lv))
                    conditions.append(Publisher.description.like(lv))

                total_result = await session.execute(
                    select(func.count()).select_from(
                        select(Publisher.id).where(or_(*conditions)).subquery()
                    )
                )
                total_like = total_result.scalar() or 0

                if total_like > 0:
                    items = (await session.execute(
                        select(Publisher.id).where(or_(*conditions)).limit(limit)
                    )).scalars().all()
                    for pid in items:
                        found[pid] = "publisher"
                else:
                    fallback = (await session.execute(
                        select(Publisher).order_by(desc(Publisher.id)).limit(limit * 10)
                    )).scalars().all()
                    for pub in fallback:
                        if (search_morph(pub.title or "", query) or
                                search_morph(pub.description or "", query)):
                            found[pub.id] = "publisher"

        search_type = "text" if total_like > 0 else "morph"

        return {
            "success": True,
            "ids": list(found.keys())[:limit],
            "types": found,
            "search_type": search_type,
            "total": len(found),
        }

    except Exception as e:
        logger.error(f"Ошибка поиска каналов: {e}", exc_info=True)
        return {"success": False, "error": str(e), "ids": [], "types": {}}


# =============================================================================
# Семантический поиск каналов по категории/тегам через ChromaDB
# =============================================================================

@router.post("/api/search-semantic", tags=["Channels"])
async def search_channels_semantic(
    body: dict,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Семантический поиск каналов по категории/тегам через ChromaDB.

    Ищет релевантные новости/посты по запросу, затем определяет какие
    каналы (sources/publishers) эти новости представляют.

    Body: {
        "query": "политика",
        "channel_type": "channel" | "publisher" | null,
        "limit": 50
    }

    Возвращает: список уникальных channel db_id с type и score.
    """
    query = (body.get("query") or "").strip()
    channel_type = body.get("channel_type") or None
    limit = min(body.get("limit", 50), 500)

    if not query:
        return {"success": True, "ids": [], "types": {}, "search_type": "none"}

    db_service = get_database_service()

    try:
        found: dict[int, str] = {}

        # Этап 1: Семантический поиск через ChromaDB
        vector_service = _get_vector_search_service()
        if vector_service:
            try:
                # Ищем похожие посты
                chroma_results = await vector_service.find_similar_posts(
                    text=query,
                    limit=limit * 4,
                    min_score=0.3,
                )

                # Собираем уникальные channel_id из постов
                channel_tg_ids = set()
                for r in chroma_results:
                    meta = r.get("metadata", {})
                    ch_id = meta.get("channel_id")
                    if ch_id:
                        channel_tg_ids.add(int(ch_id))

                # Если нужны publishers — ищем также сгенерированные новости
                if not channel_type or channel_type == "publisher":
                    news_results = await vector_service.find_related_news(
                        text=query,
                        limit=limit * 4,
                        min_score=0.3,
                    )
                    for r in news_results:
                        meta = r.get("metadata", {})
                        pub_id = meta.get("publisher_channel_id")
                        if pub_id:
                            channel_tg_ids.add(int(pub_id))

                # Маппим channel_id (telegram) → db_id
                async with db_service.session_context() as session:
                    if channel_tg_ids and (not channel_type or channel_type == "channel"):
                        ch_result = await session.execute(
                            select(Channel.id, Channel.channel_id).where(
                                Channel.channel_id.in_(list(channel_tg_ids))
                            )
                        )
                        for row in ch_result.all():
                            found[row.id] = "channel"

                    if channel_tg_ids and (not channel_type or channel_type == "publisher"):
                        pub_result = await session.execute(
                            select(Publisher.id, Publisher.channel_id).where(
                                Publisher.channel_id.in_(list(channel_tg_ids))
                            )
                        )
                        for row in pub_result.all():
                            found[row.id] = "publisher"

            except Exception as e:
                logger.warning(f"Семантический поиск каналов не выполнен: {e}")

        # Этап 2: Fallback — LIKE + морфологический поиск по tags/category
        if not found:
            async with db_service.session_context() as session:
                if not channel_type or channel_type == "channel":
                    like_vars = [f"%{query}%", f"%{query.lower()}%", f"%{query.upper()}%"]
                    cond = or_(Channel.tags.like(lv) for lv in like_vars)
                    total_like = (await session.execute(
                        select(func.count()).select_from(
                            select(Channel.id).where(cond).subquery()
                        )
                    )).scalar() or 0

                    if total_like > 0:
                        items = (await session.execute(
                            select(Channel.id).where(cond)
                        )).scalars().all()
                        for cid in items:
                            found[cid] = "channel"
                    else:
                        # Морфологический поиск по tags
                        fallback = (await session.execute(
                            select(Channel).order_by(desc(Channel.id)).limit(limit * 10)
                        )).scalars().all()
                        for ch in fallback:
                            if search_morph(ch.tags or "", query):
                                found[ch.id] = "channel"

                if not channel_type or channel_type == "publisher":
                    like_vars = [f"%{query}%", f"%{query.lower()}%", f"%{query.upper()}%"]
                    cond = or_(
                        Publisher.category.like(lv)
                        for lv in like_vars
                    )
                    total_like = (await session.execute(
                        select(func.count()).select_from(
                            select(Publisher.id).where(cond).subquery()
                        )
                    )).scalar() or 0

                    if total_like > 0:
                        items = (await session.execute(
                            select(Publisher.id).where(cond)
                        )).scalars().all()
                        for pid in items:
                            found[pid] = "publisher"
                    else:
                        # Морфологический поиск по category + description
                        fallback = (await session.execute(
                            select(Publisher).order_by(desc(Publisher.id)).limit(limit * 10)
                        )).scalars().all()
                        for pub in fallback:
                            if (search_morph(pub.category or "", query) or
                                    search_morph(pub.description or "", query)):
                                found[pub.id] = "publisher"

        search_type = "semantic" if vector_service and found else ("text" if found else "none")

        return {
            "success": True,
            "ids": list(found.keys())[:limit],
            "types": found,
            "search_type": search_type,
            "total": len(found),
        }

    except Exception as e:
        logger.error(f"Ошибка семантического поиска: {e}", exc_info=True)
        return {"success": False, "error": str(e), "ids": [], "types": {}}


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


# =============================================================================
# PUT /api/channels/{id} — редактировать источник
# =============================================================================

@router.put("/api/channels/{channel_id}", tags=["Channels"])
async def update_channel(
    channel_id: int,
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Обновить источник мониторинга."""
    try:
        data = await request.json()
        db_service = get_database_service()

        async with db_service.session_context() as session:
            result = await session.execute(select(Channel).where(Channel.id == channel_id))
            ch = result.scalar_one_or_none()

            if not ch:
                return JSONResponse(status_code=404, content={"success": False, "error": f"Канал #{channel_id} не найден"})

            if "title" in data:
                ch.title = data["title"].strip()
            if "description" in data:
                ch.description = data["description"].strip()
            if "trust_rating" in data:
                ch.trust_rating = float(data["trust_rating"])
            if "is_trusted" in data:
                ch.is_trusted = bool(data["is_trusted"])
            if "tags" in data:
                ch.tags = data["tags"]

            await session.commit()

        logger.info(f"Источник #{channel_id} обновлён")
        return {"success": True, "id": channel_id}

    except Exception as e:
        logger.error(f"Ошибка обновления канала: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =============================================================================
# DELETE /api/channels/{id} — удалить источник
# =============================================================================

@router.delete("/api/channels/{channel_id}", tags=["Channels"])
async def delete_channel(
    channel_id: int,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Удалить источник мониторинга."""
    db_service = get_database_service()

    try:
        async with db_service.session_context() as session:
            result = await session.execute(select(Channel).where(Channel.id == channel_id))
            ch = result.scalar_one_or_none()

            if not ch:
                return JSONResponse(status_code=404, content={"success": False, "error": f"Канал #{channel_id} не найден"})

            await session.delete(ch)
            await session.commit()

        logger.info(f"Источник #{channel_id} удалён")
        return {"success": True, "id": channel_id}

    except Exception as e:
        logger.error(f"Ошибка удаления канала: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =============================================================================
# PUT /api/publishers/{id} — редактировать канал публикации
# =============================================================================

@router.put("/api/publishers/{publisher_id}", tags=["Channels"])
async def update_publisher(
    publisher_id: int,
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Обновить канал публикации."""
    try:
        data = await request.json()
        db_service = get_database_service()

        async with db_service.session_context() as session:
            result = await session.execute(select(Publisher).where(Publisher.id == publisher_id))
            pub = result.scalar_one_or_none()

            if not pub:
                return JSONResponse(status_code=404, content={"success": False, "error": f"Публикатор #{publisher_id} не найден"})

            if "title" in data and data["title"] is not None:
                pub.title = data["title"].strip()
            if "description" in data and data["description"] is not None:
                pub.description = data["description"].strip()
            if "is_active" in data:
                pub.is_active = bool(data["is_active"])
            if "category" in data:
                pub.category = data["category"].strip() or None

            await session.commit()

        logger.info(f"Публикатор #{publisher_id} обновлён")
        return {"success": True, "id": publisher_id}

    except Exception as e:
        logger.error(f"Ошибка обновления публикатора: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =============================================================================
# DELETE /api/publishers/{id} — удалить канал публикации
# =============================================================================

@router.delete("/api/publishers/{publisher_id}", tags=["Channels"])
async def delete_publisher(
    publisher_id: int,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Удалить канал публикации."""
    db_service = get_database_service()

    try:
        async with db_service.session_context() as session:
            result = await session.execute(select(Publisher).where(Publisher.id == publisher_id))
            pub = result.scalar_one_or_none()

            if not pub:
                return JSONResponse(status_code=404, content={"success": False, "error": f"Публикатор #{publisher_id} не найден"})

            await session.delete(pub)
            await session.commit()

        logger.info(f"Публикатор #{publisher_id} удалён")
        return {"success": True, "id": publisher_id}

    except Exception as e:
        logger.error(f"Ошибка удаления публикатора: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =============================================================================
# GET /api/publishers/list — простой список для dropdown (перенесено из app.py)
# =============================================================================

@router.get("/api/publishers/list", tags=["Channels"])
async def list_publishers_dropdown(
    user: Optional[dict] = Depends(get_optional_user),
):
    """Получить список каналов публикации (для dropdown в модалках)."""
    try:
        db_service = get_database_service()
        async with db_service.session_context() as session:
            result = await session.execute(select(Publisher).where(Publisher.is_active == True).order_by(Publisher.title))
            publishers = result.scalars().all()

        return {"success": True, "publishers": [
            {"id": p.id, "channel_id": p.channel_id, "title": p.title, "description": p.description or ""}
            for p in publishers
        ]}

    except Exception as e:
        logger.error(f"Ошибка получения publishers: {e}", exc_info=True)
        return {"success": False, "error": str(e), "publishers": []}


# =============================================================================
# POST /api/channels/resolve-link (перенесено из app.py)
# =============================================================================

@router.post("/api/channels/resolve-link", tags=["Channels"])
async def resolve_channel_link(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Получить ID, название и описание канала по Telegram-ссылке или @username.

    Body: { "link": "@channelname" или "t.me/channelname" }
    """
    try:
        data = await request.json()
        link = data.get("link", "").strip()

        if not link:
            return {"success": False, "error": "Укажите ссылку на канал"}

        # Парсим ссылку -> username
        username = link
        if link.startswith("t.me/"):
            username = link.split("/")[1].split("/")[0].split("?")[0]
        elif link.startswith("https://t.me/"):
            username = link.split("/")[3].split("/")[0].split("?")[0]
        elif not link.startswith("@"):
            username = "@" + link

        if not username.startswith("@"):
            username = "@" + username

        from services.bot.bot import get_bot_instance_async

        bot = await get_bot_instance_async(wait=False, timeout=5.0)
        if not bot:
            return {"success": False, "error": "Бот не запущен. Запустите бота через консоль."}

        try:
            chat = await bot.get_chat(chat_id=username)
            return {
                "success": True,
                "channel_id": chat.id,
                "title": chat.title or "",
                "description": chat.description or "",
            }
        except Exception as e:
            error_msg = str(e).lower()
            if "not_found" in error_msg or "user not found" in error_msg:
                return {"success": False, "error": f"Канал @{username} не найден. Проверьте ссылку."}
            elif "chat_action_is_not_allowed" in error_msg or "privacy" in error_msg:
                return {
                    "success": False,
                    "error": "Бот не может получить данные канала. Для добавления в publishers бот должен быть участником канала.",
                    "partial": True,
                }
            else:
                return {
                    "success": False,
                    "error": f"Не удалось получить данные: {e}. Для publishers бот должен быть участником канала.",
                    "partial": True,
                }

    except Exception as e:
        logger.error(f"Ошибка резолва ссылки: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# POST /api/channels — создать источник мониторинга (перенесено из app.py)
# =============================================================================

@router.post("/api/channels", tags=["Channels"])
async def create_channel(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Добавить канал мониторинга (источник).

    Body: { "channel_id": -100..., "title": "...", "description": "...", "is_trusted": false }
    """
    try:
        data = await request.json()
        channel_id = data.get("channel_id")
        title = data.get("title", "").strip()
        description = data.get("description", "").strip()
        is_trusted = data.get("is_trusted", False)

        if not channel_id or not title:
            return {"success": False, "error": "Укажите channel_id и title"}

        db_service = get_database_service()
        async with db_service.session_context() as session:
            existing = await session.execute(
                select(Channel).where(Channel.channel_id == int(channel_id))
            )
            if existing.scalar_one_or_none():
                return {"success": False, "error": f"Канал с ID {channel_id} уже существует"}

            new_ch = Channel(
                channel_id=int(channel_id),
                title=title,
                description=description,
                is_trusted=is_trusted,
                trust_rating=1.0 if is_trusted else 0.5,
            )
            session.add(new_ch)
            await session.commit()

        return {"success": True, "id": new_ch.id, "type": "channel"}

    except Exception as e:
        logger.error(f"Ошибка добавления канала: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# POST /api/publishers — создать канал публикации (перенесено из app.py)
# =============================================================================

@router.post("/api/publishers", tags=["Channels"])
async def create_publisher(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Добавить канал публикации.

    Body: { "channel_id": -100..., "title": "...", "description": "...", "category": "..." }
    """
    try:
        data = await request.json()
        channel_id = data.get("channel_id")
        title = data.get("title", "").strip()
        description = data.get("description", "").strip()
        category = data.get("category", "").strip() or None

        if not channel_id or not title:
            return {"success": False, "error": "Укажите channel_id и title"}

        db_service = get_database_service()
        async with db_service.session_context() as session:
            existing = await session.execute(
                select(Publisher).where(Publisher.channel_id == int(channel_id))
            )
            if existing.scalar_one_or_none():
                return {"success": False, "error": f"Канал с ID {channel_id} уже существует в publishers"}

            new_pub = Publisher(
                channel_id=int(channel_id),
                title=title,
                description=description,
                category=category,
            )
            session.add(new_pub)
            await session.commit()

        return {"success": True, "id": new_pub.id, "type": "publisher"}

    except Exception as e:
        logger.error(f"Ошибка добавления публикатора: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
