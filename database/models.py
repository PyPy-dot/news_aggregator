import logging
from datetime import datetime

from aiogram import Dispatcher
from sqlalchemy import ForeignKey, String, BigInteger, Integer, DateTime, Float, Boolean, select
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine

# Приглушаем SQLAlchemy до ERROR (только критические ошибки)
logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

engine = create_async_engine(
    url='sqlite+aiosqlite:///db.sqlite3',
    echo=False  # Отключаем вывод SQL-запросов
)

async_session = async_sessionmaker(engine)


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

    async def update_trust_rating(self):
        """
        Обновляет рейтинг доверия канала на основе последних 100 новостей.
        Рейтинг = средний рейтинг последних 100 постов / 100 (нормализация к 0-1)
        """
        async with async_session() as session:
            # Получаем последние 100 новостей канала
            result = await session.execute(
                select(TelegramPost)
                .where(TelegramPost.channel_id == self.channel_id)
                .order_by(TelegramPost.created_at.desc())
                .limit(100)
            )
            posts = result.scalars().all()

            if posts:
                # Средний рейтинг новостей (нормализуем к 0-1)
                avg_rate = sum(p.rate for p in posts) / len(posts)
                self.trust_rating = min(1.0, avg_rate / 100.0)
                await session.commit()


class TelegramPost(Base):
    __tablename__ = 'posts'
    id: Mapped[int] = mapped_column(primary_key=True)
    text = mapped_column(String)
    channel_id = mapped_column(ForeignKey(Channel.channel_id))
    category = mapped_column(String)
    urgency = mapped_column(String)
    # Рейтинг новости (0-100)
    rate = mapped_column(Integer, default=50)
    # Рейтинг доверия источника на момент публикации (0.0-1.0)
    source_trust_rating = mapped_column(Float, default=0.5)
    tags = mapped_column(String)
    created_at = mapped_column(DateTime, default=datetime.now)
    # Техническое поле: оценка категории от второй ЛЛМ (0.0-1.0)
    category_confidence = mapped_column(Float, default=0.0)
    # Флаг: пост уже обработан Аналитиком (дата и время)
    analyzed_at = mapped_column(DateTime, nullable=True)
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
    # ID постов, на основе которых сгенерирована новость (JSON список)
    source_post_ids = mapped_column(String)  # JSON: [1, 2, 3]
    # ID событий/контекстов, использованных при генерации (JSON список)
    source_event_ids = mapped_column(String, default='[]')  # JSON: [1, 2]
    # Категория сгенерированной новости
    category = mapped_column(String)
    # Тэги сгенерированной новости (JSON список)
    tags = mapped_column(String, default='[]')  # JSON: ["тег1", "тег2"]
    # Статус модерации: pending, approved, rejected
    moderation_status = mapped_column(String, default='pending')
    # ID админа для модерации
    admin_id = mapped_column(BigInteger, nullable=True)
    # Флаг: новость обошла АРА (Аналитик → Редактор → Архивариус) и ушла сразу на публикацию
    bypass_ara = mapped_column(Boolean, default=False)
    # ID канала публикации (если новость опубликована)
    publisher_channel_id = mapped_column(ForeignKey('publishers.id'), nullable=True)
    # Время публикации
    published_at = mapped_column(DateTime, nullable=True)
    created_at = mapped_column(DateTime, default=datetime.now)

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
    # Краткая выжимка для векторного поиска
    summary = mapped_column(String, default='')
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
    # Дата начала подписки
    subscription_started_at = mapped_column(DateTime, nullable=True)
    # Дата окончания подписки (NULL = бессрочная)
    subscription_ends_at = mapped_column(DateTime, nullable=True)
    # Предпочтительные теги (JSON: ["тег1", "тег2"])
    preferred_tags = mapped_column(String, default='[]', nullable=False)
    # Предпочтительные категории (JSON: ["категория1", "категория2"])
    preferred_categories = mapped_column(String, default='[]', nullable=False)

    def __repr__(self):
        return f"<User(id={self.id}, role='{self.role}', has_subscription={self.has_subscription})>"

    @property
    def is_admin(self) -> bool:
        """Проверить, является ли пользователь администратором."""
        return self.role == 'admin'

    @property
    def has_active_subscription(self) -> bool:
        """Проверить, активна ли подписка."""
        if not self.has_subscription:
            return False
        if self.subscription_ends_at is None:
            # Бессрочная подписка
            return True
        return self.subscription_ends_at > datetime.now()


async def run_async_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def startup_db(dispatcher: Dispatcher):
    await run_async_db()
