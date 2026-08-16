# 🏥 Health Check — Мониторинг здоровья системы

**Версия:** 2.0  
**Дата:** 2026-08-16

---

## 📋 Обзор

Health Check система предоставляет API для проверки состояния всех компонентов приложения:

- ✅ База данных (SQLite/PostgreSQL)
- ✅ LLM провайдеры (Ollama, OpenAI, Anthropic)
- ✅ Telegram бот (Admin Bot)
- ✅ Векторный поиск (ChromaDB)
- ✅ Circuit breaker'ы
- ✅ Listener Bot (Telethon)
- ✅ Планировщик задач
- ✅ Очередь категоризации

---

## 🏗️ Архитектура

### Компоненты

```
┌─────────────────────────────────────────────────────────────┐
│                    Health Check API                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  /health         — краткий статус                   │   │
│  │  /health/full    — полная проверка                  │   │
│  │  /health/{name}  — проверка компонента              │   │
│  │  /health/live    — liveness probe (k8s)             │   │
│  │  /health/ready   — readiness probe (k8s)            │   │
│  │  /health/metrics — Prometheus метрики               │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌───────────────┐
│ HealthChecker │   │ Component Checks│   │  FastAPI      │
│ (менеджер)    │   │ (БД, LLM, Bot)  │   │  Router       │
└───────────────┘   └─────────────────┘   └───────────────┘
```

### Статусы здоровья

| Статус | Описание |
|--------|----------|
| **HEALTHY** | Компонент работает нормально |
| **DEGRADED** | Компонент работает с проблемами |
| **UNHEALTHY** | Компонент недоступен |
| **UNKNOWN** | Статус неизвестен (таймаут, ошибка проверки) |

### Уровни важности

| Уровень | Описание | Примеры |
|---------|----------|---------|
| **CRITICAL** | Критичный компонент | БД, Telegram бот |
| **HIGH** | Важный компонент | LLM провайдеры, векторный поиск |
| **MEDIUM** | Средней важности | Circuit breaker'ы, планировщик |
| **LOW** | Низкой важности | Вспомогательные сервисы |

---

## ⚙️ Настройка

### Подключение роутера

```python
from fastapi import FastAPI
from services.web_admin.health_router import router as health_router

app = FastAPI(title="News Aggregator Admin API")

# Подключаем health check роутер
app.include_router(health_router, prefix="/api")
```

### Настройка проверок

```python
from services.monitoring.health_check import (
    HealthChecker,
    create_default_health_checker,
    check_database_health,
    check_custom_service,
)
from services.database.enums import SeverityLevel

# Создание checker'а
checker = create_default_health_checker()

# Добавление своей проверки
async def check_my_service():
    from services.monitoring.health_check import ComponentHealth, HealthStatus, SeverityLevel
    
    # Логика проверки
    is_healthy = True  # Ваша логика
    
    return ComponentHealth(
        name="my_service",
        status=HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY,
        severity=SeverityLevel.HIGH,
        message="Service is running",
        latency_ms=50.0,
    )

checker.add_check("my_service", check_my_service, SeverityLevel.HIGH)
```

---

## 📡 API Endpoints

### GET /api/health

Краткий статус системы для load balancer и быстрого мониторинга.

**Ответ:**
```json
{
  "status": "healthy",
  "healthy_components": 9,
  "total_components": 10,
  "critical_issues": 0,
  "critical_issue_names": []
}
```

**Коды ответов:**
- `200 OK` — система работает
- `503 Service Unavailable` — критичные проблемы

---

### GET /api/health/full

Полная проверка всех компонентов с деталями.

**Ответ:**
```json
{
  "status": "healthy",
  "version": "3.5.0",
  "checked_at": "2026-08-10T12:00:00Z",
  "summary": {
    "total_components": 10,
    "healthy": 9,
    "unhealthy": 1,
    "critical_issues": 0
  },
  "components": [
    {
      "name": "database",
      "status": "healthy",
      "severity": "critical",
      "message": "БД подключена (sqlite)",
      "latency_ms": 5.23,
      "details": {
        "db_type": "sqlite",
        "pool_size": 1
      },
      "checked_at": "2026-08-10T12:00:00Z"
    },
    {
      "name": "ollama",
      "status": "unhealthy",
      "severity": "high",
      "message": "Ollama недоступен",
      "latency_ms": 0.5,
      "details": {
        "error": "Connection refused"
      },
      "checked_at": "2026-08-10T12:00:00Z"
    }
  ]
}
```

**Параметры:**
- `timeout` (query, float): Максимальное время проверки (сек, по умолчанию 10.0)

---

### GET /api/health/{component_name}

Проверка конкретного компонента.

**Пример:**
```bash
curl http://localhost:8000/api/health/database
```

**Ответ:**
```json
{
  "name": "database",
  "status": "healthy",
  "severity": "critical",
  "message": "БД подключена (sqlite)",
  "latency_ms": 4.15,
  "details": {
    "db_type": "sqlite",
    "pool_size": 1
  },
  "checked_at": "2026-08-10T12:00:00Z"
}
```

**Доступные компоненты:**
- `database`
- `telegram_bot`
- `llm_fallback`
- `ollama`
- `vector_search`
- `circuit_breakers`
- `scheduler`
- `listener`
- `categorization_queue`

---

### GET /api/health/live

Liveness probe для Kubernetes.

**Ответ:**
```json
{
  "status": "ok",
  "timestamp": 1691668800.123
}
```

---

### GET /api/health/ready

Readiness probe для Kubernetes. Проверяет критичные зависимости.

**Ответ (готов):**
```json
{
  "status": "ok",
  "healthy_components": 9,
  "total_components": 10,
  "critical_issues": 0
}
```

**Ответ (не готов):**
```json
{
  "status": "not_ready",
  "critical_issues": ["database", "telegram_bot"]
}
```

**Коды ответов:**
- `200 OK` — приложение готово
- `503 Service Unavailable` — критичные зависимости недоступны

---

### GET /api/health/metrics

Метрики в формате Prometheus.

**Ответ:**
```prometheus
# HELP news_aggregator_health_component_status Статус компонента (1=healthy, 0=unhealthy)
# TYPE news_aggregator_health_component_status gauge
news_aggregator_health_component_status{component="database",severity="critical"} 1
news_aggregator_health_component_status{component="ollama",severity="high"} 0
news_aggregator_health_component_status{component="telegram_bot",severity="critical"} 1

# HELP news_aggregator_health_latency_ms Latency проверки компонента (мс)
# TYPE news_aggregator_health_latency_ms gauge
news_aggregator_health_latency_ms{component="database"} 5.23
news_aggregator_health_latency_ms{component="ollama"} 0.50

# HELP news_aggregator_health_info Информация о системе
# TYPE news_aggregator_health_info gauge
news_aggregator_health_info{version="3.5.0"} 1
```

---

## 🛠️ Использование

### Python SDK

```python
from services.monitoring.health_check import (
    check_system_health,
    get_health_summary,
    check_database_health,
    check_ollama_health,
)

# Быстрая проверка
summary = await get_health_summary()
print(f"Status: {summary['status']}")

# Полная проверка
health = await check_system_health(timeout=10.0)
print(f"Healthy: {health.healthy_components}/{len(health.components)}")

# Проверка конкретного компонента
db_health = await check_database_health()
print(f"Database: {db_health.status}")
```

### Проверка состояния через API

```bash
# Краткий статус
curl http://localhost:8000/api/health

# Полная проверка
curl http://localhost:8000/api/health/full | jq

# Проверка компонента
curl http://localhost:8000/api/health/database | jq

# Prometheus метрики
curl http://localhost:8000/api/health/metrics
```

---

## 📊 Kubernetes интеграция

### Deployment с health checks

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: news-aggregator
spec:
  template:
    spec:
      containers:
      - name: app
        image: news-aggregator:3.5.0
        ports:
        - containerPort: 8000
        livenessProbe:
          httpGet:
            path: /api/health/live
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /api/health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
```

### Ingress с health check

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: news-aggregator
  annotations:
    nginx.ingress.kubernetes.io/healthcheck-path: /api/health
spec:
  rules:
  - host: news.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: news-aggregator
            port:
              number: 8000
```

---

## 📈 Prometheus + Grafana

### Scraping config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'news-aggregator'
    static_configs:
      - targets: ['news-aggregator:8000']
    metrics_path: /api/health/metrics
    scrape_interval: 30s
```

### Grafana дашборд (пример запросов)

```promql
# Количество здоровых компонентов
news_aggregator_health_component_status == 1

# Latency по компонентам
histogram_quantile(0.95, rate(news_aggregator_health_latency_ms_bucket[5m]))

# Alert: компонент недоступен
alert: ComponentDown
expr: news_aggregator_health_component_status == 0
for: 2m
labels:
  severity: warning
annotations:
  summary: "Компонент {{ $labels.component }} недоступен"
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты health check
pytest tests/test_monitoring/test_health_check.py -v

# С покрытием
pytest tests/test_monitoring/test_health_check.py -v --cov=services/monitoring/health_check
```

### Тестовые сценарии

| Тест | Описание |
|------|----------|
| `test_component_health_creation` | Создание ComponentHealth |
| `test_system_health_properties` | Свойства SystemHealth |
| `test_add_and_check_component` | Добавление и проверка компонента |
| `test_check_all_components` | Проверка всех компонентов |
| `test_check_all_timeout` | Таймаут при проверке |
| `test_check_exception_handling` | Обработка исключений |
| `test_get_summary` | Получение сводки |

---

## 🚨 Troubleshooting

### Проблема: Health check показывает UNKNOWN

**Возможные причины:**
1. Таймаут проверки
2. Ошибка при импорте зависимостей

**Решение:**
```bash
# Увеличить таймаут
curl http://localhost:8000/api/health/full?timeout=30.0

# Проверить логи
docker-compose logs app | grep health
```

### Проблема: Readiness probe не проходит

**Возможные причины:**
1. БД недоступна
2. Telegram бот не инициализирован

**Решение:**
```bash
# Проверить критичные компоненты
curl http://localhost:8000/api/health/database
curl http://localhost:8000/api/health/telegram_bot

# Проверить переменные окружения
docker-compose exec app env | grep DATABASE
docker-compose exec app env | grep BOT_TOKEN
```

---

## 📝 Changelog

### v1.0 (2026-08-10)
- ✅ HealthChecker с проверками компонентов
- ✅ FastAPI роутер с 6 endpoints
- ✅ Встроенные проверки (БД, LLM, бот, векторный поиск, circuit breaker'ы, планировщик)
- ✅ Prometheus метрики
- ✅ Kubernetes liveness/readiness probes
- ✅ Тесты (24 сценария)
- ✅ Документация

---

**Автор:** AI-агент Стефания  
**Связанные документы:**
- [CIRCUIT_BREAKER_SETUP.md](CIRCUIT_BREAKER_SETUP.md) — Circuit breaker
- [LLM_FALLBACK_SETUP.md](LLM_FALLBACK_SETUP.md) — Fallback LLM провайдеры
- [DOCKER_SETUP.md](DOCKER_SETUP.md) — Docker развёртывание
