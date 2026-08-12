"""
Tests for ChannelRepository.

Запуск:
    pytest tests/test_repositories/test_channels.py -v
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from database.repositories.channels import ChannelRepository


class TestChannelRepository:
    """Тесты для ChannelRepository."""

    @pytest.mark.asyncio
    async def test_create_channel(self, db_session: AsyncSession, mock_channel_data: dict):
        """Тест создания канала."""
        repo = ChannelRepository(db_session)

        channel = await repo.create_channel(
            channel_id=mock_channel_data['channel_id'],
            title=mock_channel_data['title'],
            description=mock_channel_data['description'],
            is_trusted=mock_channel_data['is_trusted']
        )

        assert channel is not None
        assert channel.channel_id == mock_channel_data['channel_id']
        assert channel.title == mock_channel_data['title']
        assert channel.is_trusted is False

    @pytest.mark.asyncio
    async def test_get_by_telegram_id(self, db_session: AsyncSession, mock_channel_data: dict):
        """Тест получения канала по Telegram ID."""
        repo = ChannelRepository(db_session)

        # Создаём канал
        await repo.create_channel(
            channel_id=mock_channel_data['channel_id'],
            title=mock_channel_data['title'],
            description=mock_channel_data['description']
        )

        # Получаем канал
        channel = await repo.get_by_telegram_id(mock_channel_data['channel_id'])

        assert channel is not None
        assert channel.channel_id == mock_channel_data['channel_id']

    @pytest.mark.asyncio
    async def test_get_by_telegram_id_not_found(self, db_session: AsyncSession):
        """Тест получения несуществующего канала."""
        repo = ChannelRepository(db_session)

        channel = await repo.get_by_telegram_id(-999999999999)

        assert channel is None

    @pytest.mark.asyncio
    async def test_set_trusted(self, db_session: AsyncSession, mock_channel_data: dict):
        """Тест установки флага доверенного источника."""
        repo = ChannelRepository(db_session)

        # Создаём канал
        await repo.create_channel(
            channel_id=mock_channel_data['channel_id'],
            title=mock_channel_data['title'],
            is_trusted=False
        )

        # Делаем доверенным
        result = await repo.set_trusted(mock_channel_data['channel_id'], True)

        assert result is True

        # Проверяем
        channel = await repo.get_by_telegram_id(mock_channel_data['channel_id'])
        assert channel is not None
        assert channel.is_trusted is True
        assert channel.trust_rating == 1.0

    @pytest.mark.asyncio
    async def test_add_tag(self, db_session: AsyncSession, mock_channel_data: dict):
        """Тест добавления тега каналу (case-insensitive)."""
        repo = ChannelRepository(db_session)

        # Создаём канал
        await repo.create_channel(
            channel_id=mock_channel_data['channel_id'],
            title=mock_channel_data['title']
        )

        # Добавляем тег
        result = await repo.add_tag(mock_channel_data['channel_id'], 'Политика')

        assert result is True

        # Проверяем (теги нормализуются к lowercase)
        tags = await repo.get_tags(mock_channel_data['channel_id'])
        assert 'политика' in tags

    @pytest.mark.asyncio
    async def test_get_all_channels(self, db_session: AsyncSession, mock_channel_data: dict):
        """Тест получения всех каналов."""
        repo = ChannelRepository(db_session)

        # Создаём несколько каналов
        await repo.create_channel(channel_id=-1001, title='Channel 1')
        await repo.create_channel(channel_id=-1002, title='Channel 2')
        await repo.create_channel(channel_id=-1003, title='Channel 3')

        # Получаем все каналы
        channels = await repo.get_all_channels()

        assert len(channels) >= 3
        titles = [c.title for c in channels]
        assert 'Channel 1' in titles
        assert 'Channel 2' in titles
        assert 'Channel 3' in titles

    @pytest.mark.asyncio
    async def test_delete_channel(self, db_session: AsyncSession, mock_channel_data: dict):
        """Тест удаления канала."""
        repo = ChannelRepository(db_session)

        # Создаём канал
        await repo.create_channel(
            channel_id=mock_channel_data['channel_id'],
            title=mock_channel_data['title']
        )

        # Удаляем
        result = await repo.delete_channel(mock_channel_data['channel_id'])

        assert result is True

        # Проверяем, что удалён
        channel = await repo.get_by_telegram_id(mock_channel_data['channel_id'])
        assert channel is None
