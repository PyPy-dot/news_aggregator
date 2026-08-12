# Миграции базы данных

Эта директория содержит скрипты миграции базы данных.

## Alembic (рекомендуемый способ)

Проект использует **Alembic** для управления миграциями. См. [docs/ALEMBIC_SETUP.md](../../docs/ALEMBIC_SETUP.md).

**Быстрый старт:**

```bash
# Применить все миграции
alembic upgrade head

# Создать новую миграцию
alembic revision --autogenerate -m "Описание изменений"

# Проверить текущую ревизию
alembic current
```

## Ручные миграции (устаревший способ)

> ⚠️ **Примечание:** Ручные миграции устарели. Используйте Alembic для новых изменений.

| Файл | Описание |
|------|----------|
| `migrate_add_analyzed_fields.py` | Добавление полей `analyzed_at` |
| `migrate_add_moderation_fields.py` | Добавление полей модерации (`moderation_status`, `moderated_at`) |
| `migrate_add_news_tables.py` | Создание таблиц `generated_news`, `events` |
| `migrate_add_publishers.py` | Добавление таблицы `publishers` |
| `migrate_add_trust_fields.py` | Добавление полей доверия (`is_trusted`, `trust_score`) |
| `migrate_add_users_table.py` | Создание таблицы `users` |
| `migrate_checked_at_boolean.py` | Изменение типа `checked_at` на BOOLEAN |
| `migrate_update_news_schema.py` | Обновление схемы таблицы новостей |
| `migrate_tasks_add_recurring_fields.py` | Переименование `is_daily` → `recurring`, добавление `recurrence_pattern` | |

## Запуск миграций

```bash
# Активировать виртуальное окружение
source .venv/bin/activate  # Linux/Mac
# или
.venv\Scripts\Activate  # Windows

# Запустить все миграции
python -m database.migrations.migrate_add_analyzed_fields
python -m database.migrations.migrate_add_moderation_fields
python -m database.migrations.migrate_add_news_tables
python -m database.migrations.migrate_add_publishers
python -m database.migrations.migrate_add_trust_fields
python -m database.migrations.migrate_add_users_table
python -m database.migrations.migrate_checked_at_boolean
python -m database.migrations.migrate_update_news_schema
```

## Порядок выполнения

Для развёртывания с нуля выполните миграции **в указанном порядке**:

```bash
python -m database.migrations.migrate_add_analyzed_fields
python -m database.migrations.migrate_add_moderation_fields
python -m database.migrations.migrate_add_news_tables
python -m database.migrations.migrate_add_publishers
python -m database.migrations.migrate_add_trust_fields
python -m database.migrations.migrate_add_users_table
python -m database.migrations.migrate_checked_at_boolean  # ← КРИТИЧНО!
python -m database.migrations.migrate_update_news_schema
```

> **Важно:** Миграция `migrate_checked_at_boolean` должна быть выполнена обязательно — без неё приложение не сможет обрабатывать новости.

## Примечание

Эти миграции уже выполнены в продакшене. Новые экземпляры могут использовать прямой вызов `models.Base.metadata.create_all()`.
