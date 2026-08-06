"""
Настройки приложения на основе pydantic-settings.

Загрузка из .env файла и переменных окружения.
"""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Основные настройки приложения.

    Пример использования:
        settings = Settings()
        print(settings.bot_token)
    """

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # Bot settings
    bot_token: str = Field(..., alias='BOT_TOKEN', description='Токен Telegram бота')
    channel_id: int | None = Field(None, alias='CHANNEL_ID', description='ID канала для публикаций')
    parse_channel_id: int | None = Field(None, alias='PARSE_CHANNEL_ID')

    # Telegram API settings
    api_id: int = Field(..., alias='API_ID', description='API ID Telegram')
    api_hash: str = Field(..., alias='API_HASH', description='API hash Telegram')
    phone_number: str = Field(..., alias='PHONE_NUMBER', description='Номер телефона')

    # Database settings
    db_path: str = Field(default='db.sqlite3', description='Путь к SQLite базе данных')

    # Ollama settings
    model_name: str = Field(default='qwen2.5:7b', description='Модель LLM')
    ollama_base_url: str = Field(default='http://localhost:11434', description='URL Ollama API')

    # Scheduler settings
    morning_hour: int = Field(default=9, description='Час утреннего запуска (МСК)')
    evening_hour: int = Field(default=21, description='Час вечернего запуска (МСК)')

    # Путь к проекту
    project_root: Path = Field(default=Path(__file__).parent.parent)

    @property
    def database_url(self) -> str:
        """Возвращает URL базы данных для SQLAlchemy."""
        return f'sqlite+aiosqlite:///{self.db_path}'

    @property
    def prompts_dir(self) -> Path:
        """Возвращает путь к директории с промптами."""
        return self.project_root / 'prompts'

    def get_prompt_path(self, prompt_name: str) -> Path:
        """
        Возвращает полный путь к файлу промпта.

        Args:
            prompt_name: Имя промпта (без расширения .txt)

        Returns:
            Полный путь к файлу промпта
        """
        return self.prompts_dir / f'{prompt_name}.txt'


# Глобальный экземпляр настроек
settings = Settings()


# Для обратной совместимости
def load_prompt(prompt_name: str) -> str:
    """
    Загружает текст промпта из файла.

    Args:
        prompt_name: Имя промпта (без расширения .txt)

    Returns:
        Текст промпта

    Raises:
        FileNotFoundError: Если файл промпта не найден
    """
    prompt_path = settings.get_prompt_path(prompt_name)

    if not prompt_path.exists():
        raise FileNotFoundError(f"Промпт '{prompt_name}' не найден в {prompt_path}")

    return prompt_path.read_text(encoding='utf-8')
