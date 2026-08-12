# 📋 Планировщик задач v4.0 — Архитектура и руководство

**Версия:** 4.0.0  
**Дата:** 2026-08-12  
**Статус:** ✅ Актуализировано под архитектуру v4.0

---

## 🎯 Архитектура v4.0

### Ключевые изменения

| Было (v3.x) | Стало (v4.0) |
|-------------|--------------|
| Задачи создаются в коде планировщика | **Все задачи создаются через админ-интерфейс** |
| `daily_morning`/`daily_evening` жёстко заданы | **Любые типы задач через API** |
| Расписание в коде | **Расписание в таблице `tasks`** |
| Планировщик = источник задач | **Планировщик = исполнитель задач** |

### Принцип работы

```
┌─────────────────────────────────────────────────────────────────┐
│                  ADMIN INTERFACE (Web/HTTP)                     │
│  /tasks/create         → Создание задачи                        │
│  /tasks/create-direct  → Прямая генерация новости               │
│  /tasks/create-periodic → Периодическая задача                 │
│  /tasks/quick/*        → Быстрые шаблоны задач                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DATABASE (таблица `tasks`)                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ id | task_type | status | scheduled_at | recurring | ... │  │
│  │────|───────────|────────|──────────────|───────────|─────│  │
│  │ 1  | direct_...| pending| 2026-08-12   | false     | ... │  │
│  │ 2  | daily_... | pending| 2026-08-13   | true      | ... │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SCHEDULER (исполнитель)                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Проверка каждые 10 секунд                              │  │
│  │ 2. Выбор pending задач с наступившим scheduled_at         │  │
│  │ 3. Выполнение по типу задачи                              │  │
│  │ 4. Обновление статуса (completed/failed/pending)          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Таблица `tasks`

### Структура

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | int | Первичный ключ |
| `task_type` | string | Тип задачи (см. ниже) |
| `description` | string | Описание задачи |
| `post_id` | int? | ID поста (для прямой генерации) |
| `news_id` | int? | ID новости (для плановой обработки) |
| `scheduled_at` | datetime | Запланированное время выполнения |
| `status` | string | pending/active/completed/failed/expired/canceled |
| `recurring` | boolean | Флаг периодической задачи |
| `recurrence_pattern` | int? | Периодичность в днях (1=ежедневно) |
| `publisher_channel_id` | int? | ID канала публикации |
| `created_at` | datetime | Время создания |
| `completed_at` | datetime? | Время завершения |

### Типы задач

| Тип | Описание | Периодическая |
|-----|----------|---------------|
| `direct_generation` | Прямая генерация новости по описанию | ✅ |
| `scheduled_processing` | Плановая обработка новостей | ✅ |
| `event_processing` | Обработка событий (векторный поиск) | ✅ |
| `daily_morning` | Утренняя обработка | ✅ |
| `daily_evening` | Вечерняя обработка | ✅ |
| `custom_periodic` | Пользовательская периодическая | ✅ |

### Жизненный цикл задачи

```
ПЕРИОДИЧЕСКАЯ (recurring=True):
┌─────────┐    ┌─────────┐    ┌─────────┐
│ pending │───▶│ active  │───▶│ pending │───▶ ...
└─────────┘    └─────────┘    └─────────┘
                  │
                  ▼
            reset_recurring_task()
            (новое scheduled_at)

ОДНОРАЗОВАЯ (recurring=False):
┌─────────┐    ┌─────────┐    ┌──────────────┐
│ pending │───▶│ active  │───▶│ completed    │
└─────────┘    └─────────┘    │ failed       │
                  │            │ expired      │
                  │            │ canceled     │
                  ▼            └──────────────┘
            mark_completed()
            или mark_failed()
```

---

## 🔌 API для управления задачами

### Создание задач

#### 1. Прямая генерация новости
```bash
POST /tasks/create-direct
{
  "description": "Срочная новость о событии X",
  "publisher_channel_id": null,  // null = бот, -1 = все каналы, int = конкретный
  "scheduled_at": "2026-08-12T10:00:00",  // опционально
  "recurring": false,
  "recurrence_pattern": null
}
```

#### 2. Периодическая задача
```bash
POST /tasks/create-periodic
{
  "task_type": "custom_periodic",
  "description": "Ежечасная обработка новостей",
  "scheduled_at": "2026-08-12T10:00:00",
  "recurrence_pattern": 1  // 1 = ежедневно, 7 = еженедельно
}
```

#### 3. Общая задача
```bash
POST /tasks/create
{
  "task_type": "scheduled_processing",
  "description": "Обработка новостей за день",
  "scheduled_at": "2026-08-12T21:00:00",
  "recurring": true,
  "recurrence_pattern": 1
}
```

### Быстрые шаблоны

#### Утренняя обработка (09:00)
```bash
POST /tasks/quick/daily-morning?time=09:00
```

#### Вечерняя обработка (21:00)
```bash
POST /tasks/quick/daily-evening?time=21:00
```

### Просмотр задач

#### Список задач
```bash
GET /tasks/?status=pending&task_type=direct_generation&limit=50
```

#### Статистика
```bash
GET /tasks/stats
# Ответ: {"by_status": {"pending": 5, "active": 2, ...}, "total": 10}
```

#### Задача по ID
```bash
GET /tasks/{task_id}
```

### Управление задачами

#### Отмена задачи
```bash
POST /tasks/{task_id}/cancel
```

#### Перенос времени
```bash
POST /tasks/{task_id}/reschedule?scheduled_at=2026-08-13T10:00:00
```

#### Удаление
```bash
DELETE /tasks/{task_id}  # Только completed/failed/expired/canceled
```

#### Очистка старых
```bash
POST /tasks/cleanup?days_old=7&dry_run=true
```

---

## 🏃 Запуск планировщика

### Фоновые задачи

| Задача | Интервал | Описание |
|--------|----------|----------|
| `_run_task_processor` | 10 секунд | Проверка и выполнение задач |
| `_run_expired_cleaner` | 5 минут | Удаление старых задач (>7 дней) |
| `_run_rss_parser` | 5 минут | Парсинг RSS лент |
| `_event_bus_task` | постоянно | Шина событий EventBus |

### Логика выполнения

```python
while running:
    # 1. Проверка каждые 10 секунд
    await asyncio.sleep(10)
    
    # 2. Проверка просроченных задач
    for task in pending_tasks:
        if not task.recurring and task.scheduled_at < now:
            mark_expired(task.id)
    
    # 3. Выполнение задач с наступившим временем
    for task in pending_tasks:
        if task.scheduled_at <= now:
            mark_active(task.id)
            execute_task(task)  # По типу задачи
            update_status(task)  # completed/failed/pending
```

---

## 📝 Примеры использования

### 1. Создать ежедневную утреннюю обработку

```bash
# Через API
curl -X POST "http://localhost:8001/tasks/quick/daily-morning?time=09:00"

# Результат: задача daily_morning на 09:00 каждый день
```

### 2. Создать разовую генерацию новости

```bash
curl -X POST http://localhost:8001/tasks/create-direct \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Новости дня: важное событие X произошло сегодня",
    "publisher_channel_id": -1,
    "scheduled_at": "2026-08-12T18:00:00"
  }'
```

### 3. Создать еженедельную обработку событий

```bash
curl -X POST http://localhost:8001/tasks/create-periodic \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "event_processing",
    "description": "Еженедельный анализ событий",
    "scheduled_at": "2026-08-14T10:00:00",
    "recurrence_pattern": 7
  }'
```

### 4. Посмотреть статистику

```bash
curl http://localhost:8001/tasks/stats

# Ответ:
{
  "by_status": {
    "pending": 5,
    "active": 1,
    "completed": 120,
    "failed": 3,
    "expired": 2
  },
  "total": 131
}
```

---

## 🔧 Админ-интерфейс

### Web UI (в разработке)

- **Список задач** с фильтрацией по статусу/типу
- **Создание задачи** через форму
- **Быстрые шаблоны** (утро/вечер/события)
- **Статистика** по задачам
- **Управление** (отмена/перенос/удаление)

### API Endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/tasks/` | GET | Список задач |
| `/tasks/stats` | GET | Статистика |
| `/tasks/create` | POST | Создать задачу |
| `/tasks/create-direct` | POST | Прямая генерация |
| `/tasks/create-periodic` | POST | Периодическая |
| `/tasks/{id}` | GET | Задача по ID |
| `/tasks/{id}/cancel` | POST | Отменить |
| `/tasks/{id}/reschedule` | POST | Перенести |
| `/tasks/{id}` | DELETE | Удалить |
| `/tasks/cleanup` | POST | Очистка старых |
| `/tasks/meta/task-types` | GET | Справочник типов |

---

## ⚠️ Важные замечания

1. **Не создавайте задачи в прошлом** — планировщик пометит их как expired
2. **Периодические задачи** автоматически переключаются на следующее выполнение
3. **Одноразовые задачи** завершаются терминальным статусом (completed/failed)
4. **Очистка старых задач** работает автоматически (каждые 5 минут, старше 7 дней)
5. **Все задачи** создаются через админ-интерфейс — не через код планировщика

---

## 🔄 Миграция с v3.x

### Было (v3.x)

```python
# В коде планировщика
self._morning_task = asyncio.create_task(self._run_morning_scheduler())
self._evening_task = asyncio.create_task(self._run_evening_scheduler())
```

### Стало (v4.0)

```python
# Через админ-интерфейс
POST /tasks/quick/daily-morning?time=09:00
POST /tasks/quick/daily-evening?time=21:00

# Или через API
POST /tasks/create-periodic
{
  "task_type": "daily_morning",
  "scheduled_at": "2026-08-13T09:00:00",
  "recurrence_pattern": 1
}
```

---

**Автор:** AI-агент Стефания  
**Версия:** 4.0.0  
**Дата актуализации:** 2026-08-12
