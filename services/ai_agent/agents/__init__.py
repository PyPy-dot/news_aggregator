"""
AI Agents package

Агенты для обработки новостей:
- Categorizer: первичная классификация
- Analyst: анализ и тэгирование
- Editor: генерация новостей
- Archivist: создание контекста
- DirectNewsEditor: прямая генерация SMM-постов
"""

from services.ai_agent.agents.base import BaseAgent
from services.ai_agent.agents.categorizer import CategorizerAgent
from services.ai_agent.agents.analyst import AnalystAgent
from services.ai_agent.agents.editor import EditorAgent, DirectNewsEditorAgent
from services.ai_agent.agents.archivist import ArchivistAgent

__all__ = [
    'BaseAgent',
    'CategorizerAgent',
    'AnalystAgent',
    'EditorAgent',
    'DirectNewsEditorAgent',
    'ArchivistAgent',
]
