"""
Notification Service — уведомления админов о новых новостях.

Изолирует логику уведомлений от ListenerBot и других компонентов.
Использует явную инъекцию бота через конструктор.
"""

import asyncio
import html
import json
import logging
from typing import TYPE_CHECKING, Optional

import aiohttp
from aiohttp import ClientConnectionError, ClientError
from aiogram.exceptions import TelegramNetworkError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from services.database import get_database_service
from services.util import decrypt_user_id

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from aiogram import Bot


class NotificationService:
    """
    Сервис для отправки уведомлений админам (singleton).

    Отправляет уведомления всем администраторам в БД через Telegram бота.
    Бот подхватывается лениво — при первом обращении к .bot, если не был
    передан явно в конструктор.

    Attributes:
        _bot: aiogram Bot для отправки уведомлений (может быть установлен позже)
    """

    _instance: Optional['NotificationService'] = None

    def __new__(cls, bot: Optional['Bot'] = None) -> 'NotificationService':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._bot = bot
        elif bot is not None:
            # Обновляем бот, если он появился позже
            cls._instance._bot = bot
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Сбросить singleton (для тестов)."""
        cls._instance = None

    @property
    def bot(self) -> Optional['Bot']:
        """Получить бот — явно установленный или подхваченный из BotService."""
        if self._bot is not None:
            return self._bot
        # Lazy: попробуем взять из BotService
        try:
            from services.bot.bot import get_bot_instance
            self._bot = get_bot_instance(wait=False)
        except Exception:
            pass
        return self._bot

    @bot.setter
    def bot(self, value: Optional['Bot']) -> None:
        self._bot = value


    async def _get_admin_ids(self) -> list[int]:
        """
        Получить Telegram ID всех администраторов.

        Returns:
            Список Telegram ID админов (пустой список если нет админов или ошибка расшифровки)
        """
        db_service = get_database_service()
        async with db_service.session_context() as session:
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
                # Логируем ошибку, но продолжаем обработку остальных админов
                logger.warning(f"⚠️ Не удалось расшифровать ID админа (ID={admin.id}): {e}")
                logger.warning("   Возможные причины: неверный ключ шифрования или повреждённые данные")

        if not admin_ids and admins:
            logger.warning("⚠️ Все админы имеют проблемы с расшифровкой ID")
        elif not admin_ids:
            logger.info("ℹ️ В базе данных нет пользователей с ролью 'admin'")

        return admin_ids

    async def notify_urgent_news(
        self,
        post_id: int,
        text: str,
        category: str,
        urgency: int,
        channel_title: str
    ) -> bool:
        """
        Уведомить админов о срочной новости на модерации.

        Args:
            post_id: ID поста
            text: Текст новости
            category: Категория
            urgency: Срочность (4-5)
            channel_title: Название канала-источника

        Returns:
            True если уведомления отправлены, False если нет админов
        """
        admin_ids = await self._get_admin_ids()

        if not admin_ids:
            logger.warning(
                "⚠️ Нет админов для отправки уведомления о срочной новости. "
                f"Пост ID={post_id} сохранён в БД и будет обработан планировщиком."
            )
            return False

        if not self.bot:
            logger.warning(
                f"⚠️ Бот не инициализирован, уведомление не отправлено. "
                f"Пост ID={post_id} будет обработан планировщиком."
            )
            return False

        # Форматируем текст: обрезаем, приводим переносы строк
        preview = text.strip().replace('\n', ' ')
        preview_text = preview[:200] + ('...' if len(preview) > 200 else '')

        # Полное тело новости — в блоке-цитате
        full_body = html.escape(text.strip())
        if len(full_body) > 400:
            full_body = full_body[:400] + '\n...'

        # Уровень срочности — визуальный индикатор
        if urgency >= 5:
            urgency_label = "🔴 КРИТИЧЕСКАЯ"
        elif urgency >= 4:
            urgency_label = "🟠 ВЫСОКАЯ"
        else:
            urgency_label = f"{urgency}/5"

        message = (
            f"⚡️ <b>СРОЧНАЯ НОВОСТЬ НА МОДЕРАЦИИ</b>\n\n"
            f"📁 <b>{html.escape(str(category))}</b> · {urgency_label}\n"
            f"📢 <b>Источник:</b> {html.escape(str(channel_title))}\n"
            f"🆔 ID <code>{post_id}</code>\n\n"
            f"┌─ <b>Текст:</b>\n"
            f"│ {html.escape(preview_text)}\n"
            f"└─\n\n"
            f"📝 <b>Полностью:</b>\n"
            f"<blockquote expandable>{full_body}</blockquote>"
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

        sent_count = 0
        for admin_id in admin_ids:
            try:
                # Retry logic для устойчивости к временным ошибкам сети
                retries = 3
                for attempt in range(retries):
                    try:
                        await self.bot.send_message(
                            admin_id,
                            message,
                            parse_mode='HTML',
                            reply_markup=keyboard,
                            allow_sending_without_reply=True
                        )
                        logger.info(f"✅ Отправлено уведомление админу ID={admin_id}")
                        sent_count += 1
                        break
                    except TimeoutError as e:
                        if attempt < retries - 1:
                            logger.warning(
                                f"⏳ Таймаут отправки админу ID={admin_id} "
                                f"(попытка {attempt + 1}/{retries}), повтор через {2 ** attempt}с..."
                            )
                            await asyncio.sleep(2 ** attempt)
                        else:
                            raise
                    except TelegramNetworkError as e:
                        # Сетевые ошибки aiogram (Request timeout, connection reset) — ретраим
                        if attempt < retries - 1:
                            delay = 2 ** attempt
                            logger.warning(
                                f"⏳ Сетевая ошибка админу ID={admin_id} "
                                f"(попытка {attempt + 1}/{retries}, {type(e).__name__}), повтор через {delay}с..."
                            )
                            await asyncio.sleep(delay)
                        else:
                            raise
                    except Exception as e:
                        error_name = type(e).__name__
                        # TelegramAPIError с timeout/flood — тоже ретраим
                        if 'timeout' in str(e).lower() or 'flood' in str(e).lower():
                            if attempt < retries - 1:
                                delay = 2 ** attempt
                                logger.warning(
                                    f"⏳ {error_name} админу ID={admin_id} "
                                    f"(попытка {attempt + 1}/{retries}), повтор через {delay}с..."
                                )
                                await asyncio.sleep(delay)
                            else:
                                raise
                        raise

            except Exception as e:
                logger.error(
                    f"❌ Ошибка отправки уведомления админу ID={admin_id}: {e}"
                )

        return sent_count > 0

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

        # Форматируем сообщение в HTML
        safe_text = html.escape(text[:500])
        if len(text) > 500:
            safe_text += '...'

        message = (
            f"📬 <b>Новость на модерации</b>\n\n"
            f"📁 <b>Категория:</b> {html.escape(str(category))}\n"
            f"📢 <b>Источник:</b> {html.escape(str(channel_title))}\n"
            f"🆔 <b>ID:</b> {post_id}\n\n"
            f"📝 <b>Текст:</b>\n"
            f"{safe_text}\n\n"
            f"<i>Нажмите кнопку ниже для одобрения или отклонения.</i>"
        )

        # Создаём inline-клавиатуру с кнопками одобрения/редактирования/отклонения
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='✅ Одобрить',
                        callback_data=f'approve_news_{post_id}'
                    ),
                    InlineKeyboardButton(
                        text='✏️ Редактировать',
                        callback_data=f'edit_news_{post_id}'
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
                if self._bot:
                    await self.bot.send_message(
                        admin_id,
                        message,
                        parse_mode='HTML',
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

        # Форматируем сообщение в HTML
        safe_text = html.escape(text[:500])
        if len(text) > 500:
            safe_text += '...'

        message = (
            f"🚀 <b>ОПУБЛИКОВАНО НАПРЯМУЮ</b> (доверенный источник)\n\n"
            f"📁 <b>Категория:</b> {html.escape(str(category))}\n"
            f"📢 <b>Источник:</b> {html.escape(str(channel_title))}\n"
            f"🆔 <b>ID:</b> {post_id}\n\n"
            f"📝 <b>Текст:</b>\n{safe_text}"
        )

        for admin_id in admin_ids:
            try:
                if self._bot:
                    await self.bot.send_message(
                        admin_id,
                        message,
                        parse_mode='HTML'
                    )
                    logger.info(
                        f"✅ Отправлено уведомление админу ID={admin_id} "
                        f"о прямой публикации"
                    )
            except Exception as e:
                logger.error(
                    f"❌ Ошибка отправки уведомления админу ID={admin_id}: {e}"
                )

    async def notify_subscribers(
        self,
        news_text: str,
        category: str,
        tags: list[str],
        news_id: int,
        urgency: int = 1,
        bot_username: str = '',
        publisher_channel_link: str = '',
    ) -> int:
        """
        Отправить новость подписчикам с учётом предпочтений.

        Args:
            news_text: Текст новости
            category: Категория новости
            tags: Тэги новости
            news_id: ID новости
            urgency: Срочность (1-5, >=4 — срочная новость)

        Returns:
            Количество отправленных уведомлений
        """
        db_service = get_database_service()
        sent_count = 0

        async with db_service.session_context() as session:
            # Получаем всех пользователей с активной подпиской
            result = await session.execute(
                select(User).where(User.has_subscription == True)
            )
            subscribers = result.scalars().all()

            # Обрабатываем каждого подписчика в той же сессии
            for subscriber in subscribers:
                # Явно обновляем объект из БД чтобы получить актуальные предпочтения
                await session.refresh(subscriber)

                if await self._send_to_subscriber(
                    session, subscriber, news_text, category, tags, sent_count, urgency, news_id, bot_username, publisher_channel_link
                ):
                    sent_count += 1

        return sent_count

    async def notify_all_subscribers(
        self,
        news_text: str,
        news_id: int,
        ignore_preferences: bool = True,
        urgency: int = 1,
        bot_username: str = '',
        publisher_channel_link: str = '',
    ) -> int:
        """
        Отправить новость всем подписчикам (игнорируя предпочтения).

        Используется для прямой генерации (анонсы, акции) — отправляется
        всем пользователям независимо от выбранных категорий и тэгов.

        Args:
            news_text: Текст новости
            news_id: ID новости
            ignore_preferences: Игнорировать предпочтения пользователей (по умолчанию True)
            urgency: Срочность (1-5, >=4 — срочная новость)

        Returns:
            Количество отправленных уведомлений
        """
        db_service = get_database_service()
        sent_count = 0

        async with db_service.session_context() as session:
            # Получаем всех пользователей с активной подпиской (включая админов)
            result = await session.execute(
                select(User).where(User.has_subscription == True)
            )
            subscribers = result.scalars().all()

            logger.info(f"📢 Рассылка новости ID={news_id}: найдено {len(subscribers)} подписчиков")

            # Обрабатываем каждого подписчика в той же сессии
            for subscriber in subscribers:
                # Явно обновляем объект из БД чтобы получить актуальные предпочтения
                await session.refresh(subscriber)

                # Пропускаем админов — они получают уведомления отдельно
                if subscriber.role == 'admin':
                    continue

                if ignore_preferences:
                    # Отправляем всем без проверки предпочтений
                    if await self._send_to_subscriber_simple(
                        session, subscriber, news_text, sent_count, urgency, news_id,
                        category='', bot_username=bot_username, publisher_channel_link=publisher_channel_link,
                    ):
                        sent_count += 1
                else:
                    # Отправляем с проверкой предпочтений
                    if await self._send_to_subscriber(
                        session, subscriber, news_text, 'Общее', [], sent_count, urgency, news_id, bot_username, publisher_channel_link
                    ):
                        sent_count += 1

        return sent_count

    async def _send_to_subscriber_simple(
        self,
        session: AsyncSession,
        subscriber: User,
        news_text: str,
        current_count: int,
        urgency: int = 1,
        news_id: int = None,
        category: str = '',
        bot_username: str = '',
        publisher_channel_link: str = '',
    ) -> bool:
        """
        Отправить новость одному подписчику (без проверки предпочтений).

        Args:
            session: SQLAlchemy сессия
            subscriber: Пользователь
            news_text: Текст новости
            current_count: Текущее количество отправленных
            urgency: Срочность (1-5)
            news_id: ID новости (для логирования)

        Returns:
            True если отправлено успешно
        """
        try:
            # Получаем Telegram ID
            telegram_id = _decrypt_subscriber_id(subscriber)
            if telegram_id is None:
                return False

            # Получаем бота: из контейнера или через глобальную ссылку
            bot = self._bot
            if bot is None:
                try:
                    from services.bot.bot import get_bot_instance_async
                    bot = await get_bot_instance_async(wait=False, timeout=5.0)
                except Exception:
                    bot = None

            if bot is None:
                news_id_str = f"news_id={news_id}, " if news_id else ""
                logger.error(
                    f"❌ Бот недоступен для отправки подписчику "
                    f"({news_id_str}subscriber_id={subscriber.id})"
                )
                return False

            # Отправляем уведомление с retry logic для обработки таймаутов и сетевых ошибок
            message = _format_subscriber_message(news_text, urgency, category=category, bot_username=bot_username, publisher_channel_link=publisher_channel_link)

            # Retry logic: 3 попытки с экспоненциальной задержкой
            retries = 3
            for attempt in range(retries):
                try:
                    await bot.send_message(
                        telegram_id,
                        message,
                        parse_mode='HTML',
                        request_timeout=60  # Увеличенный таймаут: 60 секунд
                    )
                    return True
                except TimeoutError as e:
                    # Таймаут — пробуем снова
                    if attempt < retries - 1:
                        delay = 2 ** attempt  # 1с, 2с, 4с
                        logger.warning(
                            f"⏳ Таймаут отправки подписчику ID={telegram_id} "
                            f"({news_id_str}попытка {attempt + 1}/{retries}), повтор через {delay}с..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"❌ Превышено количество попыток отправки подписчику ID={telegram_id} "
                            f"({news_id_str}таймаут после {retries} попыток)"
                        )
                        return False
                except (ClientConnectionError, ClientError) as e:
                    # Сетевые ошибки aiohttp — пробуем снова
                    if attempt < retries - 1:
                        delay = 2 ** attempt
                        logger.warning(
                            f"⏳ Сетевая ошибка при отправке подписчику ID={telegram_id} "
                            f"({news_id_str}попытка {attempt + 1}/{retries}, {type(e).__name__}), повтор через {delay}с..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"❌ Превышено количество попыток отправки подписчику ID={telegram_id} "
                            f"({news_id_str}сетевая ошибка: {type(e).__name__})"
                        )
                        return False
                except Exception as e:
                    # TelegramNetworkError и другие сетевые ошибки aiogram — ретраим
                    error_name = type(e).__name__
                    if 'Network' in error_name or 'Connection' in error_name or 'Timeout' in error_name:
                        if attempt < retries - 1:
                            delay = 2 ** attempt
                            logger.warning(
                                f"⏳ Сетевая ошибка при отправке подписчику ID={telegram_id} "
                                f"({news_id_str}попытка {attempt + 1}/{retries}, {error_name}), повтор через {delay}с..."
                            )
                            await asyncio.sleep(delay)
                        else:
                            logger.error(
                                f"❌ Превышено количество попыток отправки подписчику ID={telegram_id} "
                                f"({news_id_str}{error_name})"
                            )
                            return False
                    # Не временная ошибка — сразу логируем и прекращаем
                    logger.error(
                        f"❌ Ошибка отправки новости подписчику ID={telegram_id} "
                        f"({news_id_str}ошибка: {error_name}: {e})"
                    )
                    return False

            return False

        except Exception as e:
            news_id_str = f"news_id={news_id}, " if news_id else ""
            logger.error(
                f"❌ Критическая ошибка отправки новости подписчику "
                f"({news_id_str}subscriber_id={subscriber.id}): {type(e).__name__}: {e}",
                exc_info=True
            )
            return False

    async def _send_to_subscriber(
        self,
        session: AsyncSession,
        subscriber: User,
        news_text: str,
        category: str,
        tags: list[str],
        current_count: int,
        urgency: int = 1,
        news_id: int = None,
        bot_username: str = '',
        publisher_channel_link: str = '',
    ) -> bool:
        """
        Отправить новость одному подписчику.

        Args:
            session: SQLAlchemy сессия для обновления данных
            urgency: Срочность (1-5, >=4 — срочная новость)
            news_id: ID новости (для логирования)

        Returns:
            True если отправлено успешно
        """
        try:
            # Пропускаем админов
            if subscriber.role == 'admin':
                return False

            # Явно обновляем предпочтения из БД (на случай если они изменились)
            await session.refresh(subscriber, attribute_names=['preferred_categories', 'preferred_tags'])

            # Проверяем предпочтения
            user_categories = json.loads(subscriber.preferred_categories or '[]')
            user_tags = json.loads(subscriber.preferred_tags or '[]')

            # Проверяем соответствие
            if not _matches_preferences(user_categories, user_tags, category, tags):
                logger.debug(
                    f"⏭️ Пропущен подписчик ID={subscriber.id}: не подходит по предпочтениям"
                )
                return False

            # Получаем Telegram ID
            telegram_id = _decrypt_subscriber_id(subscriber)
            if telegram_id is None:
                return False

            news_id_str = f"news_id={news_id}, " if news_id else ""

            # Отправляем уведомление с retry logic для обработки таймаутов и сетевых ошибок
            if self._bot:
                message = _format_subscriber_message(news_text, urgency, category=category, bot_username=bot_username, publisher_channel_link=publisher_channel_link)

                # Retry logic: 3 попытки с экспоненциальной задержкой
                retries = 3
                for attempt in range(retries):
                    try:
                        await self.bot.send_message(
                            telegram_id,
                            message,
                            parse_mode='HTML',
                            request_timeout=60  # Увеличенный таймаут: 60 секунд
                        )
                        return True
                    except TimeoutError as e:
                        # Таймаут — пробуем снова
                        if attempt < retries - 1:
                            delay = 2 ** attempt  # 1с, 2с, 4с
                            logger.warning(
                                f"⏳ Таймаут отправки подписчику ID={telegram_id} "
                                f"({news_id_str}попытка {attempt + 1}/{retries}), повтор через {delay}с..."
                            )
                            await asyncio.sleep(delay)
                        else:
                            logger.error(
                                f"❌ Превышено количество попыток отправки подписчику ID={telegram_id} "
                                f"({news_id_str}таймаут после {retries} попыток)"
                            )
                            return False
                    except (ClientConnectionError, ClientError) as e:
                        # Сетевые ошибки aiohttp — пробуем снова
                        if attempt < retries - 1:
                            delay = 2 ** attempt
                            logger.warning(
                                f"⏳ Сетевая ошибка при отправке подписчику ID={telegram_id} "
                                f"({news_id_str}попытка {attempt + 1}/{retries}, {type(e).__name__}), повтор через {delay}с..."
                            )
                            await asyncio.sleep(delay)
                        else:
                            logger.error(
                                f"❌ Превышено количество попыток отправки подписчику ID={telegram_id} "
                                f"({news_id_str}сетевая ошибка: {type(e).__name__})"
                            )
                            return False
                    except TelegramNetworkError as e:
                        # Сетевые ошибки aiogram (Request timeout, connection reset) — ретраим
                        if attempt < retries - 1:
                            delay = 2 ** attempt
                            logger.warning(
                                f"⏳ Сетевая ошибка при отправке подписчику ID={telegram_id} "
                                f"({news_id_str}попытка {attempt + 1}/{retries}, {type(e).__name__}), повтор через {delay}с..."
                            )
                            await asyncio.sleep(delay)
                        else:
                            logger.error(
                                f"❌ Превышено количество попыток отправки подписчику ID={telegram_id} "
                                f"({news_id_str}{type(e).__name__})"
                            )
                            return False
                    except Exception as e:
                        error_name = type(e).__name__
                        # TelegramAPIError с timeout/flood — тоже ретраим
                        if 'timeout' in str(e).lower() or 'flood' in str(e).lower() or 'network' in error_name.lower():
                            if attempt < retries - 1:
                                delay = 2 ** attempt
                                logger.warning(
                                    f"⏳ {error_name} при отправке подписчику ID={telegram_id} "
                                    f"({news_id_str}попытка {attempt + 1}/{retries}), повтор через {delay}с..."
                                )
                                await asyncio.sleep(delay)
                            else:
                                logger.error(
                                    f"❌ Превышено количество попыток отправки подписчику ID={telegram_id} "
                                    f"({news_id_str}{error_name})"
                                )
                                return False
                        # Не временная ошибка — сразу логируем и прекращаем
                        logger.error(
                            f"❌ Ошибка отправки новости подписчику ID={telegram_id} "
                            f"({news_id_str}ошибка: {error_name}: {e})"
                        )
                        return False

            return False

        except Exception as e:
            logger.error(
                f"❌ Критическая ошибка отправки новости подписчику "
                f"(news_id={news_id}, subscriber_id={subscriber.id}): {type(e).__name__}: {e}",
                exc_info=True
            )
            return False


def _matches_preferences(
    user_categories: list[str],
    user_tags: list[str],
    news_category: str,
    news_tags: list[str]
) -> bool:
    """
    Проверить, соответствует ли новость предпочтениям пользователя.

    Алгоритм:
    1. Если ничего не выбрано — не отправлять (пользователь не настроил предпочтения)
    2. Если только категории — отправлять все новости этих категорий
    3. Если только тэги — отправлять все новости с этими тэгами
    4. Если и категории, и тэги — требовать совпадения хотя бы одного
    """
    has_categories = bool(user_categories)
    has_tags = bool(user_tags)

    logger.debug(
        f"Проверка предпочтений: user_cats={user_categories}, user_tags={user_tags}, "
        f"news_cat={news_category}, news_tags={news_tags}"
    )

    # Ничего не выбрано — не отправляем
    if not has_categories and not has_tags:
        logger.debug("⏭️ Предпочтения не настроены — пропускаем")
        return False

    category_match = news_category in user_categories
    tags_match = bool(news_tags) and any(tag in user_tags for tag in news_tags)

    logger.debug(f"Результат: category_match={category_match}, tags_match={tags_match}")

    # Только категории
    if has_categories and not has_tags:
        result = category_match
        logger.debug(f"Только категории: {result}")
        return result

    # Только тэги
    if has_tags and not has_categories:
        result = tags_match
        logger.debug(f"Только тэги: {result}")
        return result

    # И категории, и тэги — требуем совпадения хотя бы одного
    result = category_match or tags_match
    logger.debug(f"Категории и тэги: {result}")
    return result


def _decrypt_subscriber_id(subscriber: User) -> int | None:
    """Расшифровать Telegram ID подписчика."""
    try:
        return decrypt_user_id(subscriber.user_id_encrypted)
    except Exception:
        logger.warning(f"Не удалось расшифровать ID подписчика ID={subscriber.id}")
        return None


def format_urgent_news_html(
    text: str,
    urgency: int = 4,
    category: str = '',
    bot_username: str = '',
    publisher_channel_link: str = '',
) -> str:
    """
    Единый формат срочной новости для всех каналов доставки.

    Аргументы:
        text: Сырой текст поста/новости
        urgency: Срочность (1-5, >=4 — срочная)
        category: Категория новости
        bot_username: Username бота для ссылки (@botname)
        publisher_channel_link: Ссылка на канал публикации (t.me/channel)

    Returns:
        Форматированное HTML-сообщение
    """
    try:
        urgency = int(urgency) if urgency else 4
    except (ValueError, TypeError):
        urgency = 4

    # Все новости urgency >= 4 — «Срочная новость»
    if urgency >= 4:
        header = "🚨 <b>Срочная новость!</b>"
    else:
        header = "📰 <b>Новость</b>"

    # Очищаем тело
    clean = html.escape(text.strip()) if text else ''
    clean_lines = []
    for ln in clean.split('\n'):
        ln_s = ln.strip()
        if ln_s.startswith('\U0001f4e2') and 'точник' in ln_s:
            continue
        clean_lines.append(ln_s)
    clean = '\n'.join(ln for ln in clean_lines if ln)

    if len(clean) > 800:
        clean = clean[:800] + '...'

    parts = [header]

    if category:
        parts.append(f"<b>{html.escape(str(category))}</b>")

    parts.append(clean)

    # Подвал: ссылки на канал и бота
    footer_parts = []
    if publisher_channel_link:
        safe_link = html.escape(publisher_channel_link)
        footer_parts.append(f'<a href="{safe_link}">\U0001f4f0 Канал</a>')
    if bot_username:
        safe_url = f'https://t.me/{html.escape(bot_username)}'
        footer_parts.append(f'<a href="{safe_url}">\U0001f916 Бот</a>')

    if footer_parts:
        parts.append(' \u2022 '.join(footer_parts))

    return '\n\n'.join(parts)


def _format_subscriber_message(
    news_text: str,
    urgency: int = 1,
    category: str = '',
    channel_title: str = '',
    bot_username: str = '',
    publisher_channel_link: str = '',
) -> str:
    """
    Сформировать HTML-сообщение для подписчика.

    Для срочных новостей (urgency >= 4) — делегирует в format_urgent_news_html.
    Для плановых — использует свой формат.

    Args:
        news_text: Текст новости (может содержать HTML-разметку)
        urgency: Срочность (1-5, >=4 — срочная новость)
        category: Категория новости
        channel_title: Название канала (для совместимости)
        bot_username: Username бота для ссылки
        publisher_channel_link: Ссылка на канал публикации

    Returns:
        Форматированное HTML-сообщение
    """
    try:
        urgency = int(urgency) if urgency else 1
    except (ValueError, TypeError):
        urgency = 1

    # Для срочных — единый формат
    if urgency >= 4:
        urgent = format_urgent_news_html(
            text=news_text,
            urgency=urgency,
            category=category,
            bot_username=bot_username,
            publisher_channel_link=publisher_channel_link,
        )
        return urgent + '\n\n<i>Чтобы отписаться, нажмите /unsubscribe</i>'

    # Плановая
    header = "\U0001f4f0 <b>Новость для вас!</b>"

    clean_text = news_text.strip()
    for prefix in [
        "\U0001f6a8 <b>Срочная новость!</b>\n", "\U0001f6a8 <b>Срочная новость!</b>",
        "\U0001f4f0 <b>Новость для вас!</b>\n", "\U0001f4f0 <b>Новость для вас!</b>",
    ]:
        if clean_text.startswith(prefix):
            clean_text = clean_text[len(prefix):].strip()
            break

    # Чистим артефакты источника
    clean_lines = []
    for ln in clean_text.split('\n'):
        ln_s = ln.strip()
        if ln_s.startswith('\U0001f4e2') and 'точник' in ln_s:
            continue
        clean_lines.append(ln_s)
    clean_text = '\n'.join(ln for ln in clean_lines if ln)

    if not clean_text.startswith('<') and not any(t in clean_text for t in ['<b>', '<i>', '<code>']):
        clean_text = html.escape(clean_text)

    lines = [ln.strip() for ln in clean_text.split('\n') if ln.strip()]
    body_text = '\n'.join(lines)
    if len(body_text) > 500:
        body_text = body_text[:500] + '...'

    parts = [header]
    if category:
        parts.append(f"<b>{html.escape(str(category))}</b>")
    parts.append(body_text)
    parts.append("<i>Чтобы отписаться, нажмите /unsubscribe</i>")

    return '\n\n'.join(parts)


async def send_message_with_retry(
    message: 'Message',
    text: str,
    parse_mode: str = 'HTML',
    retries: int = 3
) -> bool:
    """
    Отправить сообщение с retry logic.

    Args:
        message: aiogram Message для отправки
        text: Текст сообщения
        parse_mode: Режим парсинга ('HTML' или 'Markdown')
        retries: Количество попыток

    Returns:
        True если отправлено успешно, False иначе
    """

    if not hasattr(message, 'bot') or not message.bot:
        logger.error("❌ У сообщения нет бота для отправки")
        return False

    for attempt in range(retries):
        try:
            await message.bot.send_message(
                chat_id=message.chat.id,
                text=text,
                parse_mode=parse_mode
            )
            logger.debug(f"✅ Сообщение отправлено (попытка {attempt + 1}/{retries})")
            return True
        except Exception as e:
            if attempt < retries - 1:
                delay = 2 ** attempt
                logger.warning(
                    f"⏳ Ошибка отправки сообщения (попытка {attempt + 1}/{retries}): "
                    f"{type(e).__name__}: {e}. Повтор через {delay}с..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"❌ Не удалось отправить сообщение после {retries} попыток: "
                    f"{type(e).__name__}: {e}"
                )
                return False
    return False
