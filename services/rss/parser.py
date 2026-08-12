"""
RSS Parser Service для парсинга RSS/Atom лент.

Использует библиотеку feedparser для парсинга RSS 2.0, RSS 1.0, Atom 1.0.
Поддерживает:
- If-Modified-Since header
- ETag header
- Асинхронные HTTP запросы через aiohttp
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import feedparser
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ParsedNewsItem:
    """
    Спарсенная новость из RSS ленты.
    """
    title: str
    link: str
    description: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    guid: Optional[str] = None
    image_url: Optional[str] = None
    categories: List[str] = None

    def __post_init__(self):
        if self.categories is None:
            self.categories = []


@dataclass
class FeedMetadata:
    """
    Метаданные RSS ленты.
    """
    title: Optional[str] = None
    link: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None
    last_modified: Optional[str] = None
    etag: Optional[str] = None


class RSSParserService:
    """
    Сервис для парсинга RSS/Atom лент.
    """

    def __init__(self, timeout: int = 30):
        """
        Инициализация сервиса.

        Args:
            timeout: Таймаут HTTP запроса (секунды)
        """
        self.timeout = timeout
        self.user_agent = "News Aggregator RSS Parser (https://github.com/your-repo)"

    async def fetch_feed(
        self,
        url: str,
        last_modified: Optional[str] = None,
        etag: Optional[str] = None,
    ) -> tuple[Optional[FeedMetadata], List[ParsedNewsItem], bool]:
        """
        Получить и распарсить RSS ленту.

        Args:
            url: URL RSS ленты
            last_modified: Last-Modified header для кэширования
            etag: ETag header для кэширования

        Returns:
            Tuple[FeedMetadata, List[ParsedNewsItem], bool]:
                - Метаданные ленты
                - Список новостей
                - False если контент не изменился (304 Not Modified)
        """
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/rss+xml, application/atom+xml, text/xml',
        }

        # Добавляем headers для кэширования
        if last_modified:
            headers['If-Modified-Since'] = last_modified
        if etag:
            headers['If-None-Match'] = etag

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=self.timeout) as response:
                    # Проверяем, изменился ли контент
                    if response.status == 304:
                        logger.debug(f"📝 Контент не изменился: {url}")
                        return None, [], False

                    if response.status != 200:
                        logger.warning(f"⚠️ Ошибка получения RSS {url}: HTTP {response.status}")
                        return None, [], False

                    # Получаем новые значения Last-Modified и ETag
                    new_last_modified = response.headers.get('Last-Modified')
                    new_etag = response.headers.get('ETag')

                    # Читаем XML контент
                    xml_content = await response.text(encoding='utf-8')

        except aiohttp.ClientError as e:
            logger.error(f"❌ Ошибка HTTP при получении {url}: {e}")
            return None, [], False
        except asyncio.TimeoutError:
            logger.error(f"❌ Таймаут при получении {url}")
            return None, [], False

        # Парсим RSS
        feed = feedparser.parse(xml_content)

        # Проверяем ошибки парсинга
        if feed.bozo:
            logger.warning(f"⚠️ Ошибка парсинга RSS {url}: {feed.bozo_exception}")

        # Извлекаем метаданные
        metadata = FeedMetadata(
            title=feed.feed.get('title'),
            link=feed.feed.get('link'),
            description=feed.feed.get('description'),
            language=feed.feed.get('language'),
            last_modified=new_last_modified,
            etag=new_etag,
        )

        # Извлекаем новости
        news_items = []
        for entry in feed.entries:
            item = self._parse_entry(entry)
            if item:
                news_items.append(item)

        logger.info(f"📰 Из {url} получено {len(news_items)} новостей")
        return metadata, news_items, True

    def _parse_entry(self, entry: feedparser.FeedParserDict) -> Optional[ParsedNewsItem]:
        """
        Распарсить одну запись из RSS.

        Args:
            entry: Запись из feedparser

        Returns:
            ParsedNewsItem или None если ошибка
        """
        try:
            # Заголовок (обязательно)
            title = entry.get('title', '')
            if not title:
                return None

            # Ссылка (обязательно)
            link = entry.get('link', '')
            if not link:
                return None

            # Описание
            description = entry.get('summary', entry.get('description', ''))

            # Полный текст
            content = None
            if 'content' in entry and entry.content:
                content = entry.content[0].get('value', '')
            elif 'description' in entry:
                # Если content нет, используем description как полный текст
                content = entry.get('description', '')

            # Автор
            author = entry.get('author', '')
            if not author and 'authors' in entry and entry.authors:
                author = entry.authors[0].get('name', '')

            # Дата публикации
            published_at = None
            if 'published_parsed' in entry and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    pass

            if not published_at and 'updated_parsed' in entry and entry.updated_parsed:
                try:
                    published_at = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    pass

            # GUID
            guid = entry.get('id', link)  # Если нет ID, используем ссылку

            # Изображение
            image_url = None
            if 'media_content' in entry and entry.media_content:
                # Проверяем media:content
                for media in entry.media_content:
                    if media.get('medium') == 'image' or media.get('url', '').endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        image_url = media.get('url')
                        break

            if not image_url and 'image' in entry:
                # Проверяем media:thumbnail
                image = entry.get('image', {})
                if isinstance(image, dict):
                    image_url = image.get('href', image.get('url'))

            # Категории/теги
            categories = []
            if 'tags' in entry and entry.tags:
                for tag in entry.tags:
                    term = tag.get('term', '')
                    if term:
                        categories.append(term)

            return ParsedNewsItem(
                title=title,
                link=link,
                description=description[:500] if description else None,  # Ограничиваем описание
                content=content,
                author=author if author else None,
                published_at=published_at,
                guid=guid,
                image_url=image_url,
                categories=categories,
            )

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга записи: {e}")
            return None

    def parse_xml_string(self, xml_content: str) -> tuple[Optional[FeedMetadata], List[ParsedNewsItem]]:
        """
        Распарсить XML строку (для тестирования).

        Args:
            xml_content: XML контент

        Returns:
            Tuple[FeedMetadata, List[ParsedNewsItem]]: Метаданные и новости
        """
        feed = feedparser.parse(xml_content)

        metadata = FeedMetadata(
            title=feed.feed.get('title'),
            link=feed.feed.get('link'),
            description=feed.feed.get('description'),
            language=feed.feed.get('language'),
        )

        news_items = []
        for entry in feed.entries:
            item = self._parse_entry(entry)
            if item:
                news_items.append(item)

        return metadata, news_items


# Singleton для глобального доступа
_rss_parser_service: Optional[RSSParserService] = None


def get_rss_parser_service() -> RSSParserService:
    """Получить экземпляр RSS парсер сервиса."""
    global _rss_parser_service
    if _rss_parser_service is None:
        _rss_parser_service = RSSParserService()
    return _rss_parser_service
