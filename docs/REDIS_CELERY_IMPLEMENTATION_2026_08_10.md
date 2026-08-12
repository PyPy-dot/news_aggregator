# 📮 Реализация распределённой очереди (Redis/Celery)

**Дата:** 2026-08-10  
**Версия:** 1.0.0  
**Статус:** ✅ Завершено

---

## 📋 Обзор

Реализована распределённая очередь задач на базе Redis с поддержкой Celery для надёжной обработки задач. Эта реализация решает задачу #5 из implementation_report.md.

---

## ✅ Выполненные задачи

### 1. Добавлены зависимости

**Файл:** `requirements.txt`

```txt
# Distributed Queue (Redis + Celery)
redis>=5.0.0
celery>=5.3.0
```

### 2. Создан RedisTaskQueue

**Файл:** `services/core/redis_queue.py`

**Компоненты:**
- `RedisTaskQueue` — основной класс очереди
- `AgentTask` — модель задачи (сериализуется в JSON)
- `TaskPriority` — приоритеты (CRITICAL, HIGH, NORMAL, LOW)
- `TaskStatus` — статусы (PENDING, PROCESSING, COMPLETED, FAILED, RETRY)

**Возможности:**
- ✅ Приоритетная очередь (sorted sets)
- ✅ Персистентность задач (hashes)
- ✅ Pub/Sub для уведомления воркеров
- ✅ Retry logic с экспоненциальной задержкой
- ✅ Мониторинг (Prometheus метрики)
- ✅ История задач (последние 50)

**Redis keys:**
```
{prefix}:queue          — sorted set с очередью
{prefix}:task:{id}      — hash с данными задачи
{prefix}:stats          — hash со статистикой
{prefix}:history        — list с историей
{prefix}:new_task       — pub/sub канал
```

### 3. Миграция AgentTaskQueue

**Файл:** `services/ai_agent/agent_queue.py`

**Изменения:**
- Автоматическое переключение на Redis при наличии `REDIS_URL`
- Fallback на локальную очередь если Redis недоступен
- Универсальные функции `start_agent_queue()`, `stop_agent_queue()`
- Функция `is_redis_queue()` для проверки режима

**Usage:**
```python
from services.ai_agent.agent_queue import get_agent_queue

queue = get_agent_queue()  # Автоматически Redis или локальная

await start_agent_queue(num_workers=2)
# ... работа ...
await stop_agent_queue()
```

### 4. Миграция CategorizationQueue

**Файл:** `services/categorization/queue.py`

**Изменения:**
- Поддержка Redis через `RedisTaskQueue`
- Автоматическое переключение по `REDIS_URL`
- Сохранение API для обратной совместимости

### 5. Docker Compose

**Файлы:** `docker-compose.yml`, `docker-compose.prod.yml`

Redis уже был добавлен в конфигурацию:

```yaml
redis:
  image: redis:7-alpine
  container_name: news-aggregator-redis
  restart: unless-stopped
  volumes:
    - redis_data:/data
  ports:
    - "6379:6379"
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
```

### 6. Тесты

**Файл:** `tests/test_core/test_redis_queue.py`

**Покрытие:**
- ✅ Сериализация/десериализация `AgentTask`
- ✅ Подключение/отключение к Redis
- ✅ Добавление задач с приоритетами
- ✅ Получение задач в порядке приоритета
- ✅ Выполнение задач (success/failure)
- ✅ Retry logic
- ✅ Статистика и история
- ✅ Очистка очереди
- ✅ Глобальный singleton

**Запуск:**
```bash
export REDIS_URL=redis://localhost:6379
pytest tests/test_core/test_redis_queue.py -v
```

### 7. Документация

**Файлы:**
- `docs/REDIS_QUEUE_SETUP.md` — полная документация по Redis очереди
- `docs/CELERY_WORKER_SETUP.md` — документация по Celery worker
- `docs/REDIS_CELERY_IMPLEMENTATION_2026_08_10.md` — этот файл

### 8. Celery Worker

**Файл:** `services/core/celery_worker.py`

**Задачи:**
- `tasks.example_sum` — пример задачи
- `tasks.process_categorization` — категоризация текста
- `tasks.process_analysis` — анализ новости
- `tasks.generate_news` — генерация новости
- `tasks.send_notification` — отправка уведомлений

**Периодические задачи (Beat):**
- `process-events-every-48h` — обработка событий
- `cleanup-cache-every-6h` — очистка кэша LLM

**Запуск:**
```bash
# Worker
celery -A services.core.celery_worker worker --loglevel=info --concurrency=4

# Beat (планировщик)
celery -A services.core.celery_worker beat --loglevel=info

# Flower (мониторинг)
celery -A services.core.celery_worker flower --port=5555
```

### 9. Интеграция в main.py

**Файл:** `main.py`

**Изменения:**
- Импорт `start_agent_queue`, `stop_agent_queue`, `is_redis_queue`
- Запуск Redis очереди при старте (если настроен)
- Корректная остановка очереди при shutdown

```python
# Запуск очереди
if is_redis_queue():
    await start_agent_queue(num_workers=2)

# Остановка
if self._agent_queue_started:
    await stop_agent_queue()
```

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         Redis Server                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Sorted Set: agent_queue:queue                           │   │
│  │  (приоритетная очередь)                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Hash: agent_queue:task:{task_id}                        │   │
│  │  (данные задач)                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Pub/Sub: agent_queue:new_task                           │   │
│  │  (уведомления)                                           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────────────┐   ┌─────────────────┐   ┌───────────────┐
│   Worker 1    │   │   Worker 2      │   │   Worker N    │
│   (app)       │   │   (app)         │   │   (Celery)    │
└───────────────┘   └─────────────────┘   └───────────────┘
```

---

## 📊 Сравнение: До и После

| Характеристика | До (локальная) | После (Redis) |
|----------------|----------------|---------------|
| **Масштабирование** | Один процесс | Несколько воркеров |
| **Персистентность** | Нет (в памяти) | Да (в Redis) |
| **Отказоустойчивость** | Нет | Да (retry + persistence) |
| **Мониторинг** | Ограниченный | Полный (Prometheus + Flower) |
| **Приоритеты** | Да | Да (улучшено) |
| **Retry logic** | Да | Да (экспоненциальный) |
| **Планирование** | Нет | Да (Celery Beat) |

---

## 🚀 Быстрый старт

### 1. Настройка

```bash
# Копируем .env.example
cp .env.example .env

# Добавляем REDIS_URL
echo "REDIS_URL=redis://redis:6379" >> .env
```

### 2. Запуск Docker

```bash
docker-compose up -d

# Проверка
docker-compose ps
# Должен быть запущен redis
```

### 3. Запуск приложения

```bash
python main.py

# В логе должно быть:
# ✅ Используем Redis очередь: redis://redis:6379
# 🚀 Redis очередь запущена (2 воркера)
```

### 4. Запуск Celery (опционально)

```bash
# Worker
celery -A services.core.celery_worker worker --loglevel=info --concurrency=4

# Или в Docker (добавить в docker-compose.yml)
```

---

## 📈 Метрики

### Prometheus

| Метрика | Описание |
|---------|----------|
| `agent_queue_size` | Размер очереди |
| `agent_queue_active_tasks` | Активные задачи (по агентам) |
| `agent_tasks_total` | Всего задач (по статусам) |
| `agent_task_duration` | Длительность выполнения |
| `agent_queue_pending_by_priority` | Ожидающие по приоритетам |

### Redis CLI

```bash
# Размер очереди
docker-compose exec redis redis-cli ZCARD agent_queue:queue

# Статистика
docker-compose exec redis redis-cli HGETALL agent_queue:stats

# История
docker-compose exec redis redis-cli LRANGE agent_queue:history 0 9
```

---

## ⚠️ Известные ограничения

1. **CategorizationQueue.get()** — не поддерживается в режиме Redis (задачи обрабатываются воркерами)
2. **Прямой вызов методов** — требует регистрации через `register_method()`
3. **Сложные объекты** — должны сериализоваться в JSON

---

## 🔜 Следующие шаги

### Рекомендуется:

1. **Добавить Celery worker в docker-compose.yml**
   ```yaml
   celery-worker:
     build: .
     command: celery -A services.core.celery_worker worker --loglevel=info
     environment:
       - REDIS_URL=redis://redis:6379
     depends_on:
       - redis
   ```

2. **Настроить Flower для мониторинга**
   ```yaml
   flower:
     build: .
     command: celery -A services.core.celery_worker flower --port=5555
     ports:
       - "5555:5555"
   ```

3. **Добавить Circuit Breaker для Redis**
   - Защита от сбоев Redis
   - Fallback на локальную очередь

4. **Rate limiting для AI-агентов**
   - Ограничение количества задач в минуту
   - Prioritization для срочных задач

---

## 📚 Ссылки

- [Redis Queue Documentation](docs/REDIS_QUEUE_SETUP.md)
- [Celery Worker Setup](docs/CELERY_WORKER_SETUP.md)
- [Implementation Report](docs/IMPLEMENTATION_REPORT.md)

---

## 📊 Статистика реализации

| Метрика | Значение |
|---------|----------|
| **Новых файлов** | 4 |
| **Изменённых файлов** | 4 |
| **Строк кода добавлено** | ~1200 |
| **Тестов** | 25+ |
| **Документации** | 3 файла |

---

**Автор:** AI-агент Стефания  
**Дата завершения:** 2026-08-10  
**Статус:** ✅ Завершено (Задача #5 из implementation_report.md)
