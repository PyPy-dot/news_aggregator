"""
Web Parsing module.

Модуль для парсинга сайтов без RSS лент.
"""

from services.web.parser import WebParserService, StaticWebParser, ParsedNewsItem

__all__ = [
    "WebParserService",
    "StaticWebParser",
    "ParsedNewsItem",
]
