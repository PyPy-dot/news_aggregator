"""
Vector Search Service — поиск похожих событий и новостей.

Использует sentence-transformers для эмбеддингов и ChromaDB для хранения.
"""

from services.vector_search.embeddings import EmbeddingService
from services.vector_search.chroma_client import ChromaVectorStore
from services.vector_search.search_engine import VectorSearchEngine

__all__ = [
    'EmbeddingService',
    'ChromaVectorStore',
    'VectorSearchEngine',
]
