"""
Исключения для слоя базы данных.
"""

from typing import Any, Optional


class DatabaseError(Exception):
    """Базовое исключение для ошибок базы данных."""

    def __init__(
        self,
        message: str,
        original_error: Optional[Exception] = None,
        context: Optional[dict[str, Any]] = None
    ) -> None:
        self.message = message
        self.original_error = original_error
        self.context = context or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.original_error:
            return f"{self.message} (Original: {type(self.original_error).__name__}: {self.original_error})"
        return self.message


class ConnectionError(DatabaseError):
    """Ошибка подключения к базе данных."""


class PoolError(DatabaseError):
    """Ошибка пула подключений."""


class TransactionError(DatabaseError):
    """Ошибка транзакции."""


class QueryError(DatabaseError):
    """Ошибка выполнения запроса."""


class ConfigurationError(DatabaseError):
    """Ошибка конфигурации базы данных."""


class ProviderNotFoundError(DatabaseError):
    """Провайдер СУБД не найден."""


class UnsupportedDatabaseError(DatabaseError):
    """СУБД не поддерживается."""


class SessionError(DatabaseError):
    """Ошибка сессии базы данных."""


class MigrationError(DatabaseError):
    """Ошибка миграции базы данных."""


class LockError(DatabaseError):
    """Ошибка блокировки."""


class TimeoutError(DatabaseError):
    """Таймаут операции базы данных."""


class IntegrityError(DatabaseError):
    """Ошибка целостности данных (unique constraint, foreign key)."""


class OperationalError(DatabaseError):
    """Операционная ошибка (проблемы с подключением, сервером)."""
