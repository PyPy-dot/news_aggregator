"""
Стратегия обработки новостей от доверенных источников.
"""

import logging
from typing import Any

from services.news.strategies.base import NewsProcessingStrategy
from database.repositories.posts import PostRepository

logger = logging.getLogger(__name__)


class TrustedSourceStrategy(NewsProcessingStrategy):
    """
    Стратегия для доверенных источников.

    Публикует новость напрямую без модерации и АРА.
    """

    @property
    def name(self) -> str:
        return 'trusted'

    async def process(self, post_id: int, **kwargs: Any) -> None:
        """
        Обработать новость от доверенного источника.

        Args:
            post_id: ID поста
            **kwargs: channel_id, text, category
        """
        channel_id = kwargs.get('channel_id')
        text = kwargs.get('text', '')
        category = kwargs.get('category', '')

        logger.info(f"✅ ДОВЕРЕННЫЙ ИСТОЧНИК! Публикация без модерации (пост ID={post_id})")

        # Получаем пост для отправки подписчикам
        post = await self.posts_repo.get(post_id)

        # Получаем активные каналы публикации с matching категорией
        publishers = await self.publishers_repo.get_all(active_only=True)

        matching_publishers = [
            pub for pub in publishers
            if pub.category and pub.category.lower() == category.lower()
        ] if category else publishers

        published_count = 0

        if matching_publishers:
            # Публикуем в каналы через PublisherService
            from services.bot.bot import get_bot_instance_async
            from services.bot.handlers.publisher import PublisherService

            bot = await get_bot_instance_async(wait=True, timeout=10.0)
            if bot:
                publisher_service = PublisherService(bot)

                for pub in matching_publishers:
                    try:
                        published = await publisher_service.publish_to_channel(
                            channel_id=pub.channel_id,
                            text=text
                        )

                        if published:
                            logger.info(f"  ✅ Опубликовано в канал '{pub.title}' (ID={pub.id})")
                            published_count += 1
                            # Помечаем пост как опубликованный в этот канал
                            await self.posts_repo.mark_direct_publish(
                                post_id=post_id,
                                publisher_channel_id=pub.id
                            )
                        else:
                            logger.error(
                                f"  ❌ Не удалось опубликовать в канал '{pub.title}' (ID={pub.id})"
                            )

                    except Exception as e:
                        logger.error(
                            f"  ❌ Ошибка публикации в канал '{pub.title}' (ID={pub.id}): {e}"
                        )
            else:
                logger.warning("⚠️ Бот не инициализирован, публикация в каналы невозможна")
        else:
            logger.info(
                f"⚠️ Нет каналов с категорией '{category}'. "
                f"Новость будет отправлена только подписчикам."
            )

        # Отправляем подписчикам (доверенные источники обычно срочные, urgency=post.urgency)
        if published_count > 0 or not matching_publishers:
            await self._notify_subscribers(
                text=text,
                category=category,
                tags=[],
                news_id=post_id,
                urgency=post.urgency if post else 4,  # Доверенные источники обычно срочные
            )

        logger.info(
            f"🚀 Пост ID={post_id} опубликован напрямую "
            f"в {published_count} канал(а/ов)"
        )

    async def _notify_subscribers(
        self,
        text: str,
        category: str,
        tags: list,
        news_id: int,
        urgency: int = 4,
    ):
        """
        Отправить новость подписчикам.

        Args:
            urgency: Срочность (1-5, >=4 — срочная новость)
        """
        try:
            from services.telegram.notification import NotificationService
            from services.bot.bot import get_bot_instance_async

            # Получаем бота из глобальной ссылки
            bot = await get_bot_instance_async(wait=True, timeout=10.0)

            # Создаём NotificationService с ботом
            notification_service = NotificationService(bot=bot)

            sent_count = await notification_service.notify_subscribers(
                news_text=text,
                category=category,
                tags=tags,
                news_id=news_id,
                urgency=urgency,
            )

            if sent_count > 0:
                logger.info(f"📬 Отправлено {sent_count} уведомлений подписчикам")
            else:
                logger.info("ℹ️ Нет подписчиков для отправки")

        except Exception as e:
            logger.error(f"❌ Ошибка отправки новости подписчикам: {e}")
