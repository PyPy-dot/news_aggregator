"""
Dashboard — API и страница аналитики.

Предоставляет:
- Страницу дашборда с графиками
- API endpoints для аналитических данных
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, or_, and_, desc, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.database import get_database_service
from services.web_admin.auth_dependency import get_optional_user, get_required_user
from services.web_admin.config import get_version

logger = logging.getLogger(__name__)

router = APIRouter()

# Пути
BASE_DIR = __file__.replace("\\", "/").rsplit("/", 1)[0]
TEMPLATES_DIR = f"{BASE_DIR}/../templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# =============================================================================
# Страница
# =============================================================================

@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request, user: dict = Depends(get_required_user)):
    """Основная страница дашборда."""
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"user": user, "version": get_version()},
    )


# =============================================================================
# API — статистика с дельтами
# =============================================================================

@router.get("/api/stats")
async def dashboard_stats(user: Optional[dict] = Depends(get_optional_user)):
    """
    Полная статистика с дельтами (сравнение за 24ч).

    Returns:
        news, channels, users, tasks — total + delta_24h (количество за последние 24ч)
    """
    from database.models import TelegramPost, Channel, User, Task, GeneratedNews, RSSSource, WebSource

    db = get_database_service()
    now = datetime.now()
    day_ago = now - timedelta(hours=24)

    stats = {}
    try:
        async with db.session_context() as session:
            # News (posts)
            r = await session.execute(select(func.count()).select_from(TelegramPost))
            total_posts = r.scalar() or 0
            r = await session.execute(
                select(func.count()).select_from(TelegramPost).where(TelegramPost.created_at >= day_ago)
            )
            stats["news"] = {"total": total_posts, "delta_24h": r.scalar() or 0}

            # Generated news
            r = await session.execute(select(func.count()).select_from(GeneratedNews))
            total_generated = r.scalar() or 0
            r = await session.execute(
                select(func.count()).select_from(GeneratedNews).where(GeneratedNews.created_at >= day_ago)
            )
            stats["generated_news"] = {"total": total_generated, "delta_24h": r.scalar() or 0}

            # Channels
            r = await session.execute(select(func.count()).select_from(Channel))
            stats["channels"] = {"total": r.scalar() or 0, "delta_24h": 0}

            # Users
            r = await session.execute(select(func.count()).select_from(User))
            total_users = r.scalar() or 0
            r = await session.execute(
                select(func.count()).select_from(User).where(User.created_at >= day_ago)
            )
            stats["users"] = {"total": total_users, "delta_24h": r.scalar() or 0}

            # Subscriptions
            r = await session.execute(
                select(func.count()).select_from(User).where(User.has_subscription == True)
            )
            stats["subscriptions"] = r.scalar() or 0

            # Tasks
            r = await session.execute(select(func.count()).select_from(Task))
            total_tasks = r.scalar() or 0
            r = await session.execute(
                select(func.count()).select_from(Task).where(
                    or_(Task.status == 'pending', Task.status == 'active')
                )
            )
            active_tasks = r.scalar() or 0
            stats["tasks"] = {"total": total_tasks, "active": active_tasks, "delta_24h": 0}

            # RSS & Web sources
            r = await session.execute(select(func.count()).select_from(RSSSource).where(RSSSource.is_active == True))
            stats["rss_sources"] = r.scalar() or 0
            r = await session.execute(select(func.count()).select_from(WebSource).where(WebSource.is_active == True))
            stats["web_sources"] = r.scalar() or 0

    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")

    return JSONResponse(content={"success": True, **stats})


# =============================================================================
# API — воронка модерации
# =============================================================================

@router.get("/api/moderation-funnel")
async def dashboard_moderation_funnel(user: Optional[dict] = Depends(get_optional_user)):
    """
    Распределение GeneratedNews по статусам модерации.

    Returns:
        {"pending": N, "approved": N, "rejected": N, "edited": N, "total": N}
    """
    from database.models import GeneratedNews

    db = get_database_service()
    try:
        async with db.session_context() as session:
            result = await session.execute(
                select(
                    GeneratedNews.moderation_status,
                    func.count(GeneratedNews.id)
                ).group_by(GeneratedNews.moderation_status)
            )
            rows = result.all()

        funnel = {"pending": 0, "approved": 0, "rejected": 0, "edited": 0, "total": 0}
        for status, count in rows:
            if status in funnel:
                funnel[status] = count
            funnel["total"] += count

        return JSONResponse(content={"success": True, **funnel})
    except Exception as e:
        logger.error(f"Moderation funnel error: {e}")
        return JSONResponse(content={"success": False, "pending": 0, "approved": 0, "rejected": 0, "edited": 0})


# =============================================================================
# API — активность по часам (последние 24ч)
# =============================================================================

@router.get("/api/activity-hourly")
async def dashboard_activity_hourly(user: Optional[dict] = Depends(get_optional_user)):
    """
    Посты по часам за последние 24 часа.

    Returns:
        {"hours": ["00:00", ...], "posts": [...], "generated": [...]}
    """
    from database.models import TelegramPost, GeneratedNews

    db = get_database_service()
    now = datetime.now()

    try:
        async with db.session_context() as session:
            # Posts по часам
            result = await session.execute(
                select(
                    func.strftime('%H', TelegramPost.created_at).label('hour'),
                    func.count(TelegramPost.id)
                )
                .where(TelegramPost.created_at >= now - timedelta(hours=24))
                .group_by(func.strftime('%H', TelegramPost.created_at))
            )
            posts_by_hour = {row[0]: row[1] for row in result.all()}

            # Generated news по часам
            result = await session.execute(
                select(
                    func.strftime('%H', GeneratedNews.created_at).label('hour'),
                    func.count(GeneratedNews.id)
                )
                .where(GeneratedNews.created_at >= now - timedelta(hours=24))
                .group_by(func.strftime('%H', GeneratedNews.created_at))
            )
            gen_by_hour = {row[0]: row[1] for row in result.all()}

        hours = [f"{h:02d}:00" for h in range(24)]
        posts = [posts_by_hour.get(f"{h:02d}", 0) for h in range(24)]
        generated = [gen_by_hour.get(f"{h:02d}", 0) for h in range(24)]

        return JSONResponse(content={"success": True, "hours": hours, "posts": posts, "generated": generated})
    except Exception as e:
        logger.error(f"Activity hourly error: {e}")
        # Fallback для PostgreSQL (strftime не работает)
        try:
            async with db.session_context() as session:
                result = await session.execute(
                    select(
                        func.to_char(TelegramPost.created_at, 'HH24').label('hour'),
                        func.count(TelegramPost.id)
                    )
                    .where(TelegramPost.created_at >= now - timedelta(hours=24))
                    .group_by(func.to_char(TelegramPost.created_at, 'HH24'))
                )
                posts_by_hour = {row[0]: row[1] for row in result.all()}

                result = await session.execute(
                    select(
                        func.to_char(GeneratedNews.created_at, 'HH24').label('hour'),
                        func.count(GeneratedNews.id)
                    )
                    .where(GeneratedNews.created_at >= now - timedelta(hours=24))
                    .group_by(func.to_char(GeneratedNews.created_at, 'HH24'))
                )
                gen_by_hour = {row[0]: row[1] for row in result.all()}

            hours = [f"{h:02d}:00" for h in range(24)]
            posts = [posts_by_hour.get(f"{h:02d}", 0) for h in range(24)]
            generated = [gen_by_hour.get(f"{h:02d}", 0) for h in range(24)]

            return JSONResponse(content={"success": True, "hours": hours, "posts": posts, "generated": generated})
        except Exception as e2:
            logger.error(f"Activity hourly PG fallback error: {e2}")
            return JSONResponse(content={
                "success": True,
                "hours": [f"{h:02d}:00" for h in range(24)],
                "posts": [0] * 24,
                "generated": [0] * 24,
            })


# =============================================================================
# API — категории (топ-10)
# =============================================================================

@router.get("/api/categories")
async def dashboard_categories(user: Optional[dict] = Depends(get_optional_user)):
    """
    Распределение постов и сгенерированных новостей по категориям.

    Returns:
        {"posts": [{"category": "...", "count": N}], "generated": [...]}
    """
    from database.models import TelegramPost, GeneratedNews

    db = get_database_service()
    try:
        async with db.session_context() as session:
            # Posts by category
            result = await session.execute(
                select(
                    TelegramPost.category,
                    func.count(TelegramPost.id)
                )
                .group_by(TelegramPost.category)
                .order_by(desc(func.count(TelegramPost.id)))
                .limit(10)
            )
            posts_cats = [{"category": row[0] or "Без категории", "count": row[1]} for row in result.all()]

            # Generated by category
            result = await session.execute(
                select(
                    GeneratedNews.category,
                    func.count(GeneratedNews.id)
                )
                .group_by(GeneratedNews.category)
                .order_by(desc(func.count(GeneratedNews.id)))
                .limit(10)
            )
            gen_cats = [{"category": row[0] or "Без категории", "count": row[1]} for row in result.all()]

        return JSONResponse(content={"success": True, "posts": posts_cats, "generated": gen_cats})
    except Exception as e:
        logger.error(f"Categories error: {e}")
        return JSONResponse(content={"success": True, "posts": [], "generated": []})


# =============================================================================
# API — задачи по статусам
# =============================================================================

@router.get("/api/tasks-by-status")
async def dashboard_tasks_by_status(user: Optional[dict] = Depends(get_optional_user)):
    """
    Задачи по статусам.

    Returns:
        {"pending": N, "active": N, "completed": N, "failed": N, ...}
    """
    from database.models import Task

    db = get_database_service()
    try:
        async with db.session_context() as session:
            result = await session.execute(
                select(Task.status, func.count(Task.id)).group_by(Task.status)
            )
            rows = result.all()

        status_counts = {row[0]: row[1] for row in rows}

        # Tasks created in last 24h
        day_ago = datetime.now() - timedelta(hours=24)
        r = await db.session_context().__aenter__()
        try:
            r2 = await r.execute(
                select(func.count()).select_from(Task).where(Task.created_at >= day_ago)
            )
            delta = r2.scalar() or 0
        finally:
            await r.close()

        return JSONResponse(content={"success": True, **status_counts, "delta_24h": delta})
    except Exception as e:
        logger.error(f"Tasks by status error: {e}")
        return JSONResponse(content={"success": True, "pending": 0, "active": 0, "completed": 0, "failed": 0})


# =============================================================================
# API — урговость постов
# =============================================================================

@router.get("/api/urgency-distribution")
async def dashboard_urgency_distribution(user: Optional[dict] = Depends(get_optional_user)):
    """
    Распределение постов по уровню срочности (1-5).

    Returns:
        {"1": N, "2": N, "3": N, "4": N, "5": N}
    """
    from database.models import TelegramPost

    db = get_database_service()
    try:
        async with db.session_context() as session:
            result = await session.execute(
                select(TelegramPost.urgency, func.count(TelegramPost.id)).group_by(TelegramPost.urgency)
            )
            rows = result.all()

        urgency = {str(i): 0 for i in range(1, 6)}
        for val, count in rows:
            urgency[val or "unknown"] = count

        return JSONResponse(content={"success": True, **urgency})
    except Exception as e:
        logger.error(f"Urgency distribution error: {e}")
        return JSONResponse(content={"success": True, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0})


# =============================================================================
# API — топ каналов по постам
# =============================================================================

@router.get("/api/top-channels")
async def dashboard_top_channels(
    limit: int = 10,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Топ каналов-источников по количеству постов.

    Returns:
        [{"title": "...", "posts": N, "trust_rating": X, "is_trusted": bool}, ...]
    """
    from database.models import Channel, TelegramPost

    db = get_database_service()
    try:
        async with db.session_context() as session:
            result = await session.execute(
                select(
                    Channel.title,
                    func.count(TelegramPost.id).label('posts'),
                    Channel.trust_rating,
                    Channel.is_trusted,
                )
                .outerjoin(TelegramPost, Channel.channel_id == TelegramPost.channel_id)
                .group_by(Channel.id)
                .order_by(desc(func.count(TelegramPost.id)))
                .limit(limit)
            )
            rows = result.all()

        channels = [
            {
                "title": row[0] or "Без названия",
                "posts": row[1],
                "trust_rating": round(row[2], 2) if row[2] else 0,
                "is_trusted": bool(row[3]),
            }
            for row in rows
        ]

        return JSONResponse(content={"success": True, "channels": channels})
    except Exception as e:
        logger.error(f"Top channels error: {e}")
        return JSONResponse(content={"success": True, "channels": []})


# =============================================================================
# API — тренд постов за 7 дней
# =============================================================================

@router.get("/api/trend-7d")
async def dashboard_trend_7d(user: Optional[dict] = Depends(get_optional_user)):
    """
    Посты и сгенерированные новости по дням за последние 7 дней.

    Returns:
        {"days": ["11.08", ...], "posts": [...], "generated": [...]}
    """
    from database.models import TelegramPost, GeneratedNews

    db = get_database_service()
    now = datetime.now()

    try:
        async with db.session_context() as session:
            # Posts по дням (SQLite strftime)
            result = await session.execute(
                select(
                    func.strftime('%m.%d', TelegramPost.created_at).label('day'),
                    func.count(TelegramPost.id)
                )
                .where(TelegramPost.created_at >= now - timedelta(days=7))
                .group_by(func.strftime('%m.%d', TelegramPost.created_at))
                .order_by(text('1'))
            )
            posts_by_day = {row[0]: row[1] for row in result.all()}

            result = await session.execute(
                select(
                    func.strftime('%m.%d', GeneratedNews.created_at).label('day'),
                    func.count(GeneratedNews.id)
                )
                .where(GeneratedNews.created_at >= now - timedelta(days=7))
                .group_by(func.strftime('%m.%d', GeneratedNews.created_at))
                .order_by(text('1'))
            )
            gen_by_day = {row[0]: row[1] for row in result.all()}

        # Build last 7 days labels
        days = [(now - timedelta(days=6 - i)).strftime('%m.%d') for i in range(7)]
        posts = [posts_by_day.get(d, 0) for d in days]
        generated = [gen_by_day.get(d, 0) for d in days]

        return JSONResponse(content={"success": True, "days": days, "posts": posts, "generated": generated})
    except Exception as e:
        logger.error(f"Trend 7d error: {e}")
        # Fallback PostgreSQL
        try:
            async with db.session_context() as session:
                result = await session.execute(
                    select(
                        func.to_char(TelegramPost.created_at, 'MM.DD').label('day'),
                        func.count(TelegramPost.id)
                    )
                    .where(TelegramPost.created_at >= now - timedelta(days=7))
                    .group_by(func.to_char(TelegramPost.created_at, 'MM.DD'))
                    .order_by(text('1'))
                )
                posts_by_day = {row[0]: row[1] for row in result.all()}

                result = await session.execute(
                    select(
                        func.to_char(GeneratedNews.created_at, 'MM.DD').label('day'),
                        func.count(GeneratedNews.id)
                    )
                    .where(GeneratedNews.created_at >= now - timedelta(days=7))
                    .group_by(func.to_char(GeneratedNews.created_at, 'MM.DD'))
                    .order_by(text('1'))
                )
                gen_by_day = {row[0]: row[1] for row in result.all()}

            days = [(now - timedelta(days=6 - i)).strftime('%m.%d') for i in range(7)]
            posts = [posts_by_day.get(d, 0) for d in days]
            generated = [gen_by_day.get(d, 0) for d in days]

            return JSONResponse(content={"success": True, "days": days, "posts": posts, "generated": generated})
        except Exception as e2:
            logger.error(f"Trend 7d PG fallback error: {e2}")
            return JSONResponse(content={
                "success": True,
                "days": [(now - timedelta(days=6 - i)).strftime('%m.%d') for i in range(7)],
                "posts": [0] * 7,
                "generated": [0] * 7,
            })


# =============================================================================
# API — источники: Telegram / RSS / Web
# =============================================================================

@router.get("/api/sources-overview")
async def dashboard_sources_overview(user: Optional[dict] = Depends(get_optional_user)):
    """
    Обзор источников: сколько активных RSS/Web, сколько постов из Telegram.

    Returns:
        {"rss_active": N, "web_active": N, "rss_news_total": N, "web_news_total": N, "tg_posts": N}
    """
    from database.models import RSSSource, WebSource, RSSNews, WebNews, TelegramPost

    db = get_database_service()
    try:
        async with db.session_context() as session:
            r = await session.execute(select(func.count()).select_from(RSSSource).where(RSSSource.is_active == True))
            rss_active = r.scalar() or 0

            r = await session.execute(select(func.count()).select_from(WebSource).where(WebSource.is_active == True))
            web_active = r.scalar() or 0

            r = await session.execute(select(func.count()).select_from(RSSNews))
            rss_news = r.scalar() or 0

            r = await session.execute(select(func.count()).select_from(WebNews))
            web_news = r.scalar() or 0

            r = await session.execute(select(func.count()).select_from(TelegramPost))
            tg_posts = r.scalar() or 0

        return JSONResponse(content={
            "success": True,
            "rss_active": rss_active,
            "web_active": web_active,
            "rss_news_total": rss_news,
            "web_news_total": web_news,
            "tg_posts": tg_posts,
        })
    except Exception as e:
        logger.error(f"Sources overview error: {e}")
        return JSONResponse(content={"success": True, "rss_active": 0, "web_active": 0})
