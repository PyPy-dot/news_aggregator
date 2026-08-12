# 📮 Настройка распределённой очереди на Redis

**Дата:** 2026-08-10  
**Версия:** 1.0.0

---

## 📋 Обзор

Распределённая очередь задач на базе Redis обеспечивает:

- **Горизонтальное масштабирование** — несколько воркеров обрабатывают задачи параллельно
- **Персистентность** — задачи сохраняются в Redis и не теряются при перезапуске
- **Приоритетную обработку** — срочные задачи выполняются в первую очередь
- **Retry logic** — автоматические повторные попытки при ошибках
- **Мониторинг** — метрики Prometheus для отслеживания состояния

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                    Redis Server                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Sorted Set: {prefix}:queue                              │   │
│  │  (приоритетная очередь задач)                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Hash: {prefix}:task:{task_id}                           │   │
│  │  (данные каждой задачи)                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Pub/Sub: {prefix}:new_task                              │   │
│  │  (уведомления воркеров о новых задачах)                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────────────┐   ┌─────────────────┐   ┌───────────────┐
│   Worker 1    │   │   Worker 2      │   │   Worker N    │
│   (consume)   │   │   (consume)     │   │   (consume)   │
└───────────────┘   └─────────────────┘   └───────────────┘
```

---

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
pip install redis celery
```

Или обновите `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 2. Настройка Redis в Docker

Redis уже добавлен в `docker-compose.yml`:

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
    interval: 5s
    timeout: 5s
    retries: 5
```

### 3. Конфигурация

Добавьте `REDIS_URL` в `.env`:

```bash
# Redis
REDIS_URL=redis://redis:6379
# или для локальной разработки
# REDIS_URL=redis://localhost:6379
```

### 4. Запуск

```bash
# Запуск всех сервисов с Redis
docker-compose up -d

# Проверка статуса
docker-compose ps

# Проверка логов Redis
docker-compose logs -f redis
```

---

## 📦 Компоненты

### RedisTaskQueue

Основной класс распределённой очереди:

```python
from services.core.redis_queue import RedisTaskQueue

queue = RedisTaskQueue(
    redis_url='redis://localhost:6379',
    prefix='agent_queue',
    max_concurrency=2,      # Параллельных задач на воркер
    max_queue_size=100,     # Максимум задач в очереди
    retry_delay=2.0,        # Базовая задержка retry (сек)
)

await queue.connect()
await queue.start(num_workers=2)
```

### Параметры

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `redis_url` | `redis://localhost:6379` | URL подключения к Redis |
| `prefix` | `agent_queue` | Префикс для ключей в Redis |
| `max_concurrency` | `2` | Макс. количество параллельных задач на воркер |
| `max_queue_size` | `100` | Максимальный размер очереди |
| `retry_delay` | `2.0` | Базовая задержка между retry (секунды) |

### Приоритеты задач

| Приоритет | Значение | Пример использования |
|-----------|----------|---------------------|
| `CRITICAL` | 1 | Критические уведомления |
| `HIGH` | 2 | Срочные новости (4-5) |
| `NORMAL` | 3 | Плановая обработка |
| `LOW` | 4 | Фоновые задачи |

---

## 🔧 Использование

### Добавление задачи

```python
from services.core.redis_queue import RedisTaskQueue, TaskPriority

queue = RedisTaskQueue()
await queue.connect()

# Добавление задачи
task_id = await queue.add_task(
    agent_name='Editor',
    method_name='generate_news',
    instance,  # self для метода
    news_data,
    priority=TaskPriority.HIGH,
    max_retries=3,
)
```

### Регистрация метода

```python
# Регистрация метода для вызова воркерами
queue.register_method('Editor', 'generate_news', editor.generate_news)
```

### Запуск воркеров

```python
# Запуск 2 воркеров
await queue.start(num_workers=2)

# ... работа ...

# Остановка
await queue.stop()
```

### Получение статистики

```python
stats = await queue.get_stats()
print(stats)
# {
#     'total': 150,
#     'completed': 145,
#     'failed': 3,
#     'retried': 2,
#     'queue_size': 2,
#     'running': True,
#     'active_by_agent': {'Editor': 1, 'Analyst': 1}
# }
```

### Получение истории

```python
# Последние 50 задач
history = await queue.get_history(limit=50)

for task in history:
    print(f"{task.task_id}: {task.status} - {task.result}")
```

### Получение задачи по ID

```python
task = await queue.get_task(task_id)
if task:
    print(f"Status: {task.status}, Result: {task.result}")
```

---

## 🔄 Интеграция с существующими очередями

### AgentTaskQueue

Модуль `services/ai_agent/agent_queue.py` автоматически использует Redis при наличии `REDIS_URL` в окружении:

```python
from services.ai_agent.agent_queue import get_agent_queue, start_agent_queue, stop_agent_queue

# Автоматически выбирает Redis или локальную очередь
queue = get_agent_queue()

# Запуск (универсальный)
await start_agent_queue(num_workers=2)

# Остановка
await stop_agent_queue()
```

### CategorizationQueue

Модуль `services/categorization/queue.py` также поддерживает Redis:

```python
from services.categorization.queue import CategorizationQueue

queue = CategorizationQueue()

# Добавление задачи (автоматически в Redis или локально)
await queue.add(task)

# Остановка
await queue.stop()
```

---

## 📊 Мониторинг

### Prometheus метрики

RedisTaskQueue экспортирует те же метрики что и локальная очередь:

| Метрика | Описание |
|---------|----------|
| `agent_queue_size` | Размер очереди |
| `agent_queue_active_tasks` | Активные задачи (по агентам) |
| `agent_tasks_total` | Всего задач (по статусам) |
| `agent_task_duration` | Длительность выполнения (по агент/метод) |
| `agent_queue_pending_by_priority` | Ожидающие задачи (по приоритетам) |

### Проверка состояния

```bash
# Подключение к Redis CLI
docker-compose exec redis redis-cli

# Просмотр ключей очереди
KEYS agent_queue:*

# Размер очереди
ZCARD agent_queue:queue

# Статистика
HGETALL agent_queue:stats

# История (последние 5 задач)
LRANGE agent_queue:history 0 4
```

---

## 🛠️ Конфигурация Redis

### Production настройки

Для production рекомендуется настроить Redis:

```conf
# /etc/redis/redis.conf

# Persistence (AOF)
appendonly yes
appendfsync everysec

# Max memory
maxmemory 2gb
maxmemory-policy allkeys-lru

# Persistence (RDB)
save 900 1
save 300 10
save 60 10000

# Bind to specific interface
bind 127.0.0.1

# Require password
requirepassword your-strong-password
```

### Docker Compose production

```yaml
redis:
  image: redis:7-alpine
  command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
  volumes:
    - redis_data:/data
    - ./redis.conf:/etc/redis/redis.conf:ro
  networks:
    - news-network
  deploy:
    resources:
      limits:
        memory: 2G
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
# С Redis (должен быть запущен)
export REDIS_URL=redis://localhost:6379
pytest tests/test_core/test_redis_queue.py -v

# С покрытием
pytest tests/test_core/test_redis_queue.py -v --cov=services/core/redis_queue
```

### Тестовый docker-compose

```yaml
# docker-compose.test.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 1s
      timeout: 3s
      retries: 5

  app:
    build: .
    command: pytest tests/test_core/test_redis_queue.py -v
    environment:
      - REDIS_URL=redis://redis:6379
    depends_on:
      redis:
        condition: service_healthy
```

---

## 🔐 Безопасность

### Рекомендации

1. **Пароль на Redis**
   ```bash
   # .env
   REDIS_URL=redis://:your-password@localhost:6379
   ```

2. **Изоляция сети**
   ```yaml
   networks:
     - news-network  # Внутренняя сеть
   
   redis:
     networks:
       - news-network  # Нет доступа извне
   ```

3. **TLS для production**
   - Используйте stunnel или HAProxy для TLS
   - Или Redis Enterprise с TLS поддержкой

---

## ⚠️ Troubleshooting

### Ошибка подключения

```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**Решение:**
1. Проверьте что Redis запущен: `docker-compose ps redis`
2. Проверьте логи: `docker-compose logs redis`
3. Проверьте сеть: `docker-compose exec redis redis-cli ping`

### Задачи не выполняются

**Причины:**
1. Воркеры не запущены — вызовите `await queue.start(num_workers=2)`
2. Метод не зарегистрирован — вызовите `queue.register_method(...)`
3. Ошибка в методе — проверьте логи воркеров

### Переполнение памяти Redis

**Решение:**
1. Настройте `maxmemory` и `maxmemory-policy`
2. Уменьшите TTL задач (по умолчанию 1 час)
3. Очищайте историю: `await queue.clear()`

---

## 📈 Масштабирование

### Горизонтальное масштабирование воркеров

```python
# Запуск 10 воркеров на одном сервере
await queue.start(num_workers=10)

# Или несколько серверов с одним Redis
# Server 1
await queue.start(num_workers=4)

# Server 2
await queue.start(num_workers=4)

# Server 3
await queue.start(num_workers=4)
```

Все воркеры будут получать задачи из общей очереди Redis.

### Шардинг Redis

Для очень высоких нагрузок используйте шардинг:

```python
# Redis Cluster
queue1 = RedisTaskQueue(redis_url='redis://node1:6379', prefix='queue_shard_1')
queue2 = RedisTaskQueue(redis_url='redis://node2:6379', prefix='queue_shard_2')

# Распределение по агентам
if agent_name in ['Categorizer', 'Analyst']:
    queue = queue1
else:
    queue = queue2
```

---

## 📚 Дополнительные ресурсы

- [Redis Documentation](https://redis.io/docs/)
- [Redis Sorted Sets](https://redis.io/docs/data-types/sorted-sets/)
- [Redis Pub/Sub](https://redis.io/docs/manual/pubsub/)
- [Redis Persistence](https://redis.io/docs/manual/persistence/)

---

**Автор:** AI-агент Стефания  
**Дата:** 2026-08-10  
**Версия:** 1.0.0
