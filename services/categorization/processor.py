"""
CategorizationProcessor — обработка задач категоризации.

Координирует AI-агент, классификатор и сохранение результатов.
"""

import logging
from typing import Optional, Protocol, TYPE_CHECKING

from services.ai_agent.agents.categorizer import CategorizerAgent
from services.categorization.queue import CategorizationTask
from services.categorization.classifier import NewsClassifier, ClassificationResult
from services.categorization.saver import NewsSaver

if TYPE_CHECKING:
    from services.telegram.notification import NotificationService

logger = logging.getLogger(__name__)


class ChannelProvider(Protocol):
    """Протокол для получения информации о канале."""
    async def get_by_telegram_id(self, channel_id: int) -> Optional[object]:
        """Получить канал по Telegram ID."""
        ...


class CategorizationProcessor:
    """
    Процессор задач категоризации.

    Координирует:
    - Вызов AI-агента для классификации
    - Обработку результатов
    - Сохранение в БД
    - Уведомления админам

    Attributes:
        categorizer: AI-агент для категоризации
        classifier: Классификатор ответов
        saver: Сервис сохранения
        notification_service: Сервис уведомлений
    """

    def __init__(
        self,
        categorizer: CategorizerAgent,
        saver: NewsSaver,
        channel_provider: ChannelProvider,
        notification_service: Optional['NotificationService'] = None,
    ) -> None:
        """
        Инициализация процессора.

        Args:
            categorizer: AI-агент для категоризации
            saver: Сервис сохранения
            channel_provider: Провайдер каналов
            notification_service: Сервис уведомлений
        """
        self.categorizer = categorizer
        self.classifier = NewsClassifier()
        self.saver = saver
        self.channel_provider = channel_provider
        self.notification_service = notification_service

    async def process(self, task: CategorizationTask) -> None:
        """
        Обработать одну задачу категоризации.

        Работает для всех источников: telegram, rss, web.

        Args:
            task: Задача на категоризацию
        """
        try:
            # Отправляем в AI-категорайзер
            ai_response = await self.categorizer.send_question(task.prompt)

            # Парсим ответ
            classification = self.classifier.parse_ai_response(ai_response)

            # Проверяем на рекламу
            if classification.is_advertisement:
                logger.info(
                    f"🚫 Пропущено (реклама): {task.source_type} "
                    f"source_id={task.source_id or task.channel_id}"
                )
                return

            # Проверяем срочность и обрабатываем соответственно
            if classification.urgency >= 4:
                await self._handle_urgent_news(task, classification)
            else:
                await self._handle_scheduled_news(task, classification)

        except Exception as e:
            logger.error(f"Ошибка обработки задачи категоризации: {e}", exc_info=True)
            raise

    async def _handle_urgent_news(
        self,
        task: CategorizationTask,
        classification: ClassificationResult,
    ) -> None:
        """
        Обработать срочную новость.

        Для Telegram: полная логика (Analyst → публикация / уведомления).
        Для RSS/Web: обогащение сырой записи + ожидание планировщика.

        Args:
            task: Задача на категоризацию
            classification: Результат классификации
        """
        logger.info(
            f"⚡ СРОЧНО! {task.source_type} срочность {classification.urgency}, "
            f"категория {classification.category}"
        )

        if task.source_type == 'telegram':
            await self._handle_urgent_telegram(task, classification)
        else:
            await self._save_non_telegram_classification(
                task=task,
                classification=classification,
            )

    async def _handle_urgent_telegram(
        self,
        task: CategorizationTask,
        classification: ClassificationResult,
    ) -> None:
        """
        Обработать срочную Telegram-новость.

        Логика:
        - Сохранение поста → Analyst → обновление поста
        - Доверенные источники: авто-публикация
        - Обычные: уведомление админам
        """
        # Сохраняем новость в БД
        post_id = await self.saver.save_urgent_news(
            channel_id=task.channel_id,
            classification=classification,
        )

        # Получаем канал для проверки is_trusted
        channel = await self.channel_provider.get_by_telegram_id(task.channel_id)
        channel_title = channel.title if channel else 'Неизвестно'
        is_trusted = channel and channel.is_trusted

        # Аналитика
        analysis_result = await self._analyze_post(
            post_id=post_id,
            text=classification.text,
            category=classification.category,
        )

        if not analysis_result:
            logger.error(f"❌ Ошибка анализа поста ID={post_id}")
            return

        await self._update_post_with_analysis(
            post_id=post_id,
            analysis=analysis_result,
        )

        logger.info(
            f"🔍 Analyst для поста ID={post_id}: "
            f"категория={analysis_result['category']}, "
            f"уверенность={analysis_result['confidence']:.2f}, "
            f"тэгов={len(analysis_result['post_tags'])}"
        )

        if is_trusted:
            logger.info(
                f"✅ ДОВЕРЕННЫЙ ИСТОЧНИК! Публикация после анализа "
                f"(пост ID={post_id})"
            )
            await self._publish_after_analysis(
                post_id=post_id,
                text=classification.text,
                category=classification.category,
                urgency=classification.urgency,
                channel_id=task.channel_id,
                tags=analysis_result['post_tags'],
            )
            return

        notifications_sent = await self._notify_urgent_news(
            post_id=post_id,
            text=classification.text,
            category=classification.category,
            urgency=classification.urgency,
            channel_title=channel_title,
        )

        if not notifications_sent:
            logger.info(
                f"📊 Срочная новость ID={post_id} будет обработана планировщиком "
                f"(нет админов для модерации)"
            )

    async def _analyze_post(
        self,
        post_id: int,
        text: str,
        category: str,
    ) -> dict | None:
        """
        Передать пост аналитику для анализа.

        Args:
            post_id: ID поста
            text: Текст поста
            category: Предварительная категория

        Returns:
            dict с результатами анализа или None при ошибке
        """
        try:
            from services.ai_agent.agents import AnalystAgent

            analyst = AnalystAgent()

            # Векторный поиск для контекста
            similar_events, similar_posts = await self._find_context(text, category)

            # Анализ новости
            analysis = await analyst.analyze(
                post_text=text,
                similar_events=similar_events,
                similar_posts=similar_posts,
                preliminary_category=category,
            )

            return analysis

        except Exception as e:
            logger.error(f"❌ Ошибка анализа поста ID={post_id}: {e}", exc_info=True)
            return None

    async def _find_context(self, text: str, category: str):
        """Найти похожие события и посты для контекста."""
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
        from database.repositories.posts import PostRepository
        from services.database import get_database_service

        db_service = get_database_service()
        async with db_service.session_context() as session:
            posts_repo = PostRepository(session)

            # Обновляем уверенность категории
            await posts_repo.update_category_confidence(post_id, analysis['confidence'])

            # Обновляем тэги
            if analysis['post_tags']:
                await posts_repo.update_post_tags(post_id, analysis['post_tags'])

            await session.commit()

    async def _publish_after_analysis(
        self,
        post_id: int,
        text: str,
        category: str,
        urgency: int,
        channel_id: int,
        tags: list[str],
    ) -> None:
        """
        Опубликовать новость после анализа (для доверенных источников).

        Публикация происходит напрямую через NotificationService,
        без использования NewsOrchestrator (который требует запущенную шину событий).

        Логика публикации:
        1. Отправка подписчикам через бота с учётом предпочтений (категории, тэги)
        2. Публикация в каналы с той же категорией (если есть)

        Args:
            post_id: ID поста
            text: Текст новости
            category: Категория
            urgency: Срочность
            channel_id: ID канала источника
            tags: Тэги новости
        """
        try:
            from services.database import get_database_service
            from services.bot.bot import get_bot_instance_async
            from services.telegram.notification import NotificationService
            from database import RepositoryFactory

            # Получаем бота и создаём NotificationService (с ожиданием готовности)
            bot = await get_bot_instance_async(wait=True, timeout=10.0)
            notification_service = NotificationService(bot=bot) if bot else None

            db_service = get_database_service()
            async with db_service.session_context() as session:
                factory = RepositoryFactory(session)
                publishers_repo = factory.publishers()

                # 1. Отправка подписчикам с учётом предпочтений
                subscribers_sent = 0
                if notification_service:
                    subscribers_sent = await notification_service.notify_subscribers(
                        news_text=text,
                        category=category,
                        tags=tags,
                        news_id=post_id,
                        urgency=urgency,
                    )

                # 2. Публикация в каналы с той же категорией
                publishers = await publishers_repo.get_all(active_only=True)
                published_to_channels = 0
                channel_names = []

                for publisher in publishers:
                    # Публикуем в каналы с совпадающей категорией
                    # Если категория канала не задана — публикуем всегда (универсальный канал)
                    if publisher.category is None or publisher.category == category:
                        try:
                            await self._publish_to_telegram_channel(
                                bot=bot,
                                channel_id=publisher.channel_id,
                                text=text,
                            )
                            published_to_channels += 1
                            channel_names.append(publisher.title)
                        except Exception as e:
                            logger.error(
                                f"❌ Ошибка публикации в канал {publisher.channel_id}: {e}"
                            )

                # Итоговый лог одним сообщением
                destinations = []
                if subscribers_sent > 0:
                    destinations.append(f"{subscribers_sent} подписчикам")
                if published_to_channels > 0:
                    destinations.append(f"{published_to_channels} каналов ({', '.join(channel_names)})")

                if destinations:
                    logger.info(
                        f"✅ Доверенный источник ID={post_id} опубликован: "
                        f"{' | '.join(destinations)}"
                    )
                else:
                    logger.warning(
                        f"⚠️ Новость от доверенного источника ID={post_id} "
                        f"не была опубликована (нет подписчиков и каналов)"
                    )

        except Exception as e:
            logger.error(f"❌ Ошибка публикации после анализа ID={post_id}: {e}", exc_info=True)

    async def _publish_to_telegram_channel(
        self,
        bot,
        channel_id: int,
        text: str,
    ) -> None:
        """
        Отправить сообщение в Telegram канал.

        Args:
            bot: aiogram Bot экземпляр
            channel_id: ID канала в Telegram
            text: Текст сообщения
        """
        if not bot:
            logger.warning("⚠️ Бот не инициализирован, публикация в канал пропущена")
            return

        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode='HTML',
        )

    async def _handle_scheduled_news(
        self,
        task: CategorizationTask,
        classification: ClassificationResult,
    ) -> None:
        """
        Обработать несрочную новость.

        Для Telegram: сохранение поста + события → Analyst → update.
        Для RSS/Web: обогащение сырой записи (категория, тэги, urgency).

        Args:
            task: Задача на категоризацию
            classification: Результат классификации
        """
        logger.info(
            f"📊 В план ({task.source_type}): Срочность {classification.urgency}, "
            f"категория {classification.category}"
        )

        if task.source_type == 'telegram':
            await self._handle_scheduled_telegram(task, classification)
        else:
            await self._save_non_telegram_classification(
                task=task,
                classification=classification,
            )

    async def _handle_scheduled_telegram(
        self,
        task: CategorizationTask,
        classification: ClassificationResult,
    ) -> None:
        """Обработать несрочную Telegram-новость (бывшая логика)."""
        post_id, event_id = await self.saver.save_scheduled_news(
            channel_id=task.channel_id,
            classification=classification,
        )

        analysis_result = await self._analyze_post(
            post_id=post_id,
            text=classification.text,
            category=classification.category,
        )

        if analysis_result:
            await self._update_post_with_analysis(
                post_id=post_id,
                analysis=analysis_result,
            )

            logger.info(
                f"🔍 Analyst для поста ID={post_id}: "
                f"категория={analysis_result['category']}, "
                f"уверенность={analysis_result['confidence']:.2f}, "
                f"тэгов={len(analysis_result['post_tags'])}"
            )
        else:
            logger.warning(f"⚠️ Пост ID={post_id} сохранён без анализа")

    async def _save_non_telegram_classification(
        self,
        task: CategorizationTask,
        classification: ClassificationResult,
    ) -> None:
        """
        Сохранить результаты категоризации в сырую таблицу (RSS/Web).

        Обновляет category, urgency, category_confidence, tags
        в соответствующей таблице (rss_news или web_news).

        Args:
            task: Задача на категоризацию
            classification: Результат классификации
        """
        from services.database import get_database_service
        from database import RepositoryFactory

        if not task.source_id:
            logger.error(
                f"❌ {task.source_type} задача без source_id — "
                f"нельзя сохранить результаты категоризации"
            )
            return

        db_service = get_database_service()
        async with db_service.session_context() as session:
            factory = RepositoryFactory(session)

            # Аналитика для определения тегов и confidence
            analysis_result = await self._analyze_post(
                post_id=task.source_id,
                text=classification.text,
                category=classification.category,
            )

            tags = analysis_result.get('post_tags', []) if analysis_result else []
            confidence = analysis_result.get('confidence', classification.confidence) if analysis_result else classification.confidence

            if task.source_type == 'rss':
                repo = factory.rss_news()
                await repo.update_category(
                    news_id=task.source_id,
                    category=classification.category,
                    urgency=classification.urgency,
                    confidence=confidence,
                    tags=tags if tags else None,
                )
            elif task.source_type == 'web':
                repo = factory.web_news()
                await repo.update_category(
                    news_id=task.source_id,
                    category=classification.category,
                    urgency=classification.urgency,
                    confidence=confidence,
                    tags=tags if tags else None,
                )
            else:
                logger.warning(f"⚠️ Неизвестный source_type: {task.source_type}")
                return

        logger.info(
            f"✅ {task.source_type.upper()} {task.source_id} категоризована: "
            f"{classification.category}, urgency={classification.urgency}, "
            f"confidence={confidence:.2f}, tags={tags}"
        )

    async def _notify_urgent_news(
        self,
        post_id: int,
        text: str,
        category: str,
        urgency: int,
        channel_title: str,
    ) -> bool:
        """
        Уведомить админов о срочной новости.

        Args:
            post_id: ID поста
            text: Текст новости
            category: Категория
            urgency: Срочность
            channel_title: Название канала

        Returns:
            True если уведомления отправлены, False иначе
        """
        if self.notification_service:
            result = await self.notification_service.notify_urgent_news(
                post_id=post_id,
                text=text,
                category=category,
                urgency=urgency,
                channel_title=channel_title,
            )
            if result:
                logger.info(f"📬 Уведомление о срочной новости отправлено")
            return result

        logger.warning("⚠️ NotificationService не инициализирован")
        return False
