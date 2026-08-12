import logging
from datetime import datetime

from sqlalchemy import ForeignKey, String, BigInteger, Integer, DateTime, Float, Boolean, select, Text
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker

# Приглушаем SQLAlchemy до ERROR (только критические ошибки)
logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

# Импортируем настройки для использования в моделях
from config.settings import settings

# =============================================================================
# УДАЛЕНО: engine создаётся в DatabaseService (services/core/database.py)
# Этот файл содержит только модели данных
# =============================================================================


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = 'channels'
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id = mapped_column(BigInteger)
    title = mapped_column(String)
    description = mapped_column(String)
    # Рейтинг доверия источника (0.0 - 1.0)
    trust_rating: Mapped[float] = mapped_column(Float, default=0.5)
    # Флаг доверенного источника (новости имеют рейтинг 100)
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    # Теги типов постов канала (JSON: ["Политика", "Воздушная тревога"])
    tags: Mapped[str] = mapped_column(String, default='[]')

    # Связь с постами
    posts = relationship("TelegramPost", back_populates="channel")


class TelegramPost(Base):
    __tablename__ = 'posts'
    id: Mapped[int] = mapped_column(primary_key=True)
    text = mapped_column(String)
    channel_id = mapped_column(ForeignKey(Channel.channel_id))
    category = mapped_column(String, index=True)  # Индекс для фильтрации по категории
    urgency = mapped_column(String, index=True)  # Индекс для фильтрации по срочности
    # Рейтинг новости (0-100)
    rate = mapped_column(Integer, default=50)
    # Рейтинг доверия источника на момент публикации (0.0-1.0)
    source_trust_rating = mapped_column(Float, default=0.5)
    tags = mapped_column(String)
    created_at = mapped_column(DateTime, default=datetime.now, index=True)  # Индекс для сортировки по времени
    # Техническое поле: оценка категории от второй ЛЛМ (0.0-1.0)
    category_confidence = mapped_column(Float, default=0.0)
    # Флаг: пост уже обработан Аналитиком (Boolean)
    checked_at = mapped_column(Boolean, default=False, index=True)  # Индекс для поиска необработанных
    # ID сгенерированной новости (если есть)
    generated_news_id = mapped_column(Integer, nullable=True)
    # Флаг: пост обошёл АРА и ушёл сразу на публикацию
    bypass_ara = mapped_column(Boolean, default=False)
    # ID канала публикации (если пост опубликован напрямую)
    publisher_channel_id = mapped_column(ForeignKey('publishers.id'), nullable=True)

    # Связь с каналом
    channel = relationship("Channel", back_populates="posts")
    # Связь с publisher
    publisher = relationship("Publisher", back_populates="direct_posts", foreign_keys=[publisher_channel_id])


class GeneratedNews(Base):
    __tablename__ = 'generated_news'
    id: Mapped[int] = mapped_column(primary_key=True)
    # Сгенерированный текст новости
    text = mapped_column(String)
    # ID событий/контекстов, использованных при генерации (JSON список)
    source_event_ids = mapped_column(String, default='[]')  # JSON: [1, 2]
    # Категория сгенерированной новости
    category = mapped_column(String, index=True)  # Индекс для фильтрации по категории
    # Тэги сгенерированной новости (JSON список)
    tags = mapped_column(String, default='[]')  # JSON: ["тег1", "тег2"]
    # Статус модерации: pending, approved, rejected, edited
    moderation_status = mapped_column(String, default='pending', index=True)  # Индекс для поиска по статусу
    # ID админа для модерации
    admin_id = mapped_column(BigInteger, nullable=True)
    # Флаг: новость обошла АРА (Аналитик → Редактор → Архивариус) и ушла сразу на публикацию
    bypass_ara = mapped_column(Boolean, default=False)
    # ID канала публикации (если новость опубликована)
    publisher_channel_id = mapped_column(ForeignKey('publishers.id'), nullable=True)
    # Время публикации
    published_at = mapped_column(DateTime, nullable=True)
    created_at = mapped_column(DateTime, default=datetime.now, index=True)  # Индекс для сортировки по времени

    # Связь с publisher
    publisher = relationship("Publisher", back_populates="published_news")


class EventContext(Base):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(primary_key=True)
    # ID оригинального поста
    post_id = mapped_column(ForeignKey(TelegramPost.id))
    # Контекст события (JSON)
    context_data = mapped_column(String)  # JSON строка с контекстом
    # Категория события (для группировки)
    event_category = mapped_column(String)
    # Тэги события (JSON список)
    tags = mapped_column(String, default='[]')  # JSON: ["тег1", "тег2"]
    # Время последней обработки планировщиком
    last_processed_at = mapped_column(DateTime, nullable=True)
    created_at = mapped_column(DateTime, default=datetime.now)


class Publisher(Base):
    __tablename__ = 'publishers'
    id: Mapped[int] = mapped_column(primary_key=True)
    # ID канала в Telegram
    channel_id = mapped_column(BigInteger, unique=True)
    # Название канала
    title = mapped_column(String)
    # Описание канала
    description = mapped_column(String, default='')
    # Активен ли канал для публикации
    is_active = mapped_column(Boolean, default=True)
    # Категория канала (опционально)
    category = mapped_column(String, nullable=True)
    created_at = mapped_column(DateTime, default=datetime.now)

    # Связь с опубликованными новостями
    published_news = relationship("GeneratedNews", back_populates="publisher",
                                  foreign_keys="GeneratedNews.publisher_channel_id")
    # Связь с прямыми постами (обошедшими АРА)
    direct_posts = relationship("TelegramPost", back_populates="publisher",
                                foreign_keys="TelegramPost.publisher_channel_id")
    # Связь с задачами на прямую генерацию
    direct_generation_tasks = relationship("Task", back_populates="publisher",
                                           foreign_keys="Task.publisher_channel_id")

    def __repr__(self):
        return f"<Publisher(id={self.id}, title='{self.title}', channel_id={self.channel_id})>"


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    # Зашифрованный ID пользователя Telegram (AES-256-GCM) — для хранения
    user_id_encrypted = mapped_column(String, nullable=False)
    # HMAC-SHA256 хэш ID пользователя — для поиска (детерминированный)
    user_id_hash = mapped_column(String, unique=True, nullable=False, index=True)
    # Роль пользователя: 'user' или 'admin'
    role = mapped_column(String(20), default='user', nullable=False)
    # Дата регистрации в боте
    created_at = mapped_column(DateTime, default=datetime.now, nullable=False)
    # Наличие активной подписки
    has_subscription = mapped_column(Boolean, default=False, nullable=False)
    # Дата начала подписки (пустая строка конвертируется в None)
    subscription_started_at = mapped_column(DateTime, nullable=True)
    # Дата окончания подписки (NULL = бессрочная, пустая строка конвертируется в None)
    subscription_ends_at = mapped_column(DateTime, nullable=True)
    # Предпочтительные теги (JSON: ["тег1", "тег2"])
    preferred_tags = mapped_column(String, default='[]', nullable=False)
    # Предпочтительные категории (JSON: ["категория1", "категория2"])
    preferred_categories = mapped_column(String, default='[]', nullable=False)

    # 2FA поля (TOTP для администраторов)
    # TOTP секрет для Google Authenticator / Authy
    totp_secret = mapped_column(String(256), nullable=True)
    # Флаг включения 2FA
    totp_enabled = mapped_column(Boolean, default=False, nullable=False)
    # Резервные коды для восстановления (JSON: ["code1", "code2", ...])
    totp_backup_codes = mapped_column(sa.Text, nullable=True)

    def __init__(self, **kwargs):
        # Конвертируем пустые строки в None для datetime полей
        for field in ['subscription_started_at', 'subscription_ends_at']:
            if field in kwargs and kwargs[field] == '':
                kwargs[field] = None
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<User(id={self.id}, role='{self.role}', has_subscription={self.has_subscription}, totp_enabled={self.totp_enabled})>"

    @property
    def is_admin(self) -> bool:
        """Проверить, является ли пользователь администратором."""
        return self.role == 'admin'

    @property
    def has_active_subscription(self) -> bool:
        """Проверить, активна ли подписка."""
        if not self.has_subscription:
            return False

        # Нормализуем пустую строку в None
        subscription_ends_at = self.subscription_ends_at
        if subscription_ends_at == '':
            subscription_ends_at = None

        if subscription_ends_at is None:
            # Бессрочная подписка
            return True

        return subscription_ends_at > datetime.now()

    @property
    def has_2fa_enabled(self) -> bool:
        """Проверить, включена ли 2FA."""
        return self.totp_enabled and self.totp_secret is not None


class NewsCategory(Base):
    """
    Справочник категорий новостей.
    """
    __tablename__ = 'news_categories'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, default='')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<NewsCategory(id={self.id}, name='{self.name}', active={self.is_active})>"


class Task(Base):
    """
    Задачи для обработки (прямая генерация, плановая обработка, периодические задачи).

    Статусы задач:
    - pending: Ожидает времени выполнения
    - active: Взято в работу (обрабатывается прямо сейчас)
    - completed: Одноразовая задача успешно завершена
    - failed: Одноразовая задача не выполнена (ошибка)
    - expired: Одноразовая задача просрочена (не успели взять в работу)
    - canceled: Задача отменена админом

    Периодические задачи (recurring=True) циклически переходят: pending → active → pending
    Одноразовые задачи (recurring=False) завершаются терминальным статусом.
    """
    __tablename__ = 'tasks'

    id: Mapped[int] = mapped_column(primary_key=True)
    task_type: Mapped[str] = mapped_column(String, nullable=False)  # 'direct_generation', 'scheduled_processing', 'daily_morning', 'daily_evening'
    description: Mapped[str] = mapped_column(String, default='')
    post_id: Mapped[int] = mapped_column(Integer, nullable=True)  # Для прямой генерации
    news_id: Mapped[int] = mapped_column(Integer, nullable=True)  # Для плановой обработки
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # Дата/время выполнения
    status: Mapped[str] = mapped_column(String, default='pending')  # pending, active, completed, failed, expired, canceled
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)  # Флаг периодической задачи
    recurrence_pattern: Mapped[int] = mapped_column(Integer, nullable=True)  # Периодичность в днях (1=ежедневно, 2=раз в 2 дня, и т.д.)
    publisher_channel_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id'), nullable=True)  # Канал публикации
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Связь с publisher
    publisher = relationship("Publisher", back_populates="direct_generation_tasks", foreign_keys=[publisher_channel_id])

    def __repr__(self):
        return f"<Task(id={self.id}, type='{self.task_type}', status='{self.status}', recurring={self.recurring})>"


class RSSSource(Base):
    """
    Источник RSS лент (сайт).
    """
    __tablename__ = 'rss_sources'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # Название источника
    url: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)  # URL RSS ленты
    site_url: Mapped[str] = mapped_column(String(512), nullable=True)  # URL сайта
    category: Mapped[str] = mapped_column(String(100), nullable=True)  # Категория
    description: Mapped[str] = mapped_column(String(1024), nullable=True)  # Описание
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # Активен ли
    last_checked: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # Последняя проверка
    last_modified: Mapped[str] = mapped_column(String(255), nullable=True)  # Last-Modified header
    etag: Mapped[str] = mapped_column(String(255), nullable=True)  # ETag header
    check_interval_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)  # Интервал проверки
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    # Связь с новостями
    news = relationship("RSSNews", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RSSSource(id={self.id}, name='{self.name}', url='{self.url}', active={self.is_active})>"


class RSSNews(Base):
    """
    Новость из RSS ленты.
    """
    __tablename__ = 'rss_news'

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey('rss_sources.id', ondelete='CASCADE'), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)  # Заголовок
    description: Mapped[str] = mapped_column(sa.Text, nullable=True)  # Описание/анонс
    content: Mapped[str] = mapped_column(sa.Text, nullable=True)  # Полный текст
    link: Mapped[str] = mapped_column(String(1024), nullable=False)  # Ссылка на новость
    author: Mapped[str] = mapped_column(String(255), nullable=True)  # Автор
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # Дата публикации
    guid: Mapped[str] = mapped_column(String(1024), nullable=True)  # Уникальный ID
    image_url: Mapped[str] = mapped_column(String(512), nullable=True)  # URL изображения
    category: Mapped[str] = mapped_column(String(100), nullable=True)  # Категория
    tags: Mapped[str] = mapped_column(String(512), nullable=True)  # Теги (JSON)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Обработана ли
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey('posts.id', ondelete='SET NULL'), nullable=True)  # Связанный пост
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    # Связь с источником
    source = relationship("RSSSource", back_populates="news")
    # Связь с постом
    post = relationship("TelegramPost", backref="rss_news")

    def __repr__(self):
        return f"<RSSNews(id={self.id}, title='{self.title[:50]}...', source_id={self.source_id}, processed={self.processed})>"


class WebSource(Base):
    """
    Источник для Web парсинга (сайт).
    """
    __tablename__ = 'web_sources'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(String(1024), nullable=True)
    parser_config: Mapped[str] = mapped_column(sa.Text, nullable=True)  # JSON конфигурация
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    check_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    # Связь с новостями
    news = relationship("WebNews", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<WebSource(id={self.id}, name='{self.name}', url='{self.url}', active={self.is_active})>"


class WebNews(Base):
    """
    Новость из Web источника.
    """
    __tablename__ = 'web_news'

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey('web_sources.id', ondelete='CASCADE'), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=True)
    content: Mapped[str] = mapped_column(sa.Text, nullable=True)
    link: Mapped[str] = mapped_column(String(1024), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    image_url: Mapped[str] = mapped_column(String(512), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    tags: Mapped[str] = mapped_column(String(512), nullable=True)  # JSON
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey('posts.id', ondelete='SET NULL'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    # Связь с источником
    source = relationship("WebSource", back_populates="news")
    # Связь с постом
    post = relationship("TelegramPost", backref="web_news")

    def __repr__(self):
        return f"<WebNews(id={self.id}, title='{self.title[:50]}...', source_id={self.source_id}, processed={self.processed})>"


async def run_async_db():
    """
    Создать все таблицы в базе данных.

    Использует DatabaseService для получения engine.
    """
    from services.core.database import get_database_service

    db_service = get_database_service()
    async with db_service.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def startup_db():
    """Инициализировать базу данных при старте."""
    await run_async_db()
