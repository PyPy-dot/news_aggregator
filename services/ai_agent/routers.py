import asyncio
import logging
from collections import defaultdict
from typing import Callable, Coroutine
from services.ai_agent.events import EventType, Event

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self, max_concurrency: int = 5):
        self._handlers: dict[EventType, list[Callable]] = defaultdict(list)
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._sem = asyncio.Semaphore(max_concurrency)

    def on(self, event_type: EventType):
        def decorator(func: Callable[[Event], Coroutine]):
            self._handlers[event_type].append(func)
            return func

        return decorator

    async def emit(self, event: Event):
        await self._queue.put(event)

    async def _run_handler(self, handler, event: Event):
        async with self._sem:
            try:
                await handler(event)
            except Exception:
                logger.exception("Ошибка в хендлере %s для события %s", handler.__name__, event.type)

    async def _dispatch(self, event: Event):
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            logger.warning("Нет хендлеров для события %s", event.type)
            return
        await asyncio.gather(*(self._run_handler(h, event) for h in handlers))

    async def run(self):
        while True:
            event = await self._queue.get()
            await asyncio.create_task(self._dispatch(event))
            self._queue.task_done()
