"""
CategorizationQueue — очередь задач на категоризацию.

Управляет очередью задач, изолированно от логики обработки.
Поддерживает как локальную очередь (deque), так и Redis (через RedisTaskQueue).
"""

import asyncio
import logging
import os
from collections import deque
from dataclasses import dataclass
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class CategorizationTask:
    """
    Задача на категоризацию (единый формат для всех источников).

    Attributes:
        source_type: Тип источника: "telegram", "rss", "web"
        source_id: ID записи в сырой таблице (rss_news.id, web_news.id) —
            используется для обновления результатов категоризации.
            Для Telegram None (там channel_id).
        channel_id: ID канала в Telegram (только для source_type="telegram")
        prompt: Промпт для AI
        original_text: Исходный текст поста
        title: Название источника
        desc: Описание источника
    """
    source_type: str = 'telegram'
    source_id: Optional[int] = None
    channel_id: int = 0
    prompt: str = ''
    original_text: str = ''
    title: str = ''
    desc: str = ''


class CategorizationQueue:
    """
    Очередь задач на категоризацию.

    Thread-safe очередь с ограничением размера.
    Поддерживает Redis через RedisTaskQueue когда доступен.

    Attributes:
        max_size: Максимальный размер очереди
    """

    def __init__(self, max_size: Optional[int] = None) -> None:
        """
        Инициализация очереди.

        Args:
            max_size: Максимальный размер (по умолчанию из конфига)
        """
        self.max_size = max_size or settings.categorization_queue_maxlen

        # Проверяем наличие Redis URL в окружении
        self._use_redis = bool(os.environ.get('REDIS_URL') or os.environ.get('REDIS_HOST'))
        self._redis_queue = None

        # Всегда инициализируем локальные атрибуты для безопасности
        self._queue: deque[CategorizationTask] = deque(maxlen=self.max_size)
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Event()

        if self._use_redis:
            logger.debug("CategorizationQueue использует Redis (с локальным fallback)")
        else:
            logger.debug("CategorizationQueue использует локальную очередь")

        self._running = False

    async def add(self, task: CategorizationTask) -> None:
        """
        Добавить задачу в очередь.

        Args:
            task: Задача на категоризацию
        """
        # Всегда пишем в локальную очередь — потребитель читает из неё
        async with self._lock:
            self._queue.append(task)
            self._not_empty.set()
            logger.debug(
                f"📊 Добавлена задача категоризации. "
                f"В очереди: {len(self._queue)} задач"
            )

        # Дополнительно дублируем в Redis (если настроен) для распределённых воркеров
        if self._use_redis:
            try:
                if self._redis_queue is None:
                    from services.core.redis_queue import RedisTaskQueue
                    redis_url = os.environ.get('REDIS_URL') or os.environ.get('REDIS_HOST', 'localhost')
                    if not redis_url.startswith('redis://'):
                        redis_url = f'redis://{redis_url}:6379'
                    self._redis_queue = RedisTaskQueue(redis_url=redis_url, prefix='categorization_queue')
                    await self._redis_queue.connect()

                await self._redis_queue.add_task(
                    agent_name='Categorizer',
                    method_name='categorize',
                    channel_id=task.channel_id,
                    prompt=task.prompt,
                    original_text=task.original_text,
                    title=task.title,
                    desc=task.desc,
                )
            except Exception as e:
                # Redis недоступен — задачи всё равно в локальной очереди
                if self._use_redis:
                    logger.warning(f"Redis недоступен для категоризации: {e} (локальная очередь работает)")
                    self._use_redis = False

    async def get(self) -> Optional[CategorizationTask]:
        """
        Получить задачу из очереди.

        Ждёт появления задачи, если очередь пуста.

        Returns:
            Задача или None если остановлена
        """
        # Redis-очередь не поддерживается в get() — потребитель читает из локальной
        # (Redis используется как дублирующий бэкэнд в add() для распределённых воркеров)
        self._use_redis = False

        # Локальная очередь
        while self._running:
            async with self._lock:
                if self._queue:
                    task = self._queue.popleft()
                    if not self._queue:
                        self._not_empty.clear()
                    return task
            # Ждём появления новой задачи (с таймаутом для проверки флага остановки)
            try:
                await asyncio.wait_for(self._not_empty.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue  # Проверяем флаг _running и продолжаем
        return None

    def start(self) -> None:
        """Запустить обработку очереди."""
        self._running = True
        logger.info("🔄 Очередь категоризации запущена")

    async def stop(self) -> None:
        """
        Остановить обработку очереди.

        Устанавливает флаг остановки и закрывает Redis подключение.
        """
        logger.info("🛑 Остановка очереди категоризации...")
        self._running = False

        if self._use_redis and self._redis_queue:
            await self._redis_queue.disconnect()
        elif hasattr(self, '_not_empty'):
            self._not_empty.set()  # Разбудить ожидающих

    @property
    def is_running(self) -> bool:
        """Проверить, запущена ли очередь."""
        return self._running

    @property
    def size(self) -> int:
        """Текущий размер очереди."""
        return len(self._queue)

    @property
    def is_empty(self) -> bool:
        """Проверить, пуста ли очередь."""
        return len(self._queue) == 0

    @property
    def use_redis(self) -> bool:
        """Проверить, используется ли Redis."""
        return self._use_redis
