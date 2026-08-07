"""
Notification Service — уведомления админов о новых новостях.

Изолирует логику уведомлений от ListenerBot и других компонентов.
Корректная работа с глобальным экземпляром бота.
"""

import logging
from typing import Optional, List

from database.repositories.users import UserRepository
from services.core.database import get_database_service
from services.util import decrypt_user_id

logger = logging.getLogger(__name__)


# Глобальная переменная для хранения бота
_bot_instance = None


def set_global_bot(bot) -> None:
    """
    Установить глобальный экземпляр бота для уведомлений.

    Args:
        bot: aiogram Bot экземпляр или None для очистки
    """
    global _bot_instance
    _bot_instance = bot
    if bot is None:
        logger.debug("🔌 Global bot instance cleared")
    else:
        logger.debug("✅ Global bot instance set")


def get_global_bot():
    """
    Получить глобальный экземпляр бота.

    Returns:
        aiogram Bot экземпляр или None
    """
    return _bot_instance


class NotificationService:
    """
    Сервис для отправки уведомлений админам.

    Отправляет уведомления всем администраторам в БД через Telegram бота.
    """

    def __init__(self) -> None:
        """Инициализация сервиса уведомлений."""
        pass

    @property
    def bot(self):
        """Получить бота из глобального контекста."""
        return get_global_bot()

    async def _get_admin_ids(self) -> List[int]:
        """
        Получить Telegram ID всех администраторов.

        Returns:
            Список Telegram ID админов
        """
        db_service = get_database_service()
        async with db_service.session_context() as session:
            user_repo = UserRepository(session)
            # Получаем всех пользователей (в реале можно добавить фильтр по роли)
            from sqlalchemy import select
            from database.models import User
            result = await session.execute(
                select(User).where(User.role == 'admin')
            )
            admins = result.scalars().all()

        # Расшифровываем ID админов
        admin_ids = []
        for admin in admins:
            try:
                telegram_id = decrypt_user_id(admin.user_id_encrypted)
                admin_ids.append(telegram_id)
            except Exception as e:
                logger.error(f"❌ Ошибка расшифровки admin ID: {e}")

        return admin_ids

    async def notify_urgent_news(
        self,
        post_id: int,
        text: str,
        category: str,
        urgency: int,
        channel_title: str
    ) -> None:
        """
        Уведомить админов о срочной новости на модерации.

        Args:
            post_id: ID поста
            text: Текст новости
            category: Категория
            urgency: Срочность (4-5)
            channel_title: Название канала-источника
        """
        admin_ids = await self._get_admin_ids()

        if not admin_ids:
            logger.warning("⚠️ Нет админов для отправки уведомления о срочной новости")
            return

        message = (
            f"⚡️ **СРОЧНАЯ НОВОСТЬ НА МОДЕРАЦИИ**\n\n"
            f"📁 **Категория:** {category}\n"
            f"🔥 **Срочность:** {urgency}\n"
            f"📢 **Источник:** {channel_title}\n"
            f"🆔 **ID:** {post_id}\n\n"
            f"📝 **Текст:**\n{text[:500]}{'...' if len(text) > 500 else ''}"
        )

        # Создаём inline-клавиатуру с кнопками одобрения/отклонения
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='✅ Одобрить',
                        callback_data=f'approve_post_{post_id}'
                    ),
                    InlineKeyboardButton(
                        text='❌ Отклонить',
                        callback_data=f'reject_post_{post_id}'
                    )
                ]
            ]
        )

        for admin_id in admin_ids:
            try:
                if self.bot:
                    await self.bot.send_message(
                        admin_id,
                        message,
                        parse_mode='Markdown',
                        reply_markup=keyboard
                    )
                    logger.info(f"✅ Отправлено уведомление админу ID={admin_id}")
                else:
                    logger.warning(
                        f"⚠️ Бот не инициализирован, "
                        f"уведомление не отправлено админу ID={admin_id}"
                    )
            except Exception as e:
                logger.error(
                    f"❌ Ошибка отправки уведомления админу ID={admin_id}: {e}"
                )

    async def notify_pending_news(
        self,
        post_id: int,
        text: str,
        category: str,
        channel_title: str
    ) -> None:
        """
        Уведомить админов о новости на плановой модерации.

        Args:
            post_id: ID сгенерированной новости
            text: Текст новости
            category: Категория
            channel_title: Название канала-источника
        """
        admin_ids = await self._get_admin_ids()

        if not admin_ids:
            logger.warning(
                "⚠️ Нет админов для отправки уведомления о новости на модерации"
            )
            return

        message = (
            f"📬 **Новость на модерации**\n\n"
            f"📁 **Категория:** {category}\n"
            f"📢 **Источник:** {channel_title}\n"
            f"🆔 **ID:** {post_id}\n\n"
            f"📝 **Текст:**\n"
            f"{text[:500]}{'...' if len(text) > 500 else ''}\n\n"
            f"Нажмите кнопку ниже для одобрения или отклонения."
        )

        # Создаём inline-клавиатуру с кнопками одобрения/отклонения
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='✅ Одобрить',
                        callback_data=f'approve_news_{post_id}'
                    ),
                    InlineKeyboardButton(
                        text='❌ Отклонить',
                        callback_data=f'reject_news_{post_id}'
                    )
                ]
            ]
        )

        for admin_id in admin_ids:
            try:
                if self.bot:
                    await self.bot.send_message(
                        admin_id,
                        message,
                        parse_mode='Markdown',
                        reply_markup=keyboard
                    )
                    logger.info(f"✅ Отправлено уведомление админу ID={admin_id}")
                else:
                    logger.warning(
                        f"⚠️ Бот не инициализирован, "
                        f"уведомление не отправлено админу ID={admin_id}"
                    )
            except Exception as e:
                logger.error(
                    f"❌ Ошибка отправки уведомления админу ID={admin_id}: {e}"
                )

    async def notify_direct_publish(
        self,
        post_id: int,
        channel_title: str,
        category: str,
        text: str
    ) -> None:
        """
        Уведомить о публикации напрямую (доверенный источник).

        Args:
            post_id: ID поста
            channel_title: Название канала
            category: Категория
            text: Текст поста
        """
        admin_ids = await self._get_admin_ids()

        if not admin_ids:
            logger.warning(
                "⚠️ Нет админов для отправки уведомления о прямой публикации"
            )
            return

        message = (
            f"🚀 **ОПУБЛИКОВАНО НАПРЯМУЮ** (доверенный источник)\n\n"
            f"📁 **Категория:** {category}\n"
            f"📢 **Источник:** {channel_title}\n"
            f"🆔 **ID:** {post_id}\n\n"
            f"📝 **Текст:**\n{text[:500]}{'...' if len(text) > 500 else ''}"
        )

        for admin_id in admin_ids:
            try:
                if self.bot:
                    await self.bot.send_message(
                        admin_id,
                        message,
                        parse_mode='Markdown'
                    )
                    logger.info(
                        f"✅ Отправлено уведомление админу ID={admin_id} "
                        f"о прямой публикации"
                    )
            except Exception as e:
                logger.error(
                    f"❌ Ошибка отправки уведомления админу ID={admin_id}: {e}"
                )
