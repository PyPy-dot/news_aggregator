"""
Настройки приложения на основе pydantic-settings.

Загрузка из .env файла и переменных окружения.
"""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Путь к корню проекта (на 2 уровня выше этого файла)
PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    """
    Основные настройки приложения.

    Пример использования:
        settings = Settings()
        print(settings.bot_token)
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / '.env',
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

    # Telegram Session (для ListenerBot / UserBot)
    telegram_session_string: str | None = Field(default=None, alias='TELEGRAM_SESSION_STRING', description='Session string для сохранения авторизации')

    # Admin ID (для авторизации ListenerBot через бота)
    admin_id: int | None = Field(default=None, alias='ADMIN_ID', description='Telegram ID администратора для авторизации')

    # Telegram Proxy (опционально, для обхода блокировок)
    telegram_proxy: str | None = Field(default=None, alias='TELEGRAM_PROXY', description='Proxy URL для Telegram (socks5://host:port)')
    telegram_mtproto_proxy: str | None = Field(default=None, alias='TELEGRAM_MTPROTO_PROXY', description='MTProto proxy для Telegram (server:port:secret)')
    telegram_use_ipv6: bool = Field(default=True, alias='TELEGRAM_USE_IPV6', description='Использовать IPv6 для подключения к Telegram (true/false в зависимости от сети)')
    disable_listener_bot: bool = Field(default=False, alias='DISABLE_LISTENER_BOT', description='Отключить ListenerBot (если Telegram заблокирован)')

    # 2FA настройки (для защиты Listener Bot)
    listener_2fa_enabled: bool = Field(default=False, alias='LISTENER_2FA_ENABLED', description='Включить 2FA для авторизации Listener Bot')
    listener_2fa_secret: str | None = Field(default=None, alias='LISTENER_2FA_SECRET', description='Секретный ключ для TOTP 2FA (base32)')
    listener_2fa_provider: str = Field(default='yandex', alias='LISTENER_2FA_PROVIDER', description='Провайдер 2FA: yandex или google')

    # Database settings
    db_path: str = Field(default='db.sqlite3', description='Путь к SQLite базе данных (если не указан DATABASE_URL)')
    database_url: str | None = Field(default=None, alias='DATABASE_URL', description='URL подключения к БД (PostgreSQL, MySQL или SQLite)')

    # Database pool settings
    db_pool_size: int = Field(default=10, description='Размер пула подключений к БД')
    db_max_overflow: int = Field(default=20, description='Максимальное количество подключений сверх pool_size')
    db_pool_timeout: int = Field(default=30, description='Таймаут ожидания подключения из пула (секунды)')
    db_pool_recycle: int = Field(default=1800, description='Время пересоздания подключения (секунды)')
    db_echo: bool = Field(default=False, description='Логировать SQL запросы')

    # LLM Provider settings (Fallback)
    llm_primary_provider: str = Field(
        default='ollama',
        description='Основной LLM провайдер: ollama, openai, anthropic'
    )

    # Ollama settings
    model_name: str = Field(default='qwen2.5:7b', description='Модель LLM')
    ollama_base_url: str = Field(default='http://localhost:11434', description='URL Ollama API')

    # OpenAI settings
    openai_api_key: str | None = Field(default=None, description='API ключ OpenAI')
    openai_model: str = Field(default='gpt-4o-mini', description='Модель OpenAI по умолчанию')
    openai_base_url: str | None = Field(default=None, description='Базовый URL OpenAI API (опционально)')

    # Anthropic settings
    anthropic_api_key: str | None = Field(default=None, description='API ключ Anthropic')
    anthropic_model: str = Field(default='claude-sonnet-4-20250514', description='Модель Anthropic по умолчанию')

    # Fallback settings
    llm_retry_attempts: int = Field(default=3, description='Количество попыток перед fallback')
    llm_retry_delay_seconds: int = Field(default=2, description='Задержка между попытками (сек)')
    llm_fallback_enabled: bool = Field(default=True, description='Включить автоматический fallback')

    # Scheduler settings
    event_processing_interval_hours: int = Field(
        default=48,
        description='Интервал обработки событий (часы)'
    )

    # AI Agent settings
    agent_model: str = Field(default='qwen2.5:7b', description='Модель для AI агентов')
    agent_message_history_limit: int = Field(
        default=3,
        description='Лимит истории сообщений для агентов'
    )
    categorizer_history_limit: int = Field(default=2, description='Лимит истории для категоризатора')

    # Vector search settings
    vector_search_events_limit: int = Field(default=5, description='Лимит похожих событий')
    vector_search_posts_limit: int = Field(default=10, description='Лимит похожих постов')
    vector_search_min_score_events: float = Field(
        default=0.7,
        description='Минимальный порог сходства для событий'
    )
    vector_search_min_score_posts: float = Field(
        default=0.6,
        description='Минимальный порог сходства для постов'
    )

    # Cache settings
    processed_messages_cache_max: int = Field(
        default=1000,
        description='Максимальный размер кэша обработанных сообщений'
    )
    processed_messages_cache_trim: int = Field(
        default=500,
        description='Размер кэша после обрезки'
    )
    categorization_queue_maxlen: int = Field(
        default=10,
        description='Максимальный размер очереди категоризации'
    )

    # Database settings
    channel_trust_window_size: int = Field(
        default=100,
        description='Количество последних постов для расчёта рейтинга канала'
    )
    repository_default_limit: int = Field(default=100, description='Лимит по умолчанию для репозиториев')

    # Путь к проекту
    project_root: Path = Field(default=Path(__file__).parent.parent)

    # Payment settings
    payment_provider: str = Field(
        default='test',
        description='Платёжный провайдер: test, telegram_stars'
    )
    subscription_price_rub: float = Field(
        default=99.0,
        description='Цена подписки в рублях'
    )
    subscription_duration_days: int = Field(
        default=30,
        description='Длительность подписки в днях'
    )

    @property
    def database_url_resolved(self) -> str:
        """
        Возвращает URL базы данных для SQLAlchemy.

        Приоритет:
        1. DATABASE_URL из окружения (если указан)
        2. SQLite из db_path (по умолчанию)
        """
        if self.database_url:
            return self.database_url
        return f'sqlite+aiosqlite:///{self.db_path}'

    @property
    def is_postgresql(self) -> bool:
        """Проверяет, используется ли PostgreSQL."""
        url = self.database_url_resolved
        return url.startswith('postgresql+asyncpg') or url.startswith('postgresql://')

    @property
    def is_mysql(self) -> bool:
        """Проверяет, используется ли MySQL."""
        url = self.database_url_resolved
        return url.startswith('mysql+aiomysql') or url.startswith('mysql://')

    @property
    def is_sqlite(self) -> bool:
        """Проверяет, используется ли SQLite."""
        url = self.database_url_resolved
        return url.startswith('sqlite+aiosqlite') or url.startswith('sqlite://')

    def get_database_config(self) -> 'DatabaseConfig':
        """
        Получить конфигурацию базы данных для нового абстрактного слоя.

        Returns:
            DatabaseConfig экземпляр
        """
        from services.database.config import DatabaseConfig
        from services.database.enums import DatabaseType

        url = self.database_url_resolved
        db_type = DatabaseType.from_url(url)

        # Определяем размер пула в зависимости от СУБД
        pool_size = self.db_pool_size
        if db_type == DatabaseType.SQLITE:
            pool_size = 1  # SQLite не поддерживает многопоточность по умолчанию

        return DatabaseConfig(
            url=url,
            db_type=db_type,
            echo=self.db_echo,
            pool_size=pool_size,
            max_overflow=self.db_max_overflow,
            pool_timeout=self.db_pool_timeout,
            pool_recycle=self.db_pool_recycle,
            pool_pre_ping=True,
        )

    @property
    def event_processing_interval_seconds(self) -> int:
        """Интервал обработки событий в секундах."""
        return self.event_processing_interval_hours * 3600

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
