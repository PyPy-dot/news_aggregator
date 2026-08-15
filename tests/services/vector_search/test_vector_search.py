"""
Тесты для векторного поиска.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from services.vector_search.embeddings import EmbeddingService
from services.vector_search.chroma_client import ChromaVectorStore
from services.vector_search.search_engine import VectorSearchEngine, LRUCache


class TestEmbeddingService:
    """Тесты для EmbeddingService."""

    def test_singleton_pattern(self):
        """Проверка паттерна Singleton."""
        service1 = EmbeddingService()
        service2 = EmbeddingService()
        assert service1 is service2

    @pytest.mark.asyncio
    async def test_embed_returns_list(self):
        """Проверка, что embed возвращает список float."""
        import numpy as np
        # Мокаем модель
        with patch('services.vector_search.embeddings.SentenceTransformer') as mock_model_class:
            mock_model = MagicMock()
            # Возвращаем numpy array с реалистичным размером (384 для paraphrase-multilingual-MiniLM-L12-v2)
            mock_embedding = np.random.rand(384).astype(np.float32)
            mock_model.encode.return_value = mock_embedding
            mock_model.get_sentence_embedding_dimension.return_value = 384
            mock_model_class.return_value = mock_model

            service = EmbeddingService()
            embedding = await service.embed("test text")

            assert isinstance(embedding, list)
            assert len(embedding) == 384
            assert all(isinstance(x, float) for x in embedding)

    def test_embed_batch_returns_list_of_lists(self):
        """Проверка, что embed_batch возвращает список списков."""
        import numpy as np
        # Сбрасываем singleton для чистоты теста
        EmbeddingService._instance = None
        EmbeddingService._model = None

        with patch('services.vector_search.embeddings.SentenceTransformer') as mock_model_class:
            mock_model = MagicMock()
            # Возвращаем 2D numpy array как в реальности
            mock_model.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
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


class TestLRUCache:
    """Тесты для LRU кэша."""

    def test_init(self):
        """Проверка инициализации."""
        cache = LRUCache(capacity=10)
        assert cache.capacity == 10

    def test_put_and_get(self):
        """Проверка добавления и получения."""
        cache = LRUCache(capacity=5)
        cache.put('key1', 'value1')
        assert cache.get('key1') == 'value1'

    def test_get_missing_key(self):
        """Проверка получения отсутствующего ключа."""
        cache = LRUCache(capacity=5)
        assert cache.get('nonexistent') is None

    def test_capacity_limit(self):
        """Проверка ограничения размера."""
        cache = LRUCache(capacity=3)
        cache.put('key1', 'value1')
        cache.put('key2', 'value2')
        cache.put('key3', 'value3')
        cache.put('key4', 'value4')  # Должно вытолкнуть key1

        assert cache.get('key1') is None  # Вытолкнут
        assert cache.get('key2') == 'value2'
        assert cache.get('key3') == 'value3'
        assert cache.get('key4') == 'value4'

    def test_lru_eviction(self):
        """Проверка LRU вытеснения."""
        cache = LRUCache(capacity=3)
        cache.put('key1', 'value1')
        cache.put('key2', 'value2')
        cache.put('key3', 'value3')

        # Обращаемся к key1, чтобы сделать его свежим
        cache.get('key1')

        # Добавляем новый ключ
        cache.put('key4', 'value4')

        # key2 должен быть вытолкнут (самый старый)
        assert cache.get('key1') == 'value1'
        assert cache.get('key2') is None
        assert cache.get('key3') == 'value3'
        assert cache.get('key4') == 'value4'

    def test_clear(self):
        """Проверка очистки."""
        cache = LRUCache(capacity=5)
        cache.put('key1', 'value1')
        cache.put('key2', 'value2')
        cache.clear()
        assert cache.get('key1') is None
        assert cache.get('key2') is None


class TestVectorSearchEngine:
    """Тесты для VectorSearchEngine."""

    def test_initialization(self):
        """Проверка инициализации."""
        with patch('services.vector_search.search_engine.EmbeddingService'):
            with patch('services.vector_search.search_engine.ChromaVectorStore'):
                engine = VectorSearchEngine()

                assert engine.embeddings is not None
                assert engine.vector_store is not None
                assert engine._search_cache is not None

    def test_initialization_with_cache_size(self):
        """Проверка инициализации с размером кэша."""
        with patch('services.vector_search.search_engine.EmbeddingService'):
            with patch('services.vector_search.search_engine.ChromaVectorStore'):
                engine = VectorSearchEngine(cache_size=100)
                assert engine._search_cache.capacity == 100

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

    def test_get_cache_stats(self):
        """Проверка получения статистики кэша."""
        with patch('services.vector_search.search_engine.EmbeddingService'):
            with patch('services.vector_search.search_engine.ChromaVectorStore'):
                engine = VectorSearchEngine(cache_size=100)
                stats = engine.get_cache_stats()

                assert stats['capacity'] == 100
                assert stats['size'] == 0

    def test_clear_cache(self):
        """Проверка очистки кэша."""
        with patch('services.vector_search.search_engine.EmbeddingService'):
            with patch('services.vector_search.search_engine.ChromaVectorStore'):
                engine = VectorSearchEngine()
                engine._search_cache.put('key1', 'value1')
                engine.clear_cache()
                assert engine._search_cache.get('key1') is None
