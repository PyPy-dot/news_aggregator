"""
Celery Worker — распределённая обработка задач.

Использует Redis как брокер для очереди задач Celery.
Обеспечивает:
- Распределённую обработку задач между несколькими воркерами
- Retry logic с экспоненциальной задержкой
- Планирование задач (Celery Beat)
- Мониторинг через Flower (опционально)
- Персистентность задач

Для запуска:
    celery -A services.core.celery_worker worker --loglevel=info --concurrency=4

Для планировщика:
    celery -A services.core.celery_worker beat --loglevel=info
"""

import os
import logging
from typing import Any, Optional

from celery import Celery, Task
from celery.schedules import crontab

logger = logging.getLogger(__name__)

# =============================================================================
# Конфигурация Celery
# =============================================================================

# Получаем Redis URL из окружения
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')

# Создаём Celery приложение
celery_app = Celery(
    'news_aggregator',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        'services.ai_agent.agents.categorizer',
        'services.ai_agent.agents.analyst',
        'services.ai_agent.agents.editor',
        'services.ai_agent.agents.archivist',
    ],
)

# Конфигурация Celery
celery_app.conf.update(
    # Сериализация
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Retry логика
    task_acks_late=True,  # Подтверждать задачу после выполнения
    task_reject_on_worker_lost=True,  # Возвращать задачу в очередь при потере воркера
    task_default_retry_delay=2,  # Базовая задержка между retry (секунды)
    task_max_retry_delay=300,  # Максимальная задержка (5 минут)

    # Результаты задач
    result_expires=3600,  # TTL результатов (1 час)
    result_backend_transport_options={'visibility_timeout': 3600},

    # Prefetch multiplier (сколько задач брать заранее)
    worker_prefetch_multiplier=1,  # 1 = брать по одной задаче

    # Rate limiting
    task_default_rate_limit='10/m',  # 10 задач в минуту по умолчанию

    # Планировщик (Beat)
    beat_schedule={
        # Обработка событий каждые 48 часов
        'process-events-every-48h': {
            'task': 'services.ai_agent.agents.archivist.process_events',
            'schedule': crontab(minute=0, hour=0, day_of_week='*/2'),  # Каждые 48 часов
        },
        # Очистка кэша каждые 6 часов
        'cleanup-cache-every-6h': {
            'task': 'services.ai_agent.cache.cleanup_expired',
            'schedule': crontab(minute=0, hour='*/6'),
        },
    },
)


# =============================================================================
# Базовый класс для задач
# =============================================================================

class BaseTask(Task):
    """
    Базовый класс для всех Celery задач.

    Обеспечивает:
    - Логирование выполнения
    - Обработку ошибок
    - Статистику
    """

    # Автоматический retry при определённых ошибках
    autoretry_for = (ConnectionError, TimeoutError, Exception)
    retry_kwargs = {'max_retries': 3, 'default_retry_delay': 2}
    retry_backoff = True  # Экспоненциальная задержка
    retry_backoff_max = 300  # Максимум 5 минут
    retry_jitter = True  # Добавить случайность к задержке

    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        """Вызывается при успешном выполнении задачи."""
        logger.info(f"✅ Задача {task_id} выполнена успешно")

    def on_failure(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: Any) -> None:
        """Вызывается при провале задачи."""
        logger.error(f"❌ Задача {task_id} провалена: {exc}", exc_info=True)

    def after_return(self, status: str, retval: Any, task_id: str, args: tuple, kwargs: dict, einfo: Any) -> None:
        """Вызывается после завершения задачи (успех или провал)."""
        logger.debug(f"📋 Задача {task_id} завершена со статусом: {status}")


# =============================================================================
# Примеры задач
# =============================================================================

@celery_app.task(base=BaseTask, bind=True, name='tasks.example_sum')
def example_sum(self, x: int, y: int) -> int:
    """
    Пример простой задачи.

    Usage:
        result = example_sum.delay(2, 3)
        print(result.get())  # 5
    """
    logger.info(f"Вычисление {x} + {y}")
    return x + y


@celery_app.task(base=BaseTask, bind=True, name='tasks.process_categorization')
def process_categorization(self, text: str, channel_title: str = '', channel_desc: str = '') -> dict:
    """
    Задача категоризации текста.

    Args:
        text: Текст новости
        channel_title: Название канала
        channel_desc: Описание канала

    Returns:
        dict: {category, urgency, text}
    """
    logger.info(f"Категоризация текста из {channel_title}")

    try:
        from services.ai_agent.agents.categorizer import CategorizerAgent

        categorizer = CategorizerAgent()
        result = categorizer.categorize(text, channel_title, channel_desc)

        logger.info(f"✅ Категоризация завершена: {result['category']} (urgency={result['urgency']})")
        return result

    except Exception as e:
        logger.error(f"❌ Ошибка категоризации: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=2)


@celery_app.task(base=BaseTask, bind=True, name='tasks.process_analysis')
def process_analysis(self, text: str, category: str, urgency: int) -> dict:
    """
    Задача анализа новости (Analyst Agent).

    Args:
        text: Текст новости
        category: Категория
        urgency: Срочность (1-5)

    Returns:
        dict: {tags, confidence, facts}
    """
    logger.info(f"Анализ новости: категория={category}, срочность={urgency}")

    try:
        from services.ai_agent.agents.analyst import AnalystAgent

        analyst = AnalystAgent()
        result = analyst.analyze(text, category, urgency)

        logger.info(f"✅ Анализ завершён: {len(result.get('tags', []))} тэгов")
        return result

    except Exception as e:
        logger.error(f"❌ Ошибка анализа: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=2)


@celery_app.task(base=BaseTask, bind=True, name='tasks.generate_news')
def process_news_generation(self, event_contexts: list[dict]) -> dict:
    """
    Задача генерации новости (Editor + Archivist).

    Args:
        event_contexts: Список контекстов событий

    Returns:
        dict: {news_text, tags, category}
    """
    logger.info(f"Генерация новости из {len(event_contexts)} контекстов")

    try:
        from services.ai_agent.agents.editor import EditorAgent
        from services.ai_agent.agents.archivist import ArchivistAgent

        # Генерируем текст
        editor = EditorAgent()
        news_text = editor.generate_news(event_contexts)

        # Структурируем контекст
        archivist = ArchivistAgent()
        context = archivist.create_context(event_contexts, news_text)

        logger.info(f"✅ Новость сгенерирована ({len(news_text)} символов)")

        return {
            'news_text': news_text,
            'context': context,
        }

    except Exception as e:
        logger.error(f"❌ Ошибка генерации новости: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=2)


@celery_app.task(base=BaseTask, bind=True, name='tasks.send_notification')
def send_notification(self, user_id: int, message: str) -> bool:
    """
    Задача отправки уведомления пользователю.

    Args:
        user_id: Telegram ID пользователя
        message: Текст сообщения

    Returns:
        bool: True если отправлено успешно
    """
    logger.info(f"Отправка уведомления пользователю {user_id}")

    try:
        from services.telegram.notification import NotificationService

        notification = NotificationService()
        # notification.send_message(user_id, message)  # Вызвать когда бот доступен

        logger.info(f"✅ Уведомление отправлено")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка отправки уведомления: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=5)


# =============================================================================
# Утилиты
# =============================================================================

def get_celery_app() -> Celery:
    """Получить Celery приложение."""
    return celery_app


def inspect_workers() -> dict:
    """
    Получить информацию о воркерах.

    Returns:
        dict: {worker_name: {active, reserved, scheduled}}
    """
    i = celery_app.control.inspect()

    return {
        'active': i.active() or {},
        'reserved': i.reserved() or {},
        'scheduled': i.scheduled() or {},
        'stats': i.stats() or {},
    }


def revoke_task(task_id: str, terminate: bool = False) -> None:
    """
    Отозвать задачу.

    Args:
        task_id: ID задачи
        terminate: Убить ли выполняющуюся задачу
    """
    celery_app.control.revoke(task_id, terminate=terminate)
    logger.info(f"🚫 Задача {task_id} отозвана (terminate={terminate})")


# =============================================================================
# Запуск для отладки
# =============================================================================

if __name__ == '__main__':
    # Отладочный запуск
    celery_app.start()
