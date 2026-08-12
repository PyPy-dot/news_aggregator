"""
Тесты для News Aggregator.

Запуск:
    pytest tests/ -v
    pytest tests/ -v --cov=services --cov=database
"""

import pytest
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from database.models import Base


# Фикстуры
@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Создать тестовую сессию БД.

    Использует in-memory SQLite для тестов.
    """
    engine = create_async_engine(
        'sqlite+aiosqlite:///:memory:',
        echo=False
    )

    # Создаём таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session = async_sessionmaker(engine, expire_on_commit=False)()

    yield session

    # Очищаем после теста
    await session.close()
    await engine.dispose()


@pytest.fixture
def mock_channel_data() -> dict:
    """Данные тестового канала."""
    return {
        'channel_id': -1001234567890,
        'title': 'Test Channel',
        'description': 'Test Description',
        'is_trusted': False
    }


@pytest.fixture
def mock_post_data() -> dict:
    """Данные тестового поста."""
    return {
        'channel_id': -1001234567890,
        'text': 'Test post text',
        'category': 'Политика',
        'urgency': 3,
        'rate': 50,
        'source_trust_rating': 0.5,
        'tags': '["тест", "политика"]'
    }


@pytest.fixture
def mock_event_data() -> dict:
    """Данные тестового события."""
    return {
        'post_id': 1,
        'context_data': {
            'event_description': 'Test event',
            'participants': [],
            'location': 'Test',
            'consequences': []
        },
        'event_category': 'Политика',
        'tags': '["тест"]'
    }


@pytest.fixture
def mock_news_data() -> dict:
    """Данные тестовой новости."""
    return {
        'text': 'Generated news text',
        'category': 'Политика',
        'source_event_ids': [1],
        'tags': '["тест", "новость"]',
        'moderation_status': 'pending'
    }


@pytest.fixture
def test_user_id() -> int:
    """Test user ID."""
    return 123456789


@pytest.fixture
def test_channel_id() -> int:
    """Test channel ID."""
    return -1001234567890


@pytest.fixture
def test_post_id() -> int:
    """Test post ID."""
    return 1
