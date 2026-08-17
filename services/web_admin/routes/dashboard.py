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
async def dashboard_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Полная статистика с фильтрацией по периоду.

    Query params:
        start_date: "2026-08-01" (ISO format, optional)
        end_date: "2026-08-17" (ISO format, optional)

    Returns total (all-time) + period (within date range).
    """
    from database.models import TelegramPost, Channel, User, Task, GeneratedNews, RSSSource, WebSource

    db = get_database_service()
    now = datetime.now()

    start = now - timedelta(hours=24)
    end = now
    if start_date:
        try: start = datetime.fromisoformat(start_date)
        except ValueError: pass
    if end_date:
        try:
            end = datetime.fromisoformat(end_date)
            if end.time() == datetime.min.time(): end = end.replace(hour=23, minute=59, second=59)
        except ValueError: pass

    stats = {}
    try:
        async with db.session_context() as session:
            # News (posts)
            r = await session.execute(select(func.count()).select_from(TelegramPost))
            total_posts = r.scalar() or 0
            r = await session.execute(
                select(func.count()).select_from(TelegramPost).where(
                    TelegramPost.created_at >= start, TelegramPost.created_at <= end
                )
            )
            stats["news"] = {"total": total_posts, "period": r.scalar() or 0}

            # Generated news
            r = await session.execute(select(func.count()).select_from(GeneratedNews))
            total_gen = r.scalar() or 0
            r = await session.execute(
                select(func.count()).select_from(GeneratedNews).where(
                    GeneratedNews.created_at >= start, GeneratedNews.created_at <= end
                )
            )
            stats["generated_news"] = {"total": total_gen, "period": r.scalar() or 0}

            # Channels
            r = await session.execute(select(func.count()).select_from(Channel))
            stats["channels"] = {"total": r.scalar() or 0}

            # Users
            r = await session.execute(select(func.count()).select_from(User))
            total_users = r.scalar() or 0
            r = await session.execute(
                select(func.count()).select_from(User).where(
                    User.created_at >= start, User.created_at <= end
                )
            )
            stats["users"] = {"total": total_users, "period": r.scalar() or 0}

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
            stats["tasks"] = {"total": total_tasks, "active": r.scalar() or 0}

            # RSS & Web sources
            r = await session.execute(select(func.count()).select_from(RSSSource).where(RSSSource.is_active == True))
            stats["rss_sources"] = r.scalar() or 0
            r = await session.execute(select(func.count()).select_from(WebSource).where(WebSource.is_active == True))
            stats["web_sources"] = r.scalar() or 0

        return JSONResponse(content={
            "success": True,
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            **stats
        })

    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        return JSONResponse(content={"success": False})


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
        day_ago = datetime.now() - timedelta(hours=24)

        async with db.session_context() as session:
            result = await session.execute(
                select(Task.status, func.count(Task.id)).group_by(Task.status)
            )
            rows = result.all()
            status_counts = {row[0]: row[1] for row in rows}

            delta_result = await session.execute(
                select(func.count()).select_from(Task).where(Task.created_at >= day_ago)
            )
            delta = delta_result.scalar() or 0

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


# =============================================================================
# API — источники по дням (30 дней)
# =============================================================================

@router.get("/api/sources-30d")
async def dashboard_sources_30d(user: Optional[dict] = Depends(get_optional_user)):
    """
    Посты по источникам (Telegram, RSS, Web) за 30 дней.

    Returns:
        {"days": [...], "telegram": [...], "rss": [...], "web": [...]}
    """
    from database.models import TelegramPost, RSSNews, WebNews

    db = get_database_service()
    now = datetime.now()
    days_ago = now - timedelta(days=30)

    try:
        async with db.session_context() as session:
            tg_result = await session.execute(
                select(
                    func.strftime('%m.%d', TelegramPost.created_at).label('day'),
                    func.count(TelegramPost.id)
                )
                .where(TelegramPost.created_at >= days_ago)
                .group_by(func.strftime('%m.%d', TelegramPost.created_at))
                .order_by(text('1'))
            )
            tg_by_day = {row[0]: row[1] for row in tg_result.all()}

            rss_result = await session.execute(
                select(
                    func.strftime('%m.%d', RSSNews.created_at).label('day'),
                    func.count(RSSNews.id)
                )
                .where(RSSNews.created_at >= days_ago)
                .group_by(func.strftime('%m.%d', RSSNews.created_at))
                .order_by(text('1'))
            )
            rss_by_day = {row[0]: row[1] for row in rss_result.all()}

            web_result = await session.execute(
                select(
                    func.strftime('%m.%d', WebNews.created_at).label('day'),
                    func.count(WebNews.id)
                )
                .where(WebNews.created_at >= days_ago)
                .group_by(func.strftime('%m.%d', WebNews.created_at))
                .order_by(text('1'))
            )
            web_by_day = {row[0]: row[1] for row in web_result.all()}

        days = [(now - timedelta(days=29 - i)).strftime('%m.%d') for i in range(30)]
        return JSONResponse(content={
            "success": True,
            "days": days,
            "telegram": [tg_by_day.get(d, 0) for d in days],
            "rss": [rss_by_day.get(d, 0) for d in days],
            "web": [web_by_day.get(d, 0) for d in days],
        })
    except Exception as e:
        logger.error(f"Sources 30d error: {e}")
        days = [(now - timedelta(days=29 - i)).strftime('%m.%d') for i in range(30)]
        return JSONResponse(content={"success": True, "days": days, "telegram": [0]*30, "rss": [0]*30, "web": [0]*30})


# =============================================================================
# API — обработка постов (пайплайн статистика)
# =============================================================================

@router.get("/api/processing-stats")
async def dashboard_processing_stats(user: Optional[dict] = Depends(get_optional_user)):
    """
    Статистика пайплайна обработки: от поста до генерации.

    Returns:
        total_posts, checked_posts, unchecked_posts, generated_news,
        bypass_ara_count, posts_by_urgency, processing_rate (avg posts->news ratio)
    """
    from database.models import TelegramPost, GeneratedNews

    db = get_database_service()
    try:
        async with db.session_context() as session:
            # Posts
            r = await session.execute(select(func.count()).select_from(TelegramPost))
            total_posts = r.scalar() or 0

            r = await session.execute(
                select(func.count()).select_from(TelegramPost).where(TelegramPost.checked_at == True)
            )
            checked = r.scalar() or 0

            r = await session.execute(
                select(func.count()).select_from(TelegramPost).where(TelegramPost.bypass_ara == True)
            )
            bypass = r.scalar() or 0

            r = await session.execute(select(func.count()).select_from(GeneratedNews))
            total_gen = r.scalar() or 0

            # Urgency breakdown
            result = await session.execute(
                select(TelegramPost.urgency, func.count(TelegramPost.id))
                .group_by(TelegramPost.urgency)
            )
            urgency = {row[0] or "unknown": row[1] for row in result.all()}

        return JSONResponse(content={
            "success": True,
            "total_posts": total_posts,
            "checked": checked,
            "unchecked": total_posts - checked,
            "generated_news": total_gen,
            "bypass_ara": bypass,
            "processing_rate": round(total_gen / total_posts * 100, 1) if total_posts > 0 else 0,
            "urgency": urgency,
        })
    except Exception as e:
        logger.error(f"Processing stats error: {e}")
        return JSONResponse(content={"success": True, "total_posts": 0, "generated_news": 0})


# =============================================================================
# API — AI агенты статистика (из Prometheus)
# =============================================================================

@router.get("/api/agent-stats")
async def dashboard_agent_stats(user: Optional[dict] = Depends(get_optional_user)):
    """
    Статистика AI-агентов из Prometheus метрик.

    Returns:
        agents: [{name, total, success, failed, avg_duration_ms}]
    """
    try:
        from services.monitoring.metrics import get_metrics
        import re
        metrics_text = get_metrics().decode('utf-8')

        agents = {}
        for line in metrics_text.split('\n'):
            # agent_tasks_total{agent_name="Analyst",status="success"} 42
            m = re.match(r'agent_tasks_total{agent_name="([^"]+)",status="([^"]+)"} ([\d.]+)', line)
            if m:
                name, status, val = m.groups()
                if name not in agents:
                    agents[name] = {"name": name, "success": 0, "failed": 0, "retried": 0}
                agents[name][status] = int(float(val))

            # agent_task_duration_seconds_sum/count
            m = re.match(r'agent_task_duration_seconds_sum{agent_name="([^"]+)",method_name="[^"]+"} ([\d.]+)', line)
            if m:
                name, val = m.groups()
                if name not in agents:
                    agents[name] = {"name": name, "success": 0, "failed": 0, "retried": 0}
                agents[name]._sum = float(val)

            m = re.match(r'agent_task_duration_seconds_count{agent_name="([^"]+)",method_name="[^"]+"} ([\d.]+)', line)
            if m:
                name, val = m.groups()
                if name in agents:
                    agents[name]._count = int(float(val))

        result = []
        for a in agents.values():
            s = getattr(a, '_sum', 0)
            c = getattr(a, '_count', 0)
            result.append({
                "name": a["name"],
                "total": a["success"] + a["failed"] + a["retried"],
                "success": a["success"],
                "failed": a["failed"],
                "retried": a["retried"],
                "avg_duration_ms": round(s / c * 1000, 1) if c > 0 else 0,
            })

        return JSONResponse(content={"success": True, "agents": result})
    except Exception as e:
        logger.error(f"Agent stats error: {e}")
        return JSONResponse(content={"success": True, "agents": []})


# =============================================================================
# API — urgency × category matrix
# =============================================================================

@router.get("/api/posts-by-category-urgency")
async def dashboard_posts_by_category_urgency(user: Optional[dict] = Depends(get_optional_user)):
    """
    Матрица: посты по категориям × срочности.

    Returns:
        matrix: [{category, u1, u2, u3, u4, u5}]
    """
    from database.models import TelegramPost

    db = get_database_service()
    try:
        async with db.session_context() as session:
            result = await session.execute(
                select(
                    TelegramPost.category,
                    TelegramPost.urgency,
                    func.count(TelegramPost.id)
                )
                .group_by(TelegramPost.category, TelegramPost.urgency)
            )
            rows = result.all()

        # Build matrix
        cat_data = {}
        for cat, urg, count in rows:
            if cat not in cat_data:
                cat_data[cat] = {"category": cat or "Без категории", "u1": 0, "u2": 0, "u3": 0, "u4": 0, "u5": 0}
            key = f"u{urg}" if urg in ("1", "2", "3", "4", "5") else None
            if key:
                cat_data[cat][key] = count
            elif isinstance(urg, int) and 1 <= urg <= 5:
                cat_data[cat][f"u{urg}"] = count

        # Sort by total
        matrix = sorted(cat_data.values(), key=lambda r: sum(r[f"u{i}"] for i in range(1, 6)), reverse=True)

        return JSONResponse(content={"success": True, "matrix": matrix})
    except Exception as e:
        logger.error(f"Category urgency matrix error: {e}")
        return JSONResponse(content={"success": True, "matrix": []})


# =============================================================================
# API — time-series (универсальный эндпоинт для всех графиков)
# =============================================================================

@router.get("/api/time-series")
async def dashboard_time_series(
    metrics: str = "posts,generated",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    granularity: str = "day",
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Универсальный эндпоинт для временных рядов.

    Query params:
        metrics: комма-separated список: posts, generated, rss, web, tasks
        start_date: "2026-08-01" (ISO, опционально)
        end_date: "2026-08-17" (ISO, опционально)
        granularity: day | week | month (группировка по осям)

    Returns:
        {labels: [...], series: {posts: [...], generated: [...]}, stats: {...}}
    """
    from database.models import TelegramPost, GeneratedNews, RSSNews, WebNews, Task

    db = get_database_service()
    now = datetime.now()

    # Parse dates
    start = now - timedelta(days=30)
    end = now
    if start_date:
        try:
            start = datetime.fromisoformat(start_date)
        except ValueError:
            pass
    if end_date:
        try:
            end = datetime.fromisoformat(end_date)
            if end.tzinfo is None and end.time() == datetime.min.time():
                end = end.replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    # Granularity format for strftime
    gran_map = {
        "hour": {"fmt": "%Y-%m-%d %H:00", "days": 1},
        "day": {"fmt": "%m.%d", "days": None},
        "week": {"fmt": "%Y-W%W", "days": None},
        "month": {"fmt": "%Y-%m", "days": None},
    }
    gran = gran_map.get(granularity, gran_map["day"])

    # Parse requested metrics
    requested = [m.strip() for m in metrics.split(",") if m.strip()]

    # Model -> metric mapping
    model_map = {
        "posts": TelegramPost,
        "generated": GeneratedNews,
        "rss": RSSNews,
        "web": WebNews,
        "tasks": Task,
    }

    # For hour granularity, limit to 1 day
    if granularity == "hour":
        start = max(start, now - timedelta(hours=23))

    result = {}
    period_stats = {}

    try:
        async with db.session_context() as session:
            for metric in requested:
                model = model_map.get(metric)
                if not model:
                    continue

                # Period total
                r = await session.execute(
                    select(func.count()).select_from(model).where(
                        model.created_at >= start, model.created_at <= end
                    )
                )
                period_stats[metric] = r.scalar() or 0

                if metric != "hour":
                    # Time series
                    r = await session.execute(
                        select(
                            func.strftime(gran["fmt"], model.created_at).label("bucket"),
                            func.count(model.id)
                        )
                        .where(model.created_at >= start, model.created_at <= end)
                        .group_by(func.strftime(gran["fmt"], model.created_at))
                        .order_by(text("1"))
                    )
                    buckets = {row[0]: row[1] for row in r.all()}
                    result[metric] = buckets
                else:
                    # For hours: aggregate all requested metrics into hourly buckets
                    r = await session.execute(
                        select(
                            func.strftime("%H", model.created_at).label("bucket"),
                            func.count(model.id)
                        )
                        .where(model.created_at >= start, model.created_at <= end)
                        .group_by(func.strftime("%H", model.created_at))
                        .order_by(text("1"))
                    )
                    buckets = {row[0]: row[1] for row in r.all()}
                    result[metric] = buckets

        # Build labels and series arrays
        all_buckets = set()
        for series_buckets in result.values():
            all_buckets.update(series_buckets.keys())

        if granularity == "hour":
            labels = [f"{h:02d}:00" for h in range(24)]
            series = {m: [result.get(m, {}).get(str(h).zfill(2), 0) for h in range(24)] for m in requested if m in result}
        else:
            labels = sorted(all_buckets)
            if not labels:
                labels = []
            series = {m: [result.get(m, {}).get(b, 0) for b in labels] for m in requested if m in result}

        return JSONResponse(content={
            "success": True,
            "labels": labels,
            "series": series,
            "stats": period_stats,
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "granularity": granularity,
        })
    except Exception as e:
        logger.error(f"Time series error: {e}")
        # PostgreSQL fallback with to_char
        try:
            async with db.session_context() as session:
                pg_fmt = {"hour": "HH24:00", "day": "MM.DD", "week": "IYYY-WWW", "month": "YYYY-MM"}.get(granularity, "MM.DD")

                for metric in requested:
                    model = model_map.get(metric)
                    if not model:
                        continue
                    r = await session.execute(
                        select(func.count()).select_from(model).where(
                            model.created_at >= start, model.created_at <= end
                        )
                    )
                    period_stats[metric] = r.scalar() or 0

                    r = await session.execute(
                        select(
                            func.to_char(model.created_at, pg_fmt).label("bucket"),
                            func.count(model.id)
                        )
                        .where(model.created_at >= start, model.created_at <= end)
                        .group_by(func.to_char(model.created_at, pg_fmt))
                        .order_by(text("1"))
                    )
                    result[metric] = {row[0]: row[1] for row in r.all()}

            all_buckets = set()
            for sb in result.values():
                all_buckets.update(sb.keys())
            labels = sorted(all_buckets)
            series = {m: [result.get(m, {}).get(b, 0) for b in labels] for m in requested if m in result}

            return JSONResponse(content={
                "success": True,
                "labels": labels,
                "series": series,
                "stats": period_stats,
                "start": start.strftime("%Y-%m-%d"),
                "end": end.strftime("%Y-%m-%d"),
                "granularity": granularity,
            })
        except Exception as e2:
            logger.error(f"Time series PG fallback error: {e2}")
            return JSONResponse(content={"success": True, "labels": [], "series": {}, "stats": {}})
