# 🤖 AI Agent Microservice

**Дата:** 2026-08-10  
**Версия:** 1.0.0  
**Статус:** ✅ Завершено

---

## 📋 Обзор

AI Agent Microservice — отдельный микросервис для AI-агентов, предоставляющий HTTP API для категоризации, анализа и генерации новостей.

**Преимущества:**
- **Независимое масштабирование** — можно масштабировать агентов отдельно от основного приложения
- **Изоляция отказов** — проблемы с агентами не влияют на основное приложение
- **Гибкое развёртывание** — можно деплоить отдельно
- **Fallback** — автоматическое переключение на локальные агенты при недоступности сервиса

---

## ✅ Выполненные задачи

### 1. Структура микросервиса

```
microservices/ai-agent-service/
├── app/
│   └── main.py           # FastAPI приложение
├── Dockerfile            # Docker образ
├── requirements.txt      # Зависимости
└── README.md            # Документация
```

### 2. HTTP API

**Endpoints:**

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/health` | GET | Health check |
| `/ready` | GET | Readiness check |
| `/api/v1/categorize` | POST | Категоризация новости |
| `/api/v1/analyze` | POST | Анализ новости |
| `/api/v1/generate-news` | POST | Генерация новости |
| `/api/v1/create-context` | POST | Создание контекста |
| `/metrics` | GET | Prometheus метрики |

### 3. AI Agent Client

**Файл:** `services/ai_agent/remote_client.py`

**Возможности:**
- Автоматическое подключение к микросервису
- Retry logic при ошибках
- Fallback на локальные агенты
- Health monitoring

### 4. Docker Compose интеграция

Микросервис добавлен в `docker-compose.yml`:
- Порт: 8002
- Health check
- Зависимость от Ollama

---

## 🚀 Быстрый старт

### Запуск микросервиса

```bash
# 1. Запустить все сервисы
docker-compose up -d ai-agent-service

# 2. Проверить статус
docker-compose ps ai-agent-service

# 3. Проверить health
curl http://localhost:8002/health
# {"status":"healthy","model":"qwen2.5:7b","llm_provider":"ollama"}
```

### Использование в коде

```python
from services.ai_agent.remote_client import init_ai_agent_client, get_ai_agent_client

# Инициализация
await init_ai_agent_client()

# Получение клиента
client = get_ai_agent_client()

# Категоризация
result = await client.categorize(
    text="Президент провёл встречу",
    channel_title="Новости",
)

# Анализ
analysis = await client.analyze(
    text=result['text'],
    category=result['category'],
    urgency=result['urgency'],
)

# Генерация новости
news = await client.generate_news([{'text': '...', 'source': '...'}])

# Создание контекста
context = await client.create_context([...], news)

# Остановка
from services.ai_agent.remote_client import shutdown_ai_agent_client
await shutdown_ai_agent_client()
```

---

## 📊 API Reference

### Categorize

**POST** `/api/v1/categorize`

**Request:**
```json
{
  "text": "Текст новости",
  "channel_title": "Название канала",
  "channel_desc": "Описание канала"
}
```

**Response:**
```json
{
  "text": "Очищенный текст",
  "category": "Политика",
  "urgency": 4
}
```

### Analyze

**POST** `/api/v1/analyze`

**Request:**
```json
{
  "text": "Текст новости",
  "category": "Политика",
  "urgency": 4
}
```

**Response:**
```json
{
  "tags": ["президент", "встреча"],
  "confidence": 0.95,
  "facts": ["Президент провёл встречу"]
}
```

### Generate News

**POST** `/api/v1/generate-news`

**Request:**
```json
{
  "contexts": [
    {
      "text": "Текст события",
      "source": "Канал",
      "timestamp": "2026-08-10T10:00:00"
    }
  ]
}
```

**Response:**
```json
{
  "news_text": "Сгенерированный текст новости...",
  "category": "Политика",
  "tags": ["президент"]
}
```

### Create Context

**POST** `/api/v1/create-context`

**Request:**
```json
{
  "contexts": [...],
  "news_text": "Текст новости"
}
```

**Response:**
```json
{
  "context": {
    "structured_data": {...}
  }
}
```

---

## 🔧 Конфигурация

### Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `OLLAMA_HOST` | `http://ollama:11434` | URL Ollama сервера |
| `AGENT_MODEL` | `qwen2.5:7b` | Модель для агентов |
| `LOG_LEVEL` | `INFO` | Уровень логирования |

### AI Agent Client настройки

```python
from services.ai_agent.remote_client import AIAgentRemoteClient

client = AIAgentRemoteClient(
    base_url="http://ai-agent-service:8002",  # URL сервиса
    timeout=30.0,                              # Таймаут запросов
    max_retries=3,                             # Максимум попыток
    use_remote=True,                           # Использовать remote
)
```

---

## 📈 Масштабирование

### Горизонтальное масштабирование

```yaml
# docker-compose.override.yml
ai-agent-service:
  deploy:
    replicas: 3
    resources:
      limits:
        cpus: '2.0'
        memory: 4G
```

### Load Balancing

```python
# Round-robin между инстансами
AI_AGENT_SERVICE_URLS=[
    "http://ai-agent-1:8002",
    "http://ai-agent-2:8002",
    "http://ai-agent-3:8002",
]
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Установить переменную окружения
export AI_AGENT_SERVICE_URL=http://localhost:8002

# Запустить тесты
pytest tests/test_microservice/ -v
```

### Интеграционные тесты

```bash
# Запустить микросервис
docker-compose up -d ai-agent-service

# Запустить тесты
pytest tests/test_microservice/test_remote_client.py -v
```

---

## 🔍 Мониторинг

### Health Check

```bash
# Проверка работоспособности
curl http://localhost:8002/health

# Проверка готовности
curl http://localhost:8002/ready
```

### Prometheus Metrics

```bash
# Получить метрики
curl http://localhost:8002/metrics
```

**Метрики:**
- `http_requests_total` — всего запросов
- `http_request_duration_seconds` — длительность запросов
- `ai_agent_calls_total` — вызовы агентов
- `ai_agent_fallback_total` — fallback события

---

## ⚠️ Troubleshooting

### Микросервис не запускается

**Проверка:**
```bash
# Проверить логи
docker-compose logs ai-agent-service

# Проверить health
curl http://localhost:8002/health
```

**Решение:**
1. Убедитесь что Ollama запущен: `docker-compose ps ollama`
2. Проверьте что модель загружена: `docker-compose exec ollama ollama list`

### Client не подключается

**Проверка:**
```python
from services.ai_agent.remote_client import get_ai_agent_client

client = get_ai_agent_client()
print(f"Healthy: {client.is_healthy}")
```

**Решение:**
1. Проверьте URL: `echo $AI_AGENT_SERVICE_URL`
2. Проверите сеть: `docker-compose exec app curl http://ai-agent-service:8002/health`

### Fallback не работает

**Причина:** Локальные агенты не инициализированы

**Решение:**
```python
# Проверить что агенты доступны
from services.ai_agent.agents.categorizer import CategorizerAgent
agent = CategorizerAgent()
```

---

## 📚 Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                    Основное приложение                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  AIAgentRemoteClient                                    │   │
│  │  ┌─────────────────────────────────────────────────┐   │   │
│  │  │  Remote Mode: HTTP к микросервису               │   │   │
│  │  │  Fallback Mode: Локальные агенты                │   │   │
│  │  └─────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP (port 8002)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              AI Agent Microservice                               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ Categorizer │ │   Analyst   │ │   Editor    │ │ Archivist │ │
│  │   Agent     │ │   Agent     │ │   Agent     │ │   Agent   │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│                              │                                  │
│                              ▼                                  │
│                     ┌─────────────┐                            │
│                     │   Ollama    │                            │
│                     │  (qwen2.5)  │                            │
│                     └─────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Сравнение: Монолит vs Микросервис

| Характеристика | Монолит | Микросервис |
|----------------|---------|-------------|
| **Масштабирование** | Вертикальное | Горизонтальное |
| **Отказоустойчивость** | Общая | Изолированная |
| **Развёртывание** | Вместе с приложением | Отдельно |
| **Ресурсы** | Общие | Выделенные |
| **Fallback** | Нет | Автоматический |

---

## 📚 Дополнительные ресурсы

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Microservices Architecture](https://martinfowler.com/articles/microservices.html)

---

## 📊 Статистика реализации

| Метрика | Значение |
|---------|----------|
| **Endpoints** | 7 |
| **Тестов** | 20+ |
| **Документация** | 1 файл |
| **Docker образ** | 1 |

---

**Автор:** AI-агент Стефания  
**Дата завершения:** 2026-08-10  
**Статус:** ✅ Завершено (Задача #10 из implementation_report.md)
