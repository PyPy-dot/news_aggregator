# Vector Search Service

Сервис для векторного поиска (ChromaDB + эмбеддинги).

## Архитектура

```
vector-search-service/
├── src/
│   ├── __init__.py
│   ├── main.py              # Точка входа
│   ├── embeddings.py        # Embedding сервис
│   ├── chroma_client.py     # ChromaDB клиент
│   ├── search_engine.py     # Поисковый движок
│   ├── auto_reindex.py      # Автопереиндексация
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

#### POST /v1/search/events
Поиск похожих событий:
```json
{
  "text": "Текст для поиска",
  "category": "politics",
  "limit": 5,
  "min_score": 0.7
}
```

#### POST /v1/search/posts
Поиск похожих постов:
```json
{
  "text": "Текст для поиска",
  "category": "politics",
  "limit": 10,
  "min_score": 0.6
}
```

#### POST /v1/index/event
Добавить событие в индекс:
```json
{
  "event_id": 123,
  "post_id": 456,
  "context_data": {...},
  "event_category": "politics",
  "tags": ["tag1", "tag2"]
}
```

#### POST /v1/reindex
Принудительная переиндексация:
```json
{
  "full": true
}
```

### gRPC Service

```protobuf
service VectorSearchService {
  rpc SearchEvents(SearchEventsRequest) returns (SearchEventsResponse);
  rpc SearchPosts(SearchPostsRequest) returns (SearchPostsResponse);
  rpc IndexEvent(IndexEventRequest) returns (IndexEventResponse);
  rpc Reindex(ReindexRequest) returns (ReindexResponse);
}
```

## Конфигурация

```yaml
server:
  host: 0.0.0.0
  port: 8002

chromadb:
  path: ./chroma_db
  # или для production:
  # host: chromadb-cluster
  # port: 8000

embedding:
  model: paraphrase-multilingual-MiniLM-L12-v2
  cache_size: 5000

reindex:
  auto_enabled: true
  batch_size: 50
```

## Запуск

### Development
```bash
python src/main.py --config configs/dev.yaml
```

### Docker
```bash
docker build -t news-aggregator/vector-search-service:latest .
docker run -p 8002:8002 -v ./chroma_db:/app/chroma_db news-aggregator/vector-search-service:latest
```

## Метрики

- `vector_search_queries_total` — всего запросов
- `vector_search_duration_seconds` — время поиска
- `vector_index_size` — размер индекса
- `embedding_cache_hit_rate` — hit rate кэша

---

**Версия:** 1.0.0  
**Статус:** 🚧 В разработке
