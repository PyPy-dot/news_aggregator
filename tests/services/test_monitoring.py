"""
Тесты для модуля мониторинга и метрик.
"""

import pytest

from services.monitoring import (
    get_metrics,
    get_metrics_content_type,
    update_queue_size,
    update_active_tasks,
    update_vector_index_stats,
    increment_categorization,
    increment_news_generation,
    increment_telegram_messages,
    get_health_status,
    track_duration,
    track_errors,
)


class TestMetricsExport:
    """Тесты для экспорта метрик."""

    def test_get_metrics_returns_bytes(self):
        """Проверка, что get_metrics возвращает bytes."""
        metrics = get_metrics()
        assert isinstance(metrics, bytes)
        assert len(metrics) > 0

    def test_get_metrics_content_type(self):
        """Проверка Content-Type для метрик."""
        content_type = get_metrics_content_type()
        assert 'text/plain' in content_type or 'openmetrics' in content_type.lower()


class TestMetricUpdates:
    """Тесты для обновления метрик."""

    def test_update_queue_size(self):
        """Проверка обновления размера очереди."""
        # Просто проверяем, что вызов не вызывает ошибок
        update_queue_size('categorization', 10)
        update_queue_size('agent', 5)

    def test_update_active_tasks(self):
        """Проверка обновления активных задач."""
        update_active_tasks('categorization', 3)
        update_active_tasks('news_generation', 1)

    def test_update_vector_index_stats(self):
        """Проверка обновления статистики векторного индекса."""
        update_vector_index_stats('events', 100)
        update_vector_index_stats('news', 50)
        update_vector_index_stats('posts', 200)

    def test_increment_categorization(self):
        """Проверка счётчика категоризации."""
        increment_categorization('success')
        increment_categorization('failed')
        increment_categorization('advertisement')

    def test_increment_news_generation(self):
        """Проверка счётчика генерации новостей."""
        increment_news_generation('success', 'urgent')
        increment_news_generation('success', 'scheduled')
        increment_news_generation('failed', 'trusted')

    def test_increment_telegram_messages(self):
        """Проверка счётчика Telegram сообщений."""
        increment_telegram_messages('notification', 'success')
        increment_telegram_messages('post', 'failed')


class TestHealthStatus:
    """Тесты для health checks."""

    def test_get_health_status(self):
        """Проверка получения статуса здоровья."""
        health = get_health_status()

        assert 'status' in health
        assert 'timestamp' in health
        assert 'components' in health
        assert health['status'] == 'healthy'
        assert 'metrics' in health['components']


class TestDecorators:
    """Тесты для декораторов."""

    @pytest.mark.asyncio
    async def test_track_duration(self):
        """Проверка декоратора track_duration."""
        from prometheus_client import Histogram

        test_histogram = Histogram(
            'test_duration',
            'Test duration',
            labelnames=['task_type'],
        )

        @track_duration(test_histogram, {'task_type': 'test'})
        async def test_func():
            return 'result'

        result = await test_func()
        assert result == 'result'

    @pytest.mark.asyncio
    async def test_track_errors_success(self):
        """Проверка декоратора track_errors (успех)."""
        from prometheus_client import Counter

        test_counter = Counter(
            'test_errors',
            'Test errors',
            labelnames=['status'],
        )

        @track_errors(test_counter, 'status', 'failed')
        async def test_func():
            return 'success'

        result = await test_func()
        assert result == 'success'

    @pytest.mark.asyncio
    async def test_track_errors_exception(self):
        """Проверка декоратора track_errors (ошибка)."""
        from prometheus_client import Counter

        test_counter = Counter(
            'test_errors_exc',
            'Test errors exception',
            labelnames=['status'],
        )

        @track_errors(test_counter, 'status', 'failed')
        async def test_func_raise():
            raise ValueError('Test error')

        with pytest.raises(ValueError):
            await test_func_raise()
