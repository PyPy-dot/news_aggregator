"""
RSS Processor Service для обработки спарсенных новостей.

Интегрируется с:
- AI агентом для категоризации
- Vector search для поиска контекста
- News orchestrator для публикации
"""

import logging
from typing import Optional, Tuple

from database import RepositoryFactory
from services.rss.parser import RSSParserService, get_rss_parser_service
from services.ai_agent.agents.categorizer import CategorizerAgent
from config.settings import settings

logger = logging.getLogger(__name__)


class RSSProcessorService:
    """
    Сервис для обработки RSS новостей.
    """

    def __init__(
        self,
        repo_factory: RepositoryFactory,
        parser_service: Optional[RSSParserService] = None,
        categorizer_agent: Optional[CategorizerAgent] = None,
    ):
        """
        Инициализация сервиса.

        Args:
            repo_factory: Фабрика репозиториев
            parser_service: RSS парсер сервис
            categorizer_agent: AI агент для категоризации
        """
        self.repo_factory = repo_factory
        self.parser_service = parser_service or get_rss_parser_service()
        self.categorizer_agent = categorizer_agent or CategorizerAgent(model=settings.agent_model)

    async def process_source(self, source_id: int) -> Tuple[int, int]:
        """
        Обработать RSS источник.

        Args:
            source_id: ID источника

        Returns:
            Tuple[int, int]: (получено новостей, добавлено новых)
        """
        rss_sources_repo = self.repo_factory.rss_sources()
        rss_news_repo = self.repo_factory.rss_news()

        # Получаем источник
        source = await rss_sources_repo.get(source_id)
        if not source:
            logger.error(f"❌ Источник RSS не найден: ID={source_id}")
            return 0, 0

        logger.info(f"📡 Обработка RSS источника: {source.name} ({source.url})")

        # Получаем последние значения Last-Modified и ETag
        last_modified = source.last_modified
        etag = source.etag

        # Получаем и парсим ленту
        metadata, news_items, has_changes = await self.parser_service.fetch_feed(
            url=source.url,
            last_modified=last_modified,
            etag=etag,
        )

        # Если контент не изменился
        if not has_changes:
            # Обновляем время проверки
            await rss_sources_repo.mark_checked(source_id, last_modified, etag)
            logger.info(f"📝 RSS лента не изменилась: {source.name}")
            return 0, 0

        # Обновляем метаданные источника
        await rss_sources_repo.mark_checked(
            source_id,
            metadata.last_modified if metadata else None,
            metadata.etag if metadata else None,
        )

        # Обрабатываем новости
        new_count = 0
        for item in news_items:
            # Проверяем, существует ли уже новость
            exists = False
            if item.guid:
                exists = await rss_news_repo.exists_by_guid(source_id, item.guid)
            if not exists and item.link:
                exists = await rss_news_repo.exists_by_link(source_id, item.link)

            if exists:
                logger.debug(f"🔄 Новость уже существует: {item.title[:50]}...")
                continue

            # Создаём новость
            try:
                news = await rss_news_repo.create_news(
                    source_id=source_id,
                    title=item.title,
                    link=item.link,
                    description=item.description,
                    content=item.content,
                    author=item.author,
                    published_at=item.published_at,
                    guid=item.guid,
                    image_url=item.image_url,
                    category=source.category,  # Категория источника по умолчанию
                    tags=item.categories,
                )
                new_count += 1
                logger.debug(f"✅ Добавлена новость: {item.title[:50]}...")

            except Exception as e:
                logger.error(f"❌ Ошибка создания новости: {e}")
                continue

        logger.info(f"📰 Из {source.name} получено {len(news_items)} новостей, добавлено {new_count} новых")
        return len(news_items), new_count

    async def process_all_active_sources(self, limit: int = 20) -> dict:
        """
        Обработать все активные источники, которые пора проверить.

        Args:
            limit: Максимальное количество источников для обработки

        Returns:
            dict: Статистика обработки
        """
        rss_sources_repo = self.repo_factory.rss_sources()

        # Получаем источники для проверки
        sources = await rss_sources_repo.get_sources_due_for_check(limit=limit)

        if not sources:
            logger.debug("📝 Нет источников для проверки")
            return {'sources_processed': 0, 'total_news': 0, 'new_news': 0}

        logger.info(f"🔍 Найдено {len(sources)} источников для проверки")

        total_news = 0
        new_news = 0
        processed_count = 0

        for source in sources:
            try:
                received, added = await self.process_source(source.id)
                total_news += received
                new_news += added
                processed_count += 1

            except Exception as e:
                logger.error(f"❌ Ошибка обработки источника {source.name}: {e}")
                continue

        return {
            'sources_processed': processed_count,
            'total_news': total_news,
            'new_news': new_news,
        }

    async def categorize_and_process_news(self, limit: int = 50) -> int:
        """
        Отправить необработанные RSS новости в общую очередь категоризации.

        Args:
            limit: Максимальное количество новостей для обработки

        Returns:
            int: Количество отправленных в очередь новостей
        """
        rss_news_repo = self.repo_factory.rss_news()
        rss_sources_repo = self.repo_factory.rss_sources()

        news_items = await rss_news_repo.get_unprocessed(limit=limit)

        if not news_items:
            logger.debug("📝 Нет необработанных RSS новостей")
            return 0

        logger.info(f"🔍 Найдено {len(news_items)} необработанных RSS новостей")

        # Получаем очередь из контейнера
        categorization_queue = None
        try:
            from services.core.container import get_container
            container = get_container()
            if container:
                categorization_queue = container.categorization_queue
        except Exception:
            pass

        if not categorization_queue:
            logger.error("❌ CategorizationQueue не инициализирован")
            return 0

        queued_count = 0
        for news in news_items:
            try:
                # Получаем источник для title/description
                source = await rss_sources_repo.get(news.source_id)
                source_title = source.name if source else 'Неизвестно'
                source_desc = source.description or ''

                # Формируем текст для категоризации
                text_for_categorization = f"{news.title}\n\n{news.description or ''}"

                # Создаём задачу на категоризацию
                from services.categorization.queue import CategorizationTask

                task = CategorizationTask(
                    source_type='rss',
                    source_id=news.id,
                    prompt=text_for_categorization,
                    original_text=text_for_categorization,
                    title=source_title,
                    desc=source_desc,
                )

                await categorization_queue.add(task)
                queued_count += 1
                logger.debug(f"📨 RSS новость {news.id} отправлена в очередь категоризации")

            except Exception as e:
                logger.error(f"❌ Ошибка подготовки RSS новости: {e}")
                continue

        logger.info(f"📨 Отправлено {queued_count}/{len(news_items)} RSS новостей в очередь")
        return queued_count


# Helper функция для получения сервиса
def get_rss_processor_service(
    repo_factory: RepositoryFactory,
) -> RSSProcessorService:
    """
    Получить экземпляр RSS процессор сервиса.

    Args:
        repo_factory: Фабрика репозиториев

    Returns:
        RSSProcessorService
    """
    return RSSProcessorService(repo_factory=repo_factory)
