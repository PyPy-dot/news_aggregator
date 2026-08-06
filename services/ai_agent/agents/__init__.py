"""
AI Agents package

Агенты для обработки новостей:
- Categorizer: первичная классификация
- Analyst: анализ и тэгирование
- Editor: генерация новостей
- Archivist: создание контекста
"""

from services.ai_agent.agents.base import BaseAgent
from services.ai_agent.agents.categorizer import CategorizerAgent
from services.ai_agent.agents.analyst import AnalystAgent
from services.ai_agent.agents.editor import EditorAgent
from services.ai_agent.agents.archivist import ArchivistAgent

__all__ = [
    'BaseAgent',
    'CategorizerAgent',
    'AnalystAgent',
    'EditorAgent',
    'ArchivistAgent',
]
