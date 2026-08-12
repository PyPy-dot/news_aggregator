"""
Categorization Service — модуль категоризации новостей.

Разделение ответственности:
- CategorizationQueue — очередь задач на категоризацию
- CategorizationProcessor — обработка AI-ответов
- NewsClassifier — классификация срочности и фильтрация
- NewsSaver — сохранение результатов в БД
"""

from services.categorization.queue import CategorizationQueue, CategorizationTask
from services.categorization.classifier import NewsClassifier
from services.categorization.saver import NewsSaver

# CategorizationProcessor импортируется отдельно для избежания циклической зависимости
# from services.categorization.processor import CategorizationProcessor

__all__ = [
    'CategorizationQueue',
    'CategorizationTask',
    'NewsClassifier',
    'NewsSaver',
    # 'CategorizationProcessor',  # Импортировать напрямую из processor.py
]
