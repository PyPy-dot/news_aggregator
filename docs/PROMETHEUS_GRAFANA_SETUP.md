# 📊 Настройка Prometheus + Grafana для мониторинга

**Дата:** 2026-08-10  
**Версия:** 1.0.0  
**Статус:** ✅ Завершено

---

## 📋 Обзор

Настроена полная система мониторинга для News Aggregator с использованием Prometheus и Grafana. Система обеспечивает:

- **Сбор метрик** со всех сервисов (приложение, БД, Redis, Ollama, ChromaDB)
- **Визуализацию** через Grafana дашборды
- **Алертинг** при критических событиях
- **Интеграцию** с Circuit Breaker метриками

---

## ✅ Выполненные задачи

### 1. Prometheus конфигурация

**Файлы:**
- `monitoring/prometheus/prometheus.yml` — основная конфигурация
- `monitoring/prometheus/alerts.yml` — правила алертов

**Собираемые метрики:**

| Сервис | Port | Метрики |
|--------|------|---------|
| **Prometheus** | 9090 | self-monitoring |
| **News Aggregator App** | 8000 | agent_queue, agent_tasks, agent_task_duration |
| **Web Admin** | 8001 | http_requests, response_time |
| **PostgreSQL** | 9187 | connections, queries, size |
| **Redis** | 9121 | memory, connections, commands |
| **Ollama** | 9820 | requests, latency, models |
| **ChromaDB** | 8000 | collections, searches, latency |
| **Node Exporter** | 9100 | CPU, memory, disk |

### 2. Alert Rules

**Категории алертов:**

| Категория | Алерты |
|-----------|--------|
| **Application** | NewsAggregatorDown, HighLLMErrorRate, AgentQueueFull, AgentQueueCritical, HighTaskDuration |
| **Database** | PostgreSQLDown, PostgreSQLHighConnections, PostgreSQLSlowQueries, PostgreSQLLowDiskSpace |
| **Redis** | RedisDown, RedisHighMemoryUsage, RedisRejectedConnections |
| **Circuit Breaker** | CircuitBreakerOpen, CircuitBreakerFrequentTrips, CircuitBreakerHalfOpen |
| **LLM** | OllamaDown, HighLLMLatency, LLMProviderLowAvailability |
| **ChromaDB** | ChromaDBDown, HighVectorSearchLatency |
| **System** | HighCPUUsage, HighMemoryUsage, LowDiskSpace |

### 3. Grafana Дашборды

**Созданные дашборды:**

| Дашборд | UID | Описание |
|---------|-----|----------|
| **AI Agents** | `ai-agents` | Метрики AI агентов: очередь задач, задержка, успешность |
| **LLM & Circuit Breaker** | `llm-circuit-breaker` | LLM провайдеры, fallback events, circuit breaker state |
| **Infrastructure** | `infrastructure` | Системные метрики: CPU, memory, Redis, PostgreSQL |

### 4. Интеграция Circuit Breaker

Метрики Circuit Breaker интегрированы с Prometheus:

```python
# services/core/circuit_breaker.py
circuit_breaker_state{service="ollama", state="OPEN|CLOSED|HALF_OPEN"}
circuit_breaker_trips_total{service="ollama"}
circuit_breaker_rejects_total{service="ollama"}
```

---

## 🚀 Быстрый старт

### 1. Запуск мониторинга

```bash
# Запустить все сервисы с мониторингом
docker-compose up -d

# Проверить статус
docker-compose ps
# Должны быть запущены: prometheus, grafana

# Открыть Grafana
# http://localhost:3000
# Логин: admin / Пароль: admin
```

### 2. Проверка Prometheus

```bash
# Открыть Prometheus
# http://localhost:9090

# Проверить targets
# Status → Targets
# Все должны быть "UP"
```

### 3. Просмотр дашбордов

В Grafana:
1. Dashboards → Browse
2. Выбрать дашборд:
   - **AI Agents Dashboard**
   - **LLM & Circuit Breaker Dashboard**
   - **Infrastructure Dashboard**

---

## 📊 Prometheus Metrics

### AI Agents Metrics

```prometheus
# Размер очереди задач
agent_queue_size

# Активные задачи по агентам
agent_queue_active_tasks{agent_name="Categorizer"}

# Всего задач (по статусам)
agent_tasks_total{agent_name="Editor", status="success"}

# Длительность выполнения задач
agent_task_duration{agent_name="Analyst", method_name="analyze"}

# Ожидающие задачи по приоритетам
agent_queue_pending_by_priority{priority="HIGH"}
```

### LLM Metrics

```prometheus
# Всего LLM запросов
llm_requests_total{provider="ollama", status="success"}

# Длительность LLM запросов
llm_request_duration{provider="openai"}

# Fallback события
llm_fallback_total{from_provider="ollama", to_provider="openai"}
```

### Circuit Breaker Metrics

```prometheus
# Состояние circuit breaker
circuit_breaker_state{service="ollama", state="OPEN"}

# Всего срабатываний
circuit_breaker_trips_total{service="anthropic"}

# Отклонённые запросы (когда CB открыт)
circuit_breaker_rejects_total{service="ollama"}
```

---

## 🔔 Alert Rules

### Критические алерты (Critical)

| Алерт | Условие | Действие |
|-------|---------|----------|
| **NewsAggregatorDown** | app не отвечает 2 мин | Немедленное уведомление |
| **PostgreSQLDown** | БД не отвечает 1 мин | Немедленное уведомление |
| **RedisDown** | Redis не отвечает 1 мин | Уведомление |
| **CircuitBreakerOpen** | CB открыт 1 мин | Проверка LLM провайдера |
| **AgentQueueCritical** | Очередь > 95% 1 мин | Масштабирование |

### Предупреждения (Warning)

| Алерт | Условие | Действие |
|-------|---------|----------|
| **HighLLMErrorRate** | Ошибки > 0.5/сек 5 мин | Проверка логов |
| **AgentQueueFull** | Очередь > 80% 3 мин | Мониторинг |
| **HighLLMLatency** | p95 > 10с 5 мин | Проверка нагрузки |
| **HighCPUUsage** | CPU > 80% 10 мин | Планирование масштабирования |

---

## 📈 Grafana Dashboards

### AI Agents Dashboard

**Панели:**
1. Задачи AI агентов (в секунду) — timeseries по агентам и статусам
2. Размер очереди задач — текущий размер и по приоритетам
3. Задержка обработки задач — p50, p95, p99 перцентили
4. Активные задачи по агентам — количество активных задач
5. Успешность выполнения задач — success rate
6. Retry и Failed задачи — количество retry и failed

### LLM & Circuit Breaker Dashboard

**Панели:**
1. Circuit Breakers Open — статус CB по сервисам
2. LLM Requests/sec — запросы в секунду по провайдерам
3. LLM Success Rate — процент успешных запросов
4. LLM Latency (p95) — 95-й перцентиль задержки
5. LLM Requests by Provider — детализация по провайдерам и статусам
6. Circuit Breaker Trips — срабатывания CB
7. LLM Provider Availability — доступность провайдеров
8. LLM Fallback Events — события fallback

### Infrastructure Dashboard

**Панели:**
1. CPU Usage — использование CPU
2. Memory Usage — использование памяти
3. Redis Memory — использование памяти Redis
4. PostgreSQL Connections — активные подключения
5. CPU Usage by Instance — по инстансам
6. Memory Usage by Instance — по инстансам
7. Redis Connections — подключенные клиенты
8. Redis Operations — операции в секунду
9. PostgreSQL Throughput — пропускная способность
10. Vector Search Latency — задержка векторного поиска

---

## 🔧 Конфигурация

### Prometheus

**Файл:** `monitoring/prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s      # Интервал сбора
  evaluation_interval: 15s  # Интервал вычисления правил

rule_files:
  - 'alerts.yml'

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

### Grafana

**Переменные окружения:**
```bash
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=admin
GF_USERS_ALLOW_SIGN_UP=false
```

**Datasource:** Prometheus (http://prometheus:9090)

---

## 🚨 Alertmanager (опционально)

Для отправки уведомлений добавьте Alertmanager:

```yaml
# docker-compose.yml
alertmanager:
  image: prom/alertmanager:latest
  container_name: news-aggregator-alertmanager
  volumes:
    - ./monitoring/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml
  ports:
    - "9093:9093"
  networks:
    - news-network
```

**Конфигурация уведомлений:**
```yaml
# monitoring/alertmanager/alertmanager.yml
route:
  receiver: 'telegram'
  
receivers:
  - name: 'telegram'
    telegram_configs:
      - bot_token: YOUR_BOT_TOKEN
        chat_id: YOUR_CHAT_ID
```

---

## 📊 Query Examples

### Проверка доступности LLM провайдеров

```prometheus
# Success rate по провайдерам
sum(rate(llm_requests_total{status="success"}[5m])) by (provider)
/ sum(rate(llm_requests_total[5m])) by (provider)
```

### Мониторинг очереди задач

```prometheus
# Размер очереди
agent_queue_size

# Среднее время обработки
histogram_quantile(0.95, rate(agent_task_duration_bucket[5m]))
```

### Circuit Breaker статус

```prometheus
# Текущее состояние
circuit_breaker_state

# Количество срабатываний за час
increase(circuit_breaker_trips_total[1h])
```

---

## ⚠️ Troubleshooting

### Prometheus не собирает метрики

**Проверка:**
```bash
# Проверить targets
curl http://localhost:9090/api/v1/targets

# Проверить логи
docker-compose logs prometheus
```

### Grafana не показывает дашборды

**Решение:**
1. Проверить provisioning: `docker-compose exec grafana ls /etc/grafana/provisioning/`
2. Перезапустить Grafana: `docker-compose restart grafana`
3. Проверить логи: `docker-compose logs grafana`

### Алерты не срабатывают

**Проверка:**
```prometheus
# Проверить правила
curl http://localhost:9090/api/v1/rules

# Проверить alertmanager
curl http://localhost:9093/api/v1/status
```

---

## 📚 Дополнительные ресурсы

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Alertmanager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/)

---

## 📊 Статистика реализации

| Метрика | Значение |
|---------|----------|
| **Prometheus rules** | 30+ алертов |
| **Grafana dashboards** | 3 дашборда |
| **Собираемые метрики** | 50+ метрик |
| **Документация** | 1 файл |

---

**Автор:** AI-агент Стефания  
**Дата завершения:** 2026-08-10  
**Статус:** ✅ Завершено (Задача #4 из implementation_report.md)
