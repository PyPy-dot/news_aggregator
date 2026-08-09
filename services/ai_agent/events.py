"""
События и типы событий для шины событий.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class EventType(Enum):
    """Типы событий."""
    NEW_NEWS = auto()           # Новый пост из Telegram
    CREATE_CONTEXT = auto()     # Создать контекст события
    GENERATE_NEWS = auto()      # Генерация итоговой новости


@dataclass
class Event:
    """
    Событие для шины событий.

    Attributes:
        type: Тип события
        payload: Данные события
        priority: Приоритет (1=высокий, 5=низкий)
    """
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 3  # Приоритет по умолчанию (средний)

    @classmethod
    def high_priority(cls, event_type: EventType, payload: dict[str, Any]) -> 'Event':
        """Создать событие с высоким приоритетом."""
        return cls(type=event_type, payload=payload, priority=1)

    @classmethod
    def low_priority(cls, event_type: EventType, payload: dict[str, Any]) -> 'Event':
        """Создать событие с низким приоритетом."""
        return cls(type=event_type, payload=payload, priority=5)
