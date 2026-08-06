from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

class EventType(Enum):
    NEW_NEWS = auto()           # Новый пост из Telegram
    CATEGORIZED = auto()        # Категория определена
    SAVE_NEWS = auto()          # Сохранить новость в БД
    CREATE_CONTEXT = auto()     # Создать контекст события
    VALIDATE_CATEGORY = auto()  # Проверка категории второй ЛЛМ
    GENERATE_NEWS = auto()      # Генерация итоговой новости

@dataclass
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)