"""
News Orchestrator — единый координатор для обработки новостей.

Использует паттерн Strategy для делегирования обработки:
- UrgentNewsStrategy — срочные новости (4-5)
- ScheduledNewsStrategy — плановые новости (1-3)
- TrustedSourceStrategy — доверенные источники

Корректное управление жизненным циклом шины событий.
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any

from database import RepositoryFactory
from services.ai_agent.routers import EventBus
from services.ai_agent.events import EventType, Event
from services.ai_agent.vector_routers import register_vector_search_handlers
from services.ai_agent.agents import DirectNewsEditorAgent, ArchivistAgent
from services.telegram.notification import NotificationService
from services.news.strategies.base import NewsProcessingStrategy
from services.news.strategies.urgent import UrgentNewsStrategy
from services.news.strategies.scheduled import ScheduledNewsStrategy
from services.news.strategies.trusted import TrustedSourceStrategy
from services.news.generation import NewsGenerationService
from services.news.context import EventContextService
from services.news.helpers import add_generated_news

logger = logging.getLogger(__name__)


class NewsOrchestrator:
    """
    Координатор обработки новостей.

    Делегирует обработку стратегиям на основе приоритета новости.

    Attributes:
        repo_factory: Фабрика репозиториев
        event_bus: Шина событий
        notification_service: Сервис уведомлений
        vector_search_service: Сервис векторного поиска
        strategies: Стратегии обработки
    """

    def __init__(
        self,
        repo_factory: RepositoryFactory,
        notification_service: Optional[NotificationService] = None,
        vector_search_service: Optional[Any] = None,
    ) -> None:
        """
        Инициализация координатора.

        Args:
            repo_factory: Фабрика репозиториев
            notification_service: Сервис уведомлений
            vector_search_service: Сервис векторного поиска (опционально)
        """
        self.repo_factory = repo_factory
        # Получаем NotificationService из аргумента
        if notification_service is None:
            self.notification_service = None
            logger.debug("⚠️ NotificationService не передан, будет установлен позже")
        else:
            self.notification_service = notification_service

        # Получаем VectorSearchService из аргумента
        self.vector_search_service = vector_search_service

        # Инициализация шины событий
        self.event_bus = EventBus(max_concurrency=3)
        register_vector_search_handlers(self.event_bus)

        # Инициализация стратегий
        self._strategies: Dict[str, NewsProcessingStrategy] = {}
        self._init_strategies()

        # Сервисы (ленивая инициализация)
        self._generation_service: Optional[NewsGenerationService] = None
        self._context_service: Optional[EventContextService] = None

        # Задачи
        self._event_bus_task: Optional[asyncio.Task] = None

        # Флаги
        self._running = False

    def _init_strategies(self) -> None:
        """Инициализировать стратегии обработки."""
        posts_repo = self.repo_factory.posts()
        events_repo = self.repo_factory.events()
        news_repo = self.repo_factory.news()
        publishers_repo = self.repo_factory.publishers()

        self._strategies = {
            'urgent': UrgentNewsStrategy(
                posts_repo=posts_repo,
                events_repo=events_repo,
                news_repo=news_repo,
                publishers_repo=publishers_repo,
                event_bus=self.event_bus,
            ),
            'scheduled': ScheduledNewsStrategy(
                posts_repo=posts_repo,
                events_repo=events_repo,
                news_repo=news_repo,
                publishers_repo=publishers_repo,
                event_bus=self.event_bus,
            ),
            'trusted': TrustedSourceStrategy(
                posts_repo=posts_repo,
                events_repo=events_repo,
                news_repo=news_repo,
                publishers_repo=publishers_repo,
                event_bus=self.event_bus,
            ),
        }
        logger.debug(f"✅ Инициализировано стратегий: {len(self._strategies)}")

    def _get_generation_service(self) -> NewsGenerationService:
        """Получить сервис генерации новостей (ленивая инициализация)."""
        if self._generation_service is None:
            posts_repo = self.repo_factory.posts()
            events_repo = self.repo_factory.events()
            news_repo = self.repo_factory.news()
            channels_repo = self.repo_factory.channels()

            self._generation_service = NewsGenerationService(
                posts_repo=posts_repo,
                events_repo=events_repo,
                news_repo=news_repo,
                channels_repo=channels_repo,
                notification_service=self.notification_service,
            )
        return self._generation_service

    def _get_context_service(self) -> EventContextService:
        """Получить сервис управления контекстом (ленивая инициализация)."""
        if self._context_service is None:
            events_repo = self.repo_factory.events()
            posts_repo = self.repo_factory.posts()

            self._context_service = EventContextService(
                events_repo=events_repo,
                posts_repo=posts_repo,
                vector_search_service=self.vector_search_service,
            )
        return self._context_service

    def parse_json_response(self, response: str, required_fields: list[str] = None) -> dict:
        """
        Распарсить JSON ответ от AI агента.

        Args:
            response: Строка с ответом (возможно с markdown)
            required_fields: Список обязательных полей для проверки

        Returns:
            Распарсенный dict

        Raises:
            ValueError: Если JSON не распарсился или нет обязательных полей
        """
        import re
        # Извлекаем JSON из markdown блока ```json ... ``` или ``` ... ```
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Пробуем найти JSON без markdown обёртки
            json_match = re.search(r'\{.*?\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Не удалось распарсить JSON: {e}")

        # Проверяем обязательные поля
        if required_fields:
            missing = [f for f in required_fields if f not in data]
            if missing:
                raise ValueError(f"Отсутствуют обязательные поля: {missing}")

        return data

    def _get_strategy(self, priority: str) -> NewsProcessingStrategy:
        """
        Получить стратегию по приоритету.

        Args:
            priority: Приоритет ('urgent', 'scheduled', 'trusted')

        Returns:
            Стратегия обработки

        Raises:
            ValueError: Если стратегия не найдена
        """
        if priority not in self._strategies:
            raise ValueError(f"Неизвестный приоритет: {priority}")
        return self._strategies[priority]

    def _determine_priority(self, urgency: int, is_trusted_source: bool) -> str:
        """
        Определить приоритет обработки.

        Args:
            urgency: Уровень срочности (1-5)
            is_trusted_source: Флаг доверенного источника

        Returns:
            Приоритет ('urgent', 'scheduled', 'trusted')
        """
        if is_trusted_source and urgency >= 4:
            return 'trusted'
        elif urgency >= 4:
            return 'urgent'
        else:
            return 'scheduled'

    async def process_news(
        self,
        post_id: int,
        text: str,
        category: str,
        urgency: int,
        channel_id: int,
        is_trusted_source: bool = False,
    ) -> None:
        """
        Обработать новость через стратегию.

        Args:
            post_id: ID поста
            text: Текст новости
            category: Категория
            urgency: Срочность (1-5)
            channel_id: ID канала
            is_trusted_source: Флаг доверенного источника
        """
        if not self._running:
            logger.warning("⚠️ NewsOrchestrator не запущен, новость не обработана")
            return

        # Определяем приоритет и выбираем стратегию
        priority = self._determine_priority(urgency, is_trusted_source)
        strategy = self._get_strategy(priority)

        logger.info(
            f"📰 Обработка новости ID={post_id}, стратегия={priority}, "
            f"срочность={urgency}, доверенный={is_trusted_source}"
        )

        # Делегируем обработку стратегии
        await strategy.process(
            post_id=post_id,
            text=text,
            category=category,
            urgency=urgency,
            channel_id=channel_id,
        )

    async def process_pending_news_batch(self, hours: int = 48) -> int:
        """
        Обработать пакет новостей из всех источников, ожидающих обработки.

        Собирает из трёх таблиц:
        - posts (Telegram): checked_at=False
        - rss_news: processed=False + category IS NOT NULL
        - web_news: processed=False + category IS NOT NULL

        Группирует по категориям → Editor → Archivist → generated_news.

        Args:
            hours: За сколько часов искать новости

        Returns:
            Количество обработанных новостей
        """
        if not self._running:
            logger.warning("⚠️ NewsOrchestrator не запущен, обработка отменена")
            return 0

        # Собираем из всех источников
        all_items = await self._collect_unprocessed_all_sources(hours=hours)

        if not all_items:
            logger.info("📭 Нет новостей для обработки (все уже обработаны)")
            return 0

        logger.info(
            f"📊 Найдено {len(all_items)} новостей для обработки "
            f"(tg={sum(1 for i in all_items if i['source_type']=='telegram')}, "
            f"rss={sum(1 for i in all_items if i['source_type']=='rss')}, "
            f"web={sum(1 for i in all_items if i['source_type']=='web')})"
        )

        # ГРУППИРОВКА ПО КАТЕГОРИЯМ
        categories = {}
        for item in all_items:
            cat = item.get('category') or 'Общее'
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(item)

        logger.info(f"📁 Категории: {', '.join(f'{k}({len(v)})' for k, v in categories.items())}")

        processed_count = 0
        for category, items in categories.items():
            try:
                count = await self._process_multi_source_batch(items, category)
                processed_count += count
            except Exception as e:
                logger.error(f"Ошибка обработки группы {category}: {e}", exc_info=True)

        return processed_count

    async def _collect_unprocessed_all_sources(self, hours: int = 48) -> list[dict]:
        """
        Собрать необработанные новости из всех источников.

        Returns:
            Список dict: {source_type, source_id, text, category, urgency, tags, confidence}
        """
        from datetime import datetime, timezone, timedelta

        all_items = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # 1. Telegram posts
        posts = await self.repo_factory.posts().get_unanalyzed(hours=hours)
        for post in posts:
            if post.created_at < cutoff:
                continue
            all_items.append({
                'source_type': 'telegram',
                'source_id': post.id,
                'text': post.text,
                'category': post.category,
                'urgency': post.urgency,
                'tags': post.tags,
                'confidence': post.category_confidence,
                'created_at': post.created_at,
            })

        # 2. RSS news
        rss_items = await self.repo_factory.rss_news().get_unprocessed_with_category(limit=500)
        for item in rss_items:
            if item.published_at and item.published_at < cutoff:
                continue
            if item.category is None:
                continue
            all_items.append({
                'source_type': 'rss',
                'source_id': item.id,
                'text': f"{item.title}\n\n{item.description or ''}",
                'category': item.category,
                'urgency': item.urgency,
                'tags': item.tags,
                'confidence': item.category_confidence,
                'created_at': item.created_at,
            })

        # 3. Web news
        web_items = await self.repo_factory.web_news().get_unprocessed_with_category(limit=500)
        for item in web_items:
            if item.published_at and item.published_at < cutoff:
                continue
            if item.category is None:
                continue
            all_items.append({
                'source_type': 'web',
                'source_id': item.id,
                'text': f"{item.title}\n\n{item.description or ''}",
                'category': item.category,
                'urgency': item.urgency,
                'tags': item.tags,
                'confidence': item.category_confidence,
                'created_at': item.created_at,
            })

        return all_items

    async def _process_multi_source_batch(
        self,
        items: list[dict],
        category: str,
    ) -> int:
        """
        Обработать группу новостей одной категории (любой источник).

        Args:
            items: Список унифицированных dict
            category: Категория

        Returns:
            Количество обработанных новостей
        """
        from services.ai_agent.agents import EditorAgent, ArchivistAgent
        from services.news.helpers import add_generated_news

        if not items:
            return 0

        # 1. Собираем тексты
        texts = [item['text'] for item in items if item.get('text')]
        if not texts:
            return 0

        combined_text = '\n\n'.join(texts[:5])

        # 2. Векторный поиск для контекста
        logger.info(f"🔍 Векторный поиск для категории {category}...")
        similar_events, similar_posts = await self._find_context(combined_text, category)

        # 3. Editor
        logger.info(f"🤖 Генерация новости для {len(items)} источников категории {category}...")
        editor = EditorAgent()

        posts_context = '\n---\n'.join([
            f"[{item['source_type']}] ID={item['source_id']} (срочность={item.get('urgency')}):\n"
            f"{item['text'][:300]}"
            for i, item in enumerate(items[:5])
        ])

        events_context = ''
        if similar_events:
            events_context = '\n\nПохожие события:\n' + '\n'.join([
                f"- {e.get('event_description', '')[:200]}"
                for e in similar_events[:3]
            ])

        editor_prompt = (
            f"Сгенерируй новость на основе следующих материалов одной категории ({category}):\n\n"
            f"{posts_context}\n"
            f"{events_context}\n\n"
            f"Важно: объедини информацию из всех источников в единую связную новость."
        )

        editor_response = await editor.send_question(editor_prompt)

        try:
            news_data = self.parse_json_response(editor_response, required_fields=['text', 'news_tags'])
        except ValueError as e:
            logger.error(f"❌ Ошибка парсинга ответа Editor: {e}")
            await self._mark_batch_processed(items, None)
            return len(items)

        news_text = news_data.get('text', '')
        news_tags = news_data.get('news_tags', [])

        if not news_text or len(news_text) < 50:
            logger.warning(f"⚠️ Пустая новость для категории {category}")
            await self._mark_batch_processed(items, None)
            return len(items)

        # Формируем source_ids
        source_ids = [f"{item['source_type']}_{item['source_id']}" for item in items]

        # 4. Сохраняем новость
        news_id = await add_generated_news(
            text=news_text,
            category=category,
            tags=news_tags,
            source_ids=source_ids,
            source_event_ids=[e['id'] for e in similar_events[:3]] if similar_events else [],
            moderation_status='pending',
        )

        logger.info(f"✅ Новость ID={news_id} сгенерирована из {len(items)} источников ({category})")

        # 5. Archivist — создаёт или обновляет контекст события
        if similar_events or news_id:
            try:
                archivist = ArchivistAgent()
                archivist_prompt = (
                    f"Определи, является ли эта новость новым событием или продолжением.\n\n"
                    f"Новость: {news_text[:300]}...\n\n"
                    f"Похожие события:{events_context}\n\n"
                    f"Ответь в формате JSON: {{\"is_new_event\": true/false, \"event_description\": \"...\", \"context_data\": {{}}}}"
                )

                archivist_response = await archivist.send_question(archivist_prompt)
                archivist_data = self.parse_json_response(
                    archivist_response,
                    required_fields=['is_new_event']
                )

                events_repo = self.repo_factory.events()

                if archivist_data.get('is_new_event', True):
                    logger.info(f"🆕 Новость ID={news_id} — новое событие")
                    context_data = archivist_data.get('context_data', {
                        'event_description': news_text[:200],
                    })
                    await events_repo.create_event(
                        post_id=None,
                        context_data=context_data,
                        event_category=category,
                        tags=news_tags,
                        source_news_ids=source_ids,
                    )
                else:
                    logger.info(f"🔗 Новость ID={news_id} — продолжение существующего события")
                    # Можно обновить существующий контекст если needed
            except Exception as e:
                logger.error(f"⚠️ Ошибка Archivist: {e}")

        # 6. Отмечаем все источники как обработанные
        await self._mark_batch_processed(items, news_id)

        logger.info(f"✅ Обработано {len(items)} источников категории {category}")
        return len(items)

    async def _mark_batch_processed(
        self,
        items: list[dict],
        news_id: int | None,
    ) -> None:
        """
        Отметить все источники как обработанные.

        Args:
            items: Список унифицированных dict
            news_id: ID сгенерированной новости (или None)
        """
        for item in items:
            st = item['source_type']
            sid = item['source_id']

            if st == 'telegram':
                await self.repo_factory.posts().mark_analyzed(sid, generated_news_id=news_id)
            elif st == 'rss':
                await self.repo_factory.rss_news().mark_processed(sid, generated_news_id=news_id)
            elif st == 'web':
                await self.repo_factory.web_news().mark_processed(sid, generated_news_id=news_id)

    async def _process_analyzed_posts_batch(
        self,
        posts: list,
        posts_repo,
        category: str
    ) -> None:
        """
        Обработать группу проанализированных постов одной категории.

        АЛГОРИТМ:
        1. Собрать тексты всех постов группы
        2. Векторный поиск в events для контекста (по категории и тэгам)
        3. Передать Editor группу постов + контекст
        4. Editor генерирует новость
        5. Передать Archivist (новое событие или продолжение)
        6. Отметить все посты как обработанные

        Args:
            posts: Список постов одной категории
            posts_repo: Репозиторий постов
            category: Категория постов
        """
        from services.ai_agent.agents import EditorAgent, ArchivistAgent

        if not posts:
            return

        # 1. Собираем тексты всех постов
        post_texts = [post.text for post in posts if post.text]
        if not post_texts:
            logger.warning(f"⚠️ Нет текстов для обработки в категории {category}")
            return

        # Объединяем тексты для контекста
        combined_text = '\n\n'.join(post_texts[:5])  # Берём первые 5 постов для контекста

        # 2. Векторный поиск для контекста через VectorSearchService
        logger.info(f"🔍 Векторный поиск для категории {category}...")

        if self.vector_search_service:
            similar_events = await self.vector_search_service.find_similar_events(
                text=combined_text,
                category=category,
                limit=5,
                min_score=0.7
            )
            similar_posts_list = await self.vector_search_service.find_similar_posts(
                text=combined_text,
                category=category,
                limit=10,
                min_score=0.6
            )
        else:
            # Fallback на глобальные функции (для обратной совместимости)
            from services.news.helpers import find_similar_events, find_similar_posts
            similar_events = await find_similar_events(
                text=combined_text,
                category=category,
                limit=5,
                min_score=0.7
            )
            similar_posts_list = await find_similar_posts(
                text=combined_text,
                category=category,
                limit=10,
                min_score=0.6
            )

        # 3. Передаём Editor группу постов + контекст
        logger.info(f"🤖 Генерация новости для {len(posts)} постов категории {category}...")
        editor = EditorAgent()

        # Формируем промпт с группой постов
        posts_context = '\n---\n'.join([
            f"Пост #{i+1} (ID={p.id}, срочность={p.urgency}):\n{p.text[:300]}"
            for i, p in enumerate(posts[:5])  # Берём первые 5 для промпта
        ])

        # Контекст из похожих событий
        events_context = ''
        if similar_events:
            events_context = '\n\nПохожие события:\n' + '\n'.join([
                f"- {e.get('event_description', '')[:200]}"
                for e in similar_events[:3]
            ])

        editor_prompt = (
            f"Сгенерируй новость на основе следующих постов одной категории ({category}):\n\n"
            f"{posts_context}\n"
            f"{events_context}\n\n"
            f"Важно: объедини информацию из всех постов в единую связную новость."
        )

        # Генерируем новость
        editor_response = await editor.send_question(editor_prompt)

        # Парсим ответ
        try:
            news_data = self.parse_json_response(editor_response, required_fields=['text', 'news_tags'])
        except ValueError as e:
            logger.error(f"❌ Ошибка парсинга ответа Editor: {e}")
            # Отмечаем посты как обработанные без новости
            for post in posts:
                await posts_repo.mark_analyzed(post.id)
            return

        news_text = news_data.get('text', '')
        news_tags = news_data.get('news_tags', [])

        if not news_text or len(news_text) < 50:
            logger.warning(f"⚠️ Пустая или слишком короткая новость для категории {category}")
            for post in posts:
                await posts_repo.mark_analyzed(post.id)
            return

        # 4. Сохраняем новость
        from services.news.helpers import add_generated_news
        news_id = await add_generated_news(
            text=news_text,
            category=category,
            tags=news_tags,
            source_event_ids=[e['id'] for e in similar_events[:3]] if similar_events else [],
            moderation_status='pending',
        )

        logger.info(f"✅ Новость ID={news_id} сгенерирована для {len(posts)} постов")

        # 5. Передаём Archivist для определения "новое/продолжение"
        if similar_events:
            archivist = ArchivistAgent()
            archivist_prompt = (
                f"Определи, является ли эта новость новым событием или продолжением существующего.\n\n"
                f"Новость: {news_text[:300]}...\n\n"
                f"Похожие события: {events_context}\n\n"
                f"Ответь в формате JSON: {{\"is_new_event\": true/false, \"event_description\": \"...\"}}"
            )

            try:
                archivist_response = await archivist.send_question(archivist_prompt)
                archivist_data = self.parse_json_response(archivist_response, required_fields=['is_new_event'])

                if archivist_data.get('is_new_event', False):
                    # Новое событие — создаём новый контекст
                    logger.info(f"🆕 Новость ID={news_id} — новое событие")
                    # Контекст будет создан при публикации
                else:
                    # Продолжение — обновляем существующий контекст
                    logger.info(f"🔗 Новость ID={news_id} — продолжение существующего события")
            except Exception as e:
                logger.error(f"⚠️ Ошибка Archivist: {e}")

        # 6. Отмечаем все посты как обработанные
        for post in posts:
            await posts_repo.mark_analyzed(post.id, generated_news_id=news_id)

        logger.info(f"✅ Обработано {len(posts)} постов категории {category}")

    async def _process_analyzed_post(self, post, posts_repo) -> None:
        """
        Обработать проанализированный пост (генерация новости).

        Analyst уже сработал на этапе категоризации, поэтому:
        - category уже установлена
        - category_confidence уже установлен
        - tags уже установлены

        Args:
            post: Объект поста
            posts_repo: Репозиторий постов
        """
        # Векторный поиск для контекста через VectorSearchService
        if self.vector_search_service:
            similar_events = await self.vector_search_service.find_similar_events(
                text=post.text,
                category=post.category,
                limit=5,
                min_score=0.7
            )
            similar_posts = await self.vector_search_service.find_similar_posts(
                text=post.text,
                category=post.category,
                limit=10,
                min_score=0.6
            )
        else:
            # Fallback на глобальные функции
            from services.news.helpers import find_similar_events, find_similar_posts
            similar_events, similar_posts = await find_similar_events(
                text=post.text,
                category=post.category,
                limit=5,
                min_score=0.7
            ), await find_similar_posts(
                text=post.text,
                category=post.category,
                limit=10,
                min_score=0.6
            )

        # Генерация новости через сервис
        generation_service = self._get_generation_service()
        news_id = await generation_service.generate_news(
            post_id=post.id,
            post_text=post.text,
            post_category=post.category,
            post_tags=[],  # Уже установлены в БД
            post_category_confidence=post.category_confidence,
            similar_events=similar_events,
            similar_posts=similar_posts,
        )

        if news_id:
            # Отмечаем пост как обработанный
            await posts_repo.mark_analyzed(post.id, generated_news_id=news_id)
            logger.info(f"✅ Новость ID={post.id} сгенерирована (news_id={news_id})")
        else:
            # Ошибка генерации — всё равно отмечаем как обработанную
            await posts_repo.mark_analyzed(post.id)
            logger.warning(f"⚠️ Новость ID={post.id} не сгенерирована")

    async def _find_context(self, text: str, category: str):
        """Найти похожие события и посты для контекста."""
        if self.vector_search_service:
            similar_events = await self.vector_search_service.find_similar_events(
                text=text,
                category=category,
                limit=5,
                min_score=0.7
            )
            similar_posts = await self.vector_search_service.find_similar_posts(
                text=text,
                category=category,
                limit=10,
                min_score=0.6
            )
            return similar_events, similar_posts
        else:
            # Fallback на глобальные функции
            from services.news.helpers import find_similar_events, find_similar_posts
            similar_events = await find_similar_events(
                text=text,
                category=category,
                limit=5,
                min_score=0.7
            )
            similar_posts = await find_similar_posts(
                text=text,
                category=category,
                limit=10,
                min_score=0.6
            )
            return similar_events, similar_posts

    async def _update_post_with_analysis(self, posts_repo, post_id: int, analysis: dict):
        """Обновить пост результатами анализа."""
        await posts_repo.update_category_confidence(post_id, analysis['confidence'])

        if analysis['post_tags']:
            await posts_repo.update_post_tags(post_id, analysis['post_tags'])

    async def _emit_generate_event(
        self,
        post_id: int,
        urgency,
        contexts,
        context: dict,
        analysis: dict
    ):
        """Отправить событие генерации новости."""
        await self.event_bus.emit(Event(
            type=EventType.GENERATE_NEWS,
            payload={
                'post_id': post_id,
                'event_id': contexts[0].id if contexts else None,
                'event_context': context,
                'category': analysis['category'],
                'urgency': int(urgency) if urgency else 1,
                'analysis': analysis,
                'scheduled': True,
                'from_scheduler': True
            }
        ))

    async def process_news_cycle(self) -> int:
        """
        Цикл обработки новостей с векторным поиском и генерацией.

        Алгоритм:
        1. Берём одну новость с checked_at = false
        2. Передаём AnalystAgent для анализа (если ещё не проанализирован)
        3. Векторный поиск похожих постов и событий
        4. Генерация новости через NewsGenerationService
        5. Отмечаем пост как обработанный (checked_at = true)

        Цикл выполняется пока есть новости с checked_at = false.

        Returns:
            Количество обработанных новостей
        """
        if not self._running:
            logger.warning("⚠️ NewsOrchestrator не запущен, цикл обработки отменён")
            return 0

        posts_repo = self.repo_factory.posts()
        processed_count = 0

        while self._running:
            # 1. Берём одну новость с checked_at = false
            unanalyzed_posts = await posts_repo.get_unanalyzed(hours=48)

            if not unanalyzed_posts:
                logger.info("📭 Все новости обработаны (checked_at = true)")
                break

            post = unanalyzed_posts[0]
            logger.info(f"🔄 Обработка новости ID={post.id} (цикл {processed_count + 1})")

            try:
                # 2. Передаём AnalystAgent если пост ещё не проанализирован
                if not post.checked_at:
                    # Проверяем, есть ли уже результаты анализа (тэги)
                    post_tags = json.loads(post.tags or '[]')
                    if not post_tags or post.category_confidence is None:
                        # Передаём аналитику
                        analysis = await self._analyze_post(post)
                        if analysis:
                            # Обновляем пост результатами анализа
                            await self._update_post_with_analysis(post.id, analysis)
                            # Перечитываем пост с обновлёнными данными
                            post = await posts_repo.get(post.id)

                # 3. Векторный поиск похожих постов и событий
                generation_service = self._get_generation_service()
                context_service = self._get_context_service()

                similar = await context_service.find_similar(
                    text=post.text,
                    category=post.category,
                )

                # 4. Генерация новости через сервис
                news_id = await generation_service.generate_news(
                    post_id=post.id,
                    post_text=post.text,
                    post_category=post.category,
                    post_tags=json.loads(post.tags or '[]'),
                    post_category_confidence=post.category_confidence,
                    similar_events=similar['events'],
                    similar_posts=similar['posts'],
                )

                if news_id:
                    # 5. Отмечаем пост как обработанный
                    await posts_repo.mark_analyzed(post.id, generated_news_id=news_id)
                    processed_count += 1
                    logger.info(f"✅ Новость ID={post.id} обработана (всего: {processed_count})")
                else:
                    # Ошибка генерации — всё равно отмечаем как обработанную
                    await posts_repo.mark_analyzed(post.id)
                    logger.warning(f"⚠️ Новость ID={post.id} не сгенерирована")

            except Exception as e:
                logger.error(f"Ошибка обработки новости ID={post.id}: {e}", exc_info=True)

                # Всё равно отмечаем как обработанную, чтобы не застрять в цикле
                await posts_repo.mark_analyzed(post.id)

        logger.info(f"🏁 Цикл обработки завершён. Обработано новостей: {processed_count}")
        return processed_count

    async def _analyze_post(self, post) -> dict | None:
        """
        Передать пост аналитику для анализа.

        Args:
            post: Объект поста

        Returns:
            dict с результатами анализа или None при ошибке
        """
        try:
            from services.ai_agent.agents import AnalystAgent

            analyst = AnalystAgent()

            # Векторный поиск для контекста через VectorSearchService
            if self.vector_search_service:
                similar_events = await self.vector_search_service.find_similar_events(
                    text=post.text,
                    category=post.category,
                    limit=5,
                    min_score=0.7
                )
                similar_posts = await self.vector_search_service.find_similar_posts(
                    text=post.text,
                    category=post.category,
                    limit=10,
                    min_score=0.6
                )
            else:
                # Fallback на глобальные функции
                from services.news.helpers import find_similar_events, find_similar_posts
                similar_events, similar_posts = await find_similar_events(
                    text=post.text,
                    category=post.category,
                    limit=5,
                    min_score=0.7
                ), await find_similar_posts(
                    text=post.text,
                    category=post.category,
                    limit=10,
                    min_score=0.6
                )

            # Анализ новости
            analysis = await analyst.analyze(
                post_text=post.text,
                similar_events=similar_events,
                similar_posts=similar_posts,
                preliminary_category=post.category,
            )

            logger.info(
                f"🔍 Analyst для поста ID={post.id}: "
                f"категория={analysis['category']}, "
                f"уверенность={analysis['confidence']:.2f}, "
                f"тэгов={len(analysis['post_tags'])}"
            )

            return analysis

        except Exception as e:
            logger.error(f"❌ Ошибка анализа поста ID={post.id}: {e}", exc_info=True)
            return None

    async def generate_direct_news(
        self,
        description: str,
        publisher_channel_id: Optional[int] = None,
        publish_immediately: bool = True,
    ) -> Optional[int]:
        """
        Сгенерировать новость по прямому описанию админа.

        Алгоритм:
        1. Использовать DirectNewsEditorAgent для генерации SMM-поста
        2. Запустить ArchivistAgent для создания контекста
        3. Сохранить новость в БД
        4. Если publish_immediately=True — опубликовать:
           Если publisher_channel_id=None (бот) — отправить всем пользователям сразу
           Если publisher_channel_id=-1 (все каналы) — опубликовать во все каналы
           Если publisher_channel_id=<конкретный> — опубликовать в конкретный канал
           Иначе — отправить на модерацию
           Если publish_immediately=False — только генерация + сохранение без публикации

        Args:
            description: Описание новости от админа
            publisher_channel_id: ID канала публикации (опционально)
                None = публикация через бота всем пользователям
                -1 = публикация во все каналы
                int > 0 = публикация в конкретный канал
            publish_immediately: Если False — только генерация и сохранение, публикация пропускается

        Returns:
            ID сгенерированной новости или None при ошибке
        """
        try:
            logger.info(f"📝 Прямая генерация новости: {description[:50]}...")

            # 1. Генерация через DirectNewsEditorAgent (SMM-пост)
            editor = DirectNewsEditorAgent()
            news_result = await editor.generate_from_description(
                description=description,
            )

            logger.info(
                f"📝 Новость сгенерирована: {len(news_result.get('text', ''))} символов"
            )

            # 2. Определяем статус модерации и канал публикации
            # None (бот) или -1 (все каналы) = мгновенная публикация без модерации
            if publisher_channel_id is None or publisher_channel_id == -1:
                moderation_status = 'approved'
                publish_immediately = True
                logger.info(f"🚀 Прямая генерация с мгновенной публикацией (publisher_channel_id={publisher_channel_id})")
            else:
                moderation_status = 'approved'  # Всё равно одобряем, но публикуем в конкретный канал
                publish_immediately = True
                logger.info(f"📢 Прямая генерация с публикацией в канал ID={publisher_channel_id}")

            # 3. Сохранение в БД
            news_id = await add_generated_news(
                text=news_result.get('text', ''),
                category='Общее',
                tags=news_result.get('news_tags', []),
                source_event_ids=[],
                moderation_status=moderation_status,
                publisher_channel_id=publisher_channel_id if publisher_channel_id and publisher_channel_id > 0 else None,
            )

            logger.info(f"✅ Новость ID={news_id} сохранена в БД (status={moderation_status})")

            # 4. Создание контекста через ArchivistAgent
            archivist = ArchivistAgent()
            context_result = await archivist.create_context(
                post_text=description,
                generated_news=news_result,
                analysis={
                    'category': 'Общее',
                    'post_tags': [],
                }
            )

            # Сохраняем контекст (создаём фиктивный пост ID=0 для описания)
            events_repo = self.repo_factory.events()
            await events_repo.create_event(
                post_id=0,  # Нет оригинального поста
                context_data=context_result['context_data'],
                event_category='Общее',
                tags=context_result['tags'],
            )

            # 5. Мгновенная публикация
            if publish_immediately:
                if publisher_channel_id is None:
                    # Публикация через бота всем пользователям (игнорируя предпочтения)
                    await self._publish_direct_to_bot(news_id, news_result.get('text', ''))
                elif publisher_channel_id == -1:
                    # Публикация во все активные каналы
                    await self._publish_direct_to_all_channels(news_id, news_result.get('text', ''))
                else:
                    # Публикация в конкретный канал
                    await self._publish_direct_to_channel(news_id, news_result.get('text', ''), publisher_channel_id)

            return news_id

        except Exception as e:
            logger.error(f"Ошибка прямой генерации новости: {e}", exc_info=True)
            return None

    async def _publish_direct_to_bot(self, news_id: int, text: str) -> None:
        """
        Опубликовать новость через бота всем пользователям (игнорируя предпочтения).

        Args:
            news_id: ID новости
            text: Текст новости
        """
        if not self.notification_service:
            logger.warning("⚠️ NotificationService не инициализирован, публикация в бот пропущена")
            return

        try:
            # Отправляем всем пользователям с активной подпиской, игнорируя предпочтения
            sent_count = await self.notification_service.notify_all_subscribers(
                news_text=text,
                news_id=news_id,
                ignore_preferences=True,  # Игнорируем категории и тэги
            )
            if sent_count > 0:
                logger.info(f"✅ Опубликована новость ID={news_id} через бот: отправлено {sent_count} уведомлений")
            else:
                logger.warning(f"⚠️ Новость ID={news_id}: бот не отправил уведомления (0 из подписчиков получило)")
        except Exception as e:
            logger.error(f"Ошибка публикации новости через бот ID={news_id}: {e}")

    async def _publish_direct_to_all_channels(self, news_id: int, text: str) -> None:
        """
        Опубликовать новость во все активные каналы.

        Args:
            news_id: ID новости
            text: Текст новости
        """
        try:
            publishers_repo = self.repo_factory.publishers()
            publishers = await publishers_repo.get_all(active_only=True)

            for publisher in publishers:
                try:
                    await self._publish_to_telegram_channel(publisher.channel_id, text)
                    logger.info(f"✅ Опубликована новость ID={news_id} в канал {publisher.title} (ID={publisher.channel_id})")
                except Exception as e:
                    logger.error(f"Ошибка публикации в канал {publisher.channel_id}: {e}")

            # Обновляем статус новости на опубликованный
            news_repo = self.repo_factory.news()
            await news_repo.mark_published(news_id)

        except Exception as e:
            logger.error(f"Ошибка публикации новости во все каналы ID={news_id}: {e}")

    async def _publish_direct_to_channel(self, news_id: int, text: str, publisher_id: int) -> None:
        """
        Опубликовать новость в конкретный канал.

        Args:
            news_id: ID новости
            text: Текст новости
            publisher_id: ID записи в таблице publishers
        """
        try:
            # Получаем Telegram channel ID из таблицы publishers
            publishers_repo = self.repo_factory.publishers()
            publisher = await publishers_repo.get_by_id(publisher_id)

            if not publisher:
                logger.error(f"❌ Канал публикации ID={publisher_id} не найден в БД")
                return

            if not publisher.channel_id:
                logger.error(f"❌ У канала публикации ID={publisher_id} не указан Telegram channel_id")
                return

            # Отправляем в Telegram канал
            await self._publish_to_telegram_channel(publisher.channel_id, text)
            logger.info(f"✅ Опубликована новость ID={news_id} в канал '{publisher.title}' (Telegram ID={publisher.channel_id})")

            # Обновляем статус новости на опубликованный
            news_repo = self.repo_factory.news()
            await news_repo.mark_published(news_id)

        except Exception as e:
            logger.error(f"Ошибка публикации новости в канал ID={publisher_id}: {e}")
            raise

    async def _publish_to_telegram_channel(self, channel_id: int, text: str) -> None:
        """
        Отправить сообщение в Telegram канал.

        Args:
            channel_id: ID канала в Telegram
            text: Текст сообщения
        """
        try:
            from services.bot.bot import get_bot_instance_async

            bot = await get_bot_instance_async(wait=False, timeout=10.0)
            if bot:
                await bot.send_message(
                    chat_id=channel_id,
                    text=text,
                    parse_mode='HTML',
                )
        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram канал ID={channel_id}: {e}")
            raise

    async def _update_post_with_analysis(
        self,
        post_id: int,
        analysis: dict,
    ) -> None:
        """
        Обновить пост результатами анализа.

        Args:
            post_id: ID поста
            analysis: Результаты анализа
        """
        posts_repo = self.repo_factory.posts()

        # Обновляем уверенность категории
        await posts_repo.update_category_confidence(post_id, analysis['confidence'])

        # Обновляем тэги
        if analysis['post_tags']:
            await posts_repo.update_post_tags(post_id, analysis['post_tags'])

    async def start_event_bus(self) -> None:
        """
        Запустить шину событий.

        Запускает event_bus.run() как фоновую задачу.
        """
        logger.info("🚀 Запуск шины событий...")
        self._running = True
        # Запускаем шину событий как задачу, чтобы не блокировать вызывающий код
        self._event_bus_task = asyncio.create_task(self.event_bus.run())
        logger.debug("✅ Шина событий запущена как фоновая задача")

    async def stop(self) -> None:
        """
        Остановить координатор.

        Последовательность:
        1. Останавливаем флаг работы
        2. Останавливаем шину событий
        """
        if not self._running:
            logger.debug("NewsOrchestrator уже остановлен")
            return

        logger.info("🛑 Остановка NewsOrchestrator...")
        self._running = False

        # Останавливаем шину событий
        if self._event_bus_task and not self._event_bus_task.done():
            logger.info("⏳ Остановка шины событий...")
            self._event_bus_task.cancel()
            try:
                await asyncio.wait_for(self._event_bus_task, timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        logger.info("✅ NewsOrchestrator остановлен")
