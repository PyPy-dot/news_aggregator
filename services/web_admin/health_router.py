"""
Health Check API Router для FastAPI.

Endpoints:
- GET /health — краткий статус (для load balancer, k8s liveness/readiness)
- GET /health/full — полная проверка всех компонентов
- GET /health/{component} — проверка конкретного компонента

Usage:
    from fastapi import FastAPI
    from services.web_admin.health_router import router as health_router

    app = FastAPI()
    app.include_router(health_router, prefix="/api")
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.monitoring.health_check import (
    get_health_checker,
    check_system_health,
    get_health_summary,
    HealthStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health Check"])


# =============================================================================
# Pydantic модели для ответов
# =============================================================================

class ComponentHealthResponse(BaseModel):
    """Ответ для компонента."""
    name: str = Field(..., description="Имя компонента")
    status: str = Field(..., description="Статус (healthy/degraded/unhealthy/unknown)")
    severity: str = Field(..., description="Уровень важности")
    message: str = Field(default="", description="Сообщение")
    latency_ms: float = Field(default=0.0, description="Время проверки (мс)")
    details: dict = Field(default_factory=dict, description="Дополнительные детали")
    checked_at: str = Field(..., description="Время проверки (ISO 8601)")


class HealthSummaryResponse(BaseModel):
    """Краткий ответ здоровья."""
    status: str = Field(..., description="Общий статус системы")
    healthy_components: int = Field(..., description="Количество здоровых компонентов")
    total_components: int = Field(..., description="Всего компонентов")
    critical_issues: int = Field(..., description="Количество критичных проблем")
    critical_issue_names: list[str] = Field(default_factory=list, description="Имена проблемных компонентов")


class FullHealthResponse(BaseModel):
    """Полный ответ здоровья."""
    status: str = Field(..., description="Общий статус системы")
    version: str = Field(..., description="Версия приложения")
    checked_at: str = Field(..., description="Время проверки (ISO 8601)")
    summary: dict = Field(..., description="Сводка")
    components: list[ComponentHealthResponse] = Field(..., description="Компоненты")


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/health", response_model=HealthSummaryResponse, tags=["Health"])
async def health_check():
    """
    Краткая проверка здоровья системы.

    Используется для:
    - Load balancer health checks
    - Kubernetes liveness/readiness probes
    - Быстрого мониторинга статуса

    Returns:
        Краткая сводка: статус, количество здоровых/больных компонентов
    """
    summary = await get_health_summary()
    return HealthSummaryResponse(**summary)


@router.get("/health/full", response_model=FullHealthResponse, tags=["Health"])
async def health_check_full(
    timeout: float = Query(default=10.0, description="Таймаут проверки (сек)", ge=1.0, le=60.0),
):
    """
    Полная проверка здоровья всех компонентов.

    Проверяет:
    - Базу данных
    - LLM провайдеры (Ollama, OpenAI, Anthropic)
    - Telegram бота
    - Векторный поиск (ChromaDB)
    - Circuit breaker'ы
    - Планировщик
    - Очередь категоризации

    Args:
        timeout: Максимальное время проверки (сек)

    Returns:
        Полный статус всех компонентов с деталями
    """
    health = await check_system_health(timeout=timeout)

    components = [
        ComponentHealthResponse(
            name=c.name,
            status=c.status.value,
            severity=c.severity.value,
            message=c.message,
            latency_ms=c.latency_ms,
            details=c.details,
            checked_at=c.checked_at,
        )
        for c in health.components
    ]

    return FullHealthResponse(
        status=health.status.value,
        version=health.version,
        checked_at=health.checked_at,
        summary={
            "total_components": len(health.components),
            "healthy": health.healthy_components,
            "unhealthy": health.unhealthy_components,
            "critical_issues": len(health.critical_issues),
        },
        components=components,
    )


@router.get("/health/{component_name}", response_model=ComponentHealthResponse, tags=["Health"])
async def health_check_component(
    component_name: str,
    timeout: float = Query(default=5.0, description="Таймаут проверки (сек)", ge=1.0, le=30.0),
):
    """
    Проверка конкретного компонента.

    Args:
        component_name: Имя компонента (database, ollama, telegram_bot, llm_fallback, ...)
        timeout: Таймаут проверки (сек)

    Returns:
        Статус компонента

    Raises:
        HTTPException 404: Компонент не найден
    """
    checker = get_health_checker()

    if component_name not in checker._checks:
        available = list(checker._checks.keys())
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Компонент '{component_name}' не найден",
                "available_components": available,
            },
        )

    result = await checker.check_component(component_name)

    return ComponentHealthResponse(
        name=result.name,
        status=result.status.value,
        severity=result.severity.value,
        message=result.message,
        latency_ms=result.latency_ms,
        details=result.details,
        checked_at=result.checked_at,
    )


@router.get("/health/live", tags=["Health"])
async def liveness_probe():
    """
    Liveness probe для Kubernetes.

    Возвращает OK если приложение запущено (не проверяет зависимости).

    Returns:
        {"status": "ok"}
    """
    return {"status": "ok", "timestamp": __import__("time").time()}


@router.get("/health/ready", tags=["Health"])
async def readiness_probe():
    """
    Readiness probe для Kubernetes.

    Проверяет критичные зависимости (БД, бот).

    Returns:
        {"status": "ok"} или HTTP 503

    Raises:
        HTTPException 503: Критичные зависимости недоступны
    """
    summary = await get_health_summary()

    if summary["status"] == "unhealthy" and summary["critical_issues"] > 0:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "critical_issues": summary["critical_issue_names"],
            },
        )

    return {"status": "ok", **summary}


# =============================================================================
# Prometheus metrics endpoint (опционально)
# =============================================================================

@router.get("/health/metrics", tags=["Health"])
async def health_metrics():
    """
    Метрики здоровья в формате Prometheus.

    Returns:
        Текст в формате Prometheus metrics
    """

    checker = get_health_checker()
    results = checker.get_last_results()

    lines = [
        "# HELP news_aggregator_health_component_status Статус компонента (1=healthy, 0=unhealthy)",
        "# TYPE news_aggregator_health_component_status gauge",
    ]

    for name, result in results.items():
        status_value = 1 if result.status == HealthStatus.HEALTHY else 0
        lines.append(
            f'news_aggregator_health_component_status{{component="{name}",severity="{result.severity.value}"}} {status_value}'
        )

    lines.append("")
    lines.append("# HELP news_aggregator_health_latency_ms Latency проверки компонента (мс)")
    lines.append("# TYPE news_aggregator_health_latency_ms gauge")

    for name, result in results.items():
        lines.append(f'news_aggregator_health_latency_ms{{component="{name}"}} {result.latency_ms:.2f}')

    lines.append("")
    lines.append("# HELP news_aggregator_health_info Информация о системе")
    lines.append("# TYPE news_aggregator_health_info gauge")
    lines.append(f'news_aggregator_health_info{{version="3.5.0"}} 1')

    return JSONResponse(
        content="\n".join(lines),
        media_type="text/plain",
    )
