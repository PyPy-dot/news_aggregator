"""
NewsSaver — сохранение результатов категоризации в БД.

Инкапсулирует логику сохранения постов, событий и обновления рейтингов.
"""

import logging

from database.repositories.channels import ChannelRepository
from database.repositories.posts import PostRepository
from database.repositories.events import EventRepository
from services.categorization.classifier import ClassificationResult

logger = logging.getLogger(__name__)


class NewsSaver:
    """
    Сервис для сохранения результатов категоризации.

    Attributes:
        posts_repo: Репозиторий постов
        channels_repo: Репозиторий каналов
        events_repo: Репозиторий событий
    """

    def __init__(
        self,
        posts_repo: PostRepository,
        channels_repo: ChannelRepository,
        events_repo: EventRepository,
    ) -> None:
        """
        Инициализация сервиса.

        Args:
            posts_repo: Репозиторий постов
            channels_repo: Репозиторий каналов
            events_repo: Репозиторий событий
        """
        self.posts_repo = posts_repo
        self.channels_repo = channels_repo
        self.events_repo = events_repo

    async def save_urgent_news(
        self,
        channel_id: int,
        classification: ClassificationResult,
    ) -> int:
        """
        Сохранить срочную новость.

        Args:
            channel_id: ID канала
            classification: Результат классификации

        Returns:
            ID сохранённого поста
        """
        # Получаем канал для расчёта рейтинга
        channel = await self.channels_repo.get_by_telegram_id(channel_id)

        # Рассчитываем рейтинг новости
        rate = self._calculate_news_rate(channel, classification.urgency)

        # Сохраняем пост
        post = await self.posts_repo.create_post(
            channel_id=channel_id,
            text=classification.text,
            category=classification.category,
            urgency=classification.urgency,
            rate=rate,
            source_trust_rating=channel.trust_rating if channel else 0.5,
            tags='',
        )

        # Обновляем рейтинг канала
        if channel:
            await self.channels_repo.update_trust_rating(channel_id)

        logger.info(
            f"✅ СРОЧНАЯ новость сохранена: {classification.category}, "
            f"срочность {classification.urgency}, рейтинг {rate}, "
            f"пост ID={post.id}"
        )

        return post.id

    async def save_scheduled_news(
        self,
        channel_id: int,
        classification: ClassificationResult,
    ) -> tuple[int, int]:
        """
        Сохранить несрочную новость для планировщика.

        Args:
            channel_id: ID канала
            classification: Результат классификации

        Returns:
            Tuple[ID поста, ID события]
        """
        # Получаем канал
        channel = await self.channels_repo.get_by_telegram_id(channel_id)

        # Рассчитываем рейтинг
        rate = self._calculate_news_rate(channel, classification.urgency)

        # Сохраняем пост
        post = await self.posts_repo.create_post(
            channel_id=channel_id,
            text=classification.text,
            category=classification.category,
            urgency=classification.urgency,
            rate=rate,
            source_trust_rating=channel.trust_rating if channel else 0.5,
            tags='',
        )

        # Обновляем рейтинг канала
        if channel:
            await self.channels_repo.update_trust_rating(channel_id)

        # Создаём контекст события для планировщика
        context_data = self._create_initial_context(classification)
        event = await self.events_repo.create_event(
            post_id=post.id,
            context_data=context_data,
            event_category=classification.category,
            tags=[],
        )

        logger.info(
            f"📝 В план: Срочность {classification.urgency}, "
            f"категория {classification.category}, "
            f"пост ID={post.id}, событие ID={event.id}"
        )

        return post.id, event.id

    def _calculate_news_rate(self, channel, urgency: int) -> int:
        """
        Рассчитать рейтинг новости.

        Args:
            channel: Объект канала (может быть None)
            urgency: Срочность (1-5)

        Returns:
            Рейтинг новости (0-100)
        """
        if channel is None:
            return 50

        # Базовый рейтинг от доверия канала (0-50)
        trust_component = int(channel.trust_rating * 50)

        # Компонент срочности (0-50)
        urgency_component = int((urgency / 5) * 50)

        return trust_component + urgency_component

    def _create_initial_context(self, classification: ClassificationResult) -> dict:
        """
        Создать начальный контекст события.

        Args:
            classification: Результат классификации

        Returns:
            Dict с данными контекста
        """
        return {
            'event_description': classification.text[:200],
            'participants': [],
            'location': None,
            'timestamp': None,
            'cause': None,
            'consequences': [],
            'related_topics': [classification.category],
            'key_facts': []
        }
