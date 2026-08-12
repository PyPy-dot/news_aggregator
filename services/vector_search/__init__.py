"""
Vector Search Service — поиск похожих событий и новостей.

Использует sentence-transformers для эмбеддингов и ChromaDB с HNSW индексами для хранения.

Оптимизация HNSW:
- Автоматическая настройка параметров (M, construction_ef, search_ef)
- Оценка потребления памяти
- Рекомендации для разных размеров базы
"""

from services.vector_search.embeddings import EmbeddingService
from services.vector_search.chroma_client import ChromaVectorStore
from services.vector_search.search_engine import VectorSearchEngine
from services.vector_search.service import VectorSearchService
from services.vector_search.auto_reindex import (
    AutoReindexService,
    EmbeddingCache,
    ReindexStats,
    get_auto_reindex_service,
    start_auto_reindex,
    stop_auto_reindex,
)
from services.vector_search.hnsw_config import (
    HNSWConfig,
    get_hnsw_config,
    estimate_memory_usage,
    get_recommended_batch_size,
)

__all__ = [
    'EmbeddingService',
    'ChromaVectorStore',
    'VectorSearchEngine',
    'VectorSearchService',
    'AutoReindexService',
    'EmbeddingCache',
    'ReindexStats',
    'get_auto_reindex_service',
    'start_auto_reindex',
    'stop_auto_reindex',
    # HNSW конфигурация
    'HNSWConfig',
    'get_hnsw_config',
    'estimate_memory_usage',
    'get_recommended_batch_size',
]
