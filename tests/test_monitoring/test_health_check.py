"""
Тесты для Health Check системы.

Проверяют:
- Проверки отдельных компонентов
- Общую проверку системы
- API endpoints
- Статусы и сводки
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.monitoring.health_check import (
    HealthStatus,
    SeverityLevel,
    ComponentHealth,
    SystemHealth,
    HealthChecker,
    check_database_health,
    check_ollama_health,
    check_llm_fallback_health,
    check_circuit_breakers_health,
    check_telegram_bot_health,
    check_vector_search_health,
    check_scheduler_health,
    create_default_health_checker,
    get_health_checker,
    check_system_health,
)


# =============================================================================
# Тесты ComponentHealth и SystemHealth
# =============================================================================

class TestComponentHealth:
    """Тесты для ComponentHealth."""

    def test_component_health_creation(self):
        """Тест: создание ComponentHealth."""
        health = ComponentHealth(
            name="test_db",
            status=HealthStatus.HEALTHY,
            severity=SeverityLevel.CRITICAL,
            message="All good",
            latency_ms=15.5,
            details={"connections": 10},
        )

        assert health.name == "test_db"
        assert health.status == HealthStatus.HEALTHY
        assert health.severity == SeverityLevel.CRITICAL
        assert health.message == "All good"
        assert health.latency_ms == 15.5
        assert health.details == {"connections": 10}

    def test_component_health_to_dict(self):
        """Тест: преобразование в dict."""
        health = ComponentHealth(
            name="test",
            status=HealthStatus.HEALTHY,
            severity=SeverityLevel.HIGH,
        )

        result = health.to_dict()

        assert result["name"] == "test"
        assert result["status"] == "healthy"
        assert result["severity"] == "high"
        assert "checked_at" in result
        assert isinstance(result["checked_at"], str)


class TestSystemHealth:
    """Тесты для SystemHealth."""

    def test_system_health_properties(self):
        """Тест: свойства SystemHealth."""
        components = [
            ComponentHealth(name="db", status=HealthStatus.HEALTHY, severity=SeverityLevel.CRITICAL),
            ComponentHealth(name="api", status=HealthStatus.HEALTHY, severity=SeverityLevel.HIGH),
            ComponentHealth(name="cache", status=HealthStatus.UNHEALTHY, severity=SeverityLevel.MEDIUM),
        ]

        system = SystemHealth(
            status=HealthStatus.DEGRADED,
            components=components,
        )

        assert system.healthy_components == 2
        assert system.unhealthy_components == 1
        assert len(system.critical_issues) == 0  # Нет критичных проблем

    def test_system_health_critical_issues(self):
        """Тест: критичные проблемы."""
        components = [
            ComponentHealth(name="db", status=HealthStatus.UNHEALTHY, severity=SeverityLevel.CRITICAL),
            ComponentHealth(name="api", status=HealthStatus.HEALTHY, severity=SeverityLevel.HIGH),
        ]

        system = SystemHealth(
            status=HealthStatus.UNHEALTHY,
            components=components,
        )

        assert len(system.critical_issues) == 1
        assert system.critical_issues[0].name == "db"

    def test_system_health_to_dict(self):
        """Тест: преобразование в dict."""
        components = [
            ComponentHealth(name="test", status=HealthStatus.HEALTHY, severity=SeverityLevel.HIGH),
        ]

        system = SystemHealth(
            status=HealthStatus.HEALTHY,
            components=components,
            version="1.0.0",
        )

        result = system.to_dict()

        assert result["status"] == "healthy"
        assert result["version"] == "1.0.0"
        assert result["summary"]["total_components"] == 1
        assert result["summary"]["healthy"] == 1
        assert len(result["components"]) == 1


# =============================================================================
# Тесты HealthChecker
# =============================================================================

class TestHealthChecker:
    """Тесты для HealthChecker."""

    @pytest.mark.asyncio
    async def test_add_and_check_component(self):
        """Тест: добавление и проверка компонента."""
        checker = HealthChecker()

        async def mock_check():
            return ComponentHealth(
                name="mock",
                status=HealthStatus.HEALTHY,
                severity=SeverityLevel.HIGH,
                message="OK",
            )

        checker.add_check("mock", mock_check, SeverityLevel.HIGH)

        result = await checker.check_component("mock")

        assert result.name == "mock"
        assert result.status == HealthStatus.HEALTHY
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_check_unknown_component(self):
        """Тест: проверка неизвестного компонента."""
        checker = HealthChecker()

        result = await checker.check_component("unknown")

        assert result.status == HealthStatus.UNKNOWN
        assert "не найдена" in result.message

    @pytest.mark.asyncio
    async def test_check_all_components(self):
        """Тест: проверка всех компонентов."""
        checker = HealthChecker()

        async def healthy_check():
            return ComponentHealth(
                name="test",
                status=HealthStatus.HEALTHY,
                severity=SeverityLevel.HIGH,
            )

        async def unhealthy_check():
            return ComponentHealth(
                name="broken",
                status=HealthStatus.UNHEALTHY,
                severity=SeverityLevel.MEDIUM,
                message="Something broke",
            )

        checker.add_check("healthy", healthy_check, SeverityLevel.HIGH)
        checker.add_check("broken", unhealthy_check, SeverityLevel.MEDIUM)

        result = await checker.check_all(timeout=5.0)

        assert result.status == HealthStatus.DEGRADED
        assert result.healthy_components == 1
        assert result.unhealthy_components == 1

    @pytest.mark.asyncio
    async def test_check_all_timeout(self):
        """Тест: таймаут при проверке всех компонентов."""
        checker = HealthChecker()

        async def slow_check():
            await asyncio.sleep(10)
            return ComponentHealth(
                name="slow",
                status=HealthStatus.HEALTHY,
                severity=SeverityLevel.LOW,
            )

        checker.add_check("slow", slow_check, SeverityLevel.LOW)

        result = await checker.check_all(timeout=0.1)

        assert any(c.status == HealthStatus.UNKNOWN for c in result.components)
        assert any("Timeout" in c.message for c in result.components)

    @pytest.mark.asyncio
    async def test_check_exception_handling(self):
        """Тест: обработка исключений при проверке."""
        checker = HealthChecker()

        async def failing_check():
            raise ValueError("Test error")

        checker.add_check("failing", failing_check, SeverityLevel.HIGH)

        result = await checker.check_component("failing")

        assert result.status == HealthStatus.UNHEALTHY
        assert "ValueError" in result.message

    @pytest.mark.asyncio
    async def test_get_last_results(self):
        """Тест: получение последних результатов."""
        checker = HealthChecker()

        async def mock_check():
            return ComponentHealth(
                name="test",
                status=HealthStatus.HEALTHY,
                severity=SeverityLevel.HIGH,
            )

        checker.add_check("test", mock_check, SeverityLevel.HIGH)
        await checker.check_component("test")

        results = checker.get_last_results()

        assert "test" in results
        assert results["test"].status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_get_summary(self):
        """Тест: получение сводки."""
        checker = HealthChecker()

        async def healthy_check():
            return ComponentHealth(
                name="healthy",
                status=HealthStatus.HEALTHY,
                severity=SeverityLevel.CRITICAL,
            )

        checker.add_check("healthy", healthy_check, SeverityLevel.CRITICAL)
        await checker.check_component("healthy")

        summary = checker.get_summary()

        assert summary["status"] == "healthy"
        assert summary["healthy_components"] == 1
        assert summary["critical_issues"] == 0


# =============================================================================
# Тесты встроенных проверок
# =============================================================================

class TestBuiltInChecks:
    """Тесты для встроенных проверок здоровья."""

    @pytest.mark.asyncio
    async def test_check_database_health_mock(self):
        """Тест: проверка БД (mock)."""
        from services.database import IDatabaseService
        from services.database.enums import DatabaseType

        mock_db_service = AsyncMock()
        mock_db_service.db_type = DatabaseType.SQLITE
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_db_service.session_factory.return_value = mock_session

        with patch('services.database.get_database_service', return_value=mock_db_service):
            result = await check_database_health()

            # Если mock настроен правильно, должно вернуть HEALTHY
            assert result.name == "database"
            assert result.severity == SeverityLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_check_ollama_health_basic(self):
        """Тест: базовая проверка Ollama (без сложных mock)."""
        # Просто проверяем что функция существует и возвращает ComponentHealth
        result = await check_ollama_health()

        assert isinstance(result, ComponentHealth)
        assert result.name == "ollama"
        assert result.severity == SeverityLevel.HIGH
        # Статус зависит от доступности Ollama в системе
        assert result.status in (HealthStatus.HEALTHY, HealthStatus.UNHEALTHY, HealthStatus.DEGRADED)

    @pytest.mark.asyncio
    async def test_check_llm_fallback_health_basic(self):
        """Тест: базовая проверка LLM fallback (без сложных mock)."""
        result = await check_llm_fallback_health()

        assert isinstance(result, ComponentHealth)
        assert result.name == "llm_fallback"
        assert result.severity == SeverityLevel.HIGH

    @pytest.mark.asyncio
    async def test_check_circuit_breakers_health_basic(self):
        """Тест: базовая проверка circuit breaker'ов (без сложных mock)."""
        result = await check_circuit_breakers_health()

        assert isinstance(result, ComponentHealth)
        assert result.name == "circuit_breakers"
        assert result.severity == SeverityLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_check_telegram_bot_health_basic(self):
        """Тест: базовая проверка Telegram бота (без сложных mock)."""
        result = await check_telegram_bot_health()

        assert isinstance(result, ComponentHealth)
        assert result.name == "telegram_bot"
        assert result.severity == SeverityLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_check_scheduler_health_mock(self):
        """Тест: проверка планировщика (mock)."""
        mock_db_service = AsyncMock()
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_db_service.session_factory.return_value = mock_session

        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("pending", 5),
            ("active", 2),
            ("completed", 100),
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch('services.database.get_database_service', return_value=mock_db_service):
            result = await check_scheduler_health()

            assert result.name == "scheduler"
            assert result.severity == SeverityLevel.MEDIUM


# =============================================================================
# Тесты интеграции
# =============================================================================

class TestIntegration:
    """Интеграционные тесты."""

    @pytest.mark.asyncio
    async def test_create_default_health_checker(self):
        """Тест: создание checker'а по умолчанию."""
        checker = create_default_health_checker()

        # Проверка наличия стандартных проверок
        assert "database" in checker._checks
        assert "telegram_bot" in checker._checks
        assert "llm_fallback" in checker._checks
        assert "ollama" in checker._checks

    @pytest.mark.asyncio
    async def test_get_health_checker_singleton(self):
        """Тест: health checker — singleton."""
        checker1 = get_health_checker()
        checker2 = get_health_checker()

        assert checker1 is checker2

    @pytest.mark.asyncio
    async def test_check_system_health_integration(self):
        """Тест: проверка системы (integration)."""
        # Создаём checker с mock проверками
        checker = HealthChecker()

        async def mock_healthy():
            return ComponentHealth(
                name="mock",
                status=HealthStatus.HEALTHY,
                severity=SeverityLevel.CRITICAL,
            )

        checker.add_check("mock_db", mock_healthy, SeverityLevel.CRITICAL)

        with patch('services.monitoring.health_check._default_checker', checker):
            result = await check_system_health(timeout=5.0)

            assert isinstance(result, SystemHealth)
            assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_get_health_summary_integration(self):
        """Тест: получение сводки (integration)."""
        from services.monitoring import health_check as hc_module

        checker = HealthChecker()

        async def mock_healthy():
            return ComponentHealth(
                name="mock",
                status=HealthStatus.HEALTHY,
                severity=SeverityLevel.HIGH,
            )

        checker.add_check("mock", mock_healthy, SeverityLevel.HIGH)
        await checker.check_component("mock")

        # Сохраняем старый checker и восстанавливаем после теста
        old_checker = hc_module._default_checker
        try:
            hc_module._default_checker = checker
            summary = await hc_module.get_health_summary()

            assert summary["status"] == "healthy"
            assert summary["healthy_components"] == 1
            assert summary["total_components"] == 1
        finally:
            hc_module._default_checker = old_checker


# =============================================================================
# Тесты HealthStatus enum
# =============================================================================

class TestHealthStatusEnum:
    """Тесты для enum HealthStatus."""

    def test_health_status_values(self):
        """Тест: значения HealthStatus."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestSeverityLevelEnum:
    """Тесты для enum SeverityLevel."""

    def test_severity_level_values(self):
        """Тест: значения SeverityLevel."""
        assert SeverityLevel.CRITICAL.value == "critical"
        assert SeverityLevel.HIGH.value == "high"
        assert SeverityLevel.MEDIUM.value == "medium"
        assert SeverityLevel.LOW.value == "low"
