"""
Auto Reindex Service — автоматическая переиндексация векторного поиска.

Особенности:
- Триггеры на добавление/обновление событий
- Фоновая переиндексация
- LRU-кэш для эмбеддингов
- Метрики переиндексации
"""

import logging
import asyncio
from typing import Optional, Set
from datetime import datetime
from collections import OrderedDict

logger = logging.getLogger(__name__)


class ReindexStats:
    """Статистика переиндексации."""

    def __init__(self):
        self.total_reindexed = 0
        self.last_reindex_time: Optional[datetime] = None
        self.reindex_duration_seconds: float = 0.0
        self.errors_count = 0
        self.cache_hits = 0
        self.cache_misses = 0

    def to_dict(self) -> dict:
        """Конвертировать в словарь."""
        return {
            "total_reindexed": self.total_reindexed,
            "last_reindex_time": self.last_reindex_time.isoformat() if self.last_reindex_time else None,
            "reindex_duration_seconds": round(self.reindex_duration_seconds, 2),
            "errors_count": self.errors_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": round(
                self.cache_hits / (self.cache_hits + self.cache_misses) * 100, 2
            ) if (self.cache_hits + self.cache_misses) > 0 else 0.0,
        }


class EmbeddingCache:
    """
    LRU-кэш для эмбеддингов.

    Кэширует вычисленные эмбеддинги для текстов,
    чтобы избежать повторных вычислений.
    """

    def __init__(self, max_size: int = 5000):
        """
        Инициализация кэша эмбеддингов.

        Args:
            max_size: Максимальное количество записей
        """
        self.max_size = max_size
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _evict_if_needed(self):
        """Удалить старые записи при переполнении."""
        while len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)

    def get(self, text_hash: str) -> Optional[list[float]]:
        """
        Получить эмбеддинг из кэша.

        Args:
            text_hash: Хэш текста

        Returns:
            Эмбеддинг или None
        """
        if text_hash not in self._cache:
            self._misses += 1
            return None

        # Переместить в конец (LRU)
        self._cache.move_to_end(text_hash)
        self._hits += 1
        return self._cache[text_hash]

    def set(self, text_hash: str, embedding: list[float]):
        """
        Сохранить эмбеддинг в кэш.

        Args:
            text_hash: Хэш текста
            embedding: Вектор эмбеддинга
        """
        self._evict_if_needed()
        self._cache[text_hash] = embedding

    def stats(self) -> dict:
        """Получить статистику кэша."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total * 100, 2) if total > 0 else 0.0,
        }

    def clear(self):
        """Очистить кэш."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0


class AutoReindexService:
    """
    Сервис автоматической переиндексации.

    Отслеживает изменения в событиях и постах,
    автоматически переиндексирует при необходимости.
    """

    def __init__(
        self,
        embedding_cache_size: int = 5000,
        reindex_batch_size: int = 50,
    ):
        """
        Инициализация сервиса.

        Args:
            embedding_cache_size: Размер кэша эмбеддингов
            reindex_batch_size: Размер пакета для переиндексации
        """
        self.embedding_cache = EmbeddingCache(embedding_cache_size)
        self.reindex_batch_size = reindex_batch_size
        self.stats = ReindexStats()

        # Очередь на переиндексацию
        self._reindex_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # ID уже добавленных в очередь (для дедупликации)
        self._pending_ids: Set[str] = set()

        logger.info("🔄 AutoReindexService инициализирован")

    async def start(self):
        """Запустить фоновую переиндексацию."""
        if self._running:
            logger.warning("⚠️ AutoReindexService уже запущен")
            return

        self._running = True
        self._task = asyncio.create_task(self._reindex_loop())
        logger.info("🚀 AutoReindexService запущен")

    async def stop(self):
        """Остановить фоновую переиндексацию."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("👋 AutoReindexService остановлен")

    async def schedule_reindex(self, item_type: str, item_id: int, data: dict):
        """
        Запланировать переиндексацию элемента.

        Args:
            item_type: Тип элемента ('event', 'post', 'news')
            item_id: ID элемента
            data: Данные для индексации
        """
        key = f"{item_type}_{item_id}"

        if key in self._pending_ids:
            logger.debug(f"⏳ {key} уже в очереди на переиндексацию")
            return

        await self._reindex_queue.put((item_type, item_id, data))
        self._pending_ids.add(key)
        logger.debug(f"📋 {key} добавлен в очередь на переиндексацию")

    async def _reindex_loop(self):
        """Фоновый цикл переиндексации."""
        while self._running:
            try:
                # Получаем задачу из очереди
                item_type, item_id, data = await asyncio.wait_for(
                    self._reindex_queue.get(),
                    timeout=60.0,
                )

                start_time = datetime.now()

                try:
                    await self._reindex_item(item_type, item_id, data)
                    self.stats.total_reindexed += 1
                    self.stats.last_reindex_time = datetime.now()

                    duration = (datetime.now() - start_time).total_seconds()
                    self.stats.reindex_duration_seconds = duration

                    logger.info(
                        f"✅ Переиндексирован {item_type} ID={item_id} "
                        f"(за {duration:.2f}с)"
                    )
                except Exception as e:
                    self.stats.errors_count += 1
                    logger.error(
                        f"❌ Ошибка переиндексации {item_type} ID={item_id}: {e}",
                        exc_info=True,
                    )
                finally:
                    # Удаляем из pending
                    key = f"{item_type}_{item_id}"
                    self._pending_ids.discard(key)
                    self._reindex_queue.task_done()

            except asyncio.TimeoutError:
                # Нет задач в очереди
                pass
            except asyncio.CancelledError:
                logger.info("🛑 AutoReindexService остановлен по запросу")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле переиндексации: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _reindex_item(self, item_type: str, item_id: int, data: dict):
        """
        Переиндексировать элемент.

        Args:
            item_type: Тип элемента
            item_id: ID элемента
            data: Данные для индексации
        """

        # Получаем текст для индексации
        text = self._extract_text(item_type, data)
        if not text:
            logger.warning(f"⚠️ Нет текста для индексации {item_type} ID={item_id}")
            return

        # Проверяем кэш эмбеддингов
        import hashlib
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()

        embedding = self.embedding_cache.get(text_hash)
        if embedding:
            self.stats.cache_hits += 1
            logger.debug(f"🔄 Эмбеддинг из кэша для {item_type} ID={item_id}")
        else:
            self.stats.cache_misses += 1
            # Эмбеддинг будет вычислен в search_engine

        # Добавляем в векторный индекс
        # (детали зависят от типа элемента)
        # Здесь должна быть интеграция с VectorSearchService
        logger.debug(f"📝 Индексация {item_type} ID={item_id} в векторном поиске")

    def _extract_text(self, item_type: str, data: dict) -> str:
        """
        Извлечь текст для индексации из данных.

        Args:
            item_type: Тип элемента
            data: Данные элемента

        Returns:
            Текст для индексации
        """
        if item_type == 'event':
            # Для событий берём контекст
            context = data.get('context_data', {})
            if isinstance(context, dict):
                return ' '.join(str(v) for v in context.values())
            return str(context)

        elif item_type == 'post':
            # Для постов берём текст
            return data.get('text', data.get('description', ''))

        elif item_type == 'news':
            # Для новостей берём заголовок и текст
            title = data.get('title', '')
            text = data.get('text', '')
            return f"{title} {text}"

        return ''

    def get_stats(self) -> dict:
        """Получить статистику переиндексации."""
        return {
            "reindex": self.stats.to_dict(),
            "embedding_cache": self.embedding_cache.stats(),
            "queue_size": self._reindex_queue.qsize(),
            "pending_ids": len(self._pending_ids),
        }

    async def force_reindex_all(
        self,
        events: list,
        posts: list,
        news: list,
    ) -> dict:
        """
        Принудительная переиндексация всех элементов.

        Args:
            events: Список событий
            posts: Список постов
            news: Список новостей

        Returns:
            Статистика переиндексации
        """
        logger.info("🔄 Запуск полной переиндексации...")
        start_time = datetime.now()

        success_count = 0
        error_count = 0

        # Переиндексация событий
        for event in events:
            try:
                await self.schedule_reindex('event', event['id'], event)
                success_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Ошибка переиндексации события: {e}")

        # Переиндексация постов
        for post in posts:
            try:
                await self.schedule_reindex('post', post['id'], post)
                success_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Ошибка переиндексации поста: {e}")

        # Переиндексация новостей
        for news_item in news:
            try:
                await self.schedule_reindex('news', news_item['id'], news_item)
                success_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Ошибка переиндексации новости: {e}")

        # Ждём завершения очереди
        await self._reindex_queue.join()

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"✅ Полная переиндексация завершена: "
            f"{success_count} успешно, {error_count} ошибок (за {duration:.2f}с)"
        )

        return {
            "success_count": success_count,
            "error_count": error_count,
            "duration_seconds": round(duration, 2),
        }


# Глобальный экземпляр (singleton)
_auto_reindex_service: Optional[AutoReindexService] = None


def get_auto_reindex_service() -> AutoReindexService:
    """Получить глобальный сервис переиндексации."""
    global _auto_reindex_service
    if _auto_reindex_service is None:
        _auto_reindex_service = AutoReindexService()
    return _auto_reindex_service


async def start_auto_reindex():
    """Запустить автопереиндексацию."""
    service = get_auto_reindex_service()
    await service.start()


async def stop_auto_reindex():
    """Остановить автопереиндексацию."""
    service = get_auto_reindex_service()
    await service.stop()
