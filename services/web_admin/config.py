"""
Конфигурация Web Admin.

Загружает настройки из .env файла и предоставляет их для использования в приложении.
"""

import os
from pathlib import Path
from typing import Optional

# Проект находится в services/web_admin/, .env в корне проекта
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_env() -> None:
    """Загрузить переменные окружения из .env файла."""
    if ENV_FILE.exists():
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)


# Загружаем .env при импорте модуля
load_env()


class Config:
    """Конфигурация приложения Web Admin."""

    # Версия приложения
    APP_VERSION: str = os.getenv("APP_VERSION", "4.0.0")

    # JWT секрет
    JWT_SECRET: Optional[str] = os.getenv("WEB_ADMIN_JWT_SECRET")

    # Хост и порт сервера
    HOST: str = os.getenv("WEB_ADMIN_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("WEB_ADMIN_PORT", "8001"))

    # Время жизни сессии (часы)
    SESSION_EXPIRE_HOURS: int = int(os.getenv("WEB_ADMIN_SESSION_EXPIRE_HOURS", "3"))


# Глобальный экземпляр конфигурации
config = Config()


def get_version() -> str:
    """Получить версию приложения."""
    return config.APP_VERSION
