"""
Channel repository для работы с каналами.
"""

import json
from typing import Optional
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Channel
from database.repositories.base import BaseRepository


class ChannelRepository(BaseRepository[Channel]):
    """
    Репозиторий для работы с каналами.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Channel)

    async def get_by_telegram_id(self, channel_id: int) -> Channel | None:
        """
        Получить канал по Telegram ID.

        Args:
            channel_id: ID канала в Telegram

        Returns:
            Канал или None
        """
        result = await self.session.execute(
            select(Channel).where(Channel.channel_id == channel_id)
        )
        return result.scalar_one_or_none()

    async def get_all_channels(self) -> list[Channel]:
        """
        Получить все каналы (отсортированные по ID).

        Returns:
            Список каналов
        """
        result = await self.session.execute(
            select(Channel).order_by(desc(Channel.channel_id))
        )
        return result.scalars().all()

    async def create_channel(
        self,
        channel_id: int,
        title: str,
        description: str = '',
        is_trusted: bool = False
    ) -> Channel:
        """
        Создать или обновить канал.

        Args:
            channel_id: ID канала в Telegram
            title: Название канала
            description: Описание канала
            is_trusted: Флаг доверенного источника

        Returns:
            Созданный канал
        """
        existing = await self.get_by_telegram_id(channel_id)
        if existing:
            return existing

        channel = Channel(
            channel_id=channel_id,
            title=title,
            description=description,
            is_trusted=is_trusted,
            trust_rating=1.0 if is_trusted else 0.5,
            tags='[]'
        )
        self.session.add(channel)
        await self.session.commit()
        await self.session.refresh(channel)
        return channel

    async def delete_channel(self, channel_id: int) -> bool:
        """
        Удалить канал по Telegram ID.

        Args:
            channel_id: ID канала в Telegram

        Returns:
            True если удалён, False если не найден
        """
        channel = await self.get_by_telegram_id(channel_id)
        if channel:
            await self.session.delete(channel)
            await self.session.commit()
            return True
        return False

    async def set_trusted(self, channel_id: int, is_trusted: bool) -> bool:
        """
        Установить флаг доверенного источника.

        Args:
            channel_id: ID канала в Telegram
            is_trusted: Флаг доверенного источника

        Returns:
            True если обновлён, False если не найден
        """
        channel = await self.get_by_telegram_id(channel_id)
        if channel:
            channel.is_trusted = is_trusted
            if is_trusted:
                channel.trust_rating = 1.0
            await self.session.commit()
            return True
        return False

    async def add_tag(self, channel_id: int, tag: str) -> bool:
        """
        Добавить тег каналу.

        Args:
            channel_id: ID канала в Telegram
            tag: Тег для добавления

        Returns:
            True если добавлен, False если не найден
        """
        channel = await self.get_by_telegram_id(channel_id)
        if channel:
            tags = json.loads(channel.tags or '[]')
            if tag not in tags:
                tags.append(tag)
                channel.tags = json.dumps(tags, ensure_ascii=False)
                await self.session.commit()
            return True
        return False

    async def update_tags(self, channel_id: int, tags: list[str]) -> bool:
        """
        Обновить теги канала.

        Args:
            channel_id: ID канала в Telegram
            tags: Новый список тегов

        Returns:
            True если обновлены, False если не найден
        """
        channel = await self.get_by_telegram_id(channel_id)
        if channel:
            channel.tags = json.dumps(tags, ensure_ascii=False)
            await self.session.commit()
            return True
        return False

    async def get_tags(self, channel_id: int) -> list[str]:
        """
        Получить теги канала.

        Args:
            channel_id: ID канала в Telegram

        Returns:
            Список тегов
        """
        channel = await self.get_by_telegram_id(channel_id)
        if channel and channel.tags:
            return json.loads(channel.tags)
        return []
