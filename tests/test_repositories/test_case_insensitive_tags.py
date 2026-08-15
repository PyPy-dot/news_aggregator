"""
Тесты для проверки case-insensitive учёта тэгов и категорий.

Проверяет:
1. Нормализация тэгов при сохранении (lowercase)
2. Поиск тэгов без учёта регистра
3. Добавление/удаление тэгов без учёта регистра
"""

import pytest
import json
from sqlalchemy.ext.asyncio import AsyncSession

from database.repositories.users import UserRepository
from database.repositories.posts import PostRepository
from database.repositories.channels import ChannelRepository
from database.repositories.events import EventRepository


@pytest.fixture
async def user_repo(db_session: AsyncSession) -> UserRepository:
    """Создать репозиторий пользователей."""
    return UserRepository(db_session)


@pytest.fixture
async def post_repo(db_session: AsyncSession) -> PostRepository:
    """Создать репозиторий постов."""
    return PostRepository(db_session)


@pytest.fixture
async def channel_repo(db_session: AsyncSession) -> ChannelRepository:
    """Создать репозиторий каналов."""
    return ChannelRepository(db_session)


@pytest.fixture
async def event_repo(db_session: AsyncSession) -> EventRepository:
    """Создать репозиторий событий."""
    return EventRepository(db_session)


class TestUserRepository_CaseInsensitive:
    """Тесты для UserRepository с учётом регистра."""

    async def test_create_user_normalizes_tags(
        self, user_repo: UserRepository, test_user_id: int
    ):
        """Создание пользователя нормализует тэги к lowercase."""
        user = await user_repo.create_user(
            telegram_id=test_user_id,
            preferred_tags=['Политика', 'ЭКОНОМИКА', 'Украина'],
            preferred_categories=['НОВОСТИ', 'Спорт']
        )

        tags = json.loads(user.preferred_tags)
        categories = json.loads(user.preferred_categories)

        assert tags == ['политика', 'экономика', 'украина']
        assert categories == ['новости', 'спорт']

    async def test_update_preferences_normalizes_tags(
        self, user_repo: UserRepository, test_user_id: int
    ):
        """Обновление предпочтений нормализует тэги."""
        # Создаём пользователя
        await user_repo.create_user(telegram_id=test_user_id)

        # Обновляем с разными регистрами
        await user_repo.update_preferences(
            telegram_id=test_user_id,
            preferred_tags=['ФУТБОЛ', 'Теннис'],
            preferred_categories=['СПОРТ']
        )

        prefs = await user_repo.get_preferences(test_user_id)

        assert prefs['preferred_tags'] == ['футбол', 'теннис']
        assert prefs['preferred_categories'] == ['спорт']

    async def test_add_tag_case_insensitive(
        self, user_repo: UserRepository, test_user_id: int
    ):
        """Добавление тега не зависит от регистра."""
        await user_repo.create_user(
            telegram_id=test_user_id,
            preferred_tags=['политика']  # lowercase
        )

        # Пытаемся добавить "ПОЛИТИКА" (uppercase) — не должен добавиться дубликат
        await user_repo.add_preferred_tag(test_user_id, 'ПОЛИТИКА')

        prefs = await user_repo.get_preferences(test_user_id)
        # Должен остаться только один тег
        assert prefs['preferred_tags'] == ['политика']
        assert len(prefs['preferred_tags']) == 1

    async def test_remove_tag_case_insensitive(
        self, user_repo: UserRepository, test_user_id: int
    ):
        """Удаление тега не зависит от регистра."""
        await user_repo.create_user(
            telegram_id=test_user_id,
            preferred_tags=['политика', 'экономика']
        )

        # Удаляем "ПОЛИТИКА" (uppercase)
        await user_repo.remove_preferred_tag(test_user_id, 'ПОЛИТИКА')

        prefs = await user_repo.get_preferences(test_user_id)
        # Должна остаться только "экономика"
        assert prefs['preferred_tags'] == ['экономика']

    async def test_add_category_case_insensitive(
        self, user_repo: UserRepository, test_user_id: int
    ):
        """Добавление категории не зависит от регистра."""
        await user_repo.create_user(
            telegram_id=test_user_id,
            preferred_categories=['новости']
        )

        # Пытаемся добавить "НОВОСТИ" — не должен добавиться дубликат
        await user_repo.add_preferred_category(test_user_id, 'НОВОСТИ')

        prefs = await user_repo.get_preferences(test_user_id)
        assert prefs['preferred_categories'] == ['новости']
        assert len(prefs['preferred_categories']) == 1

    async def test_remove_category_case_insensitive(
        self, user_repo: UserRepository, test_user_id: int
    ):
        """Удаление категории не зависит от регистра."""
        await user_repo.create_user(
            telegram_id=test_user_id,
            preferred_categories=['новости', 'спорт']
        )

        # Удаляем "НОВОСТИ" (uppercase)
        await user_repo.remove_preferred_category(test_user_id, 'НОВОСТИ')

        prefs = await user_repo.get_preferences(test_user_id)
        assert prefs['preferred_categories'] == ['спорт']


class TestPostRepository_CaseInsensitive:
    """Тесты для PostRepository с учётом регистра."""

    async def test_create_post_normalizes_tags(
        self, post_repo: PostRepository, test_channel_id: int
    ):
        """Создание поста нормализует тэги."""
        post = await post_repo.create_post(
            channel_id=test_channel_id,
            text='Тестовый пост',
            category='Политика',
            urgency=3,
            tags='["УКРАИНА", "политика", "Киев"]'
        )

        tags = json.loads(post.tags)
        assert tags == ['украина', 'политика', 'киев']

    async def test_add_tag_case_insensitive(
        self, post_repo: PostRepository, test_channel_id: int
    ):
        """Добавление тега к посту не зависит от регистра."""
        post = await post_repo.create_post(
            channel_id=test_channel_id,
            text='Тест',
            category='Тест',
            urgency=1,
            tags='["политика"]'
        )

        # Пытаемся добавить "ПОЛИТИКА" — не должен добавиться
        await post_repo.add_tag(post.id, 'ПОЛИТИКА')

        updated_post = await post_repo.get(post.id)
        tags = json.loads(updated_post.tags)
        assert tags == ['политика']
        assert len(tags) == 1

    async def test_update_post_tags_normalizes(
        self, post_repo: PostRepository, test_channel_id: int
    ):
        """Обновление тегов поста нормализует регистр."""
        post = await post_repo.create_post(
            channel_id=test_channel_id,
            text='Тест',
            category='Тест',
            urgency=1
        )

        await post_repo.update_post_tags(
            post.id,
            ['ФУТБОЛ', 'Теннис', 'СПОРТ']
        )

        updated_post = await post_repo.get(post.id)
        tags = json.loads(updated_post.tags)
        assert tags == ['футбол', 'теннис', 'спорт']


class TestChannelRepository_CaseInsensitive:
    """Тесты для ChannelRepository с учётом регистра."""

    async def test_add_tag_case_insensitive(
        self, channel_repo: ChannelRepository, db_session: AsyncSession, test_channel_id: int
    ):
        """Добавление тега к каналу не зависит от регистра."""
        # Сначала создадим канал
        from database.models import Channel
        channel = Channel(
            channel_id=test_channel_id,
            title='Test Channel',
            description='Test'
        )
        db_session.add(channel)
        await db_session.commit()

        # Теперь добавим тег
        await channel_repo.add_tag(test_channel_id, 'новости')

        # Пытаемся добавить "НОВОСТИ" — не должен добавиться
        await channel_repo.add_tag(test_channel_id, 'НОВОСТИ')

        tags = await channel_repo.get_tags(test_channel_id)
        assert tags == ['новости']
        assert len(tags) == 1

    async def test_update_tags_normalizes(
        self, channel_repo: ChannelRepository, db_session: AsyncSession, test_channel_id: int
    ):
        """Обновление тегов канала нормализует регистр."""
        # Сначала создадим канал
        from database.models import Channel
        channel = Channel(
            channel_id=test_channel_id,
            title='Test Channel',
            description='Test'
        )
        db_session.add(channel)
        await db_session.commit()

        await channel_repo.update_tags(
            test_channel_id,
            ['ПОЛИТИКА', 'экономика', 'СПОРТ']
        )

        tags = await channel_repo.get_tags(test_channel_id)
        assert tags == ['политика', 'экономика', 'спорт']


class TestEventRepository_CaseInsensitive:
    """Тесты для EventRepository с учётом регистра."""

    async def test_create_event_normalizes_tags(
        self, event_repo: EventRepository, db_session: AsyncSession, test_channel_id: int
    ):
        """Создание события нормализует тэги."""
        # Сначала создадим пост
        post_repo = PostRepository(db_session)
        post = await post_repo.create_post(
            channel_id=test_channel_id,
            text='Тест для события',
            category='Тест',
            urgency=1
        )

        event = await event_repo.create_event(
            post_id=post.id,
            context_data={'key': 'value'},
            event_category='Политика',
            tags=['УКРАИНА', 'политика']
        )

        tags = json.loads(event.tags)
        assert tags == ['украина', 'политика']

    async def test_update_event_tags_normalizes(
        self, event_repo: EventRepository, db_session: AsyncSession, test_channel_id: int
    ):
        """Обновление тэгов события нормализует регистр."""
        # Сначала создадим пост и событие
        post_repo = PostRepository(db_session)
        post = await post_repo.create_post(
            channel_id=test_channel_id,
            text='Тест',
            category='Тест',
            urgency=1
        )

        event = await event_repo.create_event(
            post_id=post.id,
            context_data={},
            event_category='Тест'
        )

        await event_repo.update_event(
            event.id,
            tags=['ФУТБОЛ', 'Теннис']
        )

        updated_event = await event_repo.get(event.id)
        tags = json.loads(updated_event.tags)
        assert tags == ['футбол', 'теннис']


class TestCaseInsensitive_Integration:
    """Интеграционные тесты case-insensitive поиска."""

    async def test_tag_deduplication_across_operations(
        self, user_repo: UserRepository, test_user_id: int
    ):
        """Тэги не дублируются при смешанных операциях."""
        # Создаём с lowercase тегом
        await user_repo.create_user(
            telegram_id=test_user_id,
            preferred_tags=['политика']
        )

        # Добавляем UPPERCASE — не должен добавиться
        await user_repo.add_preferred_tag(test_user_id, 'ПОЛИТИКА')

        # Добавляем Title Case — не должен добавиться
        await user_repo.add_preferred_tag(test_user_id, 'Политика')

        prefs = await user_repo.get_preferences(test_user_id)
        assert prefs['preferred_tags'] == ['политика']
        assert len(prefs['preferred_tags']) == 1

    async def test_mixed_case_operations(
        self, user_repo: UserRepository, test_user_id: int
    ):
        """Операции со смешанным регистром работают корректно."""
        await user_repo.create_user(
            telegram_id=test_user_id,
            preferred_tags=['политика', 'экономика', 'спорт']
        )

        # Удаляем ЭКОНОМИКА (uppercase)
        await user_repo.remove_preferred_tag(test_user_id, 'ЭКОНОМИКА')

        # Добавляем ФУТБОЛ (uppercase)
        await user_repo.add_preferred_tag(test_user_id, 'ФУТБОЛ')

        prefs = await user_repo.get_preferences(test_user_id)
        # Должны остаться: политика, спорт + добавлен футбол
        assert 'политика' in prefs['preferred_tags']
        assert 'спорт' in prefs['preferred_tags']
        assert 'футбол' in prefs['preferred_tags']
        assert 'экономика' not in prefs['preferred_tags']
        assert len(prefs['preferred_tags']) == 3
