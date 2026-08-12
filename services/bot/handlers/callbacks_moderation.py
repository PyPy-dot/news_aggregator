"""
Callback-хендлеры для модерации постов и новостей.

Модуль содержит обработчики для:
- Одобрения/отклонения срочных постов
- Одобрения/отклонения сгенерированных новостей
- Редактирования новостей
"""

import json
import logging
import re
from datetime import datetime, timezone
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from services.bot.handlers.router import admin
from services.bot.handlers.states import EditNewsStates
from database.repositories.posts import PostRepository
from database.repositories.users import UserRepository
from services.database import get_database_service

logger = logging.getLogger(__name__)


async def _check_admin_access(callback: CallbackQuery) -> bool:
    """Проверить права администратора. Возвращает True если доступ разрешён."""
    async with get_database_service().session_context() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user or user.role != 'admin':
            await callback.answer('❌ У вас нет прав для этого действия', show_alert=True)
            return False
        return True


def _extract_id(callback_data: str, pattern: str) -> int | None:
    """Извлечь ID из callback_data."""
    match = re.match(pattern, callback_data)
    if not match:
        return None
    return int(match.group(1))


def _build_moderation_response(
    item_type: str,
    item_id: int,
    action: str,
    admin_username: str,
    tag: str,
    extra_info: str = ''
) -> str:
    """Построить текст ответа модерации."""
    emoji = '✅' if action == 'approved' else '❌'
    action_text = {
        'approved': 'одобрен',
        'rejected': 'отклонён',
        'editing': 'редактируется'
    }.get(action, action)

    text = f'{emoji} **{item_type} ID={item_id} {action_text}!**\n\n'
    text += f'Админ: @{admin_username}\n'
    if tag:
        text += f'Тэг: "{tag}"\n'
    if extra_info:
        text += extra_info

    return text


@admin.callback_query(F.data.regexp(r'^approve_post_(\d+)$'))
async def approve_post_callback(callback: CallbackQuery):
    """
    Обработчик кнопки 'Одобрить' для срочной новости.
    Публикует новость во все каналы с matching категорией и отправляет подписчикам.
    """
    if not await _check_admin_access(callback):
        return

    post_id = _extract_id(callback.data, r'approve_post_(\d+)$')
    if post_id is None:
        await callback.answer('❌ Неверный формат данных', show_alert=True)
        return

    admin_username = callback.from_user.username or callback.from_user.first_name

    # Сначала логируем одобрение админом
    logger.info(f"✅ Админ ID={callback.from_user.id} одобрил пост ID={post_id}")

    async with get_database_service().session_context() as session:
        posts_repo = PostRepository(session)
        post = await posts_repo.get(post_id)

        if not post:
            await callback.answer(f'❌ Пост ID={post_id} не найден', show_alert=True)
            return

        # Добавляем тэг одобрения
        await posts_repo.add_tag(post_id, 'срочная_новость_одобрена_админом')

        # Публикация во все каналы с matching категорией
        from database.repositories.publishers import PublisherRepository
        from services.bot.handlers.publisher import PublisherService
        from services.bot.bot import get_bot_instance_async

        publishers_repo = PublisherRepository(session)
        publishers = await publishers_repo.get_all(active_only=True)

        matching_publishers = [
            pub for pub in publishers
            if pub.category and pub.category.lower() == post.category.lower()
        ]

        published_count = 0

        if matching_publishers:
            logger.info(
                f"📢 Публикация новости ID={post_id} категории '{post.category}' "
                f"в {len(matching_publishers)} канал(а/ов):"
            )

            # Получаем бота для публикации (с ожиданием готовности)
            bot_instance = await get_bot_instance_async(wait=True, timeout=10.0)
            if not bot_instance:
                logger.error("❌ Бот не инициализирован. Публикация отменена.")
                return
            publisher_service = PublisherService(bot_instance)

            for pub in matching_publishers:
                try:
                    # Реальная публикация в канал через aiogram
                    published = await publisher_service.publish_to_channel(
                        channel_id=pub.channel_id,
                        text=post.text
                    )

                    if published:
                        # Отмечаем в БД только после успешной публикации
                        await posts_repo.mark_direct_publish(post_id, pub.id)
                        logger.info(f"  ✅ Опубликовано в канал '{pub.title}' (ID={pub.id})")
                        published_count += 1
                    else:
                        logger.error(
                            f"  ❌ Не удалось опубликовать в канал '{pub.title}' (ID={pub.id})"
                        )

                except Exception as e:
                    logger.error(
                        f"  ❌ Ошибка публикации в канал '{pub.title}' (ID={pub.id}): {e}"
                    )
        else:
            logger.info(
                f"⚠️ Нет каналов с категорией '{post.category}'. "
                f"Новость будет отправлена только подписчикам."
            )

        await session.commit()

        # Отправка подписчикам
        await _notify_subscribers(
            text=post.text,
            category=post.category,
            tags=json.loads(post.tags or '[]') if post.tags else [],
            news_id=post_id,
            urgency=post.urgency,
        )

        await callback.answer(
            f'✅ Пост ID={post_id} одобрен и отправлен на публикацию '
            f'({published_count} канал(а/ов))',
            show_alert=True
        )

        await _update_moderation_message(
            callback,
            post_id,
            'Пост',
            admin_username,
            'срочная_новость_одобрена_админом',
            'Статус: Опубликовано'
        )


@admin.callback_query(F.data.regexp(r'^reject_post_(\d+)$'))
async def reject_post_callback(callback: CallbackQuery):
    """
    Обработчик кнопки 'Отклонить' для срочной новости.
    Снижает рейтинг доверия канала на 5%.
    """
    if not await _check_admin_access(callback):
        return

    post_id = _extract_id(callback.data, r'reject_post_(\d+)$')
    if post_id is None:
        await callback.answer('❌ Неверный формат данных', show_alert=True)
        return

    admin_username = callback.from_user.username or callback.from_user.first_name

    async with get_database_service().session_context() as session:
        posts_repo = PostRepository(session)
        post = await posts_repo.get(post_id)

        if not post:
            await callback.answer(f'❌ Пост ID={post_id} не найден', show_alert=True)
            return

        # Добавляем тэг и снижаем рейтинг канала
        await posts_repo.add_tag(post_id, 'срочная_новость_отклонена_админом')

        from database.repositories.channels import ChannelRepository
        channels_repo = ChannelRepository(session)
        await channels_repo.decrease_trust_rating(post.channel_id, amount=0.05)

        await callback.answer(f'❌ Пост ID={post_id} отклонён', show_alert=True)

        await _update_moderation_message(
            callback,
            post_id,
            'Пост',
            admin_username,
            'срочная_новость_отклонена_админом',
            'Рейтинг канала снижен на 5%',
            action='rejected'
        )

    logger.info(f"❌ Админ ID={callback.from_user.id} отклонил пост ID={post_id}")


@admin.callback_query(F.data.regexp(r'^approve_news_(\d+)$'))
async def approve_news_callback(callback: CallbackQuery):
    """
    Обработчик кнопки 'Одобрить' для сгенерированной новости.
    Публикует новость в каналы с matching категорией и увеличивает рейтинг канала на 15%.
    """
    if not await _check_admin_access(callback):
        return

    news_id = _extract_id(callback.data, r'approve_news_(\d+)$')
    if news_id is None:
        await callback.answer('❌ Неверный формат данных', show_alert=True)
        return

    admin_username = callback.from_user.username or callback.from_user.first_name

    async with get_database_service().session_context() as session:
        from database.repositories.news import NewsRepository
        from database.repositories.publishers import PublisherRepository
        from database.repositories.channels import ChannelRepository
        from services.bot.handlers.publisher import PublisherService
        from services.bot.bot import get_bot_instance_async

        news_repo = NewsRepository(session)
        news = await news_repo.get(news_id)

        if not news:
            await callback.answer(f'❌ Новость ID={news_id} не найдена', show_alert=True)
            return

        # Получаем активные каналы публикации с matching категорией
        publishers_repo = PublisherRepository(session)
        publishers = await publishers_repo.get_all(active_only=True)

        matching_publishers = [
            pub for pub in publishers
            if pub.category and pub.category.lower() == news.category.lower()
        ]

        published_count = 0
        first_publisher_channel_id = None

        if matching_publishers:
            logger.info(
                f"📢 Публикация сгенерированной новости ID={news_id} категории '{news.category}' "
                f"в {len(matching_publishers)} канал(а/ов):"
            )

            # Получаем бота для публикации (с ожиданием готовности)
            bot_instance = await get_bot_instance_async(wait=True, timeout=10.0)
            if not bot_instance:
                logger.error("❌ Бот не инициализирован. Публикация отменена.")
                return
            publisher_service = PublisherService(bot_instance)

            for pub in matching_publishers:
                try:
                    # Реальная публикация в канал через aiogram
                    published = await publisher_service.publish_to_channel(
                        channel_id=pub.channel_id,
                        text=news.text
                    )

                    if published:
                        logger.info(f"  ✅ Опубликовано в канал '{pub.title}' (ID={pub.id})")
                        published_count += 1
                        if first_publisher_channel_id is None:
                            first_publisher_channel_id = pub.channel_id
                    else:
                        logger.error(
                            f"  ❌ Не удалось опубликовать в канал '{pub.title}' (ID={pub.id})"
                        )

                except Exception as e:
                    logger.error(
                        f"  ❌ Ошибка публикации в канал '{pub.title}' (ID={pub.id}): {e}"
                    )
        else:
            logger.info(
                f"⚠️ Нет каналов с категорией '{news.category}'. "
                f"Новость будет отправлена только подписчикам."
            )

        # Одобряем новость
        await news_repo.approve(news_id, callback.from_user.id)

        # Увеличиваем рейтинг канала (первого канала публикации)
        if first_publisher_channel_id:
            channels_repo = ChannelRepository(session)
            await channels_repo.increase_trust_rating(first_publisher_channel_id, amount=0.15)

        # Обновляем новость
        news.tags = json.dumps(['одобрен_админом'], ensure_ascii=False)
        if published_count > 0:
            news.published_at = datetime.now(timezone.utc)
        await session.commit()

        # Отправка подписчикам (плановая новость, urgency=1)
        await _notify_subscribers(
            text=news.text,
            category=news.category,
            tags=json.loads(news.tags or '[]'),
            news_id=news_id,
            urgency=1,
        )

        await callback.answer(
            f'✅ Новость ID={news_id} одобрена и опубликована '
            f'в {published_count} канал(а/ов)',
            show_alert=True
        )

        await _update_moderation_message(
            callback,
            news_id,
            'Новость',
            admin_username,
            'одобрен_админом',
            'Рейтинг канала увеличен на 15%\nСтатус: Опубликовано'
        )

    logger.info(f"✅ Админ ID={callback.from_user.id} одобрил новость ID={news_id}")


@admin.callback_query(F.data.regexp(r'^reject_news_(\d+)$'))
async def reject_news_callback(callback: CallbackQuery):
    """
    Обработчик кнопки 'Отклонить' для сгенерированной новости.
    Снижает рейтинг канала на 30%.
    """
    if not await _check_admin_access(callback):
        return

    news_id = _extract_id(callback.data, r'reject_news_(\d+)$')
    if news_id is None:
        await callback.answer('❌ Неверный формат данных', show_alert=True)
        return

    admin_username = callback.from_user.username or callback.from_user.first_name

    async with get_database_service().session_context() as session:
        from database.repositories.news import NewsRepository
        from database.repositories.channels import ChannelRepository

        news_repo = NewsRepository(session)
        news = await news_repo.get(news_id)

        if not news:
            await callback.answer(f'❌ Новость ID={news_id} не найдена', show_alert=True)
            return

        # Отклоняем новость
        await news_repo.reject(news_id, callback.from_user.id)

        # Добавляем тэг
        news.tags = json.dumps(['отклонен_админом'], ensure_ascii=False)
        await session.commit()

        await callback.answer(f'❌ Новость ID={news_id} отклонена', show_alert=True)

        await _update_moderation_message(
            callback,
            news_id,
            'Новость',
            admin_username,
            'отклонен_админом',
            'Рейтинг канала снижен на 30%',
            action='rejected'
        )

    logger.info(f"❌ Админ ID={callback.from_user.id} отклонил новость ID={news_id}")


@admin.callback_query(F.data.regexp(r'^edit_news_(\d+)$'))
async def edit_news_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки 'Редактировать' для сгенерированной новости.
    Админ отправляет новый текст ответом на сообщение.
    """
    if not await _check_admin_access(callback):
        return

    news_id = _extract_id(callback.data, r'edit_news_(\d+)$')
    if news_id is None:
        await callback.answer('❌ Неверный формат данных', show_alert=True)
        return

    async with get_database_service().session_context() as session:
        from database.repositories.news import NewsRepository

        news_repo = NewsRepository(session)
        news = await news_repo.get(news_id)

        if not news:
            await callback.answer(f'❌ Новость ID={news_id} не найдена', show_alert=True)
            return

        # Устанавливаем статус и сохраняем ID админа
        news.moderation_status = 'editing'
        news.admin_id = callback.from_user.id
        await session.commit()

    await state.update_data(news_id=news_id, admin_telegram_id=callback.from_user.id)
    await state.set_state(EditNewsStates.waiting_for_text)

    await callback.answer('✏️ Отправьте новый текст новости ответом на это сообщение', show_alert=True)

    preview = news.text[:500] + ('...' if len(news.text) > 500 else '')
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f'✏️ **Редактирование новости ID={news_id}**\n\n'
            f'📝 **Текущий текст:**\n{preview}\n\n'
            f'👉 **Отправьте новый текст ответом на это сообщение.**\n'
            f'После отправки новость будет обновлена и опубликована.'
        )
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")

    logger.info(f"✏️ Админ ID={callback.from_user.id} начал редактирование новости ID={news_id}")


# =============================================================================
# Вспомогательные функции
# =============================================================================

async def _notify_subscribers(text: str, category: str, tags: list, news_id: int, urgency: int = 1):
    """
    Отправить новость подписчикам.

    Args:
        urgency: Срочность (1-5, >=4 — срочная новость)
    """
    try:
        from services.telegram.notification import NotificationService
        from services.bot.bot import get_bot_instance_async

        # Получаем бота из глобальной ссылки (с ожиданием готовности)
        bot = await get_bot_instance_async(wait=True, timeout=10.0)
        if not bot:
            logger.error("❌ Бот не инициализирован. Уведомление отменено.")
            return

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


async def _update_moderation_message(
    callback: CallbackQuery,
    item_id: int,
    item_type: str,
    admin_username: str,
    tag: str,
    extra_info: str,
    action: str = 'approved'
):
    """Обновить сообщение с кнопками модерации."""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            _build_moderation_response(item_type, item_id, action, admin_username, tag, extra_info)
        )
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение с кнопками: {e}")
