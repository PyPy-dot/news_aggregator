# Alembic Migration Guide для News Aggregator

## Установка

Alembic уже установлен в `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Поддерживаемые базы данных

| БД | Driver | URL формат |
|----|--------|------------|
| **SQLite** | aiosqlite | `sqlite+aiosqlite:///db.sqlite3` |
| **PostgreSQL** | asyncpg | `postgresql+asyncpg://user:pass@localhost:5432/dbname` |

Для использования PostgreSQL:

1. Установите asyncpg (уже в requirements.txt):
   ```bash
   pip install asyncpg==0.29.0
   ```

2. Создайте `.env` с переменной `DATABASE_URL`:
   ```
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/news_aggregator
   ```

3. Если `DATABASE_URL` не указан, используется SQLite по умолчанию.

## Настройка

### Структура Alembic

```
alembic/
├── env.py              # Конфигурация окружения Alembic
├── script.py.mako      # Шаблон для миграций
├── README              # Документация Alembic
└── versions/           # Файлы миграций
    └── <revision>.py   # Конкретные миграции
```

### Конфигурация

**alembic.ini:**
- `script_location = alembic` — расположение скриптов миграции
- `sqlalchemy.url` — URL базы данных (переопределяется в env.py)
- `file_template` — шаблон имён файлов миграций

**alembic/env.py:**
- Импортирует `Base.metadata` из `database.models`
- Использует `settings.database_url_resolved` из конфигурации
- Автоматически определяет тип БД (SQLite/PostgreSQL)
- Поддерживает оба режима работы

## Использование

### Создать новую миграцию

```bash
# Автоматически на основе изменений в моделях
alembic revision --autogenerate -m "Description of changes"

# Пустая миграция
alembic revision -m "Description of changes"
```

### Применить миграции

```bash
# Применить все миграции
alembic upgrade head

# Применить одну миграцию
alembic upgrade +1

# Откатить одну миграцию
alembic downgrade -1

# Откатить все миграции
alembic downgrade base
```

### Проверка состояния

```bash
# Показать текущую ревизию
alembic current

# Показать историю миграций
alembic history

# Показать миграции для применения
alembic history --verbose
```

## Существующие миграции

Ручные миграции находятся в `database/migrations/`:

| Файл | Описание |
|------|----------|
| `migrate_add_users_table.py` | Пользователи и подписки |
| `migrate_add_tasks_table.py` | Задачи планировщика |
| `migrate_add_news_tables.py` | Новости и события |
| `migrate_add_moderation_fields.py` | Поля модерации |
| `migrate_add_trust_fields.py` | Доверенные источники |
| `migrate_add_publishers.py` | Каналы публикации |
| `migrate_add_analyzed_fields.py` | Поля аналитика |
| `migrate_update_news_schema.py` | Обновление схемы новостей |
| `migrate_checked_at_boolean.py` | Исправление поля checked_at |
| `migrate_tasks_add_recurring_fields.py` | Периодические задачи |
| `migrate_tasks_add_publisher_channel.py` | Каналы для задач |
| `add_indexes_2026_08_08.py` | Индексы для таблиц |

Для применения существующих миграций используйте `main.py` — они применяются автоматически при запуске приложения.

## Создание миграций вручную

1. Внесите изменения в `database/models.py`
2. Создайте миграцию:
   ```bash
   alembic revision --autogenerate -m "Add new column"
   ```
3. Проверьте сгенерированный файл в `alembic/versions/`
4. Примените миграцию:
   ```bash
   alembic upgrade head
   ```

## Пример миграции

```python
"""Add trust_rating to channels

Revision ID: abc123
Revises: def456
Create Date: 2026-08-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'abc123'
down_revision = 'def456'

def upgrade():
    op.add_column('channels', sa.Column('trust_rating', sa.Integer(), nullable=True))

def downgrade():
    op.drop_column('channels', 'trust_rating')
```

## Troubleshooting

### Ошибка: "table _alembic_tmp_* already exists"

Очистите базу данных и примените миграции заново:

```bash
rm db.sqlite3
alembic upgrade head
```

### Ошибка: "NoSuchTableError"

Убедитесь, что таблица существует. Если таблица ещё не создана, используйте `op.create_table()` вместо `op.batch_alter_table()`.

### Ошибка: "Constraint must have a name"

Добавьте имя для внешнего ключа:

```python
# Неправильно
op.create_foreign_key(None, 'publishers', ['publisher_channel_id'], ['id'])

# Правильно
op.create_foreign_key('fk_tasks_publisher_channel_id', 'publishers', ['publisher_channel_id'], ['id'])
```

## Интеграция с приложением

Alembic настроен на использование тех же настроек базы данных, что и приложение (`settings.db_path`). При запуске приложения миграции **не применяются автоматически** — используйте команду `alembic upgrade head` перед запуском.

Для автоматического применения миграций при запуске добавьте в `main.py`:

```python
from alembic.config import Config
from alembic import command

def apply_migrations():
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
```
