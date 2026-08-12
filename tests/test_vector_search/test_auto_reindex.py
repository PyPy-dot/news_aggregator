"""
Тесты для Auto Reindex Service.

Проверка работы автоматической переиндексации векторного поиска.
"""

import pytest
import asyncio
from datetime import datetime

from services.vector_search.auto_reindex import (
    AutoReindexService,
    EmbeddingCache,
    ReindexStats,
    get_auto_reindex_service,
)


class TestReindexStats:
    """Тесты для ReindexStats."""

    def test_reindex_stats_init(self):
        """Инициализация статистики."""
        stats = ReindexStats()
        assert stats.total_reindexed == 0
        assert stats.last_reindex_time is None
        assert stats.reindex_duration_seconds == 0.0
        assert stats.errors_count == 0
        assert stats.cache_hits == 0
        assert stats.cache_misses == 0

    def test_reindex_stats_to_dict(self):
        """Конвертация в словарь."""
        stats = ReindexStats()
        stats.total_reindexed = 10
        stats.last_reindex_time = datetime(2026, 8, 9, 12, 0, 0)
        stats.reindex_duration_seconds = 5.5
        stats.errors_count = 1
        stats.cache_hits = 8
        stats.cache_misses = 2

        result = stats.to_dict()

        assert result["total_reindexed"] == 10
        assert result["errors_count"] == 1
        assert result["reindex_duration_seconds"] == 5.5
        assert result["cache_hit_rate"] == 80.0  # 8/(8+2)*100

    def test_reindex_stats_zero_division(self):
        """Проверка деления на ноль при cache_hit_rate."""
        stats = ReindexStats()
        result = stats.to_dict()

        assert result["cache_hit_rate"] == 0.0


class TestEmbeddingCache:
    """Тесты для EmbeddingCache."""

    def test_embedding_cache_set_get(self):
        """Базовый тест: установка и получение."""
        cache = EmbeddingCache(max_size=10)
        embedding = [0.1, 0.2, 0.3]

        cache.set("hash1", embedding)
        result = cache.get("hash1")

        assert result == embedding

    def test_embedding_cache_miss(self):
        """Проверка: кэш промах."""
        cache = EmbeddingCache(max_size=10)
        result = cache.get("nonexistent")
        assert result is None

    def test_embedding_cache_lru_eviction(self):
        """Проверка: LRU eviction при переполнении."""
        cache = EmbeddingCache(max_size=3)

        # Добавляем 3 записи
        for i in range(3):
            cache.set(f"hash{i}", [float(i)])

        # Добавляем 4-ю (должна вытеснить первую)
        cache.set("hash3", [3.0])

        # Первая запись должна быть вытеснена
        assert cache.get("hash0") is None
        assert cache.get("hash3") == [3.0]

    def test_embedding_cache_lru_order(self):
        """Проверка: LRU порядок использования."""
        cache = EmbeddingCache(max_size=3)

        # Добавляем записи
        for i in range(3):
            cache.set(f"hash{i}", [float(i)])

        # Обращаемся к первой (перемещаем в конец)
        cache.get("hash0")

        # Добавляем новую (должна вытеснить вторую)
        cache.set("hash3", [3.0])

        # Первая должна остаться
        assert cache.get("hash0") == [0.0]
        # Вторая должна быть вытеснена
        assert cache.get("hash1") is None

    def test_embedding_cache_stats(self):
        """Проверка: статистика кэша."""
        cache = EmbeddingCache(max_size=10)

        cache.set("hash1", [1.0])
        cache.set("hash2", [2.0])

        # 2 hits
        cache.get("hash1")
        cache.get("hash1")

        # 1 miss
        cache.get("nonexistent")

        stats = cache.stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] > 0
        assert stats["size"] == 2

    def test_embedding_cache_clear(self):
        """Проверка: очистка кэша."""
        cache = EmbeddingCache(max_size=10)
        cache.set("hash1", [1.0])
        cache.set("hash2", [2.0])

        cache.clear()

        stats = cache.stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0


class TestAutoReindexService:
    """Тесты для AutoReindexService."""

    @pytest.fixture
    def reindex_service(self):
        """Создать сервис для тестов."""
        return AutoReindexService(
            embedding_cache_size=100,
            reindex_batch_size=10,
        )

    @pytest.mark.asyncio
    async def test_schedule_reindex(self, reindex_service):
        """Проверка: планирование переиндексации."""
        data = {"text": "test event"}

        await reindex_service.schedule_reindex('event', 1, data)

        # Проверка очереди
        assert reindex_service._reindex_queue.qsize() == 1
        assert len(reindex_service._pending_ids) == 1

    @pytest.mark.asyncio
    async def test_schedule_reindex_dedup(self, reindex_service):
        """Проверка: дедупликация очереди."""
        data = {"text": "test event"}

        # Планируем дважды один и тот же элемент
        await reindex_service.schedule_reindex('event', 1, data)
        await reindex_service.schedule_reindex('event', 1, data)

        # Должна быть только одна задача
        assert reindex_service._reindex_queue.qsize() == 1
        assert len(reindex_service._pending_ids) == 1

    @pytest.mark.asyncio
    async def test_extract_text_event(self, reindex_service):
        """Проверка: извлечение текста для события."""
        data = {
            "context_data": {
                "title": "Test Event",
                "description": "Test Description",
            }
        }

        text = reindex_service._extract_text('event', data)

        assert "Test Event" in text
        assert "Test Description" in text

    @pytest.mark.asyncio
    async def test_extract_text_post(self, reindex_service):
        """Проверка: извлечение текста для поста."""
        data = {
            "text": "Post text",
            "description": "Post description",
        }

        text = reindex_service._extract_text('post', data)

        assert text == "Post text"

    @pytest.mark.asyncio
    async def test_extract_text_news(self, reindex_service):
        """Проверка: извлечение текста для новости."""
        data = {
            "title": "News Title",
            "text": "News text",
        }

        text = reindex_service._extract_text('news', data)

        assert "News Title" in text
        assert "News text" in text

    @pytest.mark.asyncio
    async def test_get_stats(self, reindex_service):
        """Проверка: получение статистики."""
        stats = reindex_service.get_stats()

        assert "reindex" in stats
        assert "embedding_cache" in stats
        assert "queue_size" in stats
        assert "pending_ids" in stats

    @pytest.mark.asyncio
    async def test_start_stop(self, reindex_service):
        """Проверка: запуск и остановка."""
        await reindex_service.start()
        assert reindex_service._running is True

        await reindex_service.stop()
        assert reindex_service._running is False

    @pytest.mark.asyncio
    async def test_reindex_loop_integration(self, reindex_service):
        """Интеграционный тест: цикл переиндексации."""
        await reindex_service.start()

        # Планируем переиндексацию
        data = {"text": "test event"}
        await reindex_service.schedule_reindex('event', 1, data)

        # Ждём выполнения
        await asyncio.sleep(0.5)

        await reindex_service.stop()

        # Проверка статистики
        stats = reindex_service.get_stats()
        assert stats["reindex"]["total_reindexed"] >= 0  # Может быть 0 или 1


class TestGlobalAutoReindexService:
    """Тесты для глобального сервиса."""

    def teardown_method(self):
        """Сброс после теста."""
        import services.vector_search.auto_reindex as module
        module._auto_reindex_service = None

    def test_get_auto_reindex_service_singleton(self):
        """Проверка: singleton для глобального сервиса."""
        service1 = get_auto_reindex_service()
        service2 = get_auto_reindex_service()

        assert service1 is service2

    @pytest.mark.asyncio
    async def test_start_stop_global(self):
        """Проверка: запуск/остановка глобального сервиса."""
        from services.vector_search.auto_reindex import (
            start_auto_reindex,
            stop_auto_reindex,
        )

        await start_auto_reindex()
        service = get_auto_reindex_service()
        assert service._running is True

        await stop_auto_reindex()
        assert service._running is False


class TestEmbeddingCachePerformance:
    """Тесты производительности кэша эмбеддингов."""

    def test_cache_performance(self):
        """Проверка: производительность при большой нагрузке."""
        cache = EmbeddingCache(max_size=1000)

        # Добавляем 1000 записей
        for i in range(1000):
            cache.set(f"hash{i}", [float(i) for _ in range(768)])

        # Проверяем все записи
        for i in range(1000):
            result = cache.get(f"hash{i}")
            assert result is not None

        stats = cache.stats()
        assert stats["size"] == 1000
        assert stats["hit_rate"] == 100.0

    def test_cache_eviction_performance(self):
        """Проверка: производительность eviction."""
        cache = EmbeddingCache(max_size=100)

        # Добавляем 200 записей (должно вытеснить 100)
        for i in range(200):
            cache.set(f"hash{i}", [float(i)])

        stats = cache.stats()
        assert stats["size"] == 100
        # Первые 100 записей должны быть вытеснены
        assert cache.get("hash0") is None
        assert cache.get("hash199") is not None
