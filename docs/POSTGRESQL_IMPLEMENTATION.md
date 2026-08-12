# Реализация поддержки PostgreSQL

**Дата:** 2026-08-09  
**Версия:** 3.2.0  
**Статус:** ✅ Завершено

---

## Обзор

Добавлена полная поддержка PostgreSQL в дополнение к существующей SQLite. Это позволяет использовать News Aggregator в production-средах с высокой нагрузкой.

---

## Изменения

### 1. Конфигурация (`config/settings.py`)

**Добавлено:**
- Новое поле `database_url` для подключения к PostgreSQL через `DATABASE_URL`
- Метод `database_url_resolved` — возвращает URL с приоритетом DATABASE_URL над SQLite
- Свойство `is_postgresql` — проверяет тип используемой БД

**Пример использования:**
```python
from config.settings import settings

# Автоматическое определение типа БД
if settings.is_postgresql:
    print("Используется PostgreSQL")
else:
    print("Используется SQLite")

# Получение URL
url = settings.database_url_resolved
```

---

### 2. Database Service (`services/core/database.py`)

**Изменения:**
- Метод `_init_engine()` автоматически определяет тип БД и применяет соответствующие настройки
- Для PostgreSQL: `pool_size=20`, `max_overflow=40`, `pool_pre_ping=True`
- Для SQLite: `pool_size=50`, `max_overflow=100` (для обратной совместимости)

**Логирование:**
```
✅ Использование PostgreSQL
# или
✅ Использование SQLite: sqlite+aiosqlite:///db.sqlite3
```

---

### 3. Alembic (`alembic/env.py`)

**Изменения:**
- Функция `get_url()` конвертирует async драйверы в sync для Alembic:
  - `sqlite+aiosqlite://` → `sqlite://`
  - `postgresql+asyncpg://` → `postgresql://`
- Функция `is_postgresql()` определяет тип БД
- `run_migrations_online()` применяет разные настройки пула для SQLite/PostgreSQL
- `render_as_batch=True` только для SQLite (требуется для ALTER TABLE)

---

### 4. Зависимости (`requirements.txt`)

**Добавлено:**
```
asyncpg==0.29.0  # PostgreSQL async driver
```

---

### 5. Документация

**Создано:**
- `docs/POSTGRESQL_SETUP.md` — полное руководство по настройке PostgreSQL
- `docs/ALEMBIC_SETUP.md` — обновлено с поддержкой PostgreSQL
- `README.md` — добавлена информация о поддержке PostgreSQL

---

### 6. Тесты

**Создано:**
- `tests/test_core/test_database_postgresql.py` — 15 тестов
- `tests/test_alembic/test_migrations.py` — 14 тестов

**Покрытие:**
- Конверсия URL (SQLite/PostgreSQL)
- Инициализация DatabaseService
- Создание engine с разными настройками
- Работа сессий
- Alembic миграции
- Интеграционные тесты

**Результат:** ✅ 29/29 тестов пройдено

---

## Использование

### Быстрый старт с PostgreSQL

1. **Установите asyncpg:**
   ```bash
   pip install asyncpg==0.29.0
   ```

2. **Создайте базу данных:**
   ```sql
   CREATE DATABASE news_aggregator;
   CREATE USER news_user WITH PASSWORD 'secure_password';
   GRANT ALL PRIVILEGES ON DATABASE news_aggregator TO news_user;
   ```

3. **Настройте окружение (.env):**
   ```env
   DATABASE_URL=postgresql+asyncpg://news_user:secure_password@localhost:5432/news_aggregator
   ```

4. **Примените миграции:**
   ```bash
   alembic upgrade head
   ```

5. **Запустите приложение:**
   ```bash
   python main.py
   ```

---

## Миграция с SQLite на PostgreSQL

### Вариант 1: Чистая установка

1. Создайте новую базу данных PostgreSQL
2. Настройте `DATABASE_URL` в `.env`
3. Примените миграции: `alembic upgrade head`
4. Запустите приложение

### Вариант 2: Перенос данных

```bash
# 1. Экспорт из SQLite
sqlite3 db.sqlite3 .dump > sqlite_export.sql

# 2. Установка pgloader
brew install pgloader  # macOS
sudo apt-get install pgloader  # Linux

# 3. Миграция данных
pgloader sqlite://db.sqlite3 postgresql://user:pass@localhost:5432/news_aggregator
```

---

## Архитектурные решения

### 1. Приоритет DATABASE_URL

```
DATABASE_URL (если указан)
    ↓
SQLite (db_path, по умолчанию)
```

Это позволяет легко переключаться между SQLite и PostgreSQL без изменения кода.

### 2. Автоматическое определение типа БД

```python
is_postgresql = (
    self.database_url.startswith('postgresql+asyncpg') or
    self.database_url.startswith('postgresql://')
)
```

### 3. Разные настройки пула для SQLite/PostgreSQL

| Параметр | SQLite | PostgreSQL |
|----------|--------|------------|
| `pool_size` | 50 | 20 |
| `max_overflow` | 100 | 40 |
| `pool_timeout` | 60 | 30 |
| `pool_pre_ping` | True | True |

---

## Тестирование

### Запуск тестов

```bash
# Все тесты PostgreSQL
pytest tests/test_core/test_database_postgresql.py -v

# Все тесты Alembic
pytest tests/test_alembic/test_migrations.py -v

# Все тесты вместе
pytest tests/test_core/test_database_postgresql.py tests/test_alembic/test_migrations.py -v
```

### Результат

```
======================== 29 passed, 2 warnings in 1.20s ========================
```

---

## Производительность

### Benchmark (ожидаемый)

| Операция | SQLite | PostgreSQL | Улучшение |
|----------|--------|------------|-----------|
| Чтение (1000 записей) | ~50ms | ~20ms | 2.5x |
| Запись (100 записей) | ~100ms | ~40ms | 2.5x |
| Concurrent connections | 10-20 | 100+ | 5-10x |

---

## Безопасность

### Хранение паролей

⚠️ **Никогда не храните пароли в коде!**

Используйте `.env` файл (добавьте в `.gitignore`):
```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/db
```

### SSL подключение

Для production используйте SSL:
```env
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db?sslmode=require
```

---

## Troubleshooting

### Ошибка: "No module named 'asyncpg'"

```bash
pip install asyncpg==0.29.0
```

### Ошибка: "connection refused"

Проверьте, что PostgreSQL запущен:
```bash
brew services list  # macOS
systemctl status postgresql  # Linux
```

### Ошибка: "database does not exist"

Создайте базу данных:
```sql
CREATE DATABASE news_aggregator;
```

### Alembic не применяет миграции

Проверьте `DATABASE_URL` в `.env`:
```bash
alembic current  # Показать текущую ревизию
alembic upgrade head  # Применить миграции
```

---

## Следующие шаги

### Рекомендации

1. **Настроить резервное копирование PostgreSQL**
   ```bash
   pg_dump -U news_user news_aggregator > backup.sql
   ```

2. **Настроить мониторинг**
   - Prometheus метрики уже доступны на `/metrics`
   - Добавить дашборд Grafana для PostgreSQL

3. **Настроить логирование медленных запросов**
   ```sql
   ALTER SYSTEM SET log_min_duration_statement = 1000;  # 1 секунда
   SELECT pg_reload_conf();
   ```

4. **Оптимизировать производительность**
   - Настроить `shared_buffers` (25% RAM)
   - Настроить `effective_cache_size` (75% RAM)
   - Настроить `work_mem` для сортировок

---

## Метрики выполнения

| Задача | Статус |
|--------|--------|
| Обновление `config/settings.py` | ✅ |
| Обновление `services/core/database.py` | ✅ |
| Обновление `alembic/env.py` | ✅ |
| Обновление `requirements.txt` | ✅ |
| Документация (`POSTGRESQL_SETUP.md`) | ✅ |
| Обновление `ALEMBIC_SETUP.md` | ✅ |
| Обновление `README.md` | ✅ |
| Тесты (29 тестов) | ✅ 29/29 |
| **Итого** | **✅ Завершено** |

---

**Исполнитель:** AI-агент Стефания  
**Дата завершения:** 2026-08-09  
**Статус:** ✅ Готово к production
