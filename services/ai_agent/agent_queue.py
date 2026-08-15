"""
Agent Task Queue — единая очередь задач для AI агентов.

Обеспечивает:
- Приоритетную очередь задач
- Ограничение параллелизма
- Retry logic при ошибках
- Мониторинг состояния очереди
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine, Optional, TypeVar
from collections import deque

from services.monitoring.metrics import (
    agent_queue_size,
    agent_queue_active_tasks,
    agent_tasks_total,
    agent_task_duration,
    agent_queue_pending_by_priority,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class TaskPriority(IntEnum):
    """
    Приоритеты задач.

    Чем меньше число, тем выше приоритет.
    """
    CRITICAL = 1    # Критические (срочные новости)
    HIGH = 2        # Высокий приоритет (Analyst/Editor для срочных)
    NORMAL = 3      # Обычный приоритет (плановая обработка)
    LOW = 4         # Низкий приоритет (фоновые задачи)


class TaskStatus(IntEnum):
    """Статусы задачи."""
    PENDING = 1
    PROCESSING = 2
    COMPLETED = 3
    FAILED = 4
    RETRY = 5


@dataclass(order=True)
class AgentTask:
    """
    Задача для AI агента.

    Сортируется по приоритету (меньше = выше), затем по времени создания.
    """
    priority: int
    created_at: float = field(compare=True)
    task_id: str = field(compare=False)
    agent_name: str = field(compare=False)
    method_name: str = field(compare=False)
    args: tuple = field(compare=False, default_factory=tuple)
    kwargs: dict = field(compare=False, default_factory=dict)
    max_retries: int = field(compare=False, default=3)
    retry_count: int = field(compare=False, default=0)
    status: TaskStatus = field(compare=False, default=TaskStatus.PENDING)
    result: Any = field(compare=False, default=None)
    error: Optional[Exception] = field(compare=False, default=None)
    callback: Optional[Callable] = field(compare=False, default=None)
    method: Optional[Callable] = field(compare=False, default=None)  # Метод для вызова


class AgentTaskQueue:
    """
    Единая очередь задач для AI агентов.

    Attributes:
        max_concurrency: Максимальное количество параллельных задач
        max_queue_size: Максимальный размер очереди
        retry_delay: Задержка между попытками (секунды)
    """

    def __init__(
        self,
        max_concurrency: int = 2,  # 2 параллельные задачи
        max_queue_size: int = 100,
        retry_delay: float = 2.0,
    ) -> None:
        """
        Инициализация очереди задач.

        Args:
            max_concurrency: Максимальное количество параллельных задач
            max_queue_size: Максимальный размер очереди
            retry_delay: Задержка между попытками выполнения
        """
        self._queue: asyncio.PriorityQueue[AgentTask] = asyncio.PriorityQueue()
        self._sem = asyncio.Semaphore(max_concurrency)
        self._max_queue_size = max_queue_size
        self._retry_delay = retry_delay
        self._running = False
        self._task_counter = 0
        self._stats = {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'retried': 0,
        }
        self._processor_task: Optional[asyncio.Task] = None

        # История последних задач (для отладки)
        self._history: deque[AgentTask] = deque(maxlen=50)

        # Счётчики активных задач по агентам
        self._active_by_agent: dict[str, int] = {}

    async def start(self) -> None:
        """Запустить обработчик очереди."""
        if self._running:
            logger.debug("🔄 Очередь уже запущена")
            return

        self._running = True
        self._processor_task = asyncio.create_task(self._process_queue())
        logger.info(f"🚀 AgentTaskQueue запущен (max_concurrency={self._sem._value})")

    async def stop(self) -> None:
        """Остановить обработчик очереди."""
        if not self._running:
            return

        logger.info("🛑 Остановка AgentTaskQueue...")
        self._running = False

        if self._processor_task:
            self._processor_task.cancel()
            try:
                await asyncio.wait_for(self._processor_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        logger.info("✅ AgentTaskQueue остановлен")

    async def add_task(
        self,
        agent_name: str,
        method_name: str,
        method: Callable[..., Coroutine[Any, Any, T]],
        *args,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        callback: Optional[Callable[[T], None]] = None,
        **kwargs,
    ) -> str:
        """
        Добавить задачу в очередь.

        Args:
            agent_name: Имя агента (Categorizer, Analyst, Editor, Archivist)
            method_name: Имя метода (categorize, analyze, generate_news, create_context)
            method: Метод для вызова
            *args: Позиционные аргументы метода
            priority: Приоритет задачи
            max_retries: Максимальное количество попыток
            callback: Callback для результата
            **kwargs: Именованные аргументы метода

        Returns:
            task_id: ID задачи
        """
        # Проверяем размер очереди
        if self._queue.qsize() >= self._max_queue_size:
            logger.warning(f"⚠️ Очередь заполнена ({self._queue.qsize()}/{self._max_queue_size})")
            # Отклоняем задачи с низким приоритетом
            if priority >= TaskPriority.NORMAL:
                raise QueueFullError(f"Очередь заполнена: {self._queue.qsize()}/{self._max_queue_size}")

        self._task_counter += 1
        task_id = f"{agent_name}_{self._task_counter}_{int(time.time())}"

        task = AgentTask(
            priority=priority.value,
            created_at=time.time(),
            task_id=task_id,
            agent_name=agent_name,
            method_name=method_name,
            args=args,
            kwargs=kwargs,
            max_retries=max_retries,
            callback=callback,
        )

        # Сохраняем метод в отдельном поле (чтобы не терялся при retry)
        task.method = method

        await self._queue.put(task)
        self._stats['total'] += 1

        # Обновляем метрики
        agent_queue_size.set(self._queue.qsize())
        agent_queue_pending_by_priority.labels(priority=priority.name).inc()

        logger.debug(
            f"📋 Задача добавлена: {task_id} "
            f"(agent={agent_name}, method={method_name}, priority={priority.name})"
        )

        return task_id

    async def _process_queue(self) -> None:
        """Обработчик очереди (фоновая задача)."""
        logger.info("🔄 Запущен обработчик очереди задач")

        while self._running:
            try:
                # Ждём задачу с таймаутом
                try:
                    task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # Пропускаем задачи на повтор с задержкой
                if task.status == TaskStatus.RETRY:
                    wait_time = self._retry_delay * (2 ** task.retry_count)  # Экспоненциальная задержка
                    logger.debug(f"⏳ Задача {task.task_id} на повторе через {wait_time:.1f}с")
                    await asyncio.sleep(wait_time)

                # Запускаем задачу
                asyncio.create_task(self._run_task(task))

                self._queue.task_done()

            except asyncio.CancelledError:
                logger.info("🛑 Обработчик очереди остановлен")
                raise
            except Exception as e:
                logger.error(f"❌ Ошибка в обработчике очереди: {e}", exc_info=True)

    async def _run_task(self, task: AgentTask) -> None:
        """
        Выполнить задачу с ограничением параллелизма.

        Args:
            task: Задача для выполнения
        """
        async with self._sem:
            await self._execute_task(task, task.method)

    async def _execute_task(
        self,
        task: AgentTask,
        method: Optional[Callable[..., Coroutine[Any, Any, T]]],
    ) -> Optional[T]:
        """
        Выполнить задачу.

        Args:
            task: Задача
            method: Метод для вызова

        Returns:
            Результат выполнения или None
        """
        task.status = TaskStatus.PROCESSING
        start_time = time.time()

        # Обновляем метрики активных задач
        self._active_by_agent[task.agent_name] = self._active_by_agent.get(task.agent_name, 0) + 1
        agent_queue_active_tasks.labels(agent_name=task.agent_name).set(
            self._active_by_agent[task.agent_name]
        )

        logger.debug(f"▶️ Задача {task.task_id} выполняется")

        try:
            if method is None:
                raise ValueError(f"Метод не найден для задачи {task.task_id}")

            # Выполняем метод
            # method — это несвязанная функция (func из декоратора @queued)
            # self хранится в task.args[0], остальные аргументы в task.args[1:]
            if len(task.args) < 1:
                raise ValueError(f"Нет аргументов для задачи {task.task_id} (ожидается self)")

            # Извлекаем self и аргументы
            instance = task.args[0]
            method_args = task.args[1:] if len(task.args) > 1 else ()
            # task.kwargs содержит только аргументы метода (служебные параметры — отдельные поля)
            method_kwargs = task.kwargs

            # Вызываем метод с instance как первым аргументом
            result = await method(instance, *method_args, **method_kwargs)

            duration = time.time() - start_time

            task.status = TaskStatus.COMPLETED
            task.result = result
            self._stats['completed'] += 1

            # Обновляем метрики
            agent_tasks_total.labels(agent_name=task.agent_name, status='success').inc()
            agent_task_duration.labels(
                agent_name=task.agent_name,
                method_name=task.method_name
            ).observe(duration)

            logger.debug(f"✅ Задача {task.task_id} выполнена за {duration:.2f}с")

            # Вызываем callback если есть
            if task.callback and result is not None:
                try:
                    task.callback(result)
                except Exception as e:
                    logger.error(f"❌ Ошибка в callback для {task.task_id}: {e}")

            # Добавляем в историю
            self._history.append(task)

            # Уменьшаем счётчик активных задач
            self._active_by_agent[task.agent_name] = max(0, self._active_by_agent.get(task.agent_name, 0) - 1)
            agent_queue_active_tasks.labels(agent_name=task.agent_name).set(
                self._active_by_agent[task.agent_name]
            )

            return result

        except Exception as e:
            duration = time.time() - start_time
            task.error = e
            task.retry_count += 1

            # Проверяем, нужно ли повторять
            if task.retry_count < task.max_retries:
                task.status = TaskStatus.RETRY
                self._stats['retried'] += 1

                # Метрика для retry
                agent_tasks_total.labels(agent_name=task.agent_name, status='retried').inc()

                logger.warning(
                    f"⚠️ Задача {task.task_id} не выполнена (попытка {task.retry_count}/{task.max_retries}): {e}"
                )
                # Возвращаем в очередь
                await self._queue.put(task)
            else:
                task.status = TaskStatus.FAILED
                self._stats['failed'] += 1

                # Метрика для failed
                agent_tasks_total.labels(agent_name=task.agent_name, status='failed').inc()
                agent_task_duration.labels(
                    agent_name=task.agent_name,
                    method_name=task.method_name
                ).observe(duration)

                logger.error(
                    f"❌ Задача {task.task_id} не выполнена после {task.max_retries} попыток: {e}",
                    exc_info=True
                )
                self._history.append(task)

            # Уменьшаем счётчик активных задач
            self._active_by_agent[task.agent_name] = max(0, self._active_by_agent.get(task.agent_name, 0) - 1)
            agent_queue_active_tasks.labels(agent_name=task.agent_name).set(
                self._active_by_agent[task.agent_name]
            )

            return None

    def get_stats(self) -> dict:
        """
        Получить статистику очереди.

        Returns:
            dict со статистикой
        """
        # Обновляем метрики перед возвратом
        agent_queue_size.set(self._queue.qsize())

        return {
            **self._stats,
            'queue_size': self._queue.qsize(),
            'running': self._running,
            'active_by_agent': self._active_by_agent,
        }

    def get_history(self) -> list[AgentTask]:
        """
        Получить историю последних задач.

        Returns:
            Список задач из истории
        """
        return list(self._history)


class QueueFullError(Exception):
    """Исключение при переполнении очереди."""


# Глобальный экземпляр очереди (singleton)
# Поддерживает как локальную AgentTaskQueue, так и RedisTaskQueue
_agent_queue: Optional[AgentTaskQueue | 'RedisTaskQueue'] = None
_use_redis: bool = False


def get_agent_queue() -> AgentTaskQueue | 'RedisTaskQueue':
    """
    Получить глобальную очередь задач.

    Если настроен Redis (есть REDIS_URL в окружении), возвращает RedisTaskQueue.
    Иначе возвращает локальную AgentTaskQueue.

    Returns:
        AgentTaskQueue или RedisTaskQueue экземпляр
    """
    global _agent_queue, _use_redis

    if _agent_queue is not None:
        return _agent_queue

    # Проверяем наличие Redis URL в окружении
    import os
    redis_url = os.environ.get('REDIS_URL') or os.environ.get('REDIS_HOST')

    if redis_url:
        # Используем Redis
        from services.core.redis_queue import RedisTaskQueue

        if not redis_url.startswith('redis://'):
            redis_url = f'redis://{redis_url}:6379'

        _agent_queue = RedisTaskQueue(
            redis_url=redis_url,
            prefix='agent_queue',
            max_concurrency=2,  # 2 параллельные задачи для защиты Ollama
            max_queue_size=100,
            retry_delay=2.0,
        )
        _use_redis = True
        logger.info(f"✅ Используем Redis очередь: {redis_url}")
    else:
        # Используем локальную очередь
        _agent_queue = AgentTaskQueue(
            max_concurrency=2,  # 2 параллельные задачи для защиты Ollama
            max_queue_size=100,  # Максимум 100 задач в очереди
            retry_delay=2.0,  # 2 секунды между попытками
        )
        _use_redis = False
        logger.info("✅ Используем локальную очередь задач")

    return _agent_queue


def reset_agent_queue() -> None:
    """Сбросить глобальную очередь (для тестов)."""
    global _agent_queue, _use_redis
    _agent_queue = None
    _use_redis = False


async def start_agent_queue(num_workers: int = 2) -> None:
    """
    Запустить очередь задач.

    Для Redis очереди запускает воркеры.
    Для локальной очереди вызывает start().

    Args:
        num_workers: Количество воркеров (для Redis)
    """
    queue = get_agent_queue()

    if _use_redis and hasattr(queue, 'start'):
        await queue.start(num_workers=num_workers)
    elif hasattr(queue, 'start'):
        await queue.start()


async def stop_agent_queue() -> None:
    """Остановить очередь задач."""
    queue = get_agent_queue()

    if _use_redis and hasattr(queue, 'stop'):
        await queue.stop()
    elif hasattr(queue, 'stop'):
        await queue.stop()


def is_redis_queue() -> bool:
    """Проверить, используется ли Redis очередь."""
    get_agent_queue()  # Убеждаемся что очередь инициализирована
    return _use_redis
