"""
Кэш для AI агентов.

LRU-кэш с TTL для ответов LLM (Ollama).

Особенности:
- Кэширование по хэшу промпта
- TTL 24 часа (настраиваемый)
- LRU eviction при достижении лимита
- Async-safe операции
"""

import hashlib
import time
import asyncio
from typing import Any, Optional
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)


class CacheEntry:
    """Запись в кэше."""

    def __init__(self, value: Any, ttl_seconds: int):
        self.value = value
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl_seconds

    def is_expired(self) -> bool:
        """Проверить, истёк ли срок действия записи."""
        return time.time() > self.expires_at

    def remaining_ttl(self) -> float:
        """Оставшееся время жизни в секундах."""
        return max(0, self.expires_at - time.time())


class LLMResponseCache:
    """
    LRU-кэш для ответов LLM.

    Attributes:
        max_size: Максимальное количество записей
        default_ttl: TTL по умолчанию (секунды)
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 86400,  # 24 часа
    ):
        """
        Инициализация кэша.

        Args:
            max_size: Максимальное количество записей в кэше
            default_ttl: Время жизни записи по умолчанию (секунды)
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()

        # Статистика
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _compute_key(self, prompt: str, model: str = "") -> str:
        """
        Вычислить ключ кэша по хэшу промпта.

        Args:
            prompt: Текст промпта
            model: Название модели (для разделения кэша по моделям)

        Returns:
            Хэш-ключ
        """
        key_data = f"{model}:{prompt}"
        return hashlib.sha256(key_data.encode('utf-8')).hexdigest()

    def _evict_if_needed(self) -> None:
        """Удалить старые записи при переполнении кэша."""
        while len(self._cache) >= self.max_size:
            # Удаляем самую старую запись (LRU)
            self._cache.popitem(last=False)
            self._evictions += 1

    def _evict_expired(self) -> int:
        """
        Удалить все истёкшие записи.

        Returns:
            Количество удалённых записей
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    async def get(self, prompt: str, model: str = "") -> Optional[Any]:
        """
        Получить значение из кэша.

        Args:
            prompt: Текст промпта
            model: Название модели

        Returns:
            Значение из кэша или None если не найдено
        """
        async with self._lock:
            key = self._compute_key(prompt, model)

            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            # Проверка на истечение срока
            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                logger.debug(f"🕒 Кэш промах (истёк TTL): {key[:16]}...")
                return None

            # Переместить в конец (LRU - недавно использованные)
            self._cache.move_to_end(key)
            self._hits += 1
            logger.debug(f"✅ Кэш попадание: {key[:16]}... (TTL={entry.remaining_ttl():.0f}s)")
            return entry.value

    async def set(
        self,
        prompt: str,
        value: Any,
        model: str = "",
        ttl: Optional[int] = None,
    ) -> None:
        """
        Сохранить значение в кэш.

        Args:
            prompt: Текст промпта
            value: Значение для кэширования
            model: Название модели
            ttl: Время жизни записи (секунды), по умолчанию self.default_ttl
        """
        async with self._lock:
            key = self._compute_key(prompt, model)
            ttl = ttl or self.default_ttl

            # Удаляем истёкшие записи перед добавлением
            self._evict_expired()

            # Удаляем старые записи при переполнении
            self._evict_if_needed()

            # Добавляем новую запись
            self._cache[key] = CacheEntry(value, ttl)
            logger.debug(f"💾 Кэш записан: {key[:16]}... (TTL={ttl}s)")

    async def delete(self, prompt: str, model: str = "") -> bool:
        """
        Удалить запись из кэша.

        Args:
            prompt: Текст промпта
            model: Название модели

        Returns:
            True если запись была удалена
        """
        async with self._lock:
            key = self._compute_key(prompt, model)

            if key in self._cache:
                del self._cache[key]
                logger.debug(f"🗑️ Кэш удалён: {key[:16]}...")
                return True
            return False

    async def clear(self) -> None:
        """Очистить весь кэш."""
        async with self._lock:
            self._cache.clear()
            logger.info("🧹 Кэш очищен полностью")

    async def stats(self) -> dict[str, Any]:
        """
        Получить статистику кэша.

        Returns:
            Статистика: hits, misses, hit_rate, size, evictions
        """
        async with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 2),
                "size": len(self._cache),
                "max_size": self.max_size,
                "evictions": self._evictions,
                "expired_count": self._evict_expired(),
            }

    async def cleanup(self) -> int:
        """
        Очистить истёкшие записи.

        Returns:
            Количество удалённых записей
        """
        async with self._lock:
            return self._evict_expired()


# Глобальный экземпляр кэша (singleton)
_llm_cache: Optional[LLMResponseCache] = None


def get_llm_cache(
    max_size: int = 1000,
    default_ttl: int = 86400,
) -> LLMResponseCache:
    """
    Получить глобальный кэш LLM (singleton).

    Args:
        max_size: Максимальное количество записей
        default_ttl: TTL по умолчанию (секунды)

    Returns:
        LLMResponseCache экземпляр
    """
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LLMResponseCache(max_size, default_ttl)
    return _llm_cache


async def reset_llm_cache() -> None:
    """Сбросить глобальный кэш LLM."""
    global _llm_cache
    if _llm_cache is not None:
        await _llm_cache.clear()
        _llm_cache = None
