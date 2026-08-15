"""
Утилиты для Telegram бота.
"""

import logging
import time
import asyncio
from typing import Optional, Callable, Any
from contextlib import asynccontextmanager
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError
from database import RepositoryFactory
from services.database import get_database_service

logger = logging.getLogger(__name__)

# Кэш для хранения времени последнего показа рекламы пользователю
# Формат: {user_id: timestamp}
_advertisement_cache = {}
ADVERTISEMENT_INTERVAL = 600  # Интервал между рекламой (секунды) = 10 минут

# Настройки повторных попыток для сетевых запросов
MAX_RETRIES = 3  # Максимальное количество попыток
RETRY_DELAY = 1.0  # Задержка между попытками (секунды)
RETRY_BACKOFF = 2.0  # Множитель увеличения задержки (экспоненциальная задержка)


async def retry_on_network_error(
    func: Callable,
    *args,
    max_retries: int = MAX_RETRIES,
    base_delay: float = RETRY_DELAY,
    backoff: float = RETRY_BACKOFF,
    **kwargs
) -> Any:
    """
    Выполнить функцию с повторными попытками при ошибке сети.

    Обрабатывает:
    - TelegramNetworkError — временные ошибки сети
    - TelegramAPIError с retry_after — Flood Control (429)

    Args:
        func: Асинхронная функция для выполнения
        *args: Позиционные аргументы для функции
        max_retries: Максимальное количество попыток
        base_delay: Начальная задержка между попытками (секунды)
        backoff: Множитель увеличения задержки
        **kwargs: Именованные аргументы для функции

    Returns:
        Результат выполнения функции

    Raises:
        Последнюю ошибку, если все попытки исчерпаны
    """
    last_exception = None
    delay = base_delay

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except TelegramAPIError as e:
            # Обработка Flood Control (429)
            if hasattr(e, 'retry_after') and e.retry_after:
                retry_after = int(e.retry_after)
                logger.warning(
                    f"⚠️ Flood Control (попытка {attempt + 1}/{max_retries + 1}): "
                    f"ждем {retry_after}с..."
                )
                if attempt < max_retries:
                    await asyncio.sleep(retry_after)
                else:
                    logger.error(f"❌ Flood Control: превышено время ожидания ({retry_after}с)")
                    raise
            else:
                # Другие API ошибки не повторяем
                logger.error(f"❌ Telegram API error: {e}")
                raise
        except TelegramNetworkError as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(
                    f"⚠️ Ошибка сети (попытка {attempt + 1}/{max_retries + 1}): {e}. "
                    f"Повторная попытка через {delay:.1f}с..."
                )
                await asyncio.sleep(delay)
                delay *= backoff  # Экспоненциальное увеличение задержки
            else:
                logger.error(
                    f"❌ Все {max_retries + 1} попыток исчерпаны. Последняя ошибка: {e}"
                )
                raise
        except Exception as e:
            # Другие ошибки не повторяем, а сразу пробрасываем
            logger.error(f"❌ Ошибка при выполнении функции: {e}")
            raise

    # Если дошли сюда (не должно случиться)
    if last_exception:
        raise last_exception


async def send_message_with_retry(
    message: Message,
    text: str,
    **kwargs
) -> Optional[Message]:
    """
    Отправить сообщение с повторными попытками при ошибке сети.

    Args:
        message: Сообщение для ответа (используется message.answer)
        text: Текст сообщения
        **kwargs: Дополнительные аргументы для message.answer

    Returns:
        Отправленное сообщение или None если все попытки не удались
    """
    try:
        return await retry_on_network_error(
            message.answer,
            text,
            **kwargs
        )
    except TelegramNetworkError as e:
        logger.error(f"❌ Не удалось отправить сообщение после всех попыток: {e}")
        return None


@asynccontextmanager
async def get_repository_factory(session=None):
    """
    Получить фабрику репозиториев в контекстном менеджере.

    Usage:
        async with get_repository_factory() as factory:
            posts_repo = factory.posts()
    """
    if session is None:
        db_service = get_database_service()
        session = await db_service.create_session()
        close_session = True
    else:
        close_session = False

    try:
        yield RepositoryFactory(session)
    finally:
        if close_session and session:
            await session.close()


async def show_last_posts(message: Message, limit: int = 10) -> None:
    """
    Показать последние посты.

    Args:
        message: Сообщение для ответа
        limit: Максимальное количество постов
    """
    async with get_repository_factory() as factory:
        posts_repo = factory.posts()
        news_repo = factory.news()

        posts = await posts_repo.get_all(limit=limit)

        if not posts:
            await message.answer('📭 Постов пока нет')
            return

        text = '📰 <b>Последние посты:</b>\n\n'
        for post in posts:
            confidence_emoji = (
                '✓' if post.category_confidence > 0.7
                else '⚠️' if post.category_confidence > 0.4
                else '❓'
            )

            # Проверяем, есть ли сгенерированная новость
            generated = await news_repo.get_by_post(post.id)
            generated_mark = '📝' if generated else ''

            text += (
                f'{generated_mark} <b>ID={post.id}</b> | {post.category} | '
                f'срочность {post.urgency} | рейтинг {post.rate}\n'
                f'   {confidence_emoji} Уверенность: {post.category_confidence:.2f}\n'
                f'   Текст: {post.text[:100]}...\n\n'
            )

        await message.answer(text, parse_mode='HTML')


async def show_generated_news(message: Message, limit: int = 10) -> None:
    """
    Показать последние сгенерированные новости.

    Args:
        message: Сообщение для ответа
        limit: Максимальное количество новостей
    """
    import html as html_lib

    async with get_repository_factory() as factory:
        news_repo = factory.news()
        events_repo = factory.events()

        news_items = await news_repo.get_recent(limit=limit)

        if not news_items:
            await message.answer('📭 Сгенерированных новостей пока нет')
            return

        text = '📝 <b>Последние сгенерированные новости:</b>\n\n'
        for news in news_items:
            # Получаем контекст события
            context = None
            if news.source_event_ids:
                import json
                event_ids = json.loads(news.source_event_ids)
                if event_ids:
                    context = await events_repo.get_context(event_ids[0])

            text += f'<b>ID={news.id}</b>\n'
            if context:
                event_desc = context.get('event_description', 'не указано')
                # Экранируем HTML спецсимволы в описании
                text += f'   📌 Контекст: {html_lib.escape(event_desc)[:100]}...\n'
            # Экранируем HTML спецсимволы в тексте новости
            text += f'   Текст: {html_lib.escape(news.text)[:200]}...\n\n'

        await message.answer(text, parse_mode='HTML')


async def show_pending_moderation(message: Message, limit: int = 20) -> None:
    """
    Показать новости, ожидающие модерации.

    Args:
        message: Сообщение для ответа
        limit: Максимальное количество новостей
    """
    async with get_repository_factory() as factory:
        news_repo = factory.news()

        pending = await news_repo.get_pending(limit=limit)

        if not pending:
            await message.answer('✅ Нет новостей, ожидающих модерации')
            return

        text = '⏳ <b>Новости на модерации:</b>\n\n'

        # Создаём inline-клавиатуру с кнопками для каждой новости
        buttons = []
        for news in pending:
            text += (
                f'<b>ID={news.id}</b> | {news.category}\n'
                f'Текст: {news.text[:150]}...\n'
                f'Теги: {news.tags}\n\n'
            )
            # Добавляем кнопки для этой новости
            buttons.append([
                InlineKeyboardButton(text=f'✅ Одобрить #{news.id}', callback_data=f'approve_news_{news.id}'),
                InlineKeyboardButton(text=f'❌ Отклонить #{news.id}', callback_data=f'reject_news_{news.id}')
            ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

        await message.answer(text, parse_mode='HTML', reply_markup=keyboard)


async def approve_news_by_id(
    message: Message,
    news_id: int,
    admin_telegram_id: int,
    with_channel_choice: bool = True,
) -> None:
    """
    Одобрить новость по ID.

    Args:
        message: Сообщение для ответа
        news_id: ID новости
        admin_telegram_id: Telegram ID админа
        with_channel_choice: Показать ли выбор канала для публикации
    """

    async with get_repository_factory() as factory:
        news_repo = factory.news()
        publishers_repo = factory.publishers()
        user_repo = factory.users()

        # Получаем пользователя из БД
        user = await user_repo.get_by_telegram_id(admin_telegram_id)
        if not user or user.role != 'admin':
            await message.answer('❌ У вас нет прав администратора')
            return

        # Получаем новость
        news = await news_repo.get_by_id(news_id)
        if not news:
            await message.answer(f'❌ Новость ID={news_id} не найдена')
            return

        # Получаем активные каналы публикации
        publishers = await publishers_repo.get_all(active_only=True)

        if with_channel_choice and publishers:
            # Показываем выбор канала
            publishers_data = [
                {'id': p.id, 'title': p.title, 'channel_id': p.channel_id}
                for p in publishers
            ]
            keyboard = create_publishers_choice_kb(publishers_data)

            await message.answer(
                f'✅ **Новость ID={news_id} одобрена!**\n\n'
                f'📝 Текст: {news.text[:200]}...\n\n'
                f'Выберите канал для публикации:',
                reply_markup=keyboard,
            )
        else:
            # Одобрение без выбора канала (старая логика)
            if await news_repo.approve(news_id, admin_telegram_id):
                await message.answer(f'✅ Новость ID={news_id} одобрена')
            else:
                await message.answer(f'❌ Новость ID={news_id} не найдена')


def create_publishers_choice_kb(publishers: list[dict]) -> InlineKeyboardMarkup:
    """
    Создать клавиатуру с выбором канала для публикации.

    Args:
        publishers: Список dict с publisher'ами [{'id': 1, 'title': 'Channel'}, ...]

    Returns:
        InlineKeyboardMarkup с кнопками выбора
    """
    buttons = []
    for pub in publishers:
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {pub['title']}",
                callback_data=f"publish_to_{pub['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_publish')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def reject_news_by_id(
    message: Message,
    news_id: int,
    admin_telegram_id: int,
) -> None:
    """
    Отклонить новость по ID.

    Args:
        message: Сообщение для ответа
        news_id: ID новости
        admin_telegram_id: Telegram ID админа
    """

    async with get_repository_factory() as factory:
        news_repo = factory.news()
        user_repo = factory.users()

        # Проверяем права администратора
        user = await user_repo.get_by_telegram_id(admin_telegram_id)
        if not user or user.role != 'admin':
            await message.answer('❌ У вас нет прав администратора')
            return

        if await news_repo.reject(news_id, admin_telegram_id):
            await message.answer(f'❌ Новость ID={news_id} отклонена')
        else:
            await message.answer(f'❌ Новость ID={news_id} не найдена')


async def check_and_show_advertisement(message: Message, user_telegram_id: int, is_admin: bool) -> None:
    """
    Проверить и показать рекламное уведомление пользователю (не админу).

    Реклама показывается раз в ADVERTISEMENT_INTERVAL секунд.

    Args:
        message: Сообщение для ответа
        user_telegram_id: Telegram ID пользователя
        is_admin: Является ли пользователь админом
    """
    global _advertisement_cache

    # Админам рекламу не показываем
    if is_admin:
        return

    current_time = time.time()
    last_ad_time = _advertisement_cache.get(user_telegram_id, 0)

    # Проверяем, прошло ли достаточно времени с последнего показа
    if current_time - last_ad_time < ADVERTISEMENT_INTERVAL:
        return

    # Показываем рекламу
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='💎 Оформить подписку', callback_data='subscription_menu')]
        ]
    )

    await message.answer(
        '📢 <b>Только у нас — самые честные новости!</b>\n\n'
        'Подпишись, чтобы получать актуальную информацию без рекламы и цензуры.',
        parse_mode='HTML',
        reply_markup=keyboard
    )

    # Обновляем кэш
    _advertisement_cache[user_telegram_id] = current_time

    # Очищаем старые записи (оптимизация)
    if len(_advertisement_cache) > 1000:
        cutoff_time = current_time - ADVERTISEMENT_INTERVAL * 2
        _advertisement_cache = {
            uid: ts for uid, ts in _advertisement_cache.items()
            if ts > cutoff_time
        }

    logger.debug(f"📢 Показана реклама пользователю ID={user_telegram_id}")
