"""
Log Handler для трансляции логов в веб-админку.

Перехватывает логи приложения и сохраняет их в буфер для отображения в консоли.
"""

import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from collections import deque


class WebAdminLogHandler(logging.Handler):
    """
    Лог handler для веб-админки.

    Сохраняет логи в кольцевой буфер для отображения в консоли.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__(level=logging.INFO)

        # Кольцевой буфер для логов (последние 500 записей)
        self._buffer: deque = deque(maxlen=500)

        # Подписчики (веб-сокеты или polling запросы)
        self._subscribers: List[asyncio.Queue] = []

        # Блокировка для потокобезопасности
        self._lock = asyncio.Lock()

        # Фильтры
        self._min_level = logging.INFO
        self._sources: set = set()  # Пустое = все источники

        self._initialized = True

        # Маппинг имён логгеров на понятные имена
        self._source_names = {
            'main': 'main',
            'services.bot': 'bot',
            'services.listener': 'listener',
            'services.scheduler': 'scheduler',
            'services.web_admin': 'web_admin',
            'services.ai_agent': 'ai_agent',
            'services.news': 'news',
            'services.vector_search': 'vector',
            'services.categorization': 'categorization',
            'services.database': 'database',
        }

    def emit(self, record: logging.LogRecord) -> None:
        """Обработать лог запись."""
        # Проверяем уровень
        if record.levelno < self._min_level:
            return

        # Проверяем источник
        if self._sources:
            source = self._get_source(record.name)
            if source not in self._sources:
                return

        # Форматируем запись
        log_entry = self._format_record(record)

        # Добавляем в буфер
        self._buffer.append(log_entry)

        # Уведомляем подписчиков
        self._notify_subscribers(log_entry)

    def _format_record(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Форматировать лог запись."""
        # Определяем источник
        source = self._get_source(record.name)

        # Определяем уровень
        level = record.levelname

        # Форматируем сообщение
        message = record.getMessage()

        return {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': level,
            'source': source,
            'message': message,
        }

    def _get_source(self, logger_name: str) -> str:
        """Получить понятное имя источника."""
        for prefix, name in self._source_names.items():
            if logger_name.startswith(prefix):
                return name
        # Возвращаем последнюю часть имени логгера
        return logger_name.split('.')[-1]

    def _notify_subscribers(self, log_entry: Dict[str, Any]) -> None:
        """Уведомить подписчиков о новой лог записи."""
        for queue in self._subscribers:
            try:
                queue.put_nowait(log_entry)
            except asyncio.QueueFull:
                # Буфер переполнен — пропускаем
                pass

    def add_subscriber(self, queue: asyncio.Queue) -> None:
        """Добавить подписчика."""
        self._subscribers.append(queue)

    def remove_subscriber(self, queue: asyncio.Queue) -> None:
        """Удалить подписчика."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def get_logs(
        self,
        limit: int = 100,
        level: str = None,
        source: str = None
    ) -> List[Dict[str, Any]]:
        """
        Получить логи из буфера.

        Args:
            limit: Максимальное количество записей
            level: Минимальный уровень (DEBUG, INFO, WARNING, ERROR)
            source: Фильтр по источнику

        Returns:
            Список лог записей
        """
        logs = list(self._buffer)

        # Фильтр по уровню
        if level:
            level_map = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
            }
            min_level = level_map.get(level.upper(), logging.INFO)
            logs = [
                log for log in logs
                if logging.getLevelName(log['level']) >= min_level
            ]

        # Фильтр по источнику
        if source and source != 'all':
            logs = [log for log in logs if log['source'] == source]

        # Возвращаем последние N записей
        return logs[-limit:] if limit else logs

    def clear(self) -> None:
        """Очистить буфер."""
        self._buffer.clear()


def get_log_handler() -> WebAdminLogHandler:
    """Получить экземпляр лог handler."""
    return WebAdminLogHandler()


def setup_web_admin_logging() -> None:
    """
    Настроить логирование для веб-админки.

    Добавляет WebAdminLogHandler к корневому логгеру.
    ВАЖНО: Добавляем только к корневому логгеру, чтобы избежать дублирования.
    Дочерние логгеры наследуют handlers от родительского.
    """
    handler = get_log_handler()

    # Добавляем handler только к корневому логгеру
    root_logger = logging.getLogger()

    # Проверяем, не добавлен ли уже такой handler
    if not any(isinstance(h, WebAdminLogHandler) for h in root_logger.handlers):
        root_logger.addHandler(handler)
