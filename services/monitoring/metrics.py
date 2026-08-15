"""
Monitoring Metrics — метрики Prometheus для мониторинга системы.

Метрики:
- Counter: количество обработанных событий
- Gauge: размер очереди, количество задач
- Histogram: время обработки
"""

import logging
import time
from typing import Optional, Callable, Any
from functools import wraps

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Метрики
# =============================================================================

# Счётчики (Counter) — только увеличиваются
categorization_tasks_total = Counter(
    'categorization_tasks_total',
    'Total number of categorization tasks processed',
    labelnames=['status'],  # success, failed, advertisement
)

news_generation_total = Counter(
    'news_generation_total',
    'Total number of news generated',
    labelnames=['status', 'source'],  # success, failed / urgent, scheduled, trusted
)

telegram_messages_total = Counter(
    'telegram_messages_total',
    'Total number of Telegram messages sent',
    labelnames=['type', 'status'],  # notification, post / success, failed
)

api_requests_total = Counter(
    'api_requests_total',
    'Total number of API requests',
    labelnames=['endpoint', 'method', 'status_code'],
)

# Калибры (Gauge) — могут увеличиваться и уменьшаться
queue_size = Gauge(
    'queue_size',
    'Current size of processing queues',
    labelnames=['queue_name'],  # categorization, agent
)

active_tasks = Gauge(
    'active_tasks',
    'Number of currently active tasks',
    labelnames=['task_type'],  # categorization, news_generation, vector_search
)

database_connections = Gauge(
    'database_connections',
    'Number of active database connections',
)

vector_index_size = Gauge(
    'vector_index_size',
    'Number of vectors in each collection',
    labelnames=['collection'],  # events, news, posts
)

# Метрики для очереди AI агентов
agent_queue_size = Gauge(
    'agent_queue_size',
    'Current size of AI agent task queue',
)

agent_queue_active_tasks = Gauge(
    'agent_queue_active_tasks',
    'Number of currently active AI agent tasks',
    labelnames=['agent_name'],  # Categorizer, Analyst, Editor, Archivist
)

agent_tasks_total = Counter(
    'agent_tasks_total',
    'Total number of AI agent tasks processed',
    labelnames=['agent_name', 'status'],  # success, failed, retried
)

agent_task_duration = Histogram(
    'agent_task_duration_seconds',
    'Time spent on AI agent tasks',
    labelnames=['agent_name', 'method_name'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float('inf')),
)

agent_queue_pending_by_priority = Gauge(
    'agent_queue_pending_by_priority',
    'Number of pending tasks by priority',
    labelnames=['priority'],  # CRITICAL, HIGH, NORMAL, LOW
)

# Гистограммы (Histogram) — распределение величин
processing_duration = Histogram(
    'processing_duration_seconds',
    'Time spent processing tasks',
    labelnames=['task_type'],  # categorization, news_generation, vector_search
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

api_request_duration = Histogram(
    'api_request_duration_seconds',
    'Time spent on API requests',
    labelnames=['endpoint'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

llm_request_duration = Histogram(
    'llm_request_duration_seconds',
    'Time spent on LLM requests',
    labelnames=['agent', 'model'],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)


# =============================================================================
# Декораторы для автоматического сбора метрик
# =============================================================================

def track_duration(metric: Histogram, labels: Optional[dict] = None):
    """
    Декоратор для отслеживания времени выполнения функции.

    Args:
        metric: Histogram метрика
        labels: Дополнительные лейблы

    Usage:
        @track_duration(processing_duration, {'task_type': 'categorization'})
        async def process_task(self, task):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)

        return wrapper

    return decorator


def track_errors(counter: Counter, label_name: str, label_value: str):
    """
    Декоратор для отслеживания ошибок.

    Args:
        counter: Counter метрика
        label_name: Имя лейбла
        label_value: Значение лейбла

    Usage:
        @track_errors(categorization_tasks_total, 'status', 'failed')
        async def process_task(self, task):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                counter.labels(**{label_name: label_value}).inc()
                logger.error(f"Ошибка в {func.__name__}: {e}")
                raise

        return wrapper

    return decorator


# =============================================================================
# Утилиты
# =============================================================================

def get_metrics() -> bytes:
    """
    Получить текущие метрики в формате Prometheus.

    Returns:
        Байты с метриками
    """
    return generate_latest()


def get_metrics_content_type() -> str:
    """
    Получить Content-Type для метрик Prometheus.

    Returns:
        Content-Type строка
    """
    return CONTENT_TYPE_LATEST


def update_queue_size(queue_name: str, size: int) -> None:
    """
    Обновить размер очереди.

    Args:
        queue_name: Имя очереди
        size: Размер очереди
    """
    queue_size.labels(queue_name=queue_name).set(size)


def update_active_tasks(task_type: str, count: int) -> None:
    """
    Обновить количество активных задач.

    Args:
        task_type: Тип задачи
        count: Количество
    """
    active_tasks.labels(task_type=task_type).set(count)


def update_vector_index_stats(collection: str, count: int) -> None:
    """
    Обновить статистику векторного индекса.

    Args:
        collection: Имя коллекции
        count: Количество векторов
    """
    vector_index_size.labels(collection=collection).set(count)


def increment_categorization(status: str) -> None:
    """
    Увеличить счётчик категоризации.

    Args:
        status: Статус (success, failed, advertisement)
    """
    categorization_tasks_total.labels(status=status).inc()


def increment_news_generation(status: str, source: str) -> None:
    """
    Увеличить счётчик генерации новостей.

    Args:
        status: Статус (success, failed)
        source: Источник (urgent, scheduled, trusted)
    """
    news_generation_total.labels(status=status, source=source).inc()


def increment_telegram_messages(msg_type: str, status: str) -> None:
    """
    Увеличить счётчик Telegram сообщений.

    Args:
        msg_type: Тип сообщения (notification, post)
        status: Статус (success, failed)
    """
    telegram_messages_total.labels(type=msg_type, status=status).inc()


def track_llm_request(agent: str, model: str):
    """
    Контекстный менеджер для отслеживания LLM запросов.

    Args:
        agent: Имя агента
        model: Название модели

    Usage:
        with track_llm_request('categorizer', 'qwen2.5:7b'):
            response = await agent.send_question(text)
    """
    class _LLMTracker:
        def __enter__(self):
            self.start_time = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = time.time() - self.start_time
            llm_request_duration.labels(agent=agent, model=model).observe(duration)
            return False

    return _LLMTracker()


# =============================================================================
# Health checks
# =============================================================================

def get_health_status() -> dict[str, Any]:
    """
    Получить статус здоровья системы.

    Returns:
        Dict со статусом компонентов
    """
    return {
        'status': 'healthy',
        'timestamp': time.time(),
        'components': {
            'metrics': 'ok',
        },
    }
