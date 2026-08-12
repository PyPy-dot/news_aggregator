# 🐍 Настройка Celery Worker для распределённой обработки задач

**Дата:** 2026-08-10  
**Версия:** 1.0.0

---

## 📋 Обзор

Celery Worker обеспечивает распределённую обработку задач с:
- **Redis как брокер** — надёжная очередь задач
- **Retry logic** — автоматические повторные попытки
- **Планирование** — Celery Beat для периодических задач
- **Мониторинг** — Flower для веб-интерфейса

---

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
pip install celery[redis] redis
```

### 2. Запуск воркера

```bash
# Базовый запуск (4 воркера)
celery -A services.core.celery_worker worker --loglevel=info --concurrency=4

# С логированием в файл
celery -A services.core.celery_worker worker --loglevel=info --concurrency=4 --logfile=logs/celery.log

# В фоне (daemon)
celery -A services.core.celery_worker multi start w1 -n worker1.%h --loglevel=info
```

### 3. Запуск планировщика (Beat)

```bash
# Celery Beat для периодических задач
celery -A services.core.celery_worker beat --loglevel=info
```

### 4. Мониторинг (Flower)

```bash
# Установка
pip install flower

# Запуск
celery -A services.core.celery_worker flower --port=5555
```

---

## 📦 Конфигурация

### Переменные окружения

```bash
# .env
REDIS_URL=redis://redis:6379

# Опционально
CELERY_CONCURRENCY=4
CELERY_LOG_LEVEL=INFO
CELERY_LOG_FILE=logs/celery.log
```

### Периодические задачи (Beat Schedule)

В `celery_worker.py` настроены:

| Задача | Расписание | Описание |
|--------|------------|----------|
| `process_events` | Каждые 48 часов | Обработка событий |
| `cleanup_cache` | Каждые 6 часов | Очистка кэша LLM |

---

## 📝 Использование

### Отправка задачи

```python
from services.core.celery_worker import process_categorization, process_analysis

# Асинхронная отправка
result = process_categorization.delay(
    text="Срочная новость...",
    channel_title="канал",
    channel_desc="описание"
)

# Получение результата (блокирует)
result.get(timeout=30)

# Или проверка статуса
if result.ready():
    print(result.get())
```

### Задача с callback

```python
from celery import chain, group

# Цепочка задач
workflow = chain(
    process_categorization.s(text, title, desc),
    process_analysis.s(),
)

result = workflow.apply_async()
```

### Отмена задачи

```python
from services.core.celery_worker import revoke_task

# Отозвать задачу
revoke_task(task_id, terminate=True)
```

---

## 📊 Мониторинг

### Flower (веб-интерфейс)

```bash
# Запуск
celery -A services.core.celery_worker flower --port=5555

# Открыть в браузере
# http://localhost:5555
```

**Возможности Flower:**
- Просмотр активных задач
- История выполненных задач
- Статистика по воркерам
- Отмена задач
- Конфигурация воркеров

### Celery events (events)

```bash
# Просмотр событий в реальном времени
celery -A services.core.celery_worker events

# Статус воркеров
celery -A services.core.celery_worker status
```

### Inspect API

```python
from services.core.celery_worker import inspect_workers

info = inspect_workers()
print(info['active'])  # Активные задачи
print(info['stats'])   # Статистика воркеров
```

---

## 🐳 Docker Compose

Celery worker уже интегрирован в docker-compose:

```yaml
# Добавить в docker-compose.yml
celery-worker:
  build:
    context: .
    dockerfile: Dockerfile
  container_name: news-aggregator-celery
  restart: unless-stopped
  command: celery -A services.core.celery_worker worker --loglevel=info --concurrency=4
  environment:
    - DATABASE_URL=postgresql+asyncpg://news:news_password@db:5432/news_aggregator
    - REDIS_URL=redis://redis:6379
    - OLLAMA_HOST=http://ollama:11434
    - CHROMA_HOST=http://chromadb:8000
  depends_on:
    - redis
    - db
  networks:
    - news-network
  volumes:
    - ./logs:/app/logs
```

---

## 🔧 Продвинутые возможности

### Rate Limiting

```python
# Ограничить 10 задачами в минуту
@celery_app.task(rate_limit='10/m')
def heavy_task():
    ...

# Применить к существующей задаче
celery_app.control.rate_limit('tasks.heavy_task', '10/m')
```

### Time Limits

```python
# Максимум 30 секунд на выполнение
@celery_app.task(time_limit=30)
def long_task():
    ...
```

### Priority Queue

```python
# Отправить с высоким приоритетом
task.apply_async(priority=9)  # 0-9, 9 = highest
```

### Expiry

```python
# Задача истекает через 1 минуту
task.apply_async(expires=60)
```

---

## ⚠️ Troubleshooting

### Задачи не выполняются

**Проверьте:**
1. Redis запущен: `redis-cli ping` → `PONG`
2. Воркер запущен: `celery -A services.core.celery_worker status`
3. Задача зарегистрирована: `celery -A services.core.celery_worker inspect registered`

### Ошибка подключения к Redis

```
redis.exceptions.ConnectionError
```

**Решение:**
- Проверьте `REDIS_URL` в окружении
- Убедитесь что Redis доступен из контейнера воркера

### Задачи теряются при перезапуске

**Решение:**
- Включите persistence: `task_acks_late=True`
- Используйте `result_backend` для сохранения результатов

---

## 📚 Дополнительные ресурсы

- [Celery Documentation](https://docs.celeryq.dev/)
- [Celery Best Practices](https://docs.celeryq.dev/en/stable/userguide/best-practices.html)
- [Flower Documentation](https://flower.readthedocs.io/)
- [Redis Documentation](https://redis.io/docs/)

---

**Автор:** AI-агент Стефания  
**Дата:** 2026-08-10  
**Версия:** 1.0.0
