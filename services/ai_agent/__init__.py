"""
AI Agent package

Агенты для обработки новостей через LLM (Ollama).
"""

from services.ai_agent.agents import (
    BaseAgent,
    CategorizerAgent,
    AnalystAgent,
    EditorAgent,
    ArchivistAgent,
)

__all__ = [
    'BaseAgent',
    'CategorizerAgent',
    'AnalystAgent',
    'EditorAgent',
    'ArchivistAgent',
]
