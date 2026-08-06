"""
Хендлеры для прямой генерации новостей админом.

Логика (FSM, 3 этапа):
1. Админ вводит описание новости (анонс, реклама и т.д.) + опционально фото/видео
2. Админ выбирает канал публикации из reply keyboard
3. Бот генерирует новость (только Editor) и публикует

Аналитик и Архивариус не участвуют — новость создаётся сразу.
"""

import logging
from datetime import datetime
from aiogram import F, Router
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from database import async_session, RepositoryFactory
from services.ai_agent.agents import EditorAgent
from services.util import load_prompt
from services.bot.handlers.keyboards import (
    create_direct_news_channel_kb,
    kb1,
)
from services.bot.handlers.states import DirectNewsStates

from database.repositories.users import UserRepository

logger = logging.getLogger(__name__)

router = Router(name='direct_news')


async def check_admin_access(message: Message) -> bool:
    """Проверить права администратора. Возвращает True если доступ разрешён."""
    async with async_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        if not user or user.role != 'admin':
            await message.answer('❌ У вас нет прав для генерации новостей', show_alert=True)
            return False
        return True


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
        "Для отмены нажмите /cancel",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(DirectNewsStates.waiting_for_description)


# === Этап 1: Обработка описания ===
@router.message(StateFilter(DirectNewsStates.waiting_for_description))
async def handle_description(message: Message, state: FSMContext):
    """Обработка описания новости — переход к этапу 2."""
    # Проверка прав не требуется — состояние устанавливается только после проверки
    description = message.text

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
    async with async_session() as session:
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

    # Показываем выбор канала — этап 2
    keyboard = create_direct_news_channel_kb(publishers)

    await message.answer(
        f"✅ **Описание получено**\n\n"
        f"📝 Текст: {description[:200]}...\n\n"
        "📢 **Этап 2: Выберите канал для публикации:**",
        reply_markup=keyboard,
    )
    await state.set_state(DirectNewsStates.waiting_for_channel)


# === Этап 2: Выбор канала и генерация ===
@router.message(StateFilter(DirectNewsStates.waiting_for_channel))
async def handle_channel_selection(message: Message, state: FSMContext):
    """Обработка выбора канала — этап 3: генерация и публикация."""
    channel_name = message.text

    # Получаем данные из состояния
    data = await state.get_data()
    description = data.get('description')
    media_info = data.get('media')

    if not description:
        await message.answer(
            "❌ Ошибка: нет описания новости. Начните заново с /direct_news",
            reply_markup=kb1,
        )
        await state.clear()
        return

    # Находим publisher по названию
    async with async_session() as session:
        factory = RepositoryFactory(session)
        publishers = await factory.publishers().get_all(active_only=True)

    # Ищем publisher по названию канала
    publisher = None
    for pub in publishers:
        if f"📢 {pub.title}" == channel_name or pub.title == channel_name:
            publisher = pub
            break

    if not publisher:
        await message.answer(
            "❌ Канал не найден. Пожалуйста, выберите канал из списка.",
            reply_markup=create_direct_news_channel_kb(publishers),
        )
        return

    # Генерируем новость через EditorAgent
    progress_msg = await message.answer("⏳ **Генерация новости...**\n\nЭто может занять 30-60 секунд.")

    try:
        editor = EditorAgent(model='qwen2.5:7b')

        # Загружаем промпт для прямой генерации
        system_prompt = load_prompt('direct_news_generator')

        # Формируем промпт с описанием
        prompt = f"""## Описание от админа
{description}

Сгенерируй пост для Telegram-канала на основе этого описания.
"""
        # Отправляем системный промпт первым сообщением
        editor.message_list = [{'role': 'system', 'content': system_prompt}]
        response = await editor.send_question(prompt)

        # Парсим ответ
        news_data = editor.parse_json_response(response, required_fields=['title', 'text', 'summary'])

        title = news_data.get('title', 'Без заголовка')
        text = news_data.get('text', description)
        summary = news_data.get('summary', '')
        # Промпт возвращает 'news_tags', но для совместимости проверяем оба поля
        tags = news_data.get('news_tags', news_data.get('tags', []))

        # Формируем текст для публикации
        publish_text = f"**{title}**\n\n{text}"
        if summary:
            publish_text += f"\n\n_Саммари: {summary}_"
        if media_info and media_info.get('caption'):
            publish_text += f"\n\n{media_info['caption']}"

        # Сохраняем в БД
        async with async_session() as session:
            factory = RepositoryFactory(session)
            news_repo = factory.news()

            news = await news_repo.create_news(
                text=publish_text,
                category='direct',  # Категория для прямых новостей
                source_post_ids=[],  # Нет исходных постов
                source_event_ids=[],
                tags=tags,
                moderation_status='approved',  # Сразу одобрено
                bypass_ara=True,  # Обошло АРА
                publisher_channel_id=publisher.id,
            )

        # Обновляем статус публикации
        async with async_session() as session:
            factory = RepositoryFactory(session)
            news_repo = factory.news()
            await news_repo.mark_published(news.id, publisher.id, datetime.now())

        # Публикуем в канал через aiogram Bot
        try:
            # Импортируем bot внутри функции для избежания циклического импорта
            from services.bot.bot import bot
            from aiogram.types import FSInputFile
            import os

            # Получаем media из состояния (если есть)
            data = await state.get_data()
            media_info = data.get('media')

            if media_info and media_info.get('file_id'):
                # Скачиваем медиа и отправляем с ним
                file_id = media_info['file_id']
                file_path = await bot.get_file(file_id)
                local_path = f"downloads/{file_id}"

                # Создаем директорию для загрузок
                os.makedirs("downloads", exist_ok=True)

                # Скачиваем файл
                await bot.download_file(file_path.file_path, local_path)

                if media_info['type'] == 'photo':
                    photo = FSInputFile(local_path)
                    await bot.send_photo(
                        chat_id=publisher.channel_id,
                        photo=photo,
                        caption=publish_text,
                        parse_mode='Markdown'
                    )
                elif media_info['type'] == 'video':
                    video = FSInputFile(local_path)
                    await bot.send_video(
                        chat_id=publisher.channel_id,
                        video=video,
                        caption=publish_text,
                        parse_mode='Markdown'
                    )

                # Удаляем временный файл
                os.remove(local_path)
                logger.info(f"📢 Новость с медиа опубликована в канал {publisher.title}")
            else:
                # Отправляем только текст
                await bot.send_message(
                    chat_id=publisher.channel_id,
                    text=publish_text,
                    parse_mode='Markdown'
                )
                logger.info(f"📢 Новость опубликована в канал {publisher.title}")

        except Exception as publish_error:
            logger.error(f"❌ Ошибка публикации через bot: {publish_error}")
            # Не прерываем процесс, новость уже сохранена в БД

        await progress_msg.delete()
        await message.answer(
            f"✅ **Новость сгенерирована и опубликована!**\n\n"
            f"📢 Канал: {publisher.title}\n"
            f"📝 Заголовок: {title}\n"
            f"🏷️ Теги: {', '.join(tags)}\n"
            f"🆔 ID в БД: {news.id}\n\n"
            "Новость сохранена в базе данных и отправлена в канал.",
            reply_markup=kb1,
        )

    except Exception as e:
        logger.error(f"Ошибка генерации новости: {e}", exc_info=True)
        await progress_msg.delete()
        await message.answer(
            f"❌ **Ошибка при генерации новости**\n\n"
            f"Попробуйте ещё раз или обратитесь к разработчикам.\n\n"
            f"Детали: {str(e)[:500]}",
            reply_markup=kb1,
        )

    await state.clear()


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
