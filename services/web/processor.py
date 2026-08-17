"""
Web Processor Service для обработки спарсенных Web новостей.

Интегрируется с:
- CategorizationQueue (общая очередь)
- Vector search для поиска контекста
"""

import json
import logging
from typing import Optional, Tuple

from database import RepositoryFactory
from services.web.parser import WebParserService, StaticWebParser, ParserConfig, get_web_parser_service
from services.categorization.queue import CategorizationQueue, CategorizationTask

logger = logging.getLogger(__name__)


class WebProcessorService:
    """
    Сервис для обработки Web новостей.

    Пайплайн:
    1. parse_source() → парсит сайт → web_news (raw)
    2. categorize_and_process_news() → CategorizationQueue → CategorizationProcessor
    """

    def __init__(
        self,
        repo_factory: RepositoryFactory,
        parser_service: Optional[WebParserService] = None,
        categorization_queue: Optional[CategorizationQueue] = None,
    ):
        """
        Инициализация сервиса.

        Args:
            repo_factory: Фабрика репозиториев
            parser_service: Web парсер сервис
            categorization_queue: Общая очередь категоризации
        """
        self.repo_factory = repo_factory
        self.parser_service = parser_service or get_web_parser_service()
        self.categorization_queue = categorization_queue

    async def parse_source(self, source_id: int) -> Tuple[int, int]:
        """
        Обработать Web источник.

        Args:
            source_id: ID источника

        Returns:
            Tuple[int, int]: (получено новостей, добавлено новых)
        """
        web_sources_repo = self.repo_factory.web_sources()
        web_news_repo = self.repo_factory.web_news()

        # Получаем источник
        source = await web_sources_repo.get(source_id)
        if not source:
            logger.error(f"❌ Web источник не найден: ID={source_id}")
            return 0, 0

        logger.info(f"🌐 Обработка Web источника: {source.name} ({source.url})")

        # Парсим по конфигурации
        if not source.parser_config:
            logger.warning(f"⚠️ Нет parser_config для источника {source.name}")
            return 0, 0

        try:
            config_dict = json.loads(source.parser_config)
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга parser_config для {source.name}: {e}")
            return 0, 0

        # Создаём ParserConfig
        parser_config = ParserConfig(
            name=source.name,
            url=source.url,
            category=source.category or 'Общее',
            selectors=config_dict.get('selectors', {}),
            pagination=config_dict.get('pagination'),
            headers=config_dict.get('headers'),
        )

        # Парсим
        parser = self.parser_service.create_static_parser(parser_config)
        items = parser.parse(source.url)

        # Сохраняем уникальные новости
        new_count = 0
        for item in items:
            exists = await web_news_repo.exists_by_link(source_id, item.link)
            if exists:
                logger.debug(f"🔄 Новость уже существует: {item.title[:50]}...")
                continue

            try:
                await web_news_repo.create_news(
                    source_id=source_id,
                    title=item.title,
                    link=item.link,
                    description=item.description,
                    content=item.content,
                    author=item.author,
                    published_at=item.published_at,
                    image_url=item.image_url,
                    category=source.category,
                )
                new_count += 1
                logger.debug(f"✅ Добавлена новость: {item.title[:50]}...")
            except Exception as e:
                logger.error(f"❌ Ошибка создания новости: {e}")
                continue

        # Отмечаем источник как проверенный
        await web_sources_repo.mark_checked(source_id)

        logger.info(f"📰 Из {source.name} получено {len(items)} новостей, добавлено {new_count} новых")
        return len(items), new_count

    async def process_all_active_sources(self, limit: int = 20) -> dict:
        """
        Обработать все активные источники, которые пора проверить.

        Args:
            limit: Максимальное количество источников для обработки

        Returns:
            dict: Статистика обработки
        """
        web_sources_repo = self.repo_factory.web_sources()

        sources = await web_sources_repo.get_sources_due_for_check(limit=limit)

        if not sources:
            logger.debug("📝 Нет Web источников для проверки")
            return {'sources_processed': 0, 'total_news': 0, 'new_news': 0}

        logger.info(f"🔍 Найдено {len(sources)} Web источников для проверки")

        total_news = 0
        new_news = 0
        processed_count = 0

        for source in sources:
            try:
                received, added = await self.parse_source(source.id)
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
        Отправить необработанные Web новости в общую очередь категоризации.

        Args:
            limit: Максимальное количество новостей для обработки

        Returns:
            int: Количество отправленных в очередь новостей
        """
        web_news_repo = self.repo_factory.web_news()
        web_sources_repo = self.repo_factory.web_sources()

        news_items = await web_news_repo.get_unprocessed(limit=limit)

        if not news_items:
            logger.debug("📝 Нет необработанных Web новостей")
            return 0

        logger.info(f"🔍 Найдено {len(news_items)} необработанных Web новостей")

        if not self.categorization_queue:
            logger.error("❌ CategorizationQueue не инициализирован")
            return 0

        queued_count = 0
        for news in news_items:
            try:
                # Получаем источник для title/description
                source = await web_sources_repo.get(news.source_id)
                source_title = source.name if source else 'Неизвестно'
                source_desc = source.description or ''

                # Формируем текст для категоризации
                text_for_categorization = f"{news.title}\n\n{news.description or ''}"

                # Создаём задачу на категоризацию
                task = CategorizationTask(
                    source_type='web',
                    source_id=news.id,
                    prompt=text_for_categorization,
                    original_text=text_for_categorization,
                    title=source_title,
                    desc=source_desc,
                )

                await self.categorization_queue.add(task)
                queued_count += 1
                logger.debug(f"📨 Web новость {news.id} отправлена в очередь категоризации")

            except Exception as e:
                logger.error(f"❌ Ошибка подготовки Web новости: {e}")
                continue

        logger.info(f"📨 Отправлено {queued_count}/{len(news_items)} Web новостей в очередь")
        return queued_count


# Singleton
_web_processor_service: Optional[WebProcessorService] = None


def get_web_processor_service(
    repo_factory: RepositoryFactory,
    categorization_queue: Optional[CategorizationQueue] = None,
) -> WebProcessorService:
    """Получить экземпляр Web процессор сервиса."""
    return WebProcessorService(
        repo_factory=repo_factory,
        categorization_queue=categorization_queue,
    )
