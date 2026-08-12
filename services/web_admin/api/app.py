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
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.database import get_database_service
from services.web_admin.api.auth import get_current_admin_user

logger = logging.getLogger(__name__)

# Пути
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Шаблоны и статика
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    logger.info("🚀 Запуск Web Admin API...")

    # Инициализация БД
    db_service = get_database_service()
    logger.info(f"✅ БД подключена: {db_service.database_url}")

    yield

    logger.info("👋 Остановка Web Admin API...")


# Создание приложения
app = FastAPI(
    title="News Aggregator Admin",
    description="Web интерфейс для администрирования News Aggregator",
    version="1.0.0",
    lifespan=lifespan,
)

# Монтирование статики
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# =============================================================================
# Главная страница
# =============================================================================

@app.get("/", response_class=HTMLResponse, tags=["Main"])
async def root(request: Request, admin: dict = Depends(get_current_admin_user)):
    """Главная страница админки."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": admin}
    )


# =============================================================================
# Включение роутов
# =============================================================================

from services.web_admin.routes import auth, dashboard, news, channels, users, tasks, rss, web, console, settings

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(news.router, prefix="/news", tags=["News"])
app.include_router(channels.router, prefix="/channels", tags=["Channels"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
app.include_router(rss.router, prefix="/rss", tags=["RSS"])
app.include_router(web.router, prefix="/web", tags=["Web Parsing"])
app.include_router(console.router, prefix="/console", tags=["Console"])
app.include_router(settings.router, prefix="/settings", tags=["Settings"])


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
