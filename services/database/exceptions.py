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
    pass


class PoolError(DatabaseError):
    """Ошибка пула подключений."""
    pass


class TransactionError(DatabaseError):
    """Ошибка транзакции."""
    pass


class QueryError(DatabaseError):
    """Ошибка выполнения запроса."""
    pass


class ConfigurationError(DatabaseError):
    """Ошибка конфигурации базы данных."""
    pass


class ProviderNotFoundError(DatabaseError):
    """Провайдер СУБД не найден."""
    pass


class UnsupportedDatabaseError(DatabaseError):
    """СУБД не поддерживается."""
    pass


class SessionError(DatabaseError):
    """Ошибка сессии базы данных."""
    pass


class MigrationError(DatabaseError):
    """Ошибка миграции базы данных."""
    pass


class LockError(DatabaseError):
    """Ошибка блокировки."""
    pass


class TimeoutError(DatabaseError):
    """Таймаут операции базы данных."""
    pass


class IntegrityError(DatabaseError):
    """Ошибка целостности данных (unique constraint, foreign key)."""
    pass


class OperationalError(DatabaseError):
    """Операционная ошибка (проблемы с подключением, сервером)."""
    pass
