"""
Абстрактный слой над СУБД для News Aggregator.

Обеспечивает единую точку доступа к базе данных независимо от выбранной СУБД.
Поддерживает SQLite, PostgreSQL и MySQL.

## Быстрый старт

### 1. Создание сервиса через фабрику

```python
from services.database import DatabaseServiceFactory, DatabaseConfig

# Из URL
service = DatabaseServiceFactory.create_from_url('sqlite+aiosqlite:///db.sqlite3')

# Или для PostgreSQL
service = DatabaseServiceFactory.create_from_url(
    'postgresql+asyncpg://user:pass@localhost:5432/mydb'
)

# Или через методы удобства
service = DatabaseServiceFactory.create_sqlite('db.sqlite3')
service = DatabaseServiceFactory.create_postgresql(
    host='localhost',
    database='mydb',
    username='user',
    password='secret'
)
```

### 2. Подключение и использование

```python
# Подключение
await service.connect()

# Использование сессии
async with service.session_context() as session:
    # Работа с сессией
    result = await session.execute(query)

# Выполнение запроса
rows = await service.execute_query("SELECT * FROM users")

# Проверка доступности
is_available = await service.health_check()

# Отключение
await service.disconnect()
```

### 3. Интеграция с приложением

```python
# В main.py или точке входа
from services.database import get_database_service

# Получение глобального сервиса (singleton)
db_service = get_database_service()

# Инициализация
await db_service.connect()

# Использование в приложении
async with db_service.session_context() as session:
    # Работа с БД
    pass

# Завершение работы
await db_service.disconnect()
```

## Архитектура

```
services/database/
├── __init__.py           # Публичное API
├── config.py             # Конфигурация подключения
├── enums.py              # Перечисления (DatabaseType, IsolationLevel)
├── exceptions.py         # Исключения
├── interfaces.py         # Абстрактные интерфейсы
├── factory.py            # Фабрика сервисов
└── providers/
    ├── __init__.py
    ├── base.py           # Базовый класс сервиса
    ├── sqlite.py         # SQLite провайдер
    ├── postgresql.py     # PostgreSQL провайдер
    └── mysql.py          # MySQL провайдер
```

## Конфигурация

### Настройки в .env

```bash
# SQLite (по умолчанию)
DATABASE_URL=sqlite+aiosqlite:///db.sqlite3

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/mydb

# MySQL
DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/mydb
```

### Параметры подключения

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `pool_size` | Размер пула подключений | 10 (SQLite: 1) |
| `max_overflow` | Дополнительные подключения | 20 |
| `pool_timeout` | Таймаут ожидания (сек) | 30 |
| `pool_recycle` | Пересоздание подключения (сек) | 1800 |
| `pool_pre_ping` | Проверка подключения | True |
| `echo` | Логирование SQL | False |

## Поддерживаемые СУБД

| СУБД | Драйвер | Версии |
|------|---------|--------|
| **SQLite** | aiosqlite | 3.x |
| **PostgreSQL** | asyncpg | 12+ |
| **MySQL** | aiomysql | 5.7+ |
"""

from services.database.enums import (
    DatabaseType,
    IsolationLevel,
    ConnectionStatus,
)

from services.database.config import DatabaseConfig

from services.database.interfaces import (
    IDatabaseService,
    IProvider,
    IConnectionPool,
)

from services.database.exceptions import (
    DatabaseError,
    ConnectionError,
    PoolError,
    TransactionError,
    QueryError,
    ConfigurationError,
    ProviderNotFoundError,
    UnsupportedDatabaseError,
    SessionError,
    MigrationError,
    LockError,
    TimeoutError,
    IntegrityError,
    OperationalError,
)

from services.database.factory import DatabaseServiceFactory

from services.database.providers import (
    BaseDatabaseService,
    SQLiteDatabaseService,
    PostgreSQLDatabaseService,
    MySQLDatabaseService,
)

# Глобальный singleton сервис
_db_service = None


def get_database_service(config: DatabaseConfig | None = None) -> IDatabaseService:
    """
    Получить глобальный сервис базы данных (singleton).

    Args:
        config: Конфигурация подключения (опционально)

    Returns:
        IDatabaseService экземпляр

    Examples:
        >>> db = get_database_service()
        >>> await db.connect()
    """
    global _db_service

    if _db_service is None:
        _db_service = DatabaseServiceFactory.create(config)

    return _db_service


def reset_database_service() -> None:
    """
    Сбросить глобальный сервис.

    Используется для тестирования или переподключения к другой БД.
    """
    global _db_service
    _db_service = None


async def dispose_database_service() -> None:
    """
    Утилизировать глобальный сервис базы данных.

    Вызывается при завершении приложения.
    """
    global _db_service

    if _db_service is not None:
        await _db_service.disconnect()
        _db_service = None


async def get_db_session():
    """
    Получить сессию БД (для dependency injection).

    Usage:
        async for session in get_db_session():
            # работа с сессией

    Или через контекстный менеджер:
        async with get_db_session() as session:
            # работа с сессией
    """
    db_service = get_database_service()
    async with db_service.session_context() as session:
        yield session


__all__ = [
    # Перечисления
    'DatabaseType',
    'IsolationLevel',
    'ConnectionStatus',

    # Конфигурация
    'DatabaseConfig',

    # Интерфейсы
    'IDatabaseService',
    'IProvider',
    'IConnectionPool',

    # Исключения
    'DatabaseError',
    'ConnectionError',
    'PoolError',
    'TransactionError',
    'QueryError',
    'ConfigurationError',
    'ProviderNotFoundError',
    'UnsupportedDatabaseError',
    'SessionError',
    'MigrationError',
    'LockError',
    'TimeoutError',
    'IntegrityError',
    'OperationalError',

    # Фабрика
    'DatabaseServiceFactory',

    # Сервисы
    'BaseDatabaseService',
    'SQLiteDatabaseService',
    'PostgreSQLDatabaseService',
    'MySQLDatabaseService',

    # Helper функции
    'get_database_service',
    'reset_database_service',
    'dispose_database_service',
    'get_db_session',
]
