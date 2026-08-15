"""
Хендлеры для прямой генерации новостей админом.

Логика (FSM, 3 этапа):
1. Админ вводит описание новости (анонс, реклама и т.д.) + опционально фото/видео
2. Админ выбирает канал публикации из reply keyboard
3. Бот генерирует новость (только Editor) и публикует

Аналитик и Архивариус не участвуют — новость создаётся сразу.
"""

import json
import logging
from datetime import datetime
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from services.database import get_database_service
from database import RepositoryFactory
from services.ai_agent.agents import EditorAgent
from services.util import load_prompt
from services.bot.handlers.keyboards import (
    kb1,
    create_direct_news_description_inline_kb,
)
from services.bot.handlers.states import DirectNewsStates

from services.bot.handlers.access import check_admin_access
from services.core.llm_provider import LLMProviderError

logger = logging.getLogger(__name__)

router = Router(name='direct_news')


# === Этап 1: Начало — команда /direct_news или кнопка ===
@router.message(F.text == '✍️ Прямая генерация новости')
@router.message(F.text == '/direct_news')
async def start_direct_news(message: Message, state: FSMContext):
    """Начать процесс прямой генерации новости — этап 1."""
    if not await check_admin_access(message):
        return

    await state.clear()
    await message.answer(
        "✍️ **Прямая генерация новости — Этап 1**\n\n"
        "**Введите описание новости**\n\n"
        "Отправьте текст, который нужно преобразовать в новость.\n"
        "Это может быть:\n"
        "- Анонс мероприятия\n"
        "- Рекламный материал\n"
        "- Краткая сводка\n"
        "- Любая другая информация\n\n"
        "📎 **Фото/видео:** Если нужно прикрепить медиа, отправьте его вместе с текстом.\n\n"
        "Для отмены нажмите /cancel или кнопку ниже",
        reply_markup=create_direct_news_description_inline_kb(),
    )
    await state.set_state(DirectNewsStates.waiting_for_description)


# === Обработчик inline-кнопки "Назад в меню" ===
@router.callback_query(F.data == 'direct_news_back_to_menu')
async def back_to_menu_from_direct_news(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню из режима прямой генерации."""
    if not await check_admin_access(callback):
        return

    await state.clear()
    await callback.answer()
    await callback.message.answer(
        "🔙 Возврат в главное меню.",
        reply_markup=kb1,  # Главное меню админа
    )


# === Этап 1: Обработка описания ===
@router.message(StateFilter(DirectNewsStates.waiting_for_description))
async def handle_description(message: Message, state: FSMContext):
    """Обработка описания новости — переход к этапу 2."""
    try:
        # Проверка прав не требуется — состояние устанавливается только после проверки

        # Получаем описание из текста или caption к медиа
        description = message.text or message.caption

        # Если нет ни текста, ни caption — запрашиваем описание
        if not description:
            await message.answer(
                "⚠️ **Пустое описание**\n\n"
                "Пожалуйста, отправьте текст описания новости или добавьте подпись к фото/видео.\n\n"
                "Для отмены нажмите /cancel"
            )
            return

        # Сохраняем описание в состоянии
        await state.update_data(description=description)

        # Если есть фото/видео, сохраняем
        media_info = None
        if message.photo:
            media_info = {
                'type': 'photo',
                'file_id': message.photo[-1].file_id,
                'caption': message.caption,
            }
        elif message.video:
            media_info = {
                'type': 'video',
                'file_id': message.video.file_id,
                'caption': message.caption,
            }

        if media_info:
            await state.update_data(media=media_info)

        # Получаем список каналов для выбора
        async with get_database_service().session_context() as session:
            factory = RepositoryFactory(session)
            publishers = await factory.publishers().get_all(active_only=True)

        if not publishers:
            await message.answer(
                "❌ Нет доступных каналов для публикации.\n"
                "Сначала добавьте каналы через /publishers",
                reply_markup=kb1,
            )
            await state.clear()
            return

        # Сохраняем описание и медиа в состоянии
        await state.update_data(description=description)
        if media_info:
            await state.update_data(media=media_info)

    except Exception as e:
        # Ошибка — очищаем состояние и сообщаем пользователю
        logger.error(f"❌ Ошибка в handle_description: {type(e).__name__}: {e}", exc_info=True)
        await state.clear()
        await message.answer(
            f"❌ **Ошибка при обработке описания**\n\n"
            f"Тип ошибки: `{type(e).__name__}`\n"
            f"Состояние сброшено. Попробуйте снова.\n\n"
            f"Для возврата в меню нажмите /start",
            parse_mode='Markdown'
        )

    # Показываем превью описания
    desc_preview = description[:200] + '...' if len(description) > 200 else description

    # Создаём клавиатуру с вариантами отправки и каналами
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    # Кнопки способов отправки
    send_buttons = [
        [InlineKeyboardButton(text='🤖 Бот (всем юзерам)', callback_data='direct_send_bot')],
        [InlineKeyboardButton(text='📢 Все каналы', callback_data='direct_send_channels')],
        [InlineKeyboardButton(text='🌐 Везде (бот + каналы)', callback_data='direct_send_everywhere')],
    ]

    # Кнопки каналов
    channel_buttons = [
        [InlineKeyboardButton(text=f"📢 {p.title}", callback_data=f'direct_channel_{p.id}')]
        for p in publishers
    ]

    # Кнопка отмены (обёрнута в список списков для правильной структуры)
    cancel_button = [[InlineKeyboardButton(text='🔙 Отмена', callback_data='direct_cancel')]]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=send_buttons + channel_buttons + cancel_button
    )

    await message.answer(
        f"✅ **Описание получено**\n\n"
        f"📝 Текст: {desc_preview}\n\n"
        f"📢 **Этап 2: Выберите способ отправки или конкретный канал:**\n\n"
        f"• **Бот** — отправить всем подписчикам (кроме админов)\n"
        f"• **Все каналы** — опубликовать во все каналы\n"
        f"• **Везде** — отправить подписчикам и в каналы\n"
        f"• **Конкретный канал** — выберите из списка ниже",
        reply_markup=keyboard,
    )

    await state.set_state(DirectNewsStates.waiting_for_channel)


# === Этап 2: Выбор канала и генерация — обработчики callback ===
@router.callback_query(F.data == 'direct_send_bot')
async def direct_send_bot_callback(callback: CallbackQuery, state: FSMContext):
    """Отправить новость через бота всем подписчикам (кроме админов)."""
    await _process_direct_send(callback, state, send_to_bot=True, send_to_channels=False)


@router.callback_query(F.data == 'direct_send_channels')
async def direct_send_channels_callback(callback: CallbackQuery, state: FSMContext):
    """Отправить новость во все каналы."""
    await _process_direct_send(callback, state, send_to_bot=False, send_to_channels=True)


@router.callback_query(F.data == 'direct_send_everywhere')
async def direct_send_everywhere_callback(callback: CallbackQuery, state: FSMContext):
    """Отправить новость везде (бот + каналы)."""
    await _process_direct_send(callback, state, send_to_bot=True, send_to_channels=True)


@router.callback_query(F.data == 'direct_cancel')
async def direct_cancel_callback(callback: CallbackQuery, state: FSMContext):
    """Отменить прямую генерацию."""
    await state.clear()
    await callback.answer('❌ Генерация отменена')
    await callback.message.edit_text('❌ Генерация новости отменена.')


async def _process_direct_send(
    callback: CallbackQuery,
    state: FSMContext,
    send_to_bot: bool,
    send_to_channels: bool
):
    """Обработать отправку новости."""
    try:
        data = await state.get_data()
        description = data.get('description')
        media_info = data.get('media')

        if not description:
            await callback.answer('❌ Ошибка: нет описания новости', show_alert=True)
            await state.clear()
            return

        await callback.answer('⏳ Генерация новости...')

        # Получаем всех publishers
        async with get_database_service().session_context() as session:
            factory = RepositoryFactory(session)
            publishers = await factory.publishers().get_all(active_only=True)

        if not publishers:
            await callback.answer('❌ Нет доступных каналов', show_alert=True)
            await state.clear()
            return

        # Генерируем новость
        news_data = await _generate_news_content(description)
        title = news_data.get('title', 'Без заголовка')
        text = news_data.get('text', description)
        tags = news_data.get('news_tags', news_data.get('tags', []))
        publish_text = _format_publish_text(title, text, media_info)

        # Сохраняем в БД
        news = await _save_news_to_db(publish_text, tags, publisher_id=None)
        news_id = news.id

        results = {'bot': 0, 'channels': 0}

        # Отправка через бота
        if send_to_bot:
            results['bot'] = await _send_to_subscribers(publish_text, title, tags, news_id)

        # Публикация в каналы
        if send_to_channels:
            for publisher in publishers:
                try:
                    await _publish_to_channel(publish_text, media_info, publisher)
                    results['channels'] += 1
                except Exception as e:
                    logger.error(f"Ошибка публикации в канал {publisher.title}: {e}")

        # Обновляем статус публикации (mark_published вместо удалённого mark_analyzed)
        async with get_database_service().session_context() as session:
            factory = RepositoryFactory(session)
            news_repo = factory.news()
            await news_repo.mark_published(news_id, published_at=datetime.now())  # Отмечаем как опубликованную

        # Сообщение об успехе
        await _send_direct_success_message(
            callback.message,
            title,
            tags,
            news_id,
            send_to_bot,
            send_to_channels,
            results
        )

        await state.clear()

    except LLMProviderError as e:
        # Ошибка LLM провайдера — логируем детали и сообщаем пользователю
        logger.error(f"❌ Ошибка LLM провайдера: {e}", exc_info=True)
        await state.clear()
        await callback.message.answer(
            f"❌ **Ошибка генерации новости**\n\n"
            f"Проблема с AI-провайдером: `{type(e).__name__}`\n"
            f"Детали: `{str(e)[:200]}`\n\n"
            f"Проверьте, что Ollama запущен и доступен.\n"
            f"Состояние сброшено. Попробуйте снова позже.\n\n"
            f"Для возврата в меню нажмите /start",
            parse_mode='Markdown'
        )

    except Exception as e:
        # Критическая ошибка — очищаем состояние и сообщаем пользователю
        logger.error(f"❌ Критическая ошибка в прямой генерации: {type(e).__name__}: {e}", exc_info=True)
        await state.clear()
        await callback.message.answer(
            f"❌ **Ошибка при генерации новости**\n\n"
            f"Тип ошибки: `{type(e).__name__}`\n"
            f"Состояние сброшено. Попробуйте снова или обратитесь к разработчику.\n\n"
            f"Для возврата в меню нажмите /start",
            parse_mode='Markdown'
        )


# === Этап 2: Выбор конкретного канала (callback) ===
@router.callback_query(F.data.startswith('direct_channel_'))
async def direct_channel_callback(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора конкретного канала."""
    # Извлекаем publisher_id из callback_data
    publisher_id = int(callback.data.replace('direct_channel_', ''))

    # Получаем данные из состояния
    data = await state.get_data()
    description = data.get('description')
    media_info = data.get('media')

    if not description:
        await callback.answer('❌ Ошибка: нет описания новости', show_alert=True)
        await state.clear()
        return

    # Находим publisher по ID
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        publishers = await factory.publishers().get_all(active_only=True)

    publisher = None
    for pub in publishers:
        if pub.id == publisher_id:
            publisher = pub
            break

    if not publisher:
        await callback.answer('❌ Канал не найден', show_alert=True)
        return

    await callback.answer('⏳ Генерация новости...')
    # Генерируем и публикуем новость
    await _generate_and_publish(callback.message, state, description, media_info, publisher)

    await state.clear()


async def _generate_and_publish(
    message: Message,
    state: FSMContext,
    description: str,
    media_info: dict | None,
    publisher
):
    """Сгенерировать новость и опубликовать в канал."""
    progress_msg = await message.answer("⏳ **Генерация новости...**\n\nЭто может занять 30-60 секунд.")

    news_id = None
    try:
        # Генерация через EditorAgent
        news_data = await _generate_news_content(description)
        title = news_data.get('title', 'Без заголовка')
        text = news_data.get('text', description)
        tags = news_data.get('news_tags', news_data.get('tags', []))

        # Формируем текст для публикации
        publish_text = _format_publish_text(title, text, media_info)

        # Сохраняем в БД
        news = await _save_news_to_db(publish_text, tags, publisher.id)
        news_id = news.id

        # Обновляем статус публикации
        async with get_database_service().session_context() as session:
            factory = RepositoryFactory(session)
            news_repo = factory.news()
            await news_repo.mark_published(news.id, publisher.id, datetime.now())

        # Публикуем в канал
        await _publish_to_channel(publish_text, media_info, publisher)

        await progress_msg.delete()
        await _send_success_message(message, publisher, title, tags, news_id)

    except Exception as e:
        logger.error(f"Ошибка генерации новости: {e}", exc_info=True)
        await progress_msg.delete()
        await _send_error_message(message, e, news_id)


async def _generate_news_content(description: str) -> dict:
    """Сгенерировать контент новости через EditorAgent."""
    from config.settings import settings

    editor = EditorAgent(model=settings.agent_model)
    system_prompt = load_prompt('direct_news_generator')

    prompt = f"""## Описание от админа
{description}

Сгенерируй пост для Telegram-канала на основе этого описания.
"""
    editor.message_list = [{'role': 'system', 'content': system_prompt}]
    response = await editor.send_question(prompt)

    return editor.parse_json_response(response, required_fields=['title', 'text'])


def _format_publish_text(title: str, text: str, media_info: dict | None) -> str:
    """Сформировать текст для публикации."""
    publish_text = f"**{title}**\n\n{text}"

    if media_info and media_info.get('caption'):
        publish_text += f"\n\n{media_info['caption']}"

    return publish_text


async def _save_news_to_db(text: str, tags: list, publisher_id: int):
    """Сохранить новость в БД."""
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        news_repo = factory.news()

        return await news_repo.create_news(
            text=text,
            category='direct',
            source_event_ids=[],
            tags=tags,
            moderation_status='approved',
            bypass_ara=True,
            publisher_channel_id=publisher_id,
        )


async def _publish_to_channel(publish_text: str, media_info: dict | None, publisher):
    """Опубликовать новость в канал."""
    from services.bot.bot import get_bot_instance_async

    # Получаем бота с ожиданием готовности (timeout 10 сек)
    bot_instance = await get_bot_instance_async(wait=True, timeout=10.0)

    if not bot_instance:
        logger.error("❌ Бот не инициализирован после ожидания. Публикация отменена.")
        raise RuntimeError("Бот не инициализирован. Попробуйте позже.")

    if media_info and media_info.get('file_id'):
        await _publish_with_media(bot_instance, media_info, publish_text, publisher)
    else:
        await bot_instance.send_message(
            chat_id=publisher.channel_id,
            text=publish_text,
            parse_mode='Markdown'
        )
        logger.info(f"📢 Новость опубликована в канал {publisher.title}")


async def _publish_with_media(bot_instance, media_info: dict, publish_text: str, publisher):
    """Опубликовать новость с медиа (фото/видео)."""
    import os

    file_id = media_info['file_id']
    file_path = await bot_instance.get_file(file_id)
    local_path = f"downloads/{file_id}"

    os.makedirs("downloads", exist_ok=True)
    await bot_instance.download_file(file_path.file_path, local_path)

    try:
        if media_info['type'] == 'photo':
            photo = FSInputFile(local_path)
            await bot_instance.send_photo(
                chat_id=publisher.channel_id,
                photo=photo,
                caption=publish_text,
                parse_mode='Markdown'
            )
        elif media_info['type'] == 'video':
            video = FSInputFile(local_path)
            await bot_instance.send_video(
                chat_id=publisher.channel_id,
                video=video,
                caption=publish_text,
                parse_mode='Markdown'
            )
        logger.info(f"📢 Новость с медиа опубликована в канал {publisher.title}")
    finally:
        os.remove(local_path)


async def _send_success_message(message: Message, publisher, title: str, tags: list, news_id: int):
    """Отправить сообщение об успешной публикации."""
    await message.answer(
        f"✅ **Новость сгенерирована и опубликована!**\n\n"
        f"📢 Канал: {publisher.title}\n"
        f"📝 Заголовок: {title}\n"
        f"🏷️ Теги: {', '.join(tags)}\n"
        f"🆔 ID в БД: {news_id}\n\n"
        "Новость сохранена в базе данных и отправлена в канал.",
        reply_markup=kb1,
    )


async def _send_error_message(message: Message, error: Exception, news_id: int | None = None):
    """Отправить сообщение об ошибке."""
    news_info = f"\n🆔 Новость ID={news_id} сохранена в БД" if news_id else ""
    await message.answer(
        f"❌ **Ошибка при генерации новости**{news_info}\n\n"
        f"Попробуйте ещё раз или обратитесь к разработчикам.\n\n"
        f"Детали: {str(error)[:500]}",
        reply_markup=kb1,
    )


async def _send_to_subscribers(text: str, title: str, tags: list, news_id: int) -> int:
    """
    Отправить новость всем подписчикам через бота (кроме админов).

    Returns:
        Количество отправленных уведомлений
    """
    from database.repositories.users import UserRepository
    from services.database import get_database_service
    from services.util import decrypt_user_id
    from sqlalchemy import select
    from database.models import User

    db_service = get_database_service()
    sent_count = 0

    async with db_service.session_context() as session:
        user_repo = UserRepository(session)

        # Получаем всех пользователей с активной подпиской (кроме админов)
        result = await session.execute(
            select(User).where(
                (User.has_subscription == True) &
                (User.role != 'admin')
            )
        )
        subscribers = result.scalars().all()

        for subscriber in subscribers:
            try:
                # Явно обновляем объект из БД чтобы получить актуальные предпочтения
                await session.refresh(subscriber)

                telegram_id = decrypt_user_id(subscriber.user_id_encrypted)

                # Проверяем предпочтения (теперь актуальные)
                user_categories = json.loads(subscriber.preferred_categories or '[]')
                user_tags = json.loads(subscriber.preferred_tags or '[]')

                # Простая логика: отправляем всем подписчикам
                # Можно добавить фильтрацию по категориям/тэгам
                message_text = (
                    f"📰 <b>Новость для вас!</b>\n\n"
                    f"📁 <b>Категория:</b> direct\n"
                    f"🏷️ <b>Тэги:</b> {', '.join(tags[:5]) if tags else 'прямая генерация'}\n\n"
                    f"{text[:500]}{'...' if len(text) > 500 else ''}"
                )

                from services.bot.bot import get_bot_instance_async
                bot_instance = await get_bot_instance_async(wait=False, timeout=5.0)
                if bot_instance:
                    await bot_instance.send_message(
                        chat_id=telegram_id,
                        text=message_text,
                        parse_mode='HTML'
                    )
                    sent_count += 1
                    logger.info(f"✅ Отправлено подписчику ID={telegram_id}")

            except Exception as e:
                logger.warning(f"Ошибка отправки подписчику: {e}")

    return sent_count


async def _send_direct_success_message(
    message: Message,
    title: str,
    tags: list,
    news_id: int,
    send_to_bot: bool,
    send_to_channels: bool,
    results: dict
):
    """Отправить сообщение об успешной прямой генерации."""
    destinations = []
    if send_to_bot:
        destinations.append(f"🤖 Бот: {results['bot']} подписчикам")
    if send_to_channels:
        destinations.append(f"📢 Каналы: {results['channels']} каналов")

    await message.answer(
        f"✅ **Новость сгенерирована и отправлена!**\n\n"
        f"📝 Заголовок: {title}\n"
        f"🏷️ Теги: {', '.join(tags)}\n"
        f"🆔 ID в БД: {news_id}\n\n"
        f"📬 **Куда отправлено:**\n"
        f"{'\n'.join(destinations)}\n\n"
        "Новость сохранена в базе данных.",
        reply_markup=kb1,
    )


# === Отмена ===
@router.message(F.text == '/cancel')
@router.message(F.text == '❌ Отмена')
async def cancel_direct_news(message: Message, state: FSMContext):
    """Отмена прямой генерации."""
    # Проверка прав не требуется — состояние устанавливается только после проверки
    await state.clear()
    await message.answer(
        "❌ Генерация новости отменена.",
        reply_markup=kb1,
    )


# === Назад в главное меню ===
@router.message(F.text == '🔙 Назад')
async def back_to_menu(message: Message, state: FSMContext):
    """Вернуться в главное меню."""
    # Проверка прав не требуется — состояние устанавливается только после проверки
    await state.clear()
    await message.answer(
        "🔙 Возврат в главное меню.",
        reply_markup=kb1,
    )
