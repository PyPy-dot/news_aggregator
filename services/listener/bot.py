import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from collections import deque

import services.listener.config as conf
from services.ai_agent.agents import (
    CategorizerAgent,
    AnalystAgent,
    EditorAgent,
    ArchivistAgent,
)
from services.ai_agent.routers import EventBus
from services.ai_agent.events import Event, EventType
from services.ai_agent.vector_routers import register_vector_search_handlers
from database import async_session, RepositoryFactory
from database.repositories.channels import ChannelRepository
from services.listener.helpers import (
    get_channel_full,
    add_tg_post,
    update_channel_trust_rating,
    calculate_news_rate,
    add_event_context,
    add_generated_news,
    find_similar_events,
    find_similar_posts,
    update_post_category_confidence,
    add_channel_tag,
    mark_post_analyzed,
)
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

logger = logging.getLogger(__name__)

# Глобальные флаги для предотвращения дублирования
_event_handlers_registered = False
_event_bus_started = False
_processed_messages = set()  # Кэш для предотвращения дублирования постов

# Очередь для категоризации (пропускная способность 2 запроса)
_categorization_queue = deque(maxlen=10)
_queue_lock = asyncio.Lock()


class ListenerBot:
    client = TelegramClient(
        'userbot',
        api_id=conf.API_ID,
        api_hash=conf.API_HASH,
        connection_retries=10,
        retry_delay=5,
        timeout=30,
        use_ipv6=False
    )

    def __init__(self):
        global _event_handlers_registered, _event_bus_started

        # Агент-категорайзер (быстрый, для первичной классификации)
        self.categorizer_agent = CategorizerAgent(model='qwen2.5:7b')

        # Агенты АРА (Аналитик, Редактор, Архивариус)
        self.analyst_agent = AnalystAgent(model='qwen2.5:7b')
        self.editor_agent = EditorAgent(model='qwen2.5:7b')
        self.archivist_agent = ArchivistAgent(model='qwen2.5:7b')

        self.event_bus = EventBus(max_concurrency=3)

        # Factory для репозиториев (создаётся при необходимости)
        self._repo_factory = None

        # Регистрируем хендлеры только один раз
        if not _event_handlers_registered:
            self._setup_event_handlers()
            _event_handlers_registered = True

        # Запускаем шину событий только один раз
        if not _event_bus_started:
            # Регистрируем обработчики векторного поиска
            register_vector_search_handlers(self.event_bus)

            asyncio.create_task(self.event_bus.run())
            asyncio.create_task(self._process_categorization_queue())
            _event_bus_started = True

    @property
    def repo_factory(self) -> RepositoryFactory:
        """Получить фабрику репозиториев."""
        if self._repo_factory is None:
            self._repo_factory = RepositoryFactory(async_session())
        return self._repo_factory

    async def _process_categorization_queue(self):
        """
        Обработчик очереди категоризации.
        Пропускная способность: 2 запроса одновременно.
        """
        while True:
            if not _categorization_queue:
                await asyncio.sleep(0.5)
                continue

            # Берём задачу из очереди
            task = _categorization_queue.popleft()

            try:
                # Отправляем в AI-категорайзер
                ai_response = await self.categorizer_agent.send_question(task['prompt'])
                parsed = self._parse_ai_response(ai_response)

                if parsed['category'] == 'Реклама':
                    logger.info(f"🚫 Пропущено (реклама): {task['channel_id']}")
                    continue

                # Проверяем срочность
                urgency = int(parsed.get('urgency', 1))

                if urgency >= 4:
                    # Срочная новость (4-5) — особая обработка
                    logger.info(f"⚡ СРОЧНО! Срочность {urgency}, категория {parsed['category']}")

                    # Получаем канал для проверки is_trusted
                    channel = await get_channel_full(task['channel_id'])

                    # Сохраняем пост
                    post_id = await add_tg_post(
                        channel_id=task['channel_id'],
                        text=parsed['text'],
                        category=parsed['category'],
                        urgency=urgency
                    )

                    # Обновляем рейтинг канала
                    if channel:
                        await update_channel_trust_rating(task['channel_id'])

                    rate = await calculate_news_rate(channel, urgency) if channel else 50

                    logger.info(
                        f"✅ СРОЧНАЯ новость сохранена: {parsed['category']}, "
                        f"срочность {urgency}, рейтинг {rate}"
                    )

                    # Проверяем: доверенный источник?
                    if channel and channel.is_trusted:
                        # ДОВЕРЕННЫЙ ИСТОЧНИК → сразу публикация без модерации
                        # Не создаём запись в generated_news, только помечаем пост
                        logger.info(f"✅ ДОВЕРЕННЫЙ ИСТОЧНИК! Публикация без модерации (помечаем пост)")

                        # Помечаем пост как опубликованный напрямую (без АРА и generated_news)
                        from database import async_session, RepositoryFactory
                        async with async_session() as session:
                            factory = RepositoryFactory(session)
                            posts_repo = factory.posts()
                            publishers_repo = factory.publishers()

                            # Получаем publisher по умолчанию (первый активный)
                            publishers = await publishers_repo.get_all(active_only=True)
                            publisher_id = publishers[0].id if publishers else None

                            # Обновляем пост флагами
                            await posts_repo.mark_direct_publish(
                                post_id=post_id,
                                publisher_channel_id=publisher_id
                            )

                        logger.info(f"🚀 Пост ID={post_id} помечен как опубликованный напрямую (доверенный источник)")

                    else:
                        # НЕ доверенный источник → админу на срочную модерацию
                        logger.info(f"📬 Отправка админу на срочную модерацию")

                        # Генерируем новость для модерации
                        news_text = parsed['text']  # Пока без полной генерации
                        news_id = await add_generated_news(
                            source_post_ids=[post_id],
                            text=news_text,
                            category=parsed['category'],
                            tags=[parsed['category']],
                            source_event_ids=[],
                            moderation_status='pending'  # Ждёт модерации
                        )

                        # Срочное уведомление админу
                        await self._notify_admin(news_id, parsed['category'], urgency, is_urgent=True)
                        logger.info(f"📬 Админ уведомлён о СРОЧНОЙ новости ID={news_id}")
                else:
                    # Несрочная новость (1-3) — отправляется планировщику
                    logger.info(f"📊 В план: Срочность {urgency}, категория {parsed['category']}")

                    # Сохраняем пост
                    channel = await get_channel_full(task['channel_id'])
                    post_id = await add_tg_post(
                        channel_id=task['channel_id'],
                        text=parsed['text'],
                        category=parsed['category'],
                        urgency=urgency
                    )

                    # Обновляем рейтинг канала
                    if channel:
                        await update_channel_trust_rating(task['channel_id'])

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

            except Exception as e:
                logger.error(f"Ошибка обработки очереди: {e}")

    async def _add_to_queue(self, task: dict):
        """Добавляет задачу в очередь категоризации"""
        async with _queue_lock:
            _categorization_queue.append(task)
            logger.debug(f"📊 В очереди на категоризацию: {len(_categorization_queue)} задач")

    def _setup_event_handlers(self):
        """Регистрация обработчиков событий (вызывается один раз)"""

        @self.event_bus.on(EventType.GENERATE_NEWS)
        async def handle_generate_news(event: Event):
            """
            Генерация новости через АРА (Аналитик → Редактор → Архивариус).

            Логика:
            - Срочность 4-5 + is_trusted → уже одобрено, пропускаем АРА
            - Срочность 4-5 + не доверенный → админу на модерацию (без АРА)
            - Срочность 1-3 → планировщик → АРА → админ
            """
            payload = event.payload
            is_urgent = payload.get('urgent', False)

            # Проверяем: если это срочная новость от доверенного источника, она уже одобрена
            if is_urgent and payload.get('already_approved', False):
                logger.info(f"✅ Новость уже одобрена (доверенный источник), пропускаем АРА")
                return

            logger.info(f"{'⚡' if is_urgent else '📝'} Генерация новости через АРА: пост ID={payload.get('post_id')}")

            try:
                post_id = payload.get('post_id')
                text = payload.get('text', payload.get('original_text', ''))
                category = payload.get('category', 'Другое')
                urgency = int(payload.get('urgency', 1))

                # Шаг 1: Векторный поиск (БЕЗ LLM)
                similar_events = await find_similar_events(text[:200], category, limit=5)
                similar_posts = await find_similar_posts(text[:200], category, limit=10)

                logger.debug(f"Найдено {len(similar_events)} похожих событий, {len(similar_posts)} похожих постов")

                # Шаг 2: Аналитик
                analysis = await self.analyst_agent.analyze(
                    post_text=text,
                    similar_events=similar_events,
                    similar_posts=similar_posts,
                    preliminary_category=category
                )

                logger.info(f"🔍 Аналитик: категория={analysis['category']}, confidence={analysis['confidence']}")

                # Обновляем оценку категории в БД
                if post_id:
                    await update_post_category_confidence(post_id, analysis['confidence'])

                # Добавляем тэги каналу
                if payload.get('channel_id'):
                    for tag in analysis['post_tags'][:5]:
                        await add_channel_tag(payload['channel_id'], tag)

                # Шаг 3: Редактор
                event_context = payload.get('event_context')
                news = await self.editor_agent.generate_news(
                    post_text=text,
                    analysis=analysis,
                    event_context=event_context
                )

                logger.info(f"📰 Редактор: заголовок={news['title'][:50]}...")

                # Шаг 4: Архивариус
                existing_context = None
                if analysis.get('is_continuation') and analysis.get('related_event_id'):
                    # TODO: Загрузить существующий контекст по ID
                    pass

                context = await self.archivist_agent.create_context(
                    post_text=text,
                    generated_news=news,
                    analysis=analysis,
                    existing_context=existing_context
                )

                logger.info(f"📚 Архивариус: выжимка={context['embedding_text'][:50]}...")

                # Шаг 5: Сохранение в БД
                if post_id:
                    # Обновляем контекст события
                    event_id = payload.get('event_id')
                    if event_id:
                        await add_event_context(
                            post_id=post_id,
                            context_data=context['context_data'],
                            event_category=analysis['category'],
                            tags=context['tags'],
                            summary=context['embedding_text']
                        )

                # Сохраняем сгенерированную новость (на модерацию)
                source_post_ids = [post_id] if post_id else []
                source_event_ids = [payload.get('event_id')] if payload.get('event_id') else []

                news_id = await add_generated_news(
                    source_post_ids=source_post_ids,
                    text=news['text'],
                    category=analysis['category'],
                    tags=news['news_tags'],
                    source_event_ids=source_event_ids,
                    moderation_status='pending'  # На модерацию
                )

                logger.info(f"✅ Новость ID={news_id} отправлена на модерацию админу")

                # Отмечаем пост как обработанный Аналитиком
                if post_id:
                    await mark_post_analyzed(post_id, generated_news_id=news_id)
                    logger.info(f"📝 Пост ID={post_id} отмечен как обработанный Аналитиком")

                # Отправляем админу на модерацию
                await self._notify_admin(news_id, news['title'], analysis['category'])

            except Exception as e:
                logger.error(f"Ошибка генерации новости: {e}")

        @self.event_bus.on(EventType.NEW_NEWS)
        async def handle_new_news(event: Event):
            """Добавление новости в очередь на категоризацию"""
            payload = event.payload
            try:
                await self._add_to_queue({
                    'channel_id': payload['channel_id'],
                    'prompt': payload['prompt'],
                    'original_text': payload['original_text'],
                    'title': payload.get('title', ''),
                    'desc': payload.get('desc', '')
                })
            except Exception as e:
                logger.error(f"Ошибка добавления в очередь: {e}")

    async def _notify_admin(self, news_id: int, title: str, category: str, urgency: int = 1, is_urgent: bool = False):
        """
        Отправляет уведомление админу о новой новости на модерации.

        Args:
            news_id: ID новости
            title: Заголовок/категория новости
            category: Категория
            urgency: Срочность (1-5)
            is_urgent: Флаг срочности (для срочных новостей 4-5)
        """
        if is_urgent:
            logger.info(f"⚡ СРОЧНО АДМИНУ! Новость ID={news_id} на модерации — срочность {urgency}, '{title}'")
        else:
            logger.info(f"📬 Админу: Новость ID={news_id} на модерации — '{title[:50]}...' ({category})")

    def _parse_ai_response(self, response: str) -> dict:
        """
        Парсит ответ от AI, извлекая JSON.
        Обрабатывает различные форматы вывода.
        """
        cleaned = response.strip()
        cleaned = re.sub(r'^```json\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()
        cleaned = re.sub(r'^json\s*\n', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        json_match = re.search(r'\{[^{}]*"text"[^{}]*"category"[^{}]*"urgency"[^{}]*\}', cleaned, re.DOTALL)
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

    async def on_start(self):
        logger.info("🔌 Подключение к Telegram...")
        await self.client.connect()

        if not await self.client.is_user_authorized():
            logger.warning("⚠️ Требуется авторизация! Введите код из Telegram.")
            await self.client.send_code_request(conf.PHONE_NUMBER)
            code = input('Enter the code: ')
            try:
                await self.client.sign_in(conf.PHONE_NUMBER, code)
            except SessionPasswordNeededError:
                password = input('Password: ')
                await self.client.sign_in(password=password)

        me = await self.client.get_me()
        logger.info(f"✅ UserBot авторизован: @{me.username}")

        # Получаем каналы из БД через репозиторий
        logger.info("📚 Получение каналов из БД...")
        try:
            async with async_session() as session:
                channels_repo = ChannelRepository(session)
                channels_db = await channels_repo.get_all_channels()
                channel_ids = [ch.channel_id for ch in channels_db]
                logger.info(f"📋 Найдено каналов в БД: {len(channels_db)}")
        except Exception as e:
            logger.error(f"❌ Ошибка получения каналов: {e}")
            channel_ids = []

        logger.info(f"📡 Мониторим каналов: {len(channel_ids)}")

        if channel_ids:
            # Регистрируем обработчик для каждого канала
            for channel_id in channel_ids:
                self.client.add_event_handler(
                    self.handle_new_post,
                    events.NewMessage(chats=[channel_id])
                )
            logger.info(f"✅ Обработчик событий добавлен для {len(channel_ids)} каналов")
        else:
            logger.warning("⚠️ Нет каналов для мониторинга! Добавьте каналы через бота.")

    async def on_stop(self):
        await self.client.disconnect()
        logger.info("👋 UserBot остановлен")

    async def handle_new_post(self, event, *args, **kwargs):
        """Обработчик новых постов"""
        text = event.message.text
        if not text:
            logger.debug("Игнорируем пост без текста")
            return

        channel_id = event.chat_id
        message_id = event.message.id

        msg_key = f"{channel_id}:{message_id}"

        if msg_key in _processed_messages:
            logger.debug(f"Сообщение {msg_key} уже обработано, пропускаем")
            return

        _processed_messages.add(msg_key)

        if len(_processed_messages) > 1000:
            for _ in range(500):
                _processed_messages.pop()

        # Получаем канал через репозиторий
        async with async_session() as session:
            channels_repo = ChannelRepository(session)
            channel_obj = await channels_repo.get_by_telegram_id(channel_id)

        if channel_obj is None:
            logger.warning(f"Канал {channel_id} не найден в БД, игнорируем")
            return

        title = channel_obj.title
        desc = channel_obj.description

        logger.info(f"📬 Новый пост из: {title}")

        prompt = f'''## Название ресурса
{title}

## Описание ресурса
{desc}

## Текст новости
{text}'''

        await self.event_bus.emit(Event(
            type=EventType.NEW_NEWS,
            payload={
                'channel_id': channel_id,
                'prompt': prompt,
                'original_text': text,
                'title': title,
                'desc': desc
            }
        ))
