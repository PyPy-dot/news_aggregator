"""
Log Handler для трансляции логов в веб-админку.

Перехватывает логи приложения и сохраняет их в буферы по источникам
для отображения в консоли.
"""

import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import deque


# Размер буфера **на каждый источник**
_PER_SOURCE_LIMIT = 300


class WebAdminLogHandler(logging.Handler):
    """
    Лог handler для веб-админки.

    Каждый источник (main, bot, listener, scheduler и т.д.) хранит логи
    в своём кольцевом буфере — буферы не конкурируют друг с другом.
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
        # Принимаем всё от DEBUG до CRITICAL — фильтрация в get_logs()
        super().__init__(level=logging.DEBUG)

        # Буфер **на каждый источник** (lazily создается в emit)
        self._buffers: Dict[str, deque] = {}

        # Подписчики (веб-сокеты или polling запросы)
        self._subscribers: List[asyncio.Queue] = []

        # Блокировка для потокобезопасности
        self._lock = asyncio.Lock()

        self._initialized = True

        # Маппинг имён логгеров на понятные имена
        # ВАЖНО: 'services' — catch-all, должен быть ПОСЛЕ подпрефиксов
        self._source_names = {
            '__main__': 'main',
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
            'services': 'main',
        }

    # ------------------------------------------------------------------
    # logging.Handler interface
    # ------------------------------------------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        """Обработать лог запись — положить в буфер нужного источника."""
        log_entry = self._format_record(record)
        source = log_entry['source']

        # Lazily создаём буфер для источника
        buf = self._buffers.get(source)
        if buf is None:
            buf = deque(maxlen=_PER_SOURCE_LIMIT)
            self._buffers[source] = buf

        buf.append(log_entry)
        self._notify_subscribers(log_entry)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _format_record(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Форматировать лог запись."""
        return {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'source': self._get_source(record.name),
            'message': record.getMessage(),
        }

    def _get_source(self, logger_name: str) -> str:
        """Получить понятное имя источника."""
        for prefix, name in self._source_names.items():
            if logger_name.startswith(prefix):
                return name
        return logger_name.split('.')[-1]

    def _notify_subscribers(self, log_entry: Dict[str, Any]) -> None:
        for queue in self._subscribers:
            try:
                queue.put_nowait(log_entry)
            except asyncio.QueueFull:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def add_subscriber(self, queue: asyncio.Queue) -> None:
        self._subscribers.append(queue)

    def remove_subscriber(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def get_sources(self) -> List[str]:
        """Возвращает список всех источников, у которых есть логи."""
        return sorted(self._buffers.keys())

    def get_logs(
        self,
        limit: int = 200,
        level: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получить логи.

        Args:
            limit: макс. записей (для конкретного источника)
            level: ALL / DEBUG / INFO / WARNING / ERROR / CRITICAL
                   ALL или None = без фильтра по уровню
            source: конкретный источник или 'all' — собрать из всех
        """
        # --- выбрать буфер(и) ------------------------------------------------
        if source and source != 'all':
            buf = self._buffers.get(source)
            if buf is None:
                return []
            logs = list(buf)
        else:
            # 'all' — собрать из всех буферов, отсортировать по времени
            all_logs: List[Dict[str, Any]] = []
            for buf in self._buffers.values():
                all_logs.extend(buf)
            all_logs.sort(key=lambda e: e['timestamp'])
            logs = all_logs

        # --- фильтр по уровню ------------------------------------------------
        if level and level.upper() != 'ALL':
            level_map = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL,
            }
            min_level = level_map.get(level.upper(), 0)
            logs = [
                log for log in logs
                if level_map.get(log['level'], 0) >= min_level
            ]

        # --- вернуть последние N ---------------------------------------------
        return logs[-limit:] if limit else logs

    def clear(self) -> None:
        """Очистить все буферы."""
        for buf in self._buffers.values():
            buf.clear()


def get_log_handler() -> WebAdminLogHandler:
    return WebAdminLogHandler()


def setup_web_admin_logging() -> None:
    """Добавляет WebAdminLogHandler к корневому логгеру."""
    handler = get_log_handler()
    root_logger = logging.getLogger()
    if not any(isinstance(h, WebAdminLogHandler) for h in root_logger.handlers):
        root_logger.addHandler(handler)
