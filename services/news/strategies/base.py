"""
Базовый класс стратегии обработки новостей.
"""

from abc import ABC, abstractmethod
from typing import Any
from database.repositories.posts import PostRepository
from database.repositories.events import EventRepository
from database.repositories.news import NewsRepository
from database.repositories.publishers import PublisherRepository
from services.ai_agent.routers import EventBus


class NewsProcessingStrategy(ABC):
    """
    Базовый класс стратегии обработки новостей.

    Определяет интерфейс для всех стратегий обработки.
    """

    def __init__(
        self,
        posts_repo: PostRepository,
        events_repo: EventRepository,
        news_repo: NewsRepository,
        publishers_repo: PublisherRepository,
        event_bus: EventBus,
    ) -> None:
        """
        Инициализация стратегии.

        Args:
            posts_repo: Репозиторий постов
            events_repo: Репозиторий событий
            news_repo: Репозиторий новостей
            publishers_repo: Репозиторий издателей
            event_bus: Шина событий
        """
        self.posts_repo = posts_repo
        self.events_repo = events_repo
        self.news_repo = news_repo
        self.publishers_repo = publishers_repo
        self.event_bus = event_bus

    @abstractmethod
    async def process(self, post_id: int, **kwargs: Any) -> None:
        """
        Обработать новость.

        Args:
            post_id: ID поста
            **kwargs: Дополнительные параметры
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Название стратегии."""
        pass
