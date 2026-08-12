# 🔄 План миграции на новый слой абстракции БД

**Версия:** 1.0  
**Дата:** 2026-08-10

---

## 📊 Текущее состояние

### Файлы, использующие старый слой (`services/core/database.py`)

| Файл | Использует | Строк с импортом |
|------|------------|------------------|
| `services/categorization/processor.py` | `get_database_service()` | 2 |
| `services/listener/bot.py` | `get_database_service()` | 5 |
| `services/core/container.py` | `DatabaseService`, `get_database_service()` | 10+ |
| `services/payment/service.py` | `get_database_service()` | 1 |
| `services/scheduler/scheduler.py` | `get_database_service()` | 1 |
| `services/news/helpers.py` | `get_database_service()` | 2 |
| `services/ai_agent/vector_routers.py` | `get_database_service()` | 2 |
| `services/telegram/notification.py` | `get_database_service()` | 3 |
| `services/bot/bot.py` | `get_database_service()` | 3 |
| `services/bot/utils.py` | `get_database_service()` | 1 |
| `services/bot/handlers/direct_news.py` | `get_database_service()` | 1 |

**Итого:** ~30 мест для обновления

---

## 🎯 Стратегия миграции

### Этап 1: Обратная совместимость (сейчас)

Создать обёртку в `services/core/database.py`, которая использует новый слой:

```python
# services/core/database.py
from services.database import (
    get_database_service as get_new_db_service,
    DatabaseServiceFactory,
    IDatabaseService,
)

# Обёртка для обратной совместимости
class DatabaseServiceAdapter:
    """Адаптер старого API к новому слою."""
    
    def __init__(self):
        self._service = get_new_db_service()
    
    @property
    def database_url(self):
        return self._service.config.resolved_url
    
    @property
    def engine(self):
        return self._service.engine
    
    @property
    def session_factory(self):
        # Вернуть factory из нового сервиса
        pass
    
    async def init_db(self):
        from database.models import Base
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def dispose(self):
        await self._service.disconnect()
    
    async def create_session(self):
        return await self._service.create_session()
    
    @asynccontextmanager
    async def session_context(self):
        async with self._service.session_context() as session:
            yield session

# Глобальная функция (обратная совместимость)
_db_service_adapter = None

def get_database_service():
    global _db_service_adapter
    if _db_service_adapter is None:
        _db_service_adapter = DatabaseServiceAdapter()
    return _db_service_adapter

async def dispose_database_service():
    global _db_service_adapter
    if _db_service_adapter:
        await _db_service_adapter.dispose()
        _db_service_adapter = None
```

### Этап 2: Постепенная миграция файлов

Мигрировать файлы по одному, начиная с наименее критичных:

1. ✅ `services/database/` — новый слой (готово)
2. ⏳ `services/news/helpers.py` — helper функции
3. ⏳ `services/ai_agent/vector_routers.py` — векторный поиск
4. ⏳ `services/payment/service.py` — платежи
5. ⏳ `services/categorization/processor.py` — категоризация
6. ⏳ `services/telegram/notification.py` — уведомления
7. ⏳ `services/bot/` — бот и хендлеры
8. ⏳ `services/listener/bot.py` — listener
9. ⏳ `services/scheduler/scheduler.py` — планировщик
10. ⏳ `services/core/container.py` — DI контейнер (последний)

### Этап 3: Обновление логов

Добавить информативные логи при подключении:

```python
# В main.py или точке входа
from services.database import get_database_service

db = get_database_service()
await db.connect()

logger.info(f"📊 СУБД: {db.db_type.name}")
logger.info(f"📊 URL: {db.config.resolved_url}")
logger.info(f"📊 Пул: size={db.config.pool_size}, overflow={db.config.max_overflow}")
```

---

## 📝 Чеклист миграции

### Код

- [ ] Создать адаптер в `services/core/database.py`
- [ ] Обновить `services/news/helpers.py`
- [ ] Обновить `services/ai_agent/vector_routers.py`
- [ ] Обновить `services/payment/service.py`
- [ ] Обновить `services/categorization/processor.py`
- [ ] Обновить `services/telegram/notification.py`
- [ ] Обновить `services/bot/bot.py`
- [ ] Обновить `services/bot/utils.py`
- [ ] Обновить `services/bot/handlers/*.py`
- [ ] Обновить `services/listener/bot.py`
- [ ] Обновить `services/scheduler/scheduler.py`
- [ ] Обновить `services/core/container.py`

### Логи

- [ ] Добавить логирование типа СУБД при старте
- [ ] Добавить логирование параметров пула
- [ ] Добавить логирование статуса подключения
- [ ] Проверить логи в `main.py`

### Тесты

- [ ] Обновить тесты для старого API
- [ ] Добавить тесты для нового API
- [ ] Запустить все тесты
- [ ] Проверить покрытие

### Документация

- [ ] Обновить README
- [ ] Документировать процесс миграции
- [ ] Обновить примеры использования

---

## 🔍 Мониторинг логов

### Ожидаемые логи при старте

```
INFO - Создание провайдера для SQLITE
INFO - Создание engine для SQLITE
INFO - ✅ Engine создан для SQLITE
INFO - ✅ Подключено к SQLITE
INFO - 📊 СУБД: SQLITE
INFO - 📊 URL: sqlite+aiosqlite:///db.sqlite3
INFO - 📊 Пул: size=1, overflow=0
```

### Для PostgreSQL

```
INFO - Создание провайдера для POSTGRESQL
INFO - Создание engine для POSTGRESQL
INFO - ✅ Engine создан для POSTGRESQL
INFO - ✅ Подключено к POSTGRESQL
INFO - 📊 СУБД: POSTGRESQL
INFO - 📊 URL: postgresql+asyncpg://***:***@localhost:5432/mydb
INFO - 📊 Пул: size=20, overflow=40
```

---

## ⚠️ Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Поломка старого API | Средняя | Высокое | Адаптер с полной совместимостью |
| Утечки подключений | Низкая | Высокое | Тестирование под нагрузкой |
| Проблемы с транзакциями | Средняя | Среднее | Тесты на откат транзакций |
| Несовместимость типов | Низкая | Среднее | Типизация и mypy |

---

## 📈 Метрики успеха

- ✅ Все тесты проходят (старые + новые)
- ✅ Логи показывают тип СУБД и параметры
- ✅ Нет импортов `from services.core.database import`
- ✅ Покрытие тестами > 90%
- ✅ Время отклика не ухудшилось

---

**Следующий шаг:** Создать адаптер для обратной совместимости и начать поэтапную миграцию.
