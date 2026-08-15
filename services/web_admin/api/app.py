"""
Web Admin API — FastAPI приложение для администрирования.

Предоставляет REST API и HTML интерфейс для управления:
- Новостями
- Каналами
- Пользователями
- Задачами
- RSS лентами
- Web парсерами
"""

import logging
import webbrowser
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from services.database import get_database_service
from services.web_admin.session_manager import get_session_manager
from services.web_admin.config import get_version

logger = logging.getLogger(__name__)

# Cookie название
COOKIE_NAME = "web_admin_session"

# Пути, не требующие авторизации
PUBLIC_PATHS = {"/", "/auth/login", "/auth/logout", "/health", "/docs", "/openapi.json"}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware для проверки авторизации.

    Перенаправляет неавторизованных пользователей на /auth/login.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Проверяем, является ли путь публичным
        if path in PUBLIC_PATHS or path.startswith("/auth/") or path.startswith("/static") or path.startswith("/ws/"):
            return await call_next(request)

        # Проверяем наличие валидного токена
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            # Для API возвращаем 401, для страниц — редирект
            if path.startswith("/api/"):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Требуется авторизация"}
                )
            return RedirectResponse(url=f"/auth/login?next={path}")

        # Проверяем токен
        manager = get_session_manager()
        payload = manager.verify_token(token)

        if not payload:
            # Для API возвращаем 401, для страниц — редирект
            if path.startswith("/api/"):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Сессия истекла"}
                )
            return RedirectResponse(url=f"/auth/login?next={path}")

        # Пользователь авторизован — продолжаем запрос
        return await call_next(request)


async def get_optional_user(request: Request) -> Optional[dict]:
    """
    Получить пользователя если авторизован, иначе None.

    Для страниц, которые должны работать без обязательной авторизации.
    """
    # Пробуем получить токен из cookies
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None

    # Проверяем токен через менеджер сессий
    manager = get_session_manager()
    payload = manager.verify_token(token)

    if not payload:
        return None

    return {
        "username": payload.get("sub"),
        "logged_in": True
    }


async def get_required_user(request: Request) -> dict:
    """
    Получить текущего пользователя.

    Для защищённых страниц, требующих авторизации.
    """
    user = await get_optional_user(request)
    if not user:
        # Middleware должен был сделать редирект, но на всякий случай
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"}
        )
    return user


async def get_current_user(request: Request) -> Optional[dict]:
    """
    Получить текущего пользователя из cookie.

    Возвращает None если не авторизован.
    """
    return await get_optional_user(request)

# Пути
BASE_DIR = Path(__file__).parent.parent  # services/web_admin/
TEMPLATES_DIR = BASE_DIR / "templates"  # services/web_admin/templates/
STATIC_DIR = BASE_DIR / "static"

# Шаблоны и статика
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    logger.info("🚀 Запуск Web Admin API...")

    # Отключаем логирование успешных HTTP запросов (200 OK)
    import logging
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Настраиваем логирование для веб-админки
    try:
        from services.web_admin.log_handler import setup_web_admin_logging
        setup_web_admin_logging()
        logger.info("✅ Логирование настроено для веб-админки")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось настроить логирование: {e}")

    # Инициализация БД
    try:
        db_service = get_database_service()
        # Получаем URL базы данных безопасно
        if hasattr(db_service, '_config') and db_service._config:
            db_url = db_service._config.resolved_url
            logger.info(f"✅ БД подключена: {db_url}")
        else:
            logger.info("✅ БД подключена (конфигурация по умолчанию)")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось получить информацию о БД: {e}")

    # Открываем браузер через 1.5 секунды после запуска
    asyncio.create_task(open_browser_delayed())

    yield

    logger.info("👋 Остановка Web Admin API...")


async def open_browser_delayed(delay: float = 1.5):
    """Открыть браузер с задержкой после запуска сервера."""
    await asyncio.sleep(delay)
    try:
        webbrowser.open("http://localhost:8001")
        logger.info("🌐 Админ-панель открыта в браузере: http://localhost:8001")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось открыть браузер автоматически: {e}")
        logger.info("📍 Откройте вручную: http://localhost:8001")


# Создание приложения
app = FastAPI(
    title="News Aggregator Admin",
    description="Web интерфейс для администрирования News Aggregator",
    version="4.0.0",
    lifespan=lifespan,
)

# Добавляем middleware для проверки авторизации
app.add_middleware(AuthMiddleware)

# Монтирование статики
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# =============================================================================
# Главная страница и API статистики
# =============================================================================

@app.get("/", response_class=HTMLResponse, tags=["Main"])
async def root(request: Request, user: dict = Depends(get_required_user)):
    """Главная страница админки (требует авторизации)."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "version": get_version()
        }
    )


@app.get("/api/stats", tags=["API"], response_class=JSONResponse)
async def get_stats(user: Optional[dict] = Depends(get_optional_user)):
    """
    Получить статистику системы для главной панели.

    Возвращает:
    - Количество новостей
    - Количество каналов
    - Количество пользователей
    - Количество задач (только active и pending)
    - Системный статус
    """
    from sqlalchemy import func, select, or_
    from database.models import TelegramPost, Channel, User, Task

    db_service = get_database_service()

    stats = {
        "news": 0,
        "channels": 0,
        "users": 0,
        "tasks": 0,
        "system_status": "unknown",  # ok, warning, error
    }

    try:
        async with db_service.session_context() as session:
            # Количество новостей (постов)
            result = await session.execute(select(func.count()).select_from(TelegramPost))
            stats["news"] = result.scalar() or 0

            # Количество каналов
            result = await session.execute(select(func.count()).select_from(Channel))
            stats["channels"] = result.scalar() or 0

            # Количество пользователей
            result = await session.execute(select(func.count()).select_from(User))
            stats["users"] = result.scalar() or 0

            # Количество задач (только active и pending)
            result = await session.execute(
                select(func.count()).select_from(Task).where(
                    or_(Task.status == 'active', Task.status == 'pending')
                )
            )
            stats["tasks"] = result.scalar() or 0

            # Определяем системный статус
            stats["system_status"] = await _calculate_system_status(session)

    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        stats["system_status"] = "error"

    return stats


async def _calculate_system_status(session) -> str:
    """
    Рассчитать системный статус на основе состояния сервисов и задач.

    Returns:
        "ok" — всё работает
        "warning" — частичная работа
        "error" — проблемы
    """
    try:
        from services.service_manager import get_service_manager
        manager = get_service_manager()
        services = manager.get_all_states()

        all_running = all(services.values())
        all_stopped = all(not s for s in services.values())
        partial = not all_running and not all_stopped

        if all_running:
            return "ok"
        elif partial:
            return "warning"
        else:
            return "error"
    except Exception:
        return "error"


@app.get("/api/services/status", tags=["API"], response_class=JSONResponse)
async def get_services_status(user: Optional[dict] = Depends(get_optional_user)):
    """
    Получить статусы сервисов для главной панели.

    Возвращает:
    - services: {bot, listener, scheduler} — bool для обратной совместимости
    - statuses: {bot, listener, scheduler} — богатый формат (state, healthy, uptime_sec, last_error)
    - notifications: список активных уведомлений (сбои сервисов)
    """
    from services.service_manager import get_service_manager

    try:
        manager = get_service_manager()
        services = manager.get_all_states()
        statuses = manager.get_all_statuses()

        # Строим уведомления из проблемных сервисов
        notifications = []
        for name, info in statuses.items():
            if info.get("state") == "crashed" or info.get("last_error"):
                notifications.append({
                    "id": f"service_{name}_{info.get('state', 'error')}",
                    "type": "error" if info.get("state") == "crashed" else "warning",
                    "title": f"Сервис {name} {'упал' if info.get('state') == 'crashed' else 'с ошибкой'}",
                    "message": info.get("last_error") or f"Состояние: {info.get('state')}",
                    "service": name,
                    "created_at": info.get("started_at"),
                    "read": False,
                })

        return {
            "success": True,
            "services": services,
            "statuses": statuses,
            "notifications": notifications,
        }
    except Exception as e:
        logger.error(f"Ошибка получения статусов сервисов: {e}")
        return {
            "success": False,
            "services": {
                "bot": False,
                "listener": False,
                "scheduler": False
            },
            "statuses": {},
            "notifications": [],
        }


@app.post("/api/notifications/read", tags=["API"], response_class=JSONResponse)
async def mark_notifications_read(
    service: Optional[str] = None,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Пометить уведомления как прочитанные.

    Args:
        service: конкретный сервис или None = все
    """
    return {"success": True, "read": service or "all"}


@app.post("/api/news/generate", tags=["API"], response_class=JSONResponse)
async def generate_news_endpoint(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Быстрая генерация новости из текста.

    Body: { "text": "...", "category": "..." }
    """
    try:
        data = await request.json()
        text = data.get("text", "").strip()
        category = data.get("category", "") or None

        if not text:
            return {"success": False, "error": "Текст не указан"}

        # Получаем orchestrator из контейнера
        from main import app as main_app
        container = getattr(main_app, '_global_container', None) if main_app else None
        if not container:
            # Fallback: ищем контейнер из модуля main
            import sys
            main_mod = sys.modules.get('main')
            container = getattr(main_mod, '_global_container', None) if main_mod else None

        if container:
            async with container.session() as session:
                from database import RepositoryFactory
                factory = RepositoryFactory(session)
                orchestrator = await container.create_orchestrator(session)
                news_id = await orchestrator.generate_direct_news(
                    description=text,
                    publisher_channel_id=None,  # всем пользователям через бота
                )
                await session.commit()
                return {"success": True, "news_id": news_id}
        else:
            return {"success": False, "error": "DI контейнер не доступен"}

    except Exception as e:
        logger.error(f"Ошибка генерации новости: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@app.post("/api/channels", tags=["API"], response_class=JSONResponse)
async def create_channel_endpoint(
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Быстрое добавление канала.

    Body: { "channel_id": -100..., "title": "...", "description": "..." }
    """
    try:
        data = await request.json()
        channel_id = data.get("channel_id")
        title = data.get("title", "").strip()
        description = data.get("description", "").strip()

        if not channel_id or not title:
            return {"success": False, "error": "Укажите channel_id и title"}

        db_service = get_database_service()
        async with db_service.session_context() as session:
            from database.repositories.channels import ChannelRepository
            repo = ChannelRepository(session)
            # Проверка дубликата
            existing = await repo.get_by_telegram_id(int(channel_id))
            if existing:
                return {"success": False, "error": f"Канал с ID {channel_id} уже существует"}

            ch_id = await repo.add_channel(
                channel_id=int(channel_id),
                title=title,
                description=description,
                trust_rating=0.5,
                is_trusted=False,
            )
            await session.commit()

        return {"success": True, "channel_id": ch_id}

    except Exception as e:
        logger.error(f"Ошибка добавления канала: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@app.get("/api/news/recent", tags=["API"], response_class=JSONResponse)
async def get_recent_news(limit: int = 5, user: Optional[dict] = Depends(get_optional_user)):
    """
    Получить последние новости для главной панели.

    Args:
        limit: Максимальное количество новостей (по умолчанию 5)
    """
    from sqlalchemy import select, desc
    from database.models import TelegramPost

    db_service = get_database_service()

    try:
        async with db_service.session_context() as session:
            query = select(TelegramPost).order_by(desc(TelegramPost.created_at)).limit(limit)
            result = await session.execute(query)
            posts = result.scalars().all()

            news_list = []
            for post in posts:
                news_list.append({
                    "id": post.id,
                    "title": getattr(post, 'title', None) or 'Без названия',
                    "category": getattr(post, 'category', None) or 'Общее',
                    "created_at": post.created_at.isoformat() if post.created_at else None,
                    "urgency": getattr(post, 'urgency', None),
                })

            return {"news": news_list}

    except Exception as e:
        logger.error(f"Ошибка получения новостей: {e}")
        return {"news": []}


# =============================================================================
# Включение роутов
# =============================================================================

from services.web_admin.routes import auth, dashboard, news, channels, users, tasks, rss, web, console, settings, listener_auth, listener_auth_ws
from services.web_admin import health_router

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(news.router, prefix="/news", tags=["News"])
app.include_router(channels.router, prefix="/channels", tags=["Channels"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
app.include_router(rss.router, prefix="/rss", tags=["RSS"])
app.include_router(web.router, prefix="/web", tags=["Web Parsing"])
app.include_router(console.router, prefix="/console", tags=["Console"])
app.include_router(listener_auth.router, prefix="/listener-auth", tags=["Listener Auth"])
app.include_router(listener_auth_ws.router, prefix="/ws", tags=["Listener Auth WS"])
app.include_router(settings.router, prefix="/settings", tags=["Settings"])
app.include_router(health_router.router, prefix="/api", tags=["Health"])


# =============================================================================
# Запуск приложения
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.web_admin.api.app:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )
