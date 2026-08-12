"""
RSS parsing module.

Модуль для парсинга RSS/Atom лент новостей.
"""

from services.rss.parser import (
    RSSParserService,
    ParsedNewsItem,
    FeedMetadata,
    get_rss_parser_service,
)

__all__ = [
    "RSSParserService",
    "ParsedNewsItem",
    "FeedMetadata",
    "get_rss_parser_service",
]
