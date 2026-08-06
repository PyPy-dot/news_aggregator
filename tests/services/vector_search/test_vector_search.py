"""
Тесты для векторного поиска.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from services.vector_search.embeddings import EmbeddingService
from services.vector_search.chroma_client import ChromaVectorStore, COLLECTION_EVENTS
from services.vector_search.search_engine import VectorSearchEngine


class TestEmbeddingService:
    """Тесты для EmbeddingService."""

    def test_singleton_pattern(self):
        """Проверка паттерна Singleton."""
        service1 = EmbeddingService()
        service2 = EmbeddingService()
        assert service1 is service2

    def test_embed_returns_list(self):
        """Проверка, что embed возвращает список float."""
        # Мокаем модель
        with patch('services.vector_search.embeddings.SentenceTransformer') as mock_model_class:
            mock_model = MagicMock()
            mock_model.encode.return_value = [0.1, 0.2, 0.3, 0.4]
            mock_model.get_sentence_embedding_dimension.return_value = 4
            mock_model_class.return_value = mock_model

            service = EmbeddingService()
            embedding = service.embed("test text")

            assert isinstance(embedding, list)
            assert len(embedding) == 4
            assert all(isinstance(x, float) for x in embedding)

    def test_embed_batch_returns_list_of_lists(self):
        """Проверка, что embed_batch возвращает список списков."""
        with patch('services.vector_search.embeddings.SentenceTransformer') as mock_model_class:
            mock_model = MagicMock()
            mock_model.encode.return_value = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
            mock_model.get_sentence_embedding_dimension.return_value = 2
            mock_model_class.return_value = mock_model

            service = EmbeddingService()
            embeddings = service.embed_batch(["text1", "text2", "text3"])

            assert isinstance(embeddings, list)
            assert len(embeddings) == 3
            assert all(isinstance(emb, list) for emb in embeddings)


class TestChromaVectorStore:
    """Тесты для ChromaVectorStore."""

    def test_get_collection_creates_if_not_exists(self):
        """Проверка создания коллекции."""
        with patch('services.vector_search.chroma_client.chromadb') as mock_chroma:
            mock_collection = Mock()
            mock_client = Mock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_chroma.PersistentClient.return_value = mock_client

            store = ChromaVectorStore(persist_directory=None)
            collection = store.get_collection('test_collection')

            mock_client.get_or_create_collection.assert_called_once()
            assert collection is mock_collection

    def test_add_calls_upsert(self):
        """Проверка добавления вектора."""
        with patch('services.vector_search.chroma_client.chromadb') as mock_chroma:
            mock_collection = Mock()
            mock_client = Mock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_chroma.PersistentClient.return_value = mock_client

            store = ChromaVectorStore(persist_directory=None)
            store.add(
                collection_name='test',
                id='id1',
                text='test text',
                embedding=[0.1, 0.2, 0.3],
                metadata={'key': 'value'},
            )

            mock_collection.upsert.assert_called_once()
            call_args = mock_collection.upsert.call_args
            assert call_args[1]['ids'] == ['id1']
            assert call_args[1]['embeddings'] == [[0.1, 0.2, 0.3]]

    def test_search_returns_formatted_results(self):
        """Проверка поиска векторов."""
        with patch('services.vector_search.chroma_client.chromadb') as mock_chroma:
            mock_collection = Mock()
            mock_collection.query.return_value = {
                'ids': [['id1', 'id2']],
                'metadatas': [[{'text': 'text1'}, {'text': 'text2'}]],
                'distances': [[0.3, 0.5]],
            }
            mock_client = Mock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_chroma.PersistentClient.return_value = mock_client

            store = ChromaVectorStore(persist_directory=None)
            results = store.search(
                collection_name='test',
                query_embedding=[0.1, 0.2, 0.3],
                limit=2,
            )

            assert len(results) == 2
            assert results[0]['id'] == 'id1'
            assert results[0]['score'] == 0.7  # 1 - 0.3


class TestVectorSearchEngine:
    """Тесты для VectorSearchEngine."""

    def test_initialization(self):
        """Проверка инициализации."""
        with patch('services.vector_search.search_engine.EmbeddingService'):
            with patch('services.vector_search.search_engine.ChromaVectorStore'):
                engine = VectorSearchEngine()

                assert engine.embeddings is not None
                assert engine.vector_store is not None

    def test_get_stats(self):
        """Проверка получения статистики."""
        with patch('services.vector_search.search_engine.EmbeddingService'):
            with patch('services.vector_search.search_engine.ChromaVectorStore') as mock_store_class:
                mock_store = Mock()
                mock_store.count.side_effect = [10, 5, 20]  # events, news, posts
                mock_store_class.return_value = mock_store

                engine = VectorSearchEngine()
                stats = engine.get_stats()

                assert stats == {
                    'events': 10,
                    'news': 5,
                    'posts': 20,
                }
