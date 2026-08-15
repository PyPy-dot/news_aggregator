"""
Moderation Notification Service — уведомления о модерации новостей.

Инкапсулирует логику отправки уведомлений админам.
"""

import logging

from database.repositories.posts import PostRepository
from database.repositories.channels import ChannelRepository
from services.telegram.notification import NotificationService

logger = logging.getLogger(__name__)


class ModerationNotificationService:
    """
    Сервис для уведомлений о модерации новостей.

    Предоставляет методы для:
    - Уведомления о срочной новости на модерации
    - Уведомления о плановой новости на модерации
    - Уведомления о прямой публикации (доверенный источник)

    Attributes:
        notification_service: Сервис уведомлений
        posts_repo: Репозиторий постов
        channels_repo: Репозиторий каналов
    """

    def __init__(
        self,
        notification_service: NotificationService,
        posts_repo: PostRepository,
        channels_repo: ChannelRepository,
    ) -> None:
        """
        Инициализация сервиса.

        Args:
            notification_service: Сервис уведомлений
            posts_repo: Репозиторий постов
            channels_repo: Репозиторий каналов
        """
        self.notification_service = notification_service
        self.posts_repo = posts_repo
        self.channels_repo = channels_repo

    async def notify_urgent_news(
        self,
        post_id: int,
        text: str,
        category: str,
        urgency: int,
    ) -> None:
        """
        Уведомить о срочной новости на модерации.

        Args:
            post_id: ID поста
            text: Текст новости
            category: Категория
            urgency: Срочность (4-5)
        """
        try:
            # Получаем информацию о канале
            channel_title = await self._get_channel_title(post_id)

            await self.notification_service.notify_urgent_news(
                post_id=post_id,
                text=text,
                category=category,
                urgency=urgency,
                channel_title=channel_title,
            )

            logger.info(
                f"📬 Отправлено уведомление о срочной новости ID={post_id}"
            )

        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

    async def notify_pending_news(
        self,
        news_id: int,
        post_id: int,
        text: str,
        category: str,
    ) -> None:
        """
        Уведомить о новости на плановой модерации.

        Args:
            news_id: ID сгенерированной новости
            post_id: ID оригинального поста
            text: Текст новости
            category: Категория
        """
        try:
            # Получаем информацию о канале
            channel_title = await self._get_channel_title(post_id)

            await self.notification_service.notify_pending_news(
                post_id=news_id,
                text=text[:500],
                category=category,
                channel_title=channel_title,
            )

            logger.info(
                f"📬 Отправлено уведомление о новости на модерации ID={news_id}"
            )

        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

    async def notify_direct_publish(
        self,
        post_id: int,
        category: str,
        text: str,
    ) -> None:
        """
        Уведомить о прямой публикации (доверенный источник).

        Args:
            post_id: ID поста
            category: Категория
            text: Текст поста
        """
        try:
            # Получаем информацию о канале
            channel_title = await self._get_channel_title(post_id)

            await self.notification_service.notify_direct_publish(
                post_id=post_id,
                channel_title=channel_title,
                category=category,
                text=text,
            )

            logger.info(
                f"🚀 Отправлено уведомление о прямой публикации ID={post_id}"
            )

        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

    async def _get_channel_title(self, post_id: int) -> str:
        """
        Получить название канала для поста.

        Args:
            post_id: ID поста

        Returns:
            Название канала или fallback строку
        """
        try:
            post = await self.posts_repo.get(post_id)
            if post:
                channel = await self.channels_repo.get_by_telegram_id(
                    post.channel_id
                )
                return channel.title if channel else f"Post ID={post_id}"
        except Exception as e:
            logger.warning(f"Не удалось получить информацию о канале: {e}")

        return f"Post ID={post_id}"
