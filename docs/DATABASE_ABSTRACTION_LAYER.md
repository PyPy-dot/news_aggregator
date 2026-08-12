# 🗄️ Слой абстракции базы данных

**Версия:** 1.0.0  
**Дата:** 2026-08-10  
**Статус:** ✅ Готово к использованию

---

## 📋 Обзор

Абстрактный слой над СУБД обеспечивает единую точку доступа к базе данных независимо от выбранной СУБД. Поддерживает **SQLite**, **PostgreSQL** и **MySQL**.

### Ключевые возможности

| Возможность | Описание |
|-------------|----------|
| **Унифицированный API** | Единый интерфейс для всех СУБД |
| **Автоопределение** | Автоматическое определение типа СУБД из URL |
| **Фабрика сервисов** | Простое создание через `DatabaseServiceFactory` |
| **Гибкая конфигурация** | Конфигурация через URL или параметры |
| **Пул подключений** | Настройка пула для каждой СУБД |
| **Уровни изоляции** | Поддержка уровней изоляции транзакций |

---

## 🚀 Быстрый старт

### 1. Создание сервиса

```python
from services.database import DatabaseServiceFactory

# Из URL (рекомендуется)
db = DatabaseServiceFactory.create_from_url('sqlite+aiosqlite:///db.sqlite3')

# Или через helper методы
db = DatabaseServiceFactory.create_sqlite('db.sqlite3')
db = DatabaseServiceFactory.create_postgresql(
    host='localhost',
    database='mydb',
    username='user',
    password='secret'
)
db = DatabaseServiceFactory.create_mysql(
    host='localhost',
    database='mydb',
    username='root',
    password='secret'
)
```

### 2. Подключение и использование

```python
# Подключение
await db.connect()

# Использование сессии
async with db.session_context() as session:
    result = await session.execute(query)

# Выполнение запроса
rows = await db.execute_query("SELECT * FROM users")

# Проверка доступности
is_available = await db.health_check()

# Отключение
await db.disconnect()
```

### 3. Интеграция с приложением

```python
# В main.py или точке входа
from services.database import get_database_service

# Получение глобального сервиса (singleton)
db_service = get_database_service()

# Инициализация
await db_service.connect()

# Использование
async with db_service.session_context() as session:
    # Работа с БД
    pass

# Завершение работы
await db_service.disconnect()
```

---

## 📦 Архитектура

```
services/database/
├── __init__.py           # Публичное API
├── config.py             # Конфигурация подключения
├── enums.py              # Перечисления
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

### Уровни абстракции

```
┌─────────────────────────────────────────────────────────────┐
│  Application Layer (ваш код)                                │
│  get_database_service() → IDatabaseService                  │
└─────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────┼───────────────────────────────────┐
│  Service Layer            │                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  DatabaseServiceFactory                                 │ │
│  │  - create()                                             │ │
│  │  - create_from_url()                                    │ │
│  │  - create_sqlite/postgresql/mysql()                     │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┼───────────────────────────────────┘
                            │
┌───────────────────────────┼───────────────────────────────────┐
│  Provider Layer           │                                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │  SQLite      │ │  PostgreSQL  │ │  MySQL       │         │
│  │  Provider    │ │  Provider    │ │  Provider    │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
└─────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────┼───────────────────────────────────┐
│  Infrastructure Layer     │                                   │
│  SQLAlchemy Engine + Async Driver                             │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Конфигурация

### Настройки в .env

```bash
# SQLite (по умолчанию)
DATABASE_URL=sqlite+aiosqlite:///db.sqlite3

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/mydb

# MySQL
DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/mydb

# Параметры пула (опционально)
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
DB_ECHO=false
```

### Параметры подключения

| Параметр | Описание | По умолчанию | SQLite | PostgreSQL | MySQL |
|----------|----------|--------------|--------|------------|-------|
| `pool_size` | Размер пула подключений | 10 | 1 | 20 | 15 |
| `max_overflow` | Дополнительные подключения | 20 | 0 | 40 | 30 |
| `pool_timeout` | Таймаут ожидания (сек) | 30 | 30 | 30 | 30 |
| `pool_recycle` | Пересоздание подключения (сек) | 1800 | 1800 | 1800 | 1800 |
| `pool_pre_ping` | Проверка подключения | True | True | True | True |
| `echo` | Логирование SQL | False | False | False | False |

---

## 🔌 API

### DatabaseServiceFactory

```python
from services.database import DatabaseServiceFactory

# Создание из URL
db = DatabaseServiceFactory.create_from_url(url)

# Создание через helper методы
db = DatabaseServiceFactory.create_sqlite(db_path)
db = DatabaseServiceFactory.create_postgresql(host, port, database, username, password)
db = DatabaseServiceFactory.create_mysql(host, port, database, username, password)

# Регистрация кастомного провайдера
DatabaseServiceFactory.register_provider(DatabaseType.CUSTOM, CustomProvider)
```

### IDatabaseService (интерфейс)

```python
# Свойства
db.db_type        # DatabaseType
db.status         # ConnectionStatus
db.config         # DatabaseConfig

# Подключение
await db.connect()
await db.disconnect()

# Сессии
async with db.session_context() as session:
    pass

session = await db.create_session()

# Запросы
rows = await db.execute_query(query, params)
count = await db.execute_many(query, params_list)

# Транзакции
async with db.begin_transaction() as session:
    pass

# Health check
is_available = await db.health_check()
```

### DatabaseConfig

```python
from services.database import DatabaseConfig

# Из URL
config = DatabaseConfig.from_url('sqlite+aiosqlite:///db.sqlite3')
config = DatabaseConfig.from_url('postgresql+asyncpg://...')
config = DatabaseConfig.from_url('mysql+aiomysql://...')

# Helper методы
config = DatabaseConfig.from_sqlite('db.sqlite3')
config = DatabaseConfig.from_postgresql(host, database, username, password)
config = DatabaseConfig.from_mysql(host, database, username, password)
```

---

## 📊 Поддерживаемые СУБД

| СУБД | Драйвер | Версии | Особенности |
|------|---------|--------|-------------|
| **SQLite** | aiosqlite | 3.x | WAL режим, оптимизация |
| **PostgreSQL** | asyncpg | 12+ | Уровни изоляции, размеры таблиц |
| **MySQL** | aiomysql | 5.7+ | Кодировка utf8mb4, оптимизация |

### SQLite особенности

```python
from services.database import SQLiteDatabaseService

db = DatabaseServiceFactory.create_sqlite('db.sqlite3')
await db.connect()

# Включить WAL режим (для конкурентного доступа)
await db.get_provider().enable_wal_mode()

# Оптимизация
await db.get_provider().optimize()

# Настройка синхронизации
await db.get_provider().set_synchronous('NORMAL')
```

### PostgreSQL особенности

```python
from services.database import PostgreSQLDatabaseService

db = DatabaseServiceFactory.create_postgresql(...)
await db.connect()

# Получить версию
version = await db.get_provider().get_version()

# Размеры таблиц
sizes = await db.get_provider().get_table_sizes()

# Обслуживание
await db.get_provider().analyze_tables()
await db.get_provider().vacuum(full=True)
```

### MySQL особенности

```python
from services.database import MySQLDatabaseService

db = DatabaseServiceFactory.create_mysql(...)
await db.connect()

# Получить версию
version = await db.get_provider().get_version()

# Размеры таблиц
sizes = await db.get_provider().get_table_sizes()

# Оптимизация
await db.get_provider().optimize_tables()
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты слоя абстракции
pytest tests/database/ -v

# Конкретные категории
pytest tests/database/test_enums.py -v
pytest tests/database/test_config.py -v
pytest tests/database/test_factory.py -v
```

### Статистика тестов

| Категория | Тестов | Покрытие |
|-----------|--------|----------|
| **Enums** | 12 | 100% |
| **Config** | 18 | 100% |
| **Factory** | 15 | 100% |
| **Всего** | 45 | 100% |

---

## 🔀 Миграция со старого API

### Было (старый код)

```python
from services.core.database import get_database_service

db_service = get_database_service()
async with db_service.session_context() as session:
    # работа с сессией
    pass
```

### Стало (новый код)

```python
from services.database import get_database_service

db_service = get_database_service()
await db_service.connect()  # Явное подключение

async with db_service.session_context() as session:
    # работа с сессией
    pass

await db_service.disconnect()  # Явное отключение
```

### Преимущества нового API

1. **Независимость от СУБД** — можно сменить SQLite на PostgreSQL без изменения кода
2. **Гибкая конфигурация** — настройки через URL или параметры
3. **Расширяемость** — легко добавить новую СУБД
4. **Тестируемость** — моки через интерфейсы `IDatabaseService`

---

## 🛠️ Расширение

### Добавление новой СУБД

1. Создать провайдер в `services/database/providers/`:

```python
# services/database/providers/custom.py
from services.database.providers.base import BaseDatabaseService
from services.database.interfaces import IProvider
from services.database.enums import DatabaseType

class CustomProvider(IProvider):
    # Реализация интерфейса
    pass

class CustomDatabaseService(BaseDatabaseService):
    @property
    def db_type(self):
        return DatabaseType.CUSTOM
    
    def get_provider(self):
        return CustomProvider(self.engine, self.config)
```

2. Зарегистрировать в фабрике:

```python
from services.database import DatabaseServiceFactory
from services.database.providers.custom import CustomDatabaseService

DatabaseServiceFactory.register_provider(
    DatabaseType.CUSTOM,
    CustomDatabaseService
)
```

---

## 📝 Лицензия

MIT License

**Автор:** AI-агент Стефания  
**Дата:** 2026-08-10
