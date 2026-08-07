"""
Categorization Service — управление очередью категоризации новостей.

Изолирует логику очереди от ListenerBot, обеспечивая:
- Очередь задач на категоризацию
- Обработку AI-ответов
- Фильтрацию рекламы
- Сохранение постов в БД

Корректное управление жизненным циклом обработки очереди.
"""

import asyncio
import logging
from collections import deque
from typing import Optional, Dict, Any

from config.settings import settings
from database import RepositoryFactory
from database.repositories.channels import ChannelRepository
from services.core.database import get_database_service
from services.ai_agent.agents import CategorizerAgent
from services.listener.helpers import (
    get_channel_full,
    add_tg_post,
    update_channel_trust_rating,
    calculate_news_rate,
    add_event_context,
)
from services.telegram.notification import NotificationService

logger = logging.getLogger(__name__)


class CategorizationTask:
    """Задача на категоризацию."""

    def __init__(
        self,
        channel_id: int,
        prompt: str,
        original_text: str,
        title: str = '',
        desc: str = ''
    ):
        self.channel_id = channel_id
        self.prompt = prompt
        self.original_text = original_text
        self.title = title
        self.desc = desc


class CategorizationService:
    """
    Сервис для управления очередью категоризации.

    Attributes:
        categorizer: AI-агент для категоризации
        queue: Очередь задач
        max_queue_size: Максимальный размер очереди
        notification_service: Сервис уведомлений
    """

    def __init__(
        self,
        model: Optional[str] = None,
        notification_service: Optional[NotificationService] = None
    ) -> None:
        """
        Инициализация сервиса категоризации.

        Args:
            model: Модель для использования (по умолчанию из конфига)
            notification_service: Сервис уведомлений
        """
        self.categorizer = CategorizerAgent(model=model or settings.agent_model)
        self.queue: deque[CategorizationTask] = deque(
            maxlen=settings.categorization_queue_maxlen
        )
        self._lock = asyncio.Lock()
        self._running = False
        self._processing_task: Optional[asyncio.Task] = None
        self.notification_service = notification_service or NotificationService()

    async def add_task(self, task: CategorizationTask) -> None:
        """
        Добавить задачу в очередь.

        Args:
            task: Задача на категоризацию
        """
        async with self._lock:
            self.queue.append(task)
            logger.debug(
                f"📊 Добавлена задача категоризации. "
                f"В очереди: {len(self.queue)} задач"
            )

    async def process_queue(self) -> None:
        """
        Обрабатывать очередь категоризации.

        Запускается как фоновая задача.
        Блокирует до остановки или отмены.
        """
        self._running = True
        logger.info("🔄 Запущена обработка очереди категоризации")

        try:
            while self._running:
                if not self.queue:
                    await asyncio.sleep(0.5)
                    continue

                # Берём задачу из очереди
                async with self._lock:
                    if not self.queue:
                        continue
                    task = self.queue.popleft()

                try:
                    await self._process_task(task)
                except Exception as e:
                    logger.error(f"Ошибка обработки задачи категоризации: {e}")

        except asyncio.CancelledError:
            logger.info("🛑 Обработка очереди категоризации отменена")
            raise
        finally:
            self._running = False
            logger.info("🛑 Обработка очереди категоризации остановлена")

    async def _process_task(self, task: CategorizationTask) -> None:
        """
        Обработать одну задачу категоризации.

        Args:
            task: Задача на категоризацию
        """
        try:
            # Отправляем в AI-категорайзер
            ai_response = await self.categorizer.send_question(task.prompt)
            parsed = self._parse_ai_response(ai_response)

            if parsed['category'] == 'Реклама':
                logger.info(f"🚫 Пропущено (реклама): канал ID={task.channel_id}")
                return

            # Проверяем срочность
            urgency = int(parsed.get('urgency', 1))

            if urgency >= 4:
                # Срочная новость (4-5) — особая обработка
                await self._handle_urgent_news(task, parsed, urgency)
            else:
                # Несрочная новость (1-3) — отправляется планировщику
                await self._handle_scheduled_news(task, parsed, urgency)

        except Exception as e:
            logger.error(f"Ошибка обработки задачи: {e}")
            raise

    async def _handle_urgent_news(
        self,
        task: CategorizationTask,
        parsed: Dict[str, Any],
        urgency: int
    ) -> None:
        """
        Обработать срочную новость.

        Args:
            task: Задача на категоризацию
            parsed: Распарсенный ответ AI
            urgency: Уровень срочности
        """
        logger.info(f"⚡ СРОЧНО! Срочность {urgency}, категория {parsed['category']}")

        # Получаем канал для проверки is_trusted
        channel = await get_channel_full(task.channel_id)
        channel_title = channel.title if channel else 'Неизвестно'

        # Сохраняем пост
        post_id = await add_tg_post(
            channel_id=task.channel_id,
            text=parsed['text'],
            category=parsed['category'],
            urgency=urgency
        )

        # Обновляем рейтинг канала
        if channel:
            await update_channel_trust_rating(task.channel_id)

        rate = await calculate_news_rate(channel, urgency) if channel else 50

        logger.info(
            f"✅ СРОЧНАЯ новость сохранена: {parsed['category']}, "
            f"срочность {urgency}, рейтинг {rate}"
        )

        # Проверяем: доверенный источник?
        if channel and channel.is_trusted:
            logger.info(
                f"✅ ДОВЕРЕННЫЙ ИСТОЧНИК! Публикация без модерации "
                f"(помечаем пост ID={post_id})"
            )
            # Доверенные источники не требуют уведомления — публикуются сразу
        else:
            logger.info(f"📬 Отправка админу уведомления о срочной модерации")
            # Отправляем уведомление админам только для срочных новостей
            if self.notification_service:
                await self.notification_service.notify_urgent_news(
                    post_id=post_id,
                    text=parsed['text'],
                    category=parsed['category'],
                    urgency=urgency,
                    channel_title=channel_title
                )

    async def _handle_scheduled_news(
        self,
        task: CategorizationTask,
        parsed: Dict[str, Any],
        urgency: int
    ) -> None:
        """
        Обработать несрочную новость (для планировщика).

        Args:
            task: Задача на категоризацию
            parsed: Распарсенный ответ AI
            urgency: Уровень срочности
        """
        logger.info(
            f"📊 В план: Срочность {urgency}, категория {parsed['category']}"
        )

        # Сохраняем пост
        channel = await get_channel_full(task.channel_id)
        post_id = await add_tg_post(
            channel_id=task.channel_id,
            text=parsed['text'],
            category=parsed['category'],
            urgency=urgency
        )

        # Обновляем рейтинг канала
        if channel:
            await update_channel_trust_rating(task.channel_id)

        # Создаём контекст события (для планировщика)
        context_data = {
            'event_description': parsed['text'][:200],
            'participants': [],
            'location': None,
            'timestamp': None,
            'cause': None,
            'consequences': [],
            'related_topics': [parsed['category']],
            'key_facts': []
        }

        event_id = await add_event_context(
            post_id=post_id,
            context_data=context_data,
            event_category=parsed['category'],
            tags=[],
            summary=parsed['text'][:100]
        )

        logger.info(f"📝 Событие ID={event_id} создано (ожидает планировщика)")

    def _parse_ai_response(self, response: str) -> Dict[str, Any]:
        """
        Парсит ответ от AI, извлекая JSON.

        Args:
            response: Строка с ответом

        Returns:
            dict: {text, category, urgency}
        """
        import re
        import json

        cleaned = response.strip()
        cleaned = re.sub(r'^```json\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()
        cleaned = re.sub(r'^json\s*\n', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        json_match = re.search(
            r'\{[^{}]*"text"[^{}]*"category"[^{}]*"urgency"[^{}]*\}',
            cleaned,
            re.DOTALL
        )
        if json_match:
            cleaned = json_match.group()

        try:
            parsed = json.loads(cleaned)
            return {
                'text': parsed.get('text', ''),
                'category': parsed.get('category', 'Другое'),
                'urgency': min(5, max(1, int(parsed.get('urgency', 1))))
            }
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}\nОтвет AI: {response}")
            return {
                'text': response[:500],
                'category': 'Другое',
                'urgency': 1
            }

    def stop(self) -> None:
        """
        Остановить обработку очереди.

        Устанавливает флаг остановки. Задача process_queue завершится
        на следующей проверке условия цикла.
        """
        logger.info("🛑 Получен сигнал остановки очереди категоризации")
        self._running = False
