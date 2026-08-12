"""
Database repositories package.

Repository pattern для работы с базой данных.
"""

from database.repositories.base import BaseRepository
from database.repositories.channels import ChannelRepository
from database.repositories.posts import PostRepository
from database.repositories.events import EventRepository
from database.repositories.news import NewsRepository
from database.repositories.publishers import PublisherRepository
from database.repositories.users import UserRepository
from database.repositories.tasks import TaskRepository

__all__ = [
    'BaseRepository',
    'ChannelRepository',
    'PostRepository',
    'EventRepository',
    'NewsRepository',
    'PublisherRepository',
    'UserRepository',
    'TaskRepository',
]
