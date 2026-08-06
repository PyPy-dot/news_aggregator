"""
Database factory для создания репозиториев.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from database.repositories.channels import ChannelRepository
from database.repositories.posts import PostRepository
from database.repositories.events import EventRepository
from database.repositories.news import NewsRepository
from database.repositories.publishers import PublisherRepository
from database.repositories.users import UserRepository


class RepositoryFactory:
    """
    Фабрика для создания репозиториев.

    Пример использования:
        factory = RepositoryFactory(session)
        channels = factory.channels()
        posts = factory.posts()
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Инициализация фабрики.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    def channels(self) -> ChannelRepository:
        """Создать ChannelRepository."""
        return ChannelRepository(self.session)

    def posts(self) -> PostRepository:
        """Создать PostRepository."""
        return PostRepository(self.session)

    def events(self) -> EventRepository:
        """Создать EventRepository."""
        return EventRepository(self.session)

    def news(self) -> NewsRepository:
        """Создать NewsRepository."""
        return NewsRepository(self.session)

    def publishers(self) -> PublisherRepository:
        """Создать PublisherRepository."""
        return PublisherRepository(self.session)

    def users(self) -> UserRepository:
        """Создать UserRepository."""
        return UserRepository(self.session)

    def all(self):
        """
        Создать все репозитории.

        Returns:
            dict: {name: repository}
        """
        return {
            'channels': self.channels(),
            'posts': self.posts(),
            'events': self.events(),
            'news': self.news(),
            'publishers': self.publishers(),
            'users': self.users(),
        }
