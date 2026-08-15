"""
Web Parser Service для парсинга сайтов.

Поддерживает:
- requests + bs4 (статические сайты)
- Конфигурация через JSON/YAML
- Извлечение новостей по селекторам
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ParsedNewsItem:
    """Спарсенная новость с сайта."""
    title: str
    link: str
    description: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    category: Optional[str] = None


@dataclass
class ParserConfig:
    """Конфигурация парсера для сайта."""
    name: str
    url: str
    category: str
    selectors: Dict[str, str]  # article, title, link, date, content, etc.
    pagination: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None


class StaticWebParser:
    """
    Парсер для статических сайтов (requests + bs4).
    """

    def __init__(self, config: ParserConfig, timeout: int = 30):
        """
        Инициализация парсера.

        Args:
            config: Конфигурация парсера
            timeout: Таймаут запроса (секунды)
        """
        self.config = config
        self.timeout = timeout
        self.session = requests.Session()

        if config.headers:
            self.session.headers.update(config.headers)
        else:
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })

    def fetch_page(self, url: str) -> Optional[str]:
        """
        Получить HTML страницу.

        Args:
            url: URL страницы

        Returns:
            HTML контент или None при ошибке
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"❌ Ошибка получения {url}: {e}")
            return None

    def parse_article(self, soup: BeautifulSoup, article_element) -> Optional[ParsedNewsItem]:
        """
        Распарсить одну новость.

        Args:
            soup: BeautifulSoup объект
            article_element: Элемент новости

        Returns:
            ParsedNewsItem или None
        """
        try:
            selectors = self.config.selectors

            # Заголовок
            title_elem = article_element.select_one(selectors.get('title', ''))
            title = title_elem.get_text(strip=True) if title_elem else None
            if not title:
                return None

            # Ссылка
            link_elem = article_element.select_one(selectors.get('link', ''))
            link = link_elem.get('href', '') if link_elem else None
            if not link:
                return None

            # Полная ссылка
            if link.startswith('/'):
                from urllib.parse import urljoin
                link = urljoin(self.config.url, link)

            # Описание
            desc_elem = article_element.select_one(selectors.get('description', ''))
            description = desc_elem.get_text(strip=True)[:500] if desc_elem else None

            # Дата публикации
            published_at = None
            date_elem = article_element.select_one(selectors.get('date', ''))
            if date_elem:
                date_str = date_elem.get_text(strip=True)
                # Попытка распарсить дату (упрощённо)
                try:
                    published_at = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except ValueError:
                    pass

            # Изображение
            image_url = None
            img_elem = article_element.select_one(selectors.get('image', ''))
            if img_elem:
                image_url = img_elem.get('src', '')

            return ParsedNewsItem(
                title=title,
                link=link,
                description=description,
                author=None,
                published_at=published_at,
                image_url=image_url,
                category=self.config.category,
            )

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга новости: {e}")
            return None

    def parse(self, url: str) -> List[ParsedNewsItem]:
        """
        Распарсить страницу и извлечь новости.

        Args:
            url: URL страницы

        Returns:
            Список новостей
        """
        html = self.fetch_page(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'lxml')

        # Находим все новости
        article_selector = self.config.selectors.get('article', '')
        articles = soup.select(article_selector)

        news_items = []
        for article in articles:
            item = self.parse_article(soup, article)
            if item:
                news_items.append(item)

        logger.info(f"📰 Из {url} получено {len(news_items)} новостей")
        return news_items


class WebParserService:
    """
    Сервис для управления Web парсингом.
    """

    def __init__(self, timeout: int = 30):
        """
        Инициализация сервиса.

        Args:
            timeout: Таймаут запроса (секунды)
        """
        self.timeout = timeout

    def create_static_parser(self, config: ParserConfig) -> StaticWebParser:
        """
        Создать статический парсер.

        Args:
            config: Конфигурация парсера

        Returns:
            StaticWebParser
        """
        return StaticWebParser(config, timeout=self.timeout)

    def parse_site(self, config: ParserConfig) -> List[ParsedNewsItem]:
        """
        Распарсить сайт.

        Args:
            config: Конфигурация парсера

        Returns:
            Список новостей
        """
        parser = self.create_static_parser(config)
        return parser.parse(config.url)


# Singleton
_web_parser_service: Optional[WebParserService] = None


def get_web_parser_service() -> WebParserService:
    """Получить экземпляр сервиса."""
    global _web_parser_service
    if _web_parser_service is None:
        _web_parser_service = WebParserService()
    return _web_parser_service
