# Настройка PostgreSQL для News Aggregator

## Обзор

News Aggregator поддерживает работу как с SQLite (по умолчанию), так и с PostgreSQL для production-развёртываний.

## Требования

- PostgreSQL 14+
- Python 3.10+
- asyncpg 0.29.0 (уже в `requirements.txt`)

## Быстрый старт

### 1. Установка PostgreSQL

**macOS (Homebrew):**
```bash
brew install postgresql@14
brew services start postgresql@14
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install postgresql-14 postgresql-contrib
sudo systemctl start postgresql
```

**Windows:**
Скачайте установщик с https://www.postgresql.org/download/windows/

### 2. Создание базы данных

```bash
# Переключиться на пользователя postgres
sudo -i -u postgres

# Войти в psql
psql

# Создать базу данных и пользователя
CREATE DATABASE news_aggregator;
CREATE USER news_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE news_aggregator TO news_user;
\q
```

### 3. Настройка окружения

Создайте или обновите `.env` файл в корне проекта:

```env
# Database URL для PostgreSQL
DATABASE_URL=postgresql+asyncpg://news_user:your_secure_password@localhost:5432/news_aggregator

# Или для SQLite (по умолчанию)
# DATABASE_URL=sqlite+aiosqlite:///db.sqlite3
```

### 4. Применение миграций

```bash
# Применить все миграции
alembic upgrade head

# Проверить текущую ревизию
alembic current
```

### 5. Запуск приложения

```bash
python main.py
```

## Конфигурация

### Переменные окружения

| Переменная | Описание | Пример |
|------------|----------|--------|
| `DATABASE_URL` | URL подключения к БД | `postgresql+asyncpg://user:pass@host:5432/db` |
| `db_path` | Путь к SQLite (если не указан DATABASE_URL) | `db.sqlite3` |

### Формат DATABASE_URL

```
postgresql+asyncpg://<user>:<password>@<host>:<port>/<database_name>
```

**Примеры:**

```
# Local PostgreSQL
postgresql+asyncpg://news_user:password@localhost:5432/news_aggregator

# Remote PostgreSQL
postgresql+asyncpg://news_user:password@db.example.com:5432/news_aggregator

# С параметрами подключения
postgresql+asyncpg://news_user:password@localhost:5432/news_aggregator?sslmode=require
```

## Миграция с SQLite на PostgreSQL

### Шаг 1: Экспорт данных из SQLite

```bash
# Установите sqlite3 утилиту если не установлена
# macOS: brew install sqlite
# Linux: sudo apt-get install sqlite3

# Экспорт в SQL
sqlite3 db.sqlite3 .dump > sqlite_export.sql
```

### Шаг 2: Создание схемы в PostgreSQL

```bash
# Применить миграции для создания схемы
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/news_aggregator alembic upgrade head
```

### Шаг 3: Перенос данных (опционально)

Для переноса данных используйте скрипт миграции или инструменты типа `pgloader`:

```bash
# Установка pgloader
# macOS: brew install pgloader
# Linux: sudo apt-get install pgloader

# Миграция данных
pgloader sqlite://db.sqlite3 postgresql://user:pass@localhost:5432/news_aggregator
```

## Мониторинг и обслуживание

### Проверка подключения

```python
from services.core.database import get_database_service

db_service = get_database_service()
async with db_service.session_context() as session:
    result = await session.execute("SELECT 1")
    print("✅ PostgreSQL подключён")
```

### Резервное копирование

```bash
# Создать дамп базы
pg_dump -U news_user news_aggregator > backup.sql

# Восстановить из дампа
psql -U news_user news_aggregator < backup.sql
```

### Очистка старых данных

```sql
-- Удалить старые обработанные посты (старше 30 дней)
DELETE FROM posts WHERE created_at < NOW() - INTERVAL '30 days';

-- Удалить завершённые задачи (старше 7 дней)
DELETE FROM tasks WHERE status = 'completed' AND updated_at < NOW() - INTERVAL '7 days';
```

## Производительность

### Индексы

Alembic автоматически создаёт индексы при применении миграций. Проверьте наличие индексов:

```sql
-- Показать все индексы
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public';
```

### Пул подключений

Настройки пула подключений в `services/core/database.py`:

```python
pool_size=20       # Размер пула для PostgreSQL
max_overflow=40    # Дополнительные соединения
pool_timeout=30    # Таймаут ожидания
pool_recycle=1800  # Пересоздание через 30 минут
```

### Мониторинг

Prometheus метрики доступны на `/metrics`:

```bash
curl http://localhost:8000/metrics
```

## Troubleshooting

### Ошибка: "connection refused"

Проверьте, что PostgreSQL запущен:

```bash
# macOS
brew services list

# Linux
systemctl status postgresql
```

### Ошибка: "authentication failed"

Проверьте `pg_hba.conf`:

```bash
# Найти расположение pg_hba.conf
sudo -u postgres psql -c "SHOW hba_file;"

# Добавить строку для локального подключения
host    news_aggregator    news_user    127.0.0.1/32    md5
```

### Ошибка: "database does not exist"

Создайте базу данных:

```sql
CREATE DATABASE news_aggregator;
```

### Ошибка Alembic: "target metadata is None"

Убедитесь, что модели импортированы в `alembic/env.py`:

```python
from database.models import Base
target_metadata = Base.metadata
```

## Безопасность

### Хранение паролей

Никогда не храните пароли в коде. Используйте `.env` файл или переменные окружения:

```bash
# .env (добавьте в .gitignore!)
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/db
```

### SSL подключение

Для production используйте SSL:

```
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db?sslmode=require
```

### Ограничение доступа

Настройте брандмауэр для ограничения доступа к порту PostgreSQL (5432):

```bash
# Разрешить только с localhost
sudo ufw allow from 127.0.0.1 to any port 5432
```

## Дополнительные ресурсы

- [Документация PostgreSQL](https://www.postgresql.org/docs/)
- [Документация asyncpg](https://magicstack.github.io/asyncpg/)
- [Документация Alembic](https://alembic.sqlalchemy.org/)
- [pgloader для миграции данных](https://pgloader.io/)

---

**Версия:** 1.0  
**Дата:** 2026-08-09  
**Статус:** ✅ Готово к использованию
