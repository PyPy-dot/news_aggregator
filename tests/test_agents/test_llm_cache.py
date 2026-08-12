"""
Тесты для LLM Response Cache.

Проверка работы кэширования ответов AI агентов.
"""

import pytest
import asyncio
import time
from services.ai_agent.cache import (
    LLMResponseCache,
    CacheEntry,
    get_llm_cache,
    reset_llm_cache,
)


class TestCacheEntry:
    """Тесты для CacheEntry."""

    def test_cache_entry_creation(self):
        """Создание записи в кэше."""
        entry = CacheEntry(value="test", ttl_seconds=60)
        assert entry.value == "test"
        assert entry.expires_at > entry.created_at

    def test_cache_entry_not_expired(self):
        """Проверка: запись не истекла."""
        entry = CacheEntry(value="test", ttl_seconds=60)
        assert entry.is_expired() is False
        assert entry.remaining_ttl() > 0

    def test_cache_entry_expired(self):
        """Проверка: запись истекла."""
        entry = CacheEntry(value="test", ttl_seconds=-1)  # Уже истекло
        assert entry.is_expired() is True
        assert entry.remaining_ttl() == 0

    def test_cache_entry_remaining_ttl(self):
        """Проверка: оставшееся время TTL."""
        entry = CacheEntry(value="test", ttl_seconds=10)
        remaining = entry.remaining_ttl()
        assert 0 < remaining <= 10


class TestLLMResponseCache:
    """Тесты для LLMResponseCache."""

    @pytest.fixture
    def cache(self):
        """Создать кэш для тестов."""
        return LLMResponseCache(max_size=5, default_ttl=60)

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, cache):
        """Базовый тест: установка и получение значения."""
        prompt = "test prompt"
        value = "test response"

        await cache.set(prompt, value)
        result = await cache.get(prompt)

        assert result == value

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache):
        """Проверка: кэш промах."""
        result = await cache.get("nonexistent prompt")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_with_model(self, cache):
        """Кэширование с указанием модели."""
        prompt = "test prompt"
        value1 = "response from model1"
        value2 = "response from model2"

        await cache.set(prompt, value1, model="model1")
        await cache.set(prompt, value2, model="model2")

        assert await cache.get(prompt, model="model1") == value1
        assert await cache.get(prompt, model="model2") == value2

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self):
        """Проверка: истечение TTL."""
        cache = LLMResponseCache(max_size=5, default_ttl=1)  # 1 секунда

        await cache.set("prompt", "value")
        assert await cache.get("prompt") == "value"

        # Ждём истечения TTL
        await asyncio.sleep(1.1)

        assert await cache.get("prompt") is None

    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self, cache):
        """Проверка: LRU eviction при переполнении."""
        # Добавляем 5 записей (max_size=5)
        for i in range(5):
            await cache.set(f"prompt{i}", f"value{i}")

        # Добавляем 6-ю запись (должна вытеснить первую)
        await cache.set("prompt5", "value5")

        # Первая запись должна быть вытеснена
        assert await cache.get("prompt0") is None
        assert await cache.get("prompt5") == "value5"

    @pytest.mark.asyncio
    async def test_cache_lru_order(self, cache):
        """Проверка: LRU порядок использования."""
        # Добавляем записи
        for i in range(5):
            await cache.set(f"prompt{i}", f"value{i}")

        # Обращаемся к первой записи (перемещаем в конец)
        await cache.get("prompt0")

        # Добавляем новую запись (должна вытеснить вторую, не первую)
        await cache.set("prompt5", "value5")

        # Первая запись должна остаться
        assert await cache.get("prompt0") == "value0"
        # Вторая запись должна быть вытеснена
        assert await cache.get("prompt1") is None

    @pytest.mark.asyncio
    async def test_cache_delete(self, cache):
        """Проверка: удаление записи."""
        await cache.set("prompt", "value")
        assert await cache.get("prompt") == "value"

        result = await cache.delete("prompt")
        assert result is True
        assert await cache.get("prompt") is None

        # Повторное удаление
        result = await cache.delete("prompt")
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_clear(self, cache):
        """Проверка: очистка всего кэша."""
        for i in range(5):
            await cache.set(f"prompt{i}", f"value{i}")

        await cache.clear()

        stats = await cache.stats()
        assert stats["size"] == 0

    @pytest.mark.asyncio
    async def test_cache_stats(self, cache):
        """Проверка: статистика кэша."""
        # Добавляем записи
        await cache.set("prompt1", "value1")
        await cache.set("prompt2", "value2")

        # Получаем записи (hits)
        await cache.get("prompt1")
        await cache.get("prompt1")

        # Пропуск (miss)
        await cache.get("nonexistent")

        stats = await cache.stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] > 0
        assert stats["size"] == 2
        assert stats["max_size"] == 5

    @pytest.mark.asyncio
    async def test_cache_cleanup(self, cache):
        """Проверка: очистка истёкших записей."""
        # Добавляем записи с коротким TTL
        await cache.set("prompt1", "value1", ttl=1)
        await cache.set("prompt2", "value2", ttl=60)

        # Ждём истечения первой записи
        await asyncio.sleep(1.1)

        # Очищаем истёкшие
        expired_count = await cache.cleanup()

        assert expired_count == 1
        assert await cache.get("prompt1") is None
        assert await cache.get("prompt2") == "value2"

    @pytest.mark.asyncio
    async def test_cache_compute_key_consistency(self, cache):
        """Проверка: стабильность вычисления ключа."""
        prompt = "test prompt"
        model = "test model"

        key1 = cache._compute_key(prompt, model)
        key2 = cache._compute_key(prompt, model)

        assert key1 == key2
        assert len(key1) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_cache_compute_key_different(self, cache):
        """Проверка: разные ключи для разных промптов."""
        key1 = cache._compute_key("prompt1", "model")
        key2 = cache._compute_key("prompt2", "model")
        key3 = cache._compute_key("prompt1", "model2")

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3


class TestGlobalCache:
    """Тесты для глобального кэша (singleton)."""

    def teardown_method(self):
        """Сброс кэша после каждого теста."""
        import asyncio
        asyncio.run(reset_llm_cache())

    @pytest.mark.asyncio
    async def test_get_llm_cache_singleton(self):
        """Проверка: singleton для глобального кэша."""
        cache1 = get_llm_cache()
        cache2 = get_llm_cache()

        assert cache1 is cache2

    @pytest.mark.asyncio
    async def test_get_llm_cache_custom_params(self):
        """Проверка: кэш с кастомными параметрами."""
        # Первый вызов создаёт кэш
        cache1 = get_llm_cache(max_size=100, default_ttl=3600)

        # Второй вызов возвращает тот же кэш (игнорирует параметры)
        cache2 = get_llm_cache(max_size=200, default_ttl=7200)

        assert cache1 is cache2
        assert cache1.max_size == 100  # Оригинальные параметры

    @pytest.mark.asyncio
    async def test_reset_llm_cache(self):
        """Проверка: сброс глобального кэша."""
        cache1 = get_llm_cache()
        await reset_llm_cache()
        cache2 = get_llm_cache()

        assert cache1 is not cache2  # Новый экземпляр


class TestCacheConcurrency:
    """Тесты конкурентного доступа к кэшу."""

    @pytest.mark.asyncio
    async def test_concurrent_set_get(self):
        """Проверка: конкурентная запись и чтение."""
        cache = LLMResponseCache(max_size=100)

        async def worker(i):
            await cache.set(f"prompt{i}", f"value{i}")
            return await cache.get(f"prompt{i}")

        # Запускаем 10 воркеров параллельно
        tasks = [worker(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert results == [f"value{i}" for i in range(10)]

    @pytest.mark.asyncio
    async def test_concurrent_same_key(self):
        """Проверка: конкурентный доступ к одному ключу."""
        cache = LLMResponseCache(max_size=100)

        async def setter():
            await cache.set("prompt", "value")

        async def getter():
            return await cache.get("prompt")

        # Параллельная запись и чтение
        await asyncio.sleep(0.01)  # Небольшая задержка
        set_task = asyncio.create_task(setter())
        await asyncio.sleep(0.01)  # Даём записи начаться
        get_task = asyncio.create_task(getter())

        await set_task
        result = await get_task

        # Чтение должно вернуть значение (или None если не успело записаться)
        assert result is None or result == "value"
