"""
Event Bus — шина событий для AI агентов.

Корректное управление жизненным циклом с возможностью остановки.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Coroutine, Optional

from services.ai_agent.events import EventType, Event

logger = logging.getLogger(__name__)


class EventBus:
    """
    Шина событий для координации AI агентов.

    Поддерживает:
    - Регистрацию обработчиков событий
    - Очередь событий
    - Ограничение параллелизма
    - Корректную остановку
    """

    def __init__(self, max_concurrency: int = 5) -> None:
        """
        Инициализация шины событий.

        Args:
            max_concurrency: Максимальное количество параллельных обработчиков
        """
        self._handlers: dict[EventType, list[Callable]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._sem = asyncio.Semaphore(max_concurrency)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def on(self, event_type: EventType):
        """
        Декоратор для регистрации обработчика событий.

        Args:
            event_type: Тип события для подписки

        Returns:
            Декоратор для функции-обработчика
        """
        def decorator(func: Callable[[Event], Coroutine]):
            self._handlers[event_type].append(func)
            return func

        return decorator

    async def emit(self, event: Event) -> None:
        """
        Отправить событие в шину.

        Args:
            event: Событие для отправки
        """
        if not self._running:
            logger.warning("⚠️ Попытка отправки события в остановленную шину: %s", event.type)
            return
        await self._queue.put(event)

    async def _run_handler(self, handler: Callable, event: Event) -> None:
        """
        Запустить обработчик события с ограничением параллелизма.

        Args:
            handler: Функция-обработчик
            event: Событие для обработки
        """
        async with self._sem:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Ошибка в хендлере %s для события %s",
                    handler.__name__,
                    event.type
                )

    async def _dispatch(self, event: Event) -> None:
        """
        Диспетчеризация события обработчикам.

        Args:
            event: Событие для диспетчеризации
        """
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            logger.warning("Нет хендлеров для события %s", event.type)
            return
        await asyncio.gather(
            *(self._run_handler(h, event) for h in handlers),
            return_exceptions=True
        )

    async def run(self) -> None:
        """
        Запустить обработку событий.

        Блокирует до остановки или отмены.
        """
        self._running = True
        logger.info("🚀 EventBus запущен")

        try:
            while self._running:
                try:
                    # Ждём событие с таймаутом для проверки флага остановки
                    event = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                    await asyncio.create_task(self._dispatch(event))
                    self._queue.task_done()
                except asyncio.TimeoutError:
                    # Проверяем флаг остановки
                    continue
                except asyncio.CancelledError:
                    logger.info("🛑 EventBus получил сигнал отмены")
                    raise
        finally:
            self._running = False
            logger.info("🛑 EventBus остановлен")

    async def stop(self) -> None:
        """
        Остановить шину событий.

        Устанавливает флаг остановки и ждёт завершения очереди.
        """
        if not self._running:
            logger.debug("EventBus уже остановлен")
            return

        logger.info("🛑 Остановка EventBus...")
        self._running = False

        # Ждём завершения обработки очереди
        if not self._queue.empty():
            logger.info(
                f"⏳ Ожидание обработки {self._queue.qsize()} событий..."
            )
            try:
                await asyncio.wait_for(self._queue.join(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("⚠️ Таймаут ожидания завершения очереди событий")

        logger.info("✅ EventBus остановлен")

    @property
    def is_running(self) -> bool:
        """Проверить, запущена ли шина событий."""
        return self._running

    @property
    def pending_events(self) -> int:
        """Количество событий в очереди."""
        return self._queue.qsize()
