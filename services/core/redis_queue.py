"""
RedisTaskQueue — распределённая очередь задач на базе Redis.

Обеспечивает:
- Распределённую очередь задач между несколькими воркерами
- Приоритетную обработку задач
- Ограничение параллелизма
- Retry logic с экспоненциальной задержкой
- Мониторинг состояния очереди
- Персистентность задач (сохранение в Redis)

Использует Redis sorted sets для приоритетной очереди и Redis hashes для хранения данных задач.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from typing import Any, Callable, Coroutine, Optional, TypeVar, Dict, List
from datetime import datetime

import redis.asyncio as redis

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


@dataclass
class AgentTask:
    """
    Задача для AI агента.

    Сериализуется в JSON для хранения в Redis.
    """
    task_id: str
    priority: int
    created_at: float
    agent_name: str
    method_name: str
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    max_retries: int = field(default=3)
    retry_count: int = field(default=0)
    status: int = field(default=TaskStatus.PENDING.value)
    result: Any = field(default=None)
    error: Optional[str] = field(default=None)
    callback: Optional[str] = field(default=None)  # Имя callback функции
    scheduled_at: Optional[float] = field(default=None)  # Время выполнения (для retry)

    def to_dict(self) -> dict:
        """Сериализовать в dict для JSON."""
        return {
            'task_id': self.task_id,
            'priority': self.priority,
            'created_at': self.created_at,
            'agent_name': self.agent_name,
            'method_name': self.method_name,
            'args': list(self.args) if self.args else [],
            'kwargs': self.kwargs or {},
            'max_retries': self.max_retries,
            'retry_count': self.retry_count,
            'status': self.status,
            'result': self.result,
            'error': self.error,
            'callback': self.callback,
            'scheduled_at': self.scheduled_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AgentTask':
        """Десериализовать из dict."""
        return cls(
            task_id=data['task_id'],
            priority=data['priority'],
            created_at=data['created_at'],
            agent_name=data['agent_name'],
            method_name=data['method_name'],
            args=tuple(data.get('args', [])),
            kwargs=data.get('kwargs', {}),
            max_retries=data.get('max_retries', 3),
            retry_count=data.get('retry_count', 0),
            status=data.get('status', TaskStatus.PENDING.value),
            result=data.get('result'),
            error=data.get('error'),
            callback=data.get('callback'),
            scheduled_at=data.get('scheduled_at'),
        )


class RedisTaskQueue:
    """
    Распределённая очередь задач на базе Redis.

    Использует:
    - Sorted set для приоритетной очереди (score = priority * 10^15 + timestamp)
    - Hash для хранения данных задач
    - Pub/Sub для уведомления воркеров о новых задачах

    Keys в Redis:
    - {prefix}:queue — sorted set с очередью задач
    - {prefix}:task:{task_id} — hash с данными задачи
    - {prefix}:stats — hash со статистикой
    - {prefix}:active:{agent_name} — счётчик активных задач по агентам
    - {prefix}:history — list с последними задачами

    Attributes:
        redis_url: URL подключения к Redis
        prefix: Префикс для ключей в Redis
        max_concurrency: Максимальное количество параллельных задач
        max_queue_size: Максимальный размер очереди
        retry_delay: Базовая задержка между попытками (секунды)
    """

    def __init__(
        self,
        redis_url: str = 'redis://localhost:6379',
        prefix: str = 'agent_queue',
        max_concurrency: int = 2,
        max_queue_size: int = 100,
        retry_delay: float = 2.0,
    ) -> None:
        """
        Инициализация очереди задач.

        Args:
            redis_url: URL подключения к Redis
            prefix: Префикс для ключей в Redis
            max_concurrency: Максимальное количество параллельных задач
            max_queue_size: Максимальный размер очереди
            retry_delay: Базовая задержка между попытками выполнения
        """
        self.redis_url = redis_url
        self.prefix = prefix
        self.max_concurrency = max_concurrency
        self.max_queue_size = max_queue_size
        self.retry_delay = retry_delay

        self._redis: Optional[redis.Redis] = None
        self._sem: Optional[asyncio.Semaphore] = None
        self._running = False
        self._stats = {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'retried': 0,
        }
        self._active_by_agent: dict[str, int] = {}
        self._worker_tasks: list[asyncio.Task] = []
        self._pubsub: Optional[redis.client.PubSub] = None
        self._method_registry: dict[str, Callable] = {}

    async def connect(self) -> None:
        """Подключиться к Redis."""
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                encoding='utf-8',
                decode_responses=True,
            )
            self._sem = asyncio.Semaphore(self.max_concurrency)
            logger.info(f"✅ Подключено к Redis: {self.redis_url}")

    async def disconnect(self) -> None:
        """Отключиться от Redis."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("✅ Отключено от Redis")

    def register_method(self, agent_name: str, method_name: str, method: Callable) -> None:
        """
        Зарегистрировать метод для вызова.

        Args:
            agent_name: Имя агента
            method_name: Имя метода
            method: Callable для вызова
        """
        key = f"{agent_name}:{method_name}"
        self._method_registry[key] = method
        logger.debug(f"📝 Зарегистрирован метод: {key}")

    async def start(self, num_workers: int = 2) -> None:
        """
        Запустить воркеры очереди.

        Args:
            num_workers: Количество воркеров
        """
        if self._running:
            logger.debug("🔄 Очередь уже запущена")
            return

        if self._redis is None:
            await self.connect()

        self._running = True

        # Запускаем воркеров
        for i in range(num_workers):
            task = asyncio.create_task(self._worker(i), name=f"redis_worker_{i}")
            self._worker_tasks.append(task)

        logger.info(f"🚀 RedisTaskQueue запущен (workers={num_workers}, concurrency={self.max_concurrency})")

    async def stop(self) -> None:
        """Остановить воркеры очереди."""
        if not self._running:
            return

        logger.info("🛑 Остановка RedisTaskQueue...")
        self._running = False

        # Отменяем воркеры
        for task in self._worker_tasks:
            task.cancel()

        # Ждём завершения
        results = await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, asyncio.CancelledError):
                logger.debug(f"✅ Воркер {i} остановлен")
            elif isinstance(result, Exception):
                logger.error(f"❌ Воркер {i} ошибка: {result}")

        self._worker_tasks.clear()

        # Отключаем pubsub
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None

        logger.info("✅ RedisTaskQueue остановлен")

    async def add_task(
        self,
        agent_name: str,
        method_name: str,
        method: Optional[Callable[..., Coroutine[Any, Any, T]]] = None,
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
            method: Метод для вызова (опционально, если зарегистрирован через register_method)
            *args: Позиционные аргументы метода
            priority: Приоритет задачи
            max_retries: Максимальное количество попыток
            callback: Callback для результата
            **kwargs: Именованные аргументы метода

        Returns:
            task_id: ID задачи

        Raises:
            QueueFullError: Если очередь заполнена
        """
        if self._redis is None:
            await self.connect()

        # Проверяем размер очереди
        queue_size = await self._redis.zcard(f"{self.prefix}:queue")
        if queue_size >= self.max_queue_size:
            logger.warning(f"⚠️ Очередь заполнена ({queue_size}/{self.max_queue_size})")
            if priority >= TaskPriority.NORMAL:
                raise QueueFullError(f"Очередь заполнена: {queue_size}/{self.max_queue_size}")

        task_id = f"{agent_name}_{uuid.uuid4().hex[:8]}_{int(time.time() * 1000)}"

        task = AgentTask(
            task_id=task_id,
            priority=priority.value,
            created_at=time.time(),
            agent_name=agent_name,
            method_name=method_name,
            args=args,
            kwargs=kwargs,
            max_retries=max_retries,
            callback=callback.__name__ if callback else None,
        )

        # Регистрируем метод если передан
        if method:
            self.register_method(agent_name, method_name, method)

        # Вычисляем score для sorted set (приоритет + timestamp)
        # Меньший score = выше приоритет
        score = priority.value * 10**15 + int(time.time() * 1000)

        # Сохраняем задачу в hash
        task_key = f"{self.prefix}:task:{task_id}"
        await self._redis.hset(task_key, mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in task.to_dict().items()})
        await self._redis.expire(task_key, 3600)  # TTL 1 час

        # Добавляем в sorted set
        await self._redis.zadd(f"{self.prefix}:queue", {task_id: score})

        # Обновляем статистику
        await self._redis.hincrby(f"{self.prefix}:stats", 'total', 1)
        self._stats['total'] += 1

        # Обновляем метрики
        agent_queue_size.set(queue_size + 1)
        agent_queue_pending_by_priority.labels(priority=priority.name).inc()

        # Публикуем событие о новой задаче (для уведомления воркеров)
        await self._redis.publish(f"{self.prefix}:new_task", task_id)

        logger.debug(
            f"📋 Задача добавлена: {task_id} "
            f"(agent={agent_name}, method={method_name}, priority={priority.name})"
        )

        return task_id

    async def _worker(self, worker_id: int) -> None:
        """
        Воркер очереди задач.

        Args:
            worker_id: ID воркера
        """
        logger.info(f"👷 Воркер {worker_id} запущен")

        # Подписываемся на уведомления о новых задачах
        if self._pubsub is None:
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(f"{self.prefix}:new_task")

        while self._running:
            try:
                # Получаем задачу из очереди
                task = await self._get_next_task()

                if task is None:
                    # Очередь пуста, ждём уведомления
                    try:
                        await asyncio.wait_for(self._wait_for_task(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    continue

                # Запускаем задачу
                asyncio.create_task(self._run_task(task, worker_id))

            except asyncio.CancelledError:
                logger.info(f"🛑 Воркер {worker_id} остановлен")
                raise
            except Exception as e:
                logger.error(f"❌ Воркер {worker_id} ошибка: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _get_next_task(self) -> Optional[AgentTask]:
        """
        Получить следующую задачу из очереди.

        Returns:
            Задача или None если очередь пуста
        """
        if self._redis is None:
            return None

        # Получаем задачу с наименьшим score (наивысший приоритет)
        # Проверяем задачи которые готовы к выполнению (scheduled_at <= now)
        now = time.time()
        results = await self._redis.zrangebyscore(
            f"{self.prefix}:queue",
            min=0,
            max=now * 10**15 + 10**15,  # Все задачи которые должны выполниться
            start=0,
            num=1,
            withscores=True,
        )

        if not results:
            return None

        task_id = results[0][0]

        # Удаляем из очереди
        await self._redis.zrem(f"{self.prefix}:queue", task_id)

        # Загружаем данные задачи
        task_key = f"{self.prefix}:task:{task_id}"
        task_data = await self._redis.hgetall(task_key)

        if not task_data:
            logger.warning(f"⚠️ Задача {task_id} не найдена в hash")
            return None

        # Парсим данные
        parsed_data = {}
        for k, v in task_data.items():
            try:
                parsed_data[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                parsed_data[k] = v

        task = AgentTask.from_dict(parsed_data)
        task.status = TaskStatus.PROCESSING.value

        # Сохраняем обновлённый статус
        await self._redis.hset(task_key, 'status', str(TaskStatus.PROCESSING.value))

        return task

    async def _wait_for_task(self) -> None:
        """Ждать уведомления о новой задаче."""
        if self._pubsub:
            message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if message and message['type'] == 'message':
                logger.debug(f"📬 Получено уведомление о задаче: {message['data']}")

    async def _run_task(self, task: AgentTask, worker_id: int) -> None:
        """
        Выполнить задачу с ограничением параллелизма.

        Args:
            task: Задача для выполнения
            worker_id: ID воркера
        """
        async with self._sem:
            await self._execute_task(task, worker_id)

    async def _execute_task(self, task: AgentTask, worker_id: int) -> None:
        """
        Выполнить задачу.

        Args:
            task: Задача
            worker_id: ID воркера
        """
        start_time = time.time()

        # Обновляем метрики активных задач
        self._active_by_agent[task.agent_name] = self._active_by_agent.get(task.agent_name, 0) + 1
        agent_queue_active_tasks.labels(agent_name=task.agent_name).set(
            self._active_by_agent[task.agent_name]
        )

        logger.debug(f"▶️ Задача {task.task_id} выполняется (worker={worker_id})")

        try:
            # Находим метод
            method_key = f"{task.agent_name}:{task.method_name}"
            method = self._method_registry.get(method_key)

            if method is None:
                raise ValueError(f"Метод не найден: {method_key}")

            # Извлекаем self и аргументы
            if len(task.args) < 1:
                raise ValueError(f"Нет аргументов для задачи {task.task_id} (ожидается self)")

            instance = task.args[0]
            method_args = task.args[1:] if len(task.args) > 1 else ()
            method_kwargs = task.kwargs

            # Вызываем метод
            result = await method(instance, *method_args, **method_kwargs)

            duration = time.time() - start_time

            task.status = TaskStatus.COMPLETED.value
            task.result = result

            # Сохраняем результат
            await self._save_task_result(task)

            # Обновляем статистику
            self._stats['completed'] += 1
            await self._redis.hincrby(f"{self.prefix}:stats", 'completed', 1)

            # Обновляем метрики
            agent_tasks_total.labels(agent_name=task.agent_name, status='success').inc()
            agent_task_duration.labels(
                agent_name=task.agent_name,
                method_name=task.method_name
            ).observe(duration)

            logger.debug(f"✅ Задача {task.task_id} выполнена за {duration:.2f}с")

            # Добавляем в историю
            await self._add_to_history(task)

        except Exception as e:
            duration = time.time() - start_time
            task.error = str(e)
            task.retry_count += 1

            # Проверяем, нужно ли повторять
            if task.retry_count < task.max_retries:
                task.status = TaskStatus.RETRY.value
                self._stats['retried'] += 1
                await self._redis.hincrby(f"{self.prefix}:stats", 'retried', 1)

                # Вычисляем задержку с экспоненциальным backoff
                delay = self.retry_delay * (2 ** task.retry_count)
                task.scheduled_at = time.time() + delay

                logger.warning(
                    f"⚠️ Задача {task.task_id} не выполнена (попытка {task.retry_count}/{task.max_retries}): {e}"
                )

                # Возвращаем в очередь с новым scheduled_at
                await self._requeue_task(task)

            else:
                task.status = TaskStatus.FAILED.value
                self._stats['failed'] += 1
                await self._redis.hincrby(f"{self.prefix}:stats", 'failed', 1)

                # Сохраняем результат
                await self._save_task_result(task)

                # Обновляем метрики
                agent_tasks_total.labels(agent_name=task.agent_name, status='failed').inc()
                agent_task_duration.labels(
                    agent_name=task.agent_name,
                    method_name=task.method_name
                ).observe(duration)

                logger.error(
                    f"❌ Задача {task.task_id} не выполнена после {task.max_retries} попыток: {e}",
                    exc_info=True
                )

                # Добавляем в историю
                await self._add_to_history(task)

        finally:
            # Уменьшаем счётчик активных задач
            self._active_by_agent[task.agent_name] = max(0, self._active_by_agent.get(task.agent_name, 0) - 1)
            agent_queue_active_tasks.labels(agent_name=task.agent_name).set(
                self._active_by_agent[task.agent_name]
            )

    async def _save_task_result(self, task: AgentTask) -> None:
        """Сохранить результат задачи в Redis."""
        if self._redis is None:
            return

        task_key = f"{self.prefix}:task:{task.task_id}"
        await self._redis.hset(task_key, mapping={
            'status': str(task.status),
            'result': json.dumps(task.result) if task.result is not None else '',
            'error': task.error or '',
        })

    async def _requeue_task(self, task: AgentTask) -> None:
        """
        Вернуть задачу в очередь для повторной попытки.

        Args:
            task: Задача для повторной очереди
        """
        if self._redis is None:
            return

        # Вычисляем новый score с учётом scheduled_at
        scheduled_at = task.scheduled_at or time.time()
        score = task.priority * 10**15 + int(scheduled_at * 1000)

        # Обновляем задачу в hash
        task_key = f"{self.prefix}:task:{task.task_id}"
        await self._redis.hset(task_key, mapping={
            'status': str(task.status),
            'retry_count': str(task.retry_count),
            'scheduled_at': str(task.scheduled_at),
            'error': task.error or '',
        })

        # Добавляем обратно в очередь
        await self._redis.zadd(f"{self.prefix}:queue", {task.task_id: score})

        logger.debug(f"🔄 Задача {task.task_id} возвращена в очередь (retry={task.retry_count})")

    async def _add_to_history(self, task: AgentTask) -> None:
        """
        Добавить задачу в историю.

        Args:
            task: Задача
        """
        if self._redis is None:
            return

        # Добавляем в list истории (храним последние 50 задач)
        history_key = f"{self.prefix}:history"
        await self._redis.lpush(history_key, json.dumps(task.to_dict()))
        await self._redis.ltrim(history_key, 0, 49)  # Храним только последние 50

    async def get_stats(self) -> dict:
        """
        Получить статистику очереди.

        Returns:
            dict со статистикой
        """
        if self._redis is None:
            return {**self._stats, 'queue_size': 0, 'running': self._running}

        queue_size = await self._redis.zcard(f"{self.prefix}:queue")
        stats = await self._redis.hgetall(f"{self.prefix}:stats")

        # Обновляем метрики
        agent_queue_size.set(queue_size)

        return {
            'total': int(stats.get('total', self._stats['total'])),
            'completed': int(stats.get('completed', self._stats['completed'])),
            'failed': int(stats.get('failed', self._stats['failed'])),
            'retried': int(stats.get('retried', self._stats['retried'])),
            'queue_size': queue_size,
            'running': self._running,
            'active_by_agent': self._active_by_agent,
        }

    async def get_history(self, limit: int = 50) -> list[AgentTask]:
        """
        Получить историю последних задач.

        Args:
            limit: Максимальное количество задач

        Returns:
            Список задач из истории
        """
        if self._redis is None:
            return []

        history_key = f"{self.prefix}:history"
        history = await self._redis.lrange(history_key, 0, limit - 1)

        tasks = []
        for item in history:
            try:
                data = json.loads(item)
                tasks.append(AgentTask.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                continue

        return tasks

    async def get_task(self, task_id: str) -> Optional[AgentTask]:
        """
        Получить задачу по ID.

        Args:
            task_id: ID задачи

        Returns:
            Задача или None
        """
        if self._redis is None:
            return None

        task_key = f"{self.prefix}:task:{task_id}"
        task_data = await self._redis.hgetall(task_key)

        if not task_data:
            return None

        # Парсим данные
        parsed_data = {}
        for k, v in task_data.items():
            try:
                parsed_data[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                parsed_data[k] = v

        return AgentTask.from_dict(parsed_data)

    async def clear(self) -> None:
        """Очистить очередь."""
        if self._redis is None:
            return

        # Удаляем все ключи с префиксом
        keys = await self._redis.keys(f"{self.prefix}:*")
        if keys:
            await self._redis.delete(*keys)

        logger.info(f"🧹 Очередь очищена")


class QueueFullError(Exception):
    """Исключение при переполнении очереди."""
    pass


# Глобальный экземпляр очереди (singleton)
_redis_queue: Optional[RedisTaskQueue] = None


def get_redis_queue() -> RedisTaskQueue:
    """
    Получить глобальную очередь задач.

    Returns:
        RedisTaskQueue экземпляр
    """
    global _redis_queue
    if _redis_queue is None:
        from config.settings import settings

        # Получаем Redis URL из настроек или используем default
        redis_url = getattr(settings, 'redis_url', 'redis://localhost:6379')

        _redis_queue = RedisTaskQueue(
            redis_url=redis_url,
            prefix='agent_queue',
            max_concurrency=5,
            max_queue_size=100,
            retry_delay=2.0,
        )

    return _redis_queue


def reset_redis_queue() -> None:
    """Сбросить глобальную очередь (для тестов)."""
    global _redis_queue
    _redis_queue = None
