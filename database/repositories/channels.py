"""
Channel repository для работы с каналами.
"""

import json
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Channel, TelegramPost
from database.repositories.base import BaseRepository
from config.settings import settings


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

    async def add_channel(
        self,
        channel_id: int,
        title: str,
        description: str = '',
        is_trusted: bool = False,
        trust_rating: float = 0.5,
    ) -> int:
        """
        Создать канал и вернуть его DB ID (обёртка для API endpoint).

        Args:
            channel_id: ID канала в Telegram
            title: Название канала
            description: Описание канала
            is_trusted: Флаг доверенного источника
            trust_rating: Рейтинг доверия

        Returns:
            ID созданной записи в БД
        """
        channel = await self.create_channel(
            channel_id=channel_id,
            title=title,
            description=description,
            is_trusted=is_trusted,
        )
        if is_trusted:
            channel.trust_rating = 1.0
        else:
            channel.trust_rating = trust_rating
        await self.session.commit()
        return channel.id

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
        Добавить тег каналу (case-insensitive).

        Args:
            channel_id: ID канала в Telegram
            tag: Тег для добавления

        Returns:
            True если добавлен, False если не найден
        """
        channel = await self.get_by_telegram_id(channel_id)
        if channel:
            tag_normalized = tag.lower()
            tags = [t.lower() for t in json.loads(channel.tags or '[]')]
            if tag_normalized not in tags:
                tags.append(tag_normalized)
                channel.tags = json.dumps(tags, ensure_ascii=False)
                await self.session.commit()
            return True
        return False

    async def update_tags(self, channel_id: int, tags: list[str]) -> bool:
        """
        Обновить теги канала (case-insensitive).

        Args:
            channel_id: ID канала в Telegram
            tags: Новый список тегов

        Returns:
            True если обновлены, False если не найден
        """
        channel = await self.get_by_telegram_id(channel_id)
        if channel:
            # Нормализация тэгов к нижнему регистру
            channel.tags = json.dumps(
                [tag.lower() for tag in tags], ensure_ascii=False
            )
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

    async def update_trust_rating(self, channel_id: int) -> bool:
        """
        Обновить рейтинг доверия канала на основе последних N новостей.

        Рейтинг = средний рейтинг последних постов / 100 (нормализация к 0-1)
        N берётся из конфига (channel_trust_window_size).

        Args:
            channel_id: ID канала в Telegram

        Returns:
            True если обновлён, False если не найден
        """
        channel = await self.get_by_telegram_id(channel_id)
        if not channel:
            return False

        # Получаем последние N новостей канала (из конфига)
        result = await self.session.execute(
            select(TelegramPost)
            .where(TelegramPost.channel_id == channel_id)
            .order_by(desc(TelegramPost.created_at))
            .limit(settings.channel_trust_window_size)
        )
        posts = result.scalars().all()

        if posts:
            # Средний рейтинг новостей (нормализуем к 0-1)
            avg_rate = sum(p.rate for p in posts) / len(posts)
            channel.trust_rating = min(1.0, avg_rate / 100.0)
            await self.session.commit()
            return True
        return False

    async def decrease_trust_rating(self, channel_id: int, amount: float = 0.05) -> bool:
        """
        Снизить рейтинг доверия канала на указанную величину.

        Args:
            channel_id: ID канала в Telegram
            amount: Величина снижения (по умолчанию 0.05 = 5%)

        Returns:
            True если обновлён, False если не найден
        """
        channel = await self.get_by_telegram_id(channel_id)
        if channel:
            channel.trust_rating = max(0.0, channel.trust_rating - amount)
            await self.session.commit()
            return True
        return False

    async def increase_trust_rating(self, channel_id: int, amount: float = 0.15) -> bool:
        """
        Увеличить рейтинг доверия канала на указанную величину.

        Args:
            channel_id: ID канала в Telegram
            amount: Величина увеличения (по умолчанию 0.15 = 15%)

        Returns:
            True если обновлён, False если не найден
        """
        channel = await self.get_by_telegram_id(channel_id)
        if channel:
            channel.trust_rating = min(1.0, channel.trust_rating + amount)
            await self.session.commit()
            return True
        return False
