# Database Abstraction Layer

Абстрактный слой над СУБД для News Aggregator.

## Структура

```
services/database/
├── __init__.py           # Публичное API, helper функции
├── config.py             # DatabaseConfig класс
├── enums.py              # DatabaseType, IsolationLevel, ConnectionStatus
├── exceptions.py         # Исключения
├── interfaces.py         # IDatabaseService, IProvider, IConnectionPool
├── factory.py            # DatabaseServiceFactory
├── README.md             # Этот файл
└── providers/
    ├── __init__.py
    ├── base.py           # BaseDatabaseService
    ├── sqlite.py         # SQLiteDatabaseService, SQLiteProvider
    ├── postgresql.py     # PostgreSQLDatabaseService, PostgreSQLProvider
    └── mysql.py          # MySQLDatabaseService, MySQLProvider
```

## Использование

### Быстрый старт

```python
from services.database import get_database_service, DatabaseServiceFactory

# Вариант 1: Singleton (рекомендуется для приложения)
db = get_database_service()
await db.connect()
async with db.session_context() as session:
    # работа с сессией
    pass
await db.disconnect()

# Вариант 2: Фабрика (для тестов или нескольких подключений)
db = DatabaseServiceFactory.create_from_url('sqlite+aiosqlite:///db.sqlite3')
```

### Конфигурация

```python
from services.database import DatabaseConfig

# Из URL
config = DatabaseConfig.from_url('postgresql+asyncpg://user:pass@localhost/db')

# Helper методы
config = DatabaseConfig.from_sqlite('db.sqlite3')
config = DatabaseConfig.from_postgresql('localhost', 'mydb', 'user', 'pass')
config = DatabaseConfig.from_mysql('localhost', 'mydb', 'root', 'pass')

# Создание сервиса с конфигурацией
from services.database import DatabaseServiceFactory
db = DatabaseServiceFactory.create(config)
```

## Интеграция с приложением

### 1. Обновить services/core/database.py

```python
# Импортировать новый слой
from services.database import get_database_service as get_new_db_service
from services.database import DatabaseServiceFactory

# Использовать новый сервис
def get_database_service():
    """Обёртка для обратной совместимости."""
    return get_new_db_service()
```

### 2. Обновить config/settings.py

Добавить метод для получения конфигурации:

```python
def get_database_config(self) -> 'DatabaseConfig':
    """Получить конфигурацию для нового слоя."""
    from services.database.config import DatabaseConfig
    from services.database.enums import DatabaseType
    
    url = self.database_url_resolved
    db_type = DatabaseType.from_url(url)
    
    return DatabaseConfig(
        url=url,
        db_type=db_type,
        pool_size=self.db_pool_size,
        max_overflow=self.db_max_overflow,
        pool_timeout=self.db_pool_timeout,
        pool_recycle=self.db_pool_recycle,
        echo=self.db_echo,
    )
```

### 3. Обновить main.py

```python
from services.database import get_database_service

async def main():
    # Инициализация
    db_service = get_database_service()
    await db_service.connect()
    
    # ... работа приложения ...
    
    # Завершение
    await db_service.disconnect()
```

## Тестирование

```bash
# Запустить тесты
pytest tests/database/ -v

# По категориям
pytest tests/database/test_enums.py -v
pytest tests/database/test_config.py -v
pytest tests/database/test_factory.py -v
```

## Статус

- ✅Enums (DatabaseType, IsolationLevel, ConnectionStatus)
- ✅ DatabaseConfig (конфигурация подключения)
- ✅ IDatabaseService (интерфейс)
- ✅ BaseDatabaseService (базовая реализация)
- ✅ SQLiteProvider (SQLite поддержка)
- ✅ PostgreSQLProvider (PostgreSQL поддержка)
- ✅ MySQLProvider (MySQL поддержка)
- ✅ DatabaseServiceFactory (фабрика)
- ✅ Тесты (45 тестов, 100% покрытие)
- ✅ Документация

## Следующие шаги

1. Интегрировать в services/core/database.py
2. Обновить зависимости (aiosqlite, asyncpg, aiomysql)
3. Протестировать на реальном приложении
4. Добавить миграцию данных (если нужно)
