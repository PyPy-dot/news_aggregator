# Микросервисная архитектура News Aggregator

**Дата:** 2026-08-09  
**Версия:** 1.0.0  
**Статус:** 🚧 В разработке (проект)

---

## Обзор

Документ описывает план выделения сервисов из монолитной архитектуры News Aggregator в микросервисы.

## Текущая архитектура (монолит)

```
┌─────────────────────────────────────────────────────────────┐
│                      main.py                                 │
│              Application (lifecycle management)              │
└─────────────────────────────────────────────────────────────┘
                              │
    ┌─────────────────────────┼─────────────────────────┐
    │                         │                         │
    ▼                         ▼                         ▼
┌───────────┐         ┌───────────────┐         ┌───────────┐
│ Admin Bot │         │ Listener Bot  │         │ Scheduler │
│ (aiogram) │         │  (Telethon)   │         │           │
└───────────┘         └───────────────┘         └───────────┘
                               │                    │
                               └──────────┬─────────┘
                                          ▼
                              ┌─────────────────────┐
                              │  NewsOrchestrator   │
                              │  (3 стратегии)      │
                              └─────────────────────┘
                                          │
              ┌───────────────────────────┼───────────────────────┐
              │                           │                       │
              ▼                           ▼                       ▼
    ┌─────────────────┐         ┌─────────────────┐     ┌─────────────────┐
    │   AI Agents     │         │  Vector Search  │     │  Notifications  │
    │   (Ollama)      │         │   (ChromaDB)    │     │  (Telegram API) │
    └─────────────────┘         └─────────────────┘     └─────────────────┘
           │                           │                       │
           └───────────────────────────┴───────────────────────┘
                                      │
                                      ▼
                              ┌─────────────────┐
                              │  Database       │
                              │  (SQLite/PG)    │
                              └─────────────────┘
```

**Проблемы монолита:**
- Сложность масштабирования отдельных компонентов
- Общий процесс отказа — падение всего приложения
- Сложность развёртывания и обновления
- Блокировка ресурсов (один сервис может замедлить все)

---

## Целевая архитектура (микросервисы)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         API Gateway                                  │
│                    (nginx / Kong / Traefik)                         │
└─────────────────────────────────────────────────────────────────────┘
                              │
    ┌─────────────────────────┼─────────────────────────┐
    │                         │                         │
    ▼                         ▼                         ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   AI Agent      │ │  Vector Search  │ │  Notification   │
│    Service      │ │     Service     │ │     Service     │
│   (port 8001)   │ │   (port 8002)   │ │   (port 8003)   │
│                 │ │                 │ │                 │
│ - Categorizer   │ │ - Embeddings    │ │ - Admin Notify  │
│ - Analyst       │ │ - ChromaDB      │ │ - Sub Notify    │
│ - Editor        │ │ - Auto Reindex  │ │ - Broadcast     │
│ - Archivist     │ │                 │ │                 │
│                 │ │                 │ │                 │
│ - LLM Cache     │ │ - Embed Cache   │ │ - Retry Logic   │
│ - Task Queue    │ │                 │ │ - Rate Limit    │
└─────────────────┘ └─────────────────┘ └─────────────────┘
         │                   │                   │
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │   Ollama LLM    │           │   ChromaDB      │
    │   (port 11434)  │           │   (port 8000)   │
    └─────────────────┘           └─────────────────┘
```

**Преимущества:**
- Независимое масштабирование каждого сервиса
- Изоляция сбоев (падение одного сервиса не влияет на другие)
- Гибкое развёртывание и обновление
- Возможность использования разных технологий

---

## Сервисы

### 1. AI Agent Service

**Порт:** 8001  
**Протоколы:** REST, gRPC

**Ответственность:**
- Классификация новостей (Categorizer)
- Анализ новостей (Analyst)
- Генерация новостей (Editor)
- Архивирование событий (Archivist)
- Кэширование LLM ответов

**Зависимости:**
- Ollama (LLM)
- Внутренний кэш (Redis/in-memory)

**API:**
- `POST /v1/categorize` — классификация
- `POST /v1/analyze` — анализ
- `POST /v1/generate` — генерация
- `POST /v1/archive` — архивирование

---

### 2. Vector Search Service

**Порт:** 8002  
**Протоколы:** REST, gRPC

**Ответственность:**
- Векторный поиск событий
- Векторный поиск постов
- Векторный поиск новостей
- Автопереиндексация
- Кэширование эмбеддингов

**Зависимости:**
- ChromaDB (векторное хранилище)
- Sentence Transformers (эмбеддинги)

**API:**
- `POST /v1/search/events` — поиск событий
- `POST /v1/search/posts` — поиск постов
- `POST /v1/index/event` — индексация события
- `POST /v1/reindex` — переиндексация

---

### 3. Notification Service

**Порт:** 8003  
**Протоколы:** REST, gRPC

**Ответственность:**
- Уведомления админам
- Уведомления подписчикам
- Рассылки
- Retry логика
- Rate limiting

**Зависимости:**
- Telegram Bot API

**API:**
- `POST /v1/notify/admin` — уведомление админа
- `POST /v1/notify/subscriber` — уведомление подписчика
- `POST /v1/broadcast` — рассылка

---

## Коммуникация

### REST API

Для синхронных запросов:
```bash
curl -X POST http://ai-agent-service:8001/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "..."}'
```

### gRPC

Для высокопроизводительной коммуникации:
```protobuf
service AIAgentService {
  rpc Analyze(AnalyzeRequest) returns (AnalyzeResponse);
}
```

### Message Queue (опционально)

Для асинхронной обработки:
- RabbitMQ / Kafka / Redis Streams
- События: `news.analyzed`, `news.generated`, `event.archived`

---

## Развёртывание

### Docker Compose (development)

```yaml
version: '3.8'
services:
  ai-agent-service:
    build: ./microservices/ai-agent-service
    ports:
      - "8001:8001"
    depends_on:
      - ollama
  
  vector-search-service:
    build: ./microservices/vector-search-service
    ports:
      - "8002:8002"
    depends_on:
      - chromadb
  
  notification-service:
    build: ./microservices/notification-service
    ports:
      - "8003:8003"
  
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
  
  chromadb:
    image: chromadb/chroma:latest
    ports:
      - "8000:8000"
```

### Kubernetes (production)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-agent-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ai-agent-service
  template:
    spec:
      containers:
      - name: ai-agent-service
        image: news-aggregator/ai-agent-service:latest
        ports:
        - containerPort: 8001
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

---

## Миграция с монолита

### Этап 1: Подготовка (неделя 1-2)

1. Создать базовую структуру микросервисов
2. Настроить CI/CD для каждого сервиса
3. Создать Dockerfile для каждого сервиса
4. Настроить мониторинг и логирование

### Этап 2: Выделение AI Agent Service (неделя 3-4)

1. Перенести код агентов в отдельный сервис
2. Создать REST/gRPC API
3. Настроить коммуникацию с монолитом
4. Протестировать интеграцию

### Этап 3: Выделение Vector Search Service (неделя 5-6)

1. Перенести код векторного поиска
2. Настроить ChromaDB как отдельный сервис
3. Мигрировать автопереиндексацию
4. Протестировать производительность

### Этап 4: Выделение Notification Service (неделя 7-8)

1. Перенести код уведомлений
2. Настроить retry логику
3. Настроить rate limiting
4. Протестировать надёжность

### Этап 5: Полная миграция (неделя 9-10)

1. Переключить весь трафик на микросервисы
2. Отключить монолитные компоненты
3. Финальное тестирование
4. Документирование

---

## Метрики и мониторинг

### Prometheus метрики

Каждый сервис экспортирует метрики на `/metrics`:

```
# AI Agent Service
ai_agent_tasks_total{status="success"}
ai_agent_task_duration_seconds
ai_cache_hits_total
ai_cache_misses_total

# Vector Search Service
vector_search_queries_total
vector_search_duration_seconds
vector_index_size
embedding_cache_hit_rate

# Notification Service
notifications_sent_total{type="admin"}
notifications_failed_total
notification_retry_count
notification_duration_seconds
```

### Grafana дашборды

- Общий дашборд системы
- Дашборд каждого сервиса
- Дашборд производительности
- Дашборд ошибок

---

## Безопасность

### Аутентификация между сервисами

- JWT токены для сервис-сервис коммуникации
- mTLS для gRPC соединений

### Секреты

- Kubernetes Secrets / HashiCorp Vault
- Никогда не хранить секреты в коде

### Rate Limiting

- Ограничение запросов между сервисами
- Защита от DDoS

---

## Roadmap

| Этап | Задача | Срок | Статус |
|------|--------|------|--------|
| 1 | Подготовка инфраструктуры | Неделя 1-2 | 🔴 |
| 2 | AI Agent Service | Неделя 3-4 | 🔴 |
| 3 | Vector Search Service | Неделя 5-6 | 🔴 |
| 4 | Notification Service | Неделя 7-8 | 🔴 |
| 5 | Полная миграция | Неделя 9-10 | 🔴 |

---

## Риски и mitigation

| Риск | Вероятность | Влияние | Mitigation |
|------|-------------|---------|------------|
| Сложность отладки | Средняя | Высокое | Централизованное логирование (ELK) |
| Сетевые задержки | Высокая | Среднее | gRPC, кэширование |
| Отказ сервиса | Средняя | Высокое | Circuit breaker, retry |
| Сложность развёртывания | Средняя | Среднее | Kubernetes, Helm charts |

---

**Исполнитель:** AI-агент Стефания  
**Дата:** 2026-08-09  
**Статус:** 🚧 Проект (требует обсуждения)
