"""
Performance Dashboard — API метрик производительности системы.

Предоставляет:
- Circuit breaker состояния и статистику
- Queue sizes (categorization, agent)
- Vector search (ChromaDB коллекции)
- Service uptime и статусы
- LLM провайдер статистика
- Database метрики
- Prometheus метрики
"""

import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.database import get_database_service
from services.web_admin.auth_dependency import get_optional_user, get_required_user
from services.web_admin.config import get_version

logger = logging.getLogger(__name__)

router = APIRouter()

BASE_DIR = __file__.replace("\\", "/").rsplit("/", 1)[0]
TEMPLATES_DIR = f"{BASE_DIR}/../templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# =============================================================================
# Страница
# =============================================================================

@router.get("/", response_class=HTMLResponse)
async def performance_page(request: Request, user: dict = Depends(get_required_user)):
    """Страница производительности системы."""
    return templates.TemplateResponse(
        request=request,
        name="performance.html",
        context={"user": user, "version": get_version()},
    )


# =============================================================================
# Circuit breakers
# =============================================================================

@router.get("/api/circuit-breakers")
async def api_circuit_breakers(user: Optional[dict] = Depends(get_optional_user)):
    """
    Состояние всех circuit breaker'ов.

    Returns:
        list[{name, state, avg_response_time_ms, success_rate, failed, total, ...}]
    """
    try:
        from services.core.circuit_breaker import get_circuit_breaker_manager
        manager = get_circuit_breaker_manager()
        states = manager.get_all_states()

        breakers = []
        for name, s in states.items():
            stats = s.get("stats", {})
            total = stats.get("total_calls", 0)
            successful = stats.get("successful_calls", 0)
            failed = stats.get("failed_calls", 0)
            rejected = stats.get("rejected_calls", 0)
            success_rate = round(successful / total * 100, 1) if total > 0 else 100.0

            breakers.append({
                "name": name,
                "state": s.get("state", "closed"),
                "avg_response_time_ms": stats.get("avg_response_time_ms", 0),
                "success_rate": success_rate,
                "total_calls": total,
                "successful": successful,
                "failed": failed,
                "rejected": rejected,
                "timeout": stats.get("timeout_calls", 0),
                "consecutive_failures": stats.get("consecutive_failures", 0),
                "state_changes": stats.get("state_changes", 0),
                "last_failure": stats.get("last_failure_time"),
                "last_success": stats.get("last_success_time"),
            })

        return JSONResponse(content={"success": True, "breakers": breakers})
    except Exception as e:
        logger.error(f"Circuit breakers API error: {e}")
        return JSONResponse(content={"success": True, "breakers": []})


# =============================================================================
# Queues
# =============================================================================

@router.get("/api/queues")
async def api_queues(user: Optional[dict] = Depends(get_optional_user)):
    """
    Размер всех очередей.

    Returns:
        categorization: {current, max, pending, agent_running, agent_stats}
        agent_queue: {pending, active, workers, total_processed}
    """
    result = {}

    # Categorization queue
    try:
        from services.categorization.queue import CategorizationQueue
        queue = CategorizationQueue()
        current_size = len(queue._queue) if hasattr(queue, '_queue') else 0
        max_size = getattr(queue, '_maxlen', 0) or 'N/A'

        result["categorization"] = {
            "current": current_size,
            "max": max_size,
        }
    except Exception as e:
        result["categorization"] = {"current": 0, "error": str(e)}

    # Agent queue
    try:
        from services.ai_agent.agent_queue import get_agent_queue
        agent_queue = get_agent_queue()

        agent_running = getattr(agent_queue, '_running', False)
        agent_stats = getattr(agent_queue, '_stats', {}) or {}

        # pending count
        pending = 0
        if hasattr(agent_queue, '_queue'):
            pending = len(agent_queue._queue)

        # workers
        workers = 0
        if hasattr(agent_queue, '_workers'):
            workers = len([w for w in agent_queue._workers if not w.done()])

        result["agent_queue"] = {
            "pending": pending,
            "active": agent_stats.get("active", 0),
            "workers": workers,
            "running": agent_running,
            "total_processed": agent_stats.get("total_processed", 0),
        }
    except Exception as e:
        result["agent_queue"] = {"error": str(e)}

    return JSONResponse(content={"success": True, **result})


# =============================================================================
# Vector search (ChromaDB)
# =============================================================================

@router.get("/api/vector-search")
async def api_vector_search(user: Optional[dict] = Depends(get_optional_user)):
    """
    Статистика ChromaDB.

    Returns:
        collections: [{name, count, last_indexed}]
        total_vectors: N
        reindex_status: bool
    """
    try:
        from services.vector_search.chroma_client import ChromaVectorStore
        store = ChromaVectorStore()
        client = store._client

        collections = client.list_collections()
        coll_data = []
        total = 0

        for c in collections:
            name = c.name if hasattr(c, 'name') else str(c)
            try:
                count = store.count(name)
                total += count
                coll_data.append({"name": name, "count": count})
            except Exception as e:
                coll_data.append({"name": name, "count": 0, "error": str(e)})

        # Reindex status
        import os
        reindexed = os.path.exists('vector_store/.reindexed')

        return JSONResponse(content={
            "success": True,
            "collections": coll_data,
            "total_vectors": total,
            "reindexed": reindexed,
        })
    except Exception as e:
        logger.error(f"Vector search API error: {e}")
        return JSONResponse(content={"success": True, "collections": [], "total_vectors": 0, "error": str(e)})


# =============================================================================
# Service uptime & status
# =============================================================================

@router.get("/api/service-uptime")
async def api_service_uptime(user: Optional[dict] = Depends(get_optional_user)):
    """
    Uptime и статус всех сервисов.

    Returns:
        {bot: {state, uptime_sec, started_at, last_error}, listener: ..., scheduler: ...}
        web_admin: {uptime_sec} — всегда работает
    """
    try:
        from services.service_manager import get_service_manager
        manager = get_service_manager()
        statuses = manager.get_all_statuses()

        # Web admin uptime (приблизительно — из process start time)
        web_admin_uptime = time.time() - getattr(api_service_uptime, '_start_time', time.time())
        if not hasattr(api_service_uptime, '_start_time'):
            api_service_uptime._start_time = time.time()

        return JSONResponse(content={
            "success": True,
            "services": statuses,
            "web_admin": {"uptime_sec": round(web_admin_uptime, 0)},
        })
    except Exception as e:
        logger.error(f"Service uptime API error: {e}")
        return JSONResponse(content={"success": True, "services": {}})


# =============================================================================
# LLM providers stats
# =============================================================================

@router.get("/api/llm-stats")
async def api_llm_stats(user: Optional[dict] = Depends(get_optional_user)):
    """
    Статистика LLM провайдеров.

    Returns:
        primary: {model, provider, available}
        fallback: {providers: [{name, healthy, latency_ms, fallback_count}]}
        circuit_breakers: list[str] — открытые
    """
    result = {}
    try:
        from services.core.llm_provider import get_llm_provider, FallbackLLMProvider
        provider = get_llm_provider()

        if isinstance(provider, FallbackLLMProvider):
            all_stats = provider.get_all_stats()
            providers_list = []
            for name, stats in all_stats.items():
                providers_list.append({
                    "name": name,
                    "healthy": stats.is_healthy,
                    "latency_ms": round(getattr(stats, 'last_latency_ms', 0), 1),
                    "fallback_count": stats.fallback_count,
                    "model": getattr(stats, 'model', ''),
                })
            result["primary"] = providers_list[0] if providers_list else {}
            result["fallback"] = {"providers": providers_list}
        else:
            stats = provider.get_stats()
            result["primary"] = {
                "name": type(provider).__name__,
                "model": getattr(stats, 'model', getattr(provider, 'default_model', '')),
                "healthy": stats.is_healthy,
                "latency_ms": round(getattr(stats, 'last_latency_ms', 0), 1),
            }
            result["fallback"] = {"providers": []}

    except Exception as e:
        logger.error(f"LLM stats API error: {e}")
        result["error"] = str(e)

    # Open circuit breakers
    try:
        from services.core.circuit_breaker import get_circuit_breaker_manager
        manager = get_circuit_breaker_manager()
        result["open_breakers"] = manager.get_open_breakers()
    except Exception:
        result["open_breakers"] = []

    return JSONResponse(content={"success": True, **result})


# =============================================================================
# Database metrics
# =============================================================================

@router.get("/api/db-metrics")
async def api_db_metrics(user: Optional[dict] = Depends(get_optional_user)):
    """
    Метрики базы данных.

    Returns:
        db_type, tables: {name, count}, db_size_mb (SQLite/PG)
    """
    from services.database.enums import DatabaseType

    try:
        db_service = get_database_service()
        db_type = getattr(db_service, 'db_type', None)
        if db_type is None and hasattr(db_service, '_service') and db_service._service:
            db_type = db_service._service.db_type

        db_type_label = db_type.name if db_type else "unknown"

        # Table counts
        from database.models import (
            Channel, TelegramPost, GeneratedNews, EventContext,
            Publisher, User, Task, NewsCategory, RSSSource, RSSNews,
            WebSource, WebNews,
        )

        table_models = [
            ("channels", Channel),
            ("posts", TelegramPost),
            ("generated_news", GeneratedNews),
            ("events", EventContext),
            ("publishers", Publisher),
            ("users", User),
            ("tasks", Task),
            ("categories", NewsCategory),
            ("rss_sources", RSSSource),
            ("rss_news", RSSNews),
            ("web_sources", WebSource),
            ("web_news", WebNews),
        ]

        tables = {}
        async with db_service.session_context() as session:
            for name, model in table_models:
                try:
                    r = await session.execute(select(func.count()).select_from(model))
                    tables[name] = r.scalar() or 0
                except Exception:
                    tables[name] = -1  # Table doesn't exist or error

        # DB size
        db_size_mb = 0
        if db_type == DatabaseType.SQLITE:
            import os
            from config.settings import settings
            db_path = settings.db_path
            if os.path.exists(db_path):
                db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 1)
        elif db_type == DatabaseType.POSTGRESQL:
            try:
                async with db_service.session_context() as session:
                    r = await session.execute(text("SELECT pg_database_size(current_database()) / 1024 / 1024 AS size_mb"))
                    row = r.scalar()
                    if row:
                        db_size_mb = round(float(row), 1)
            except Exception:
                pass

        return JSONResponse(content={
            "success": True,
            "db_type": db_type_label,
            "tables": tables,
            "db_size_mb": db_size_mb,
        })
    except Exception as e:
        logger.error(f"DB metrics API error: {e}")
        return JSONResponse(content={"success": True, "db_type": "error", "tables": {}, "error": str(e)})


# =============================================================================
# Prometheus metrics (raw)
# =============================================================================

@router.get("/api/prometheus")
async def api_prometheus(user: Optional[dict] = Depends(get_optional_user)):
    """
    Prometheus метрики в raw формате.

    Returns:
        content: Prometheus text format metrics
    """
    try:
        from services.monitoring.metrics import get_metrics
        metrics_text = get_metrics().decode('utf-8')
        return JSONResponse(content={"success": True, "content": metrics_text})
    except Exception as e:
        return JSONResponse(content={"success": True, "content": str(e)})


# =============================================================================
# System info
# =============================================================================

@router.get("/api/system-info")
async def api_system_info(user: Optional[dict] = Depends(get_optional_user)):
    """
    Информация о системе (Python, версия приложения, платформа).

    Returns:
        python_version, platform, process_start_time, app_uptime_sec, memory_rss_mb
    """
    import sys
    import platform
    import os

    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        rss_mb = round(mem_info.rss / (1024 * 1024), 1)
    except ImportError:
        rss_mb = None
    except Exception:
        rss_mb = None

    start_time = getattr(api_system_info, '_start_time', None)
    if start_time is None:
        api_system_info._start_time = time.time()
        start_time = api_system_info._start_time

    return JSONResponse(content={
        "success": True,
        "python_version": sys.version,
        "platform": platform.platform(),
        "app_version": get_version(),
        "uptime_sec": round(time.time() - start_time, 0),
        "memory_rss_mb": rss_mb,
        "cwd": os.getcwd(),
    })
