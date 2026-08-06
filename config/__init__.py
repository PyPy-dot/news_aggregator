"""
Конфигурация приложения.

Настройки загружаются из .env файла через pydantic-settings.
"""

from config.settings import Settings, settings, load_prompt

__all__ = ['Settings', 'settings', 'load_prompt']
