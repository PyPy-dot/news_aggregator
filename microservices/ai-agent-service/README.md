# AI Agent Service

Сервис для работы с AI агентами (LLM через Ollama).

## Архитектура

```
ai-agent-service/
├── src/
│   ├── __init__.py
│   ├── main.py              # Точка входа
│   ├── agents/              # AI агенты
│   │   ├── base.py
│   │   ├── categorizer.py
│   │   ├── analyst.py
│   │   ├── editor.py
│   │   └── archivist.py
│   ├── queue.py             # Очередь задач
│   ├── cache.py             # Кэш LLM ответов
│   └── api.py               # REST/gRPC API
├── tests/
├── configs/
│   ├── dev.yaml
│   └── prod.yaml
├── Dockerfile
├── requirements.txt
└── README.md
```

## API

### REST Endpoints

#### POST /v1/categorize
Классификация новости:
```json
{
  "text": "Текст новости",
  "category": "politics"
}
```

#### POST /v1/analyze
Анализ новости (категория + confidence + тэги):
```json
{
  "text": "Текст новости"
}
```

#### POST /v1/generate
Генерация новости:
```json
{
  "posts": [...],
  "context": {...}
}
```

#### POST /v1/archive
Архивирование события:
```json
{
  "news": {...},
  "context": {...}
}
```

### gRPC Service

```protobuf
service AIAgentService {
  rpc Categorize(CategorizeRequest) returns (CategorizeResponse);
  rpc Analyze(AnalyzeRequest) returns (AnalyzeResponse);
  rpc Generate(GenerateRequest) returns (GenerateResponse);
  rpc Archive(ArchiveRequest) returns (ArchiveResponse);
}
```

## Конфигурация

```yaml
server:
  host: 0.0.0.0
  port: 8001

ollama:
  base_url: http://localhost:11434
  model: qwen2.5:7b

cache:
  max_size: 1000
  ttl_seconds: 86400

queue:
  max_size: 100
  workers: 4
```

## Запуск

### Development
```bash
python src/main.py --config configs/dev.yaml
```

### Docker
```bash
docker build -t news-aggregator/ai-agent-service:latest .
docker run -p 8001:8001 news-aggregator/ai-agent-service:latest
```

## Метрики

- `ai_agent_tasks_total` — всего задач
- `ai_agent_task_duration_seconds` — время выполнения
- `ai_cache_hits_total` — попадания кэша
- `ai_cache_misses_total` — промахи кэша

---

**Версия:** 1.0.0  
**Статус:** 🚧 В разработке
