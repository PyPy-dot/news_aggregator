"""
AI Agent Microservice — отдельный сервис для AI-агентов.

Предоставляет HTTP API для:
- Категоризации новостей (Categorizer)
- Анализа новостей (Analyst)
- Генерации новостей (Editor)
- Создания контекста (Archivist)

Запуск:
    uvicorn app.main:app --host 0.0.0.0 --port 8002
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Модели данных
# =============================================================================

class CategorizeRequest(BaseModel):
    """Запрос на категоризацию."""
    text: str = Field(..., description="Текст новости", min_length=1)
    channel_title: str = Field(default="", description="Название канала")
    channel_desc: str = Field(default="", description="Описание канала")


class CategorizeResponse(BaseModel):
    """Ответ категоризации."""
    text: str
    category: str
    urgency: int
    confidence: Optional[float] = None


class AnalyzeRequest(BaseModel):
    """Запрос на анализ."""
    text: str = Field(..., description="Текст новости")
    category: str = Field(..., description="Категория")
    urgency: int = Field(..., description="Срочность (1-5)", ge=1, le=5)


class AnalyzeResponse(BaseModel):
    """Ответ анализа."""
    tags: list[str]
    confidence: float
    facts: list[str] = Field(default_factory=list)


class GenerateNewsRequest(BaseModel):
    """Запрос на генерацию новости."""
    contexts: list[dict] = Field(..., description="Список контекстов событий")


class GenerateNewsResponse(BaseModel):
    """Ответ генерации новости."""
    news_text: str
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class CreateContextRequest(BaseModel):
    """Запрос на создание контекста."""
    contexts: list[dict] = Field(..., description="Список контекстов")
    news_text: str = Field(..., description="Текст новости")


class CreateContextResponse(BaseModel):
    """Ответ создания контекста."""
    context: dict
    vector_embedding: Optional[list[float]] = None


class HealthResponse(BaseModel):
    """Ответ health check."""
    status: str
    model: str
    llm_provider: str


# =============================================================================
# Жизненный цикл приложения
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и очистка ресурсов."""
    logger.info("🚀 AI Agent Service запускается...")

    # Инициализация агентов
    from services.ai_agent.agents.categorizer import CategorizerAgent
    from services.ai_agent.agents.analyst import AnalystAgent
    from services.ai_agent.agents.editor import EditorAgent
    from services.ai_agent.agents.archivist import ArchivistAgent

    app.state.categorizer = CategorizerAgent()
    app.state.analyst = AnalystAgent()
    app.state.editor = EditorAgent()
    app.state.archivist = ArchivistAgent()

    logger.info("✅ AI агенты инициализированы")

    yield

    # Очистка
    logger.info("👋 AI Agent Service останавливается...")


# =============================================================================
# FastAPI приложение
# =============================================================================

app = FastAPI(
    title="AI Agent Service",
    description="Микросервис для AI-агентов (категоризация, анализ, генерация новостей)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Проверка работоспособности сервиса."""
    from config.settings import settings

    return HealthResponse(
        status="healthy",
        model=settings.agent_model,
        llm_provider="ollama",
    )


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Проверка готовности к обработке запросов."""
    try:
        # Проверяем что агенты инициализированы
        assert hasattr(app.state, 'categorizer')
        assert hasattr(app.state, 'analyst')
        assert hasattr(app.state, 'editor')
        assert hasattr(app.state, 'archivist')

        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service not ready: {str(e)}"
        )


# =============================================================================
# AI Agent Endpoints
# =============================================================================

@app.post("/api/v1/categorize", response_model=CategorizeResponse, tags=["AI Agents"])
async def categorize(request: CategorizeRequest):
    """
    Категоризация новости.

    Определяет категорию, срочность и очищает текст от рекламы.
    """
    try:
        categorizer = app.state.categorizer

        result = await categorizer.categorize(
            text=request.text,
            channel_title=request.channel_title,
            channel_desc=request.channel_desc,
        )

        return CategorizeResponse(
            text=result['text'],
            category=result['category'],
            urgency=result['urgency'],
        )

    except Exception as e:
        logger.error(f"Ошибка категоризации: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Категоризация не удалась: {str(e)}"
        )


@app.post("/api/v1/analyze", response_model=AnalyzeResponse, tags=["AI Agents"])
async def analyze(request: AnalyzeRequest):
    """
    Анализ новости.

    Оценивает уверенность категории, извлекает факты и генерирует тэги.
    """
    try:
        analyst = app.state.analyst

        result = await analyst.analyze(
            text=request.text,
            category=request.category,
            urgency=request.urgency,
        )

        return AnalyzeResponse(
            tags=result.get('tags', []),
            confidence=result.get('confidence', 0.0),
            facts=result.get('facts', []),
        )

    except Exception as e:
        logger.error(f"Ошибка анализа: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Анализ не удался: {str(e)}"
        )


@app.post("/api/v1/generate-news", response_model=GenerateNewsResponse, tags=["AI Agents"])
async def generate_news(request: GenerateNewsRequest):
    """
    Генерация новости.

    Создаёт связный текст новости на основе контекстов событий.
    """
    try:
        editor = app.state.editor

        news_text = await editor.generate_news(request.contexts)

        # Извлекаем категорию и тэги из первого контекста (если есть)
        category = None
        tags = []
        if request.contexts:
            category = request.contexts[0].get('category')
            tags = request.contexts[0].get('tags', [])

        return GenerateNewsResponse(
            news_text=news_text,
            category=category,
            tags=tags,
        )

    except Exception as e:
        logger.error(f"Ошибка генерации новости: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Генерация новости не удалась: {str(e)}"
        )


@app.post("/api/v1/create-context", response_model=CreateContextResponse, tags=["AI Agents"])
async def create_context(request: CreateContextRequest):
    """
    Создание контекста для векторного поиска.

    Структурирует информацию для сохранения в векторную базу.
    """
    try:
        archivist = app.state.archivist

        context = await archivist.create_context(
            contexts=request.contexts,
            news_text=request.news_text,
        )

        return CreateContextResponse(
            context=context,
        )

    except Exception as e:
        logger.error(f"Ошибка создания контекста: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Создание контекста не удалось: {str(e)}"
        )


# =============================================================================
# Metrics Endpoint (для Prometheus)
# =============================================================================

@app.get("/metrics", tags=["Monitoring"])
async def metrics():
    """
    Prometheus метрики.

    Возвращает метрики в формате Prometheus.
    """
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
    )
