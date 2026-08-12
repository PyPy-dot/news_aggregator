"""
Стратегии обработки новостей.

Модуль реализует паттерн Strategy для различных сценариев обработки:
- UrgentNewsStrategy — срочные новости (4-5)
- ScheduledNewsStrategy — плановые новости (1-3)
- TrustedSourceStrategy — доверенные источники
"""

from services.news.strategies.base import NewsProcessingStrategy
from services.news.strategies.urgent import UrgentNewsStrategy
from services.news.strategies.scheduled import ScheduledNewsStrategy
from services.news.strategies.trusted import TrustedSourceStrategy

__all__ = [
    'NewsProcessingStrategy',
    'UrgentNewsStrategy',
    'ScheduledNewsStrategy',
    'TrustedSourceStrategy',
]
