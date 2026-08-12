"""
Monitoring module — мониторинг и метрики системы.

Использует Prometheus client для сбора метрик:
- Counter: счётчики событий
- Gauge: текущие значения (размер очереди, задачи)
- Histogram: распределение времени обработки

Экспорт метрик: /metrics endpoint (текстовый формат Prometheus)
"""

from services.monitoring.metrics import (
    # Метрики
    categorization_tasks_total,
    news_generation_total,
    telegram_messages_total,
    api_requests_total,
    queue_size,
    active_tasks,
    database_connections,
    vector_index_size,
    processing_duration,
    api_request_duration,
    llm_request_duration,
    # Декораторы
    track_duration,
    track_errors,
    # Утилиты
    get_metrics,
    get_metrics_content_type,
    update_queue_size,
    update_active_tasks,
    update_vector_index_stats,
    increment_categorization,
    increment_news_generation,
    increment_telegram_messages,
    track_llm_request,
    get_health_status,
)

__all__ = [
    # Метрики
    'categorization_tasks_total',
    'news_generation_total',
    'telegram_messages_total',
    'api_requests_total',
    'queue_size',
    'active_tasks',
    'database_connections',
    'vector_index_size',
    'processing_duration',
    'api_request_duration',
    'llm_request_duration',
    # Декораторы
    'track_duration',
    'track_errors',
    # Утилиты
    'get_metrics',
    'get_metrics_content_type',
    'update_queue_size',
    'update_active_tasks',
    'update_vector_index_stats',
    'increment_categorization',
    'increment_news_generation',
    'increment_telegram_messages',
    'track_llm_request',
    'get_health_status',
]
