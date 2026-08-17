"""
Web Admin — Пользователи.

REST API для просмотра списка пользователей с пагинацией и сортировкой,
а также получение имени из Telegram API.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, desc, asc, or_

from database.models import User
from services.database import get_database_service
from services.search_db import text_search_condition, search_morph
from services.util import decrypt_user_id
from services.web_admin.auth_dependency import get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# API — список пользователей
# =============================================================================

@router.get("/api/users", tags=["Users"])
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at", pattern="^(id|role|has_subscription|created_at|subscription_ends_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    role: Optional[str] = Query(None, description="Фильтр по роли (user/admin)"),
    subscription: Optional[bool] = Query(None, description="Фильтр по подписке"),
    categories: Optional[str] = Query(None, description="Комма-разделённые категории для мультивыбора"),
    search_ids: Optional[str] = Query(None, description="Комма-разделённые ID из поискового запроса"),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Получить список пользователей с пагинацией, сортировкой и фильтрацией."""
    db_service = get_database_service()

    try:
        order_func = desc if sort_dir == "desc" else asc
        sort_col = getattr(User, sort_by, User.created_at)

        # Разбираем параметры
        id_filter = None
        if search_ids:
            if search_ids == "__empty__":
                # Фронтенд сигнализирует: поиск по тегам активен но 0 результатов
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

        cat_filter = None
        if categories:
            cat_filter = [c.strip() for c in categories.split(",") if c.strip()]

        async with db_service.session_context() as session:
            # Счётчик
            count_stmt = select(func.count()).select_from(User)
            if role:
                count_stmt = count_stmt.where(User.role == role)
            if subscription is not None:
                count_stmt = count_stmt.where(User.has_subscription == subscription)
            if cat_filter:
                # ANY-логика: пользователь имеет хотя бы одну из выбранных категорий
                cat_conditions = []
                for c in cat_filter:
                    cat_conditions.append(
                        User.preferred_categories.like(f'%"{c}"%') | User.preferred_categories.like(f"%'{c}%'")
                    )
                count_stmt = count_stmt.where(or_(*cat_conditions))
            if id_filter:
                count_stmt = count_stmt.where(User.id.in_(id_filter))

            total_result = await session.execute(count_stmt)
            total = total_result.scalar() or 0

            # Данные
            stmt = select(User).order_by(order_func(sort_col))
            if role:
                stmt = stmt.where(User.role == role)
            if subscription is not None:
                stmt = stmt.where(User.has_subscription == subscription)
            if cat_filter:
                cat_conditions = []
                for c in cat_filter:
                    cat_conditions.append(
                        User.preferred_categories.like(f'%"{c}"%') | User.preferred_categories.like(f"%'{c}%'")
                    )
                stmt = stmt.where(or_(*cat_conditions))
            if id_filter:
                stmt = stmt.where(User.id.in_(id_filter))

            stmt = stmt.offset((page - 1) * limit).limit(limit)
            items_result = await session.execute(stmt)
            items = items_result.scalars().all()

        # Сериализация с дешифровкой telegram_id
        rows = []
        for u in items:
            telegram_id = None
            try:
                telegram_id = decrypt_user_id(u.user_id_encrypted)
            except Exception as e:
                logger.warning(f"Не удалось расшифровать user_id для User ID={u.id}: {e}")

            sub_label = ""
            if u.has_subscription:
                if u.subscription_ends_at is None:
                    sub_label = "бессрочно"
                elif u.subscription_ends_at > datetime.now():
                    sub_label = u.subscription_ends_at.strftime("%Y-%m-%d")
                else:
                    sub_label = "истекла"

            rows.append({
                "id": u.id,
                "telegram_id": telegram_id,
                "role": u.role,
                "has_subscription": u.has_subscription,
                "subscription_label": sub_label,
                "subscription_started_at": u.subscription_started_at.isoformat() if u.subscription_started_at else None,
                "subscription_ends_at": u.subscription_ends_at.isoformat() if u.subscription_ends_at else None,
                "preferred_tags": u.preferred_tags or "[]",
                "preferred_categories": u.preferred_categories or "[]",
                "totp_enabled": u.totp_enabled,
                "created_at": u.created_at.isoformat() if u.created_at else None,
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
        logger.error(f"Ошибка получения списка пользователей: {e}", exc_info=True)
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
# API — получить имя из Telegram
# =============================================================================

@router.get("/api/users/{user_db_id}/telegram-name", tags=["Users"])
async def get_telegram_name(
    user_db_id: int,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Получить имя пользователя из Telegram API.

    Делает get_chat(telegram_id) через бота и возвращает first_name, last_name, username.
    Имя НЕ сохраняется в БД — грузится динамически.
    """
    db_service = get_database_service()

    # Получаем пользователя из БД
    async with db_service.session_context() as session:
        result = await session.execute(select(User).where(User.id == user_db_id))
        u = result.scalar_one_or_none()

        if not u:
            return JSONResponse(status_code=404, content={"success": False, "error": f"Пользователь #{user_db_id} не найден"})

        telegram_id = None
        try:
            telegram_id = decrypt_user_id(u.user_id_encrypted)
        except Exception as e:
            return JSONResponse(status_code=400, content={"success": False, "error": f"Не удалось расшифровать ID: {e}"})

    # Пытаемся получить имя через бота
    try:
        from services.bot.bot import get_bot_instance_async

        bot = await get_bot_instance_async(wait=False, timeout=5.0)
        if not bot:
            return {
                "success": False,
                "error": "Бот не запущен. Запустите бота через консоль.",
                "telegram_id": telegram_id,
            }

        chat = await bot.get_chat(chat_id=telegram_id)

        first_name = getattr(chat, "first_name", None) or ""
        last_name = getattr(chat, "last_name", None) or ""
        username = getattr(chat, "username", None) or ""

        full_name = f"{first_name} {last_name}".strip()

        return {
            "success": True,
            "telegram_id": telegram_id,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "full_name": full_name,
        }

    except Exception as e:
        error_msg = str(e).lower()
        if "not_found" in error_msg or "user not found" in error_msg:
            return {
                "success": False,
                "error": "Пользователь не найден в Telegram",
                "telegram_id": telegram_id,
            }
        else:
            return {
                "success": False,
                "error": f"Ошибка Telegram API: {e}",
                "telegram_id": telegram_id,
            }


# =============================================================================
# API — изменить роль
# =============================================================================

@router.post("/api/users/{user_db_id}/set-role", tags=["Users"])
async def set_user_role(
    user_db_id: int,
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Изменить роль пользователя (user / admin)."""
    try:
        data = await request.json()
        new_role = data.get("role", "").strip()

        if new_role not in ("user", "admin"):
            return JSONResponse(status_code=400, content={"success": False, "error": "Допустимые роли: user, admin"})

        db_service = get_database_service()
        async with db_service.session_context() as session:
            result = await session.execute(select(User).where(User.id == user_db_id))
            u = result.scalar_one_or_none()

            if not u:
                return JSONResponse(status_code=404, content={"success": False, "error": f"Пользователь #{user_db_id} не найден"})

            u.role = new_role
            await session.commit()

        logger.info(f"Роль пользователя #{user_db_id} изменена на '{new_role}'")
        return {"success": True, "id": user_db_id, "role": new_role}

    except Exception as e:
        logger.error(f"Ошибка изменения роли: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =============================================================================
# API — список уникальных тегов
# =============================================================================

@router.get("/api/tags", tags=["Users"])
async def list_tags(
    user: Optional[dict] = Depends(get_optional_user),
):
    """Получить список уникальных тегов из preferred_tags всех пользователей."""
    import json as json_mod

    db_service = get_database_service()

    try:
        async with db_service.session_context() as session:
            result = await session.execute(select(User.preferred_tags).where(
                User.preferred_tags.isnot(None),
                User.preferred_tags != "[]",
            ))
            raw_tags = result.scalars().all()

        tag_counts = {}
        for raw in raw_tags:
            try:
                tags = json_mod.loads(raw)
                if isinstance(tags, list):
                    for t in tags:
                        tag_counts[t] = tag_counts.get(t, 0) + 1
            except (json_mod.JSONDecodeError, TypeError):
                pass

        sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
        return {
            "success": True,
            "tags": [{"tag": t, "count": c} for t, c in sorted_tags],
        }

    except Exception as e:
        logger.error(f"Ошибка получения тегов: {e}", exc_info=True)
        return {"success": False, "error": str(e), "tags": []}


# =============================================================================
# API — список уникальных категорий
# =============================================================================

@router.get("/api/categories", tags=["Users"])
async def list_categories(
    user: Optional[dict] = Depends(get_optional_user),
):
    """Получить список категорий из справочника NewsCategory."""
    from database.models import NewsCategory

    db_service = get_database_service()

    try:
        async with db_service.session_context() as session:
            result = await session.execute(
                select(NewsCategory).where(NewsCategory.is_active == True)
                .order_by(NewsCategory.name)
            )
            cats = result.scalars().all()

        return {
            "success": True,
            "categories": [{"value": c.name, "label": c.name} for c in cats],
        }

    except Exception as e:
        logger.error(f"Ошибка получения категорий: {e}", exc_info=True)
        return {"success": False, "error": str(e), "categories": []}


# =============================================================================
# API — поиск пользователей по тегам (морфологический + LIKE)
# =============================================================================

@router.post("/api/search", tags=["Users"])
async def search_users(
    body: dict,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Поиск пользователей по тегам через SQL LIKE + морфологический n-gram.

    Body: { "query": "политика", "limit": 100 }

    Стратегия:
    1. SQL LIKE по preferred_tags и preferred_categories (адаптивный к СУБД)
    2. Fallback: морфологический поиск (n-gram) по последним N записям
    3. Возвращает список ID для подстановки в основной список
    """
    query = (body.get("query") or "").strip()
    limit = min(body.get("limit", 100), 500)

    if not query:
        return {"success": True, "ids": [], "search_type": "none"}

    db_service = get_database_service()

    try:
        async with db_service.session_context() as session:
            # Этап 1: SQL LIKE с учётом СУБД
            condition = text_search_condition(
                query=query,
                text_col=User.preferred_tags,
                category_col=User.preferred_categories,
            )

            stmt = select(User.id).where(condition)
            total_result = await session.execute(
                select(func.count()).select_from(stmt.subquery())
            )
            total_like = total_result.scalar() or 0

            found_ids = set()
            if total_like > 0:
                items = (await session.execute(stmt.limit(limit))).scalars().all()
                for item in items:
                    found_ids.add(item)
            else:
                # Этап 2: морфологический поиск по последним N записям
                fallback_stmt = select(User).order_by(desc(User.created_at)).limit(limit * 10)
                all_items = (await session.execute(fallback_stmt)).scalars().all()
                for u in all_items:
                    tags_val = u.preferred_tags or ""
                    cats_val = u.preferred_categories or ""
                    if search_morph(tags_val, query) or search_morph(cats_val, query):
                        found_ids.add(u.id)

        return {
            "success": True,
            "ids": list(found_ids)[:limit],
            "search_type": "text" if total_like > 0 else "morph",
            "total": len(found_ids),
        }

    except Exception as e:
        logger.error(f"Ошибка поиска пользователей: {e}", exc_info=True)
        return {"success": False, "error": str(e), "ids": []}


# =============================================================================
# API — изменить подписку
# =============================================================================

@router.post("/api/users/{user_db_id}/set-subscription", tags=["Users"])
async def set_user_subscription(
    user_db_id: int,
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Изменить подписку пользователя.

    Body: {
        "has_subscription": bool,
        "ends_at": "2026-12-31" | null  // null = бессрочно
    }
    """
    try:
        data = await request.json()
        has_sub = data.get("has_subscription", False)
        ends_at_str = data.get("ends_at")

        ends_at = None
        if ends_at_str:
            try:
                ends_at = datetime.strptime(ends_at_str, "%Y-%m-%d")
            except ValueError:
                return JSONResponse(status_code=400, content={"success": False, "error": "Формат даты: YYYY-MM-DD"})

        db_service = get_database_service()
        async with db_service.session_context() as session:
            result = await session.execute(select(User).where(User.id == user_db_id))
            u = result.scalar_one_or_none()

            if not u:
                return JSONResponse(status_code=404, content={"success": False, "error": f"Пользователь #{user_db_id} не найден"})

            u.has_subscription = has_sub
            if has_sub:
                u.subscription_started_at = u.subscription_started_at or datetime.now()
                u.subscription_ends_at = ends_at
            else:
                u.subscription_started_at = None
                u.subscription_ends_at = None

            await session.commit()

        logger.info(f"Подписка пользователя #{user_db_id} обновлена: has={has_sub}, ends={ends_at}")
        return {"success": True, "id": user_db_id}

    except Exception as e:
        logger.error(f"Ошибка изменения подписки: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =============================================================================
# API — удалить пользователя
# =============================================================================

@router.delete("/api/users/{user_db_id}", tags=["Users"])
async def delete_user(
    user_db_id: int,
    user: Optional[dict] = Depends(get_optional_user),
):
    """Удалить пользователя из базы данных."""
    db_service = get_database_service()

    try:
        async with db_service.session_context() as session:
            result = await session.execute(select(User).where(User.id == user_db_id))
            u = result.scalar_one_or_none()

            if not u:
                return JSONResponse(status_code=404, content={"success": False, "error": f"Пользователь #{user_db_id} не найден"})

            await session.delete(u)

        logger.info(f"Пользователь #{user_db_id} удалён")
        return {"success": True, "id": user_db_id}

    except Exception as e:
        logger.error(f"Ошибка удаления пользователя: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
