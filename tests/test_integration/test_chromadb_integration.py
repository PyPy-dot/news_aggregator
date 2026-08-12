"""
Интеграционные тесты для ChromaDB.

Проверяют:
- Подключение к ChromaDB серверу
- Создание коллекций
- Добавление и поиск векторов
- Фильтрацию по метаданным
- Персистентность данных

Требования:
- Запущенный ChromaDB сервер (localhost:8000 или в Docker)
"""

import os
import pytest
import asyncio
from typing import List

# Пропускаем тесты если CHROMA_HOST не настроен
pytestmark = pytest.mark.skipif(
    not os.environ.get('CHROMA_HOST'),
    reason="Требуется ChromaDB (CHROMA_HOST в окружении)"
)

from services.vector_search.embeddings import EmbeddingService
from services.vector_search.chroma_client import ChromaVectorStore
from services.vector_search.search_engine import VectorSearchEngine


@pytest.fixture
def chroma_host():
    """Получить ChromaDB host из окружения."""
    return os.environ.get('CHROMA_HOST', 'http://localhost:8000')


@pytest.fixture
def collection_name():
    """Имя тестовой коллекции."""
    return 'test_collection_' + str(os.getpid())  # Уникальное имя для каждого процесса


@pytest.fixture
async def embedding_service():
    """Создать сервис эмбеддингов."""
    service = EmbeddingService(model='sentence-transformers/all-MiniLM-L6-v2')
    yield service
    # Очистка
    await service.close()


@pytest.fixture
async def chroma_client(chroma_host):
    """Создать ChromaDB клиента."""
    client = ChromaVectorStore(chroma_host=chroma_host)
    yield client
    # Очистка после теста
    await client.disconnect()


@pytest.fixture
async def vector_engine(chroma_host):
    """Создать векторный поисковый движок."""
    engine = VectorSearchEngine(chroma_host=chroma_host)
    yield engine
    # Очистка
    await engine.close()


class TestChromaDBConnection:
    """Тесты подключения к ChromaDB."""

    @pytest.mark.asyncio
    async def test_connection_success(self, chroma_client):
        """Тест успешного подключения."""
        assert chroma_client._client is not None

    @pytest.mark.asyncio
    async def test_heartbeat(self, chroma_client):
        """Тест heartbeat."""
        heartbeat = await chroma_client._client.heartbeat()
        assert heartbeat is not None
        assert isinstance(heartbeat, int)


class TestChromaDBCollections:
    """Тесты коллекций ChromaDB."""

    @pytest.mark.asyncio
    async def test_create_collection(self, chroma_client, collection_name):
        """Тест создания коллекции."""
        collection = await chroma_client.create_collection(collection_name)

        assert collection is not None
        assert collection.name == collection_name

    @pytest.mark.asyncio
    async def test_get_collection(self, chroma_client, collection_name):
        """Тест получения коллекции."""
        # Создаём
        await chroma_client.create_collection(collection_name)

        # Получаем
        collection = await chroma_client.get_collection(collection_name)

        assert collection is not None
        assert collection.name == collection_name

    @pytest.mark.asyncio
    async def test_get_or_create_collection(self, chroma_client, collection_name):
        """Тест получения или создания коллекции."""
        # Получаем или создаём
        collection1 = await chroma_client.get_or_create_collection(collection_name)

        # Получаем снова
        collection2 = await chroma_client.get_or_create_collection(collection_name)

        assert collection1.name == collection2.name

    @pytest.mark.asyncio
    async def test_delete_collection(self, chroma_client, collection_name):
        """Тест удаления коллекции."""
        # Создаём
        await chroma_client.create_collection(collection_name)

        # Удаляем
        await chroma_client.delete_collection(collection_name)

        # Проверяем что удалена
        collections = await chroma_client.list_collections()
        assert collection_name not in collections

    @pytest.mark.asyncio
    async def test_list_collections(self, chroma_client, collection_name):
        """Тест списка коллекций."""
        # Создаём несколько коллекций
        await chroma_client.create_collection(f'{collection_name}_1')
        await chroma_client.create_collection(f'{collection_name}_2')

        collections = await chroma_client.list_collections()

        assert len(collections) >= 2
        assert f'{collection_name}_1' in collections
        assert f'{collection_name}_2' in collections

        # Очищаем
        await chroma_client.delete_collection(f'{collection_name}_1')
        await chroma_client.delete_collection(f'{collection_name}_2')


class TestChromaDBVectors:
    """Тесты векторных операций."""

    @pytest.mark.asyncio
    async def test_add_vectors(self, chroma_client, collection_name, embedding_service):
        """Тест добавления векторов."""
        # Создаём коллекцию
        await chroma_client.create_collection(collection_name)

        # Генерируем эмбеддинги
        texts = ['Текст 1', 'Текст 2', 'Текст 3']
        embeddings = await embedding_service.embed_documents(texts)

        # Добавляем
        ids = ['doc1', 'doc2', 'doc3']
        await chroma_client.add_documents(
            collection_name=collection_name,
            ids=ids,
            embeddings=embeddings,
            documents=texts,
        )

        # Проверяем количество
        collection = await chroma_client._client.get_collection(collection_name)
        count = await collection.count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_search_vectors(self, chroma_client, collection_name, embedding_service):
        """Тест поиска векторов."""
        # Создаём коллекцию с данными
        await chroma_client.create_collection(collection_name)

        texts = [
            'Москва — столица России',
            'Санкт-Петербург — культурная столица',
            'Казань — столица Татарстана',
        ]
        embeddings = await embedding_service.embed_documents(texts)
        ids = ['msk', 'spb', 'kzn']

        await chroma_client.add_documents(
            collection_name=collection_name,
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=[{'city': 'Москва'}, {'city': 'Санкт-Петербург'}, {'city': 'Казань'}],
        )

        # Ищем
        query_embedding = await embedding_service.embed_query('столица России')
        results = await chroma_client.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            k=2,
        )

        assert len(results) == 2
        # Первый результат должен быть про Москву
        assert 'Москва' in results[0].document or 'России' in results[0].document

    @pytest.mark.asyncio
    async def test_search_with_filter(self, chroma_client, collection_name, embedding_service):
        """Тест поиска с фильтрацией."""
        # Создаём коллекцию
        await chroma_client.create_collection(collection_name)

        texts = [
            'Политические новости',
            'Спортивные новости',
            'Политический анализ',
            'Спортивный обзор',
        ]
        embeddings = await embedding_service.embed_documents(texts)
        ids = ['pol1', 'spo1', 'pol2', 'spo2']
        metadatas = [
            {'category': 'politics'},
            {'category': 'sports'},
            {'category': 'politics'},
            {'category': 'sports'},
        ]

        await chroma_client.add_documents(
            collection_name=collection_name,
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        # Ищем с фильтром
        query_embedding = await embedding_service.embed_query('новости')
        results = await chroma_client.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            k=2,
            where={'category': 'politics'},
        )

        # Должны быть только политические новости
        assert len(results) <= 2
        for result in results:
            assert result.metadata.get('category') == 'politics'

    @pytest.mark.asyncio
    async def test_update_document(self, chroma_client, collection_name, embedding_service):
        """Тест обновления документа."""
        # Создаём коллекцию
        await chroma_client.create_collection(collection_name)

        # Добавляем
        text = 'Старый текст'
        embedding = await embedding_service.embed_documents([text])
        await chroma_client.add_documents(
            collection_name=collection_name,
            ids=['doc1'],
            embeddings=embedding,
            documents=[text],
        )

        # Обновляем
        new_text = 'Новый текст'
        new_embedding = await embedding_service.embed_documents([new_text])
        await chroma_client.update_documents(
            collection_name=collection_name,
            ids=['doc1'],
            embeddings=new_embedding,
            documents=[new_text],
        )

        # Ищем и проверяем
        query_embedding = await embedding_service.embed_query('Новый текст')
        results = await chroma_client.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            k=1,
        )

        assert 'Новый' in results[0].document

    @pytest.mark.asyncio
    async def test_delete_document(self, chroma_client, collection_name, embedding_service):
        """Тест удаления документа."""
        # Создаём коллекцию
        await chroma_client.create_collection(collection_name)

        # Добавляем
        texts = ['Текст 1', 'Текст 2']
        embeddings = await embedding_service.embed_documents(texts)
        await chroma_client.add_documents(
            collection_name=collection_name,
            ids=['doc1', 'doc2'],
            embeddings=embeddings,
            documents=texts,
        )

        # Удаляем
        await chroma_client.delete_documents(collection_name=collection_name, ids=['doc1'])

        # Проверяем
        collection = await chroma_client._client.get_collection(collection_name)
        count = await collection.count()
        assert count == 1


class TestVectorSearchEngine:
    """Тесты поискового движка."""

    @pytest.mark.asyncio
    async def test_create_and_search(self, vector_engine, collection_name):
        """Тест создания и поиска."""
        # Создаём коллекцию
        await vector_engine.create_collection(collection_name)

        # Добавляем документы
        documents = [
            {'id': '1', 'text': 'Москва столица России', 'metadata': {'city': 'Москва'}},
            {'id': '2', 'text': 'Санкт-Петербург культурная столица', 'metadata': {'city': 'СПб'}},
        ]
        await vector_engine.add_documents(collection_name, documents)

        # Ищем
        results = await vector_engine.search_similar(
            collection_name=collection_name,
            query='столица России',
            k=1,
        )

        assert len(results) == 1
        assert results[0]['score'] > 0

    @pytest.mark.asyncio
    async def test_batch_add(self, vector_engine, collection_name):
        """Тест пакетного добавления."""
        await vector_engine.create_collection(collection_name)

        # Добавляем батчами
        batch1 = [
            {'id': str(i), 'text': f'Текст {i}', 'metadata': {'index': i}}
            for i in range(10)
        ]
        batch2 = [
            {'id': str(i), 'text': f'Текст {i}', 'metadata': {'index': i}}
            for i in range(10, 20)
        ]

        await vector_engine.add_documents(collection_name, batch1)
        await vector_engine.add_documents(collection_name, batch2)

        # Проверяем
        results = await vector_engine.search_similar(
            collection_name=collection_name,
            query='Текст',
            k=25,
        )

        assert len(results) == 20


class TestEmbeddingService:
    """Тесты сервиса эмбеддингов."""

    @pytest.mark.asyncio
    async def test_embed_query(self, embedding_service):
        """Тест эмбеддинга запроса."""
        embedding = await embedding_service.embed_query('Тестовый запрос')

        assert embedding is not None
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        # Стандартный размер эмбеддинга MiniLM
        assert len(embedding) == 384

    @pytest.mark.asyncio
    async def test_embed_documents(self, embedding_service):
        """Тест эмбеддинга документов."""
        texts = ['Текст 1', 'Текст 2', 'Текст 3']
        embeddings = await embedding_service.embed_documents(texts)

        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == 384

    @pytest.mark.asyncio
    async def test_embed_empty(self, embedding_service):
        """Тест пустого документа."""
        embedding = await embedding_service.embed_query('')

        assert embedding is not None
        assert len(embedding) == 384


class TestChromaDBPersistence:
    """Тесты персистентности ChromaDB."""

    @pytest.mark.asyncio
    async def test_data_persistence(self, chroma_host, collection_name, embedding_service):
        """Тест сохранения данных между подключениями."""
        # Создаём клиента и добавляем данные
        client1 = ChromaVectorStore(chroma_host=chroma_host)
        await client1.create_collection(collection_name)

        texts = ['Персистентный текст']
        embeddings = await embedding_service.embed_documents(texts)
        await client1.add_documents(
            collection_name=collection_name,
            ids=['persist1'],
            embeddings=embeddings,
            documents=texts,
        )
        await client1.disconnect()

        # Создаём нового клиента и проверяем
        client2 = ChromaVectorStore(chroma_host=chroma_host)
        collection = await client2.get_collection(collection_name)

        assert collection is not None

        # Ищем данные
        query_embedding = await embedding_service.embed_query('персистентный')
        results = await client2.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            k=1,
        )

        assert len(results) == 1
        assert 'Персистентный' in results[0].document

        await client2.disconnect()
        # Очищаем
        client3 = ChromaVectorStore(chroma_host=chroma_host)
        await client3.delete_collection(collection_name)
        await client3.disconnect()


class TestChromaDBPerformance:
    """Тесты производительности."""

    @pytest.mark.asyncio
    async def test_search_latency(self, chroma_client, collection_name, embedding_service):
        """Тест задержки поиска."""
        # Создаём коллекцию с данными
        await chroma_client.create_collection(collection_name)

        texts = [f'Текст номер {i}' for i in range(100)]
        embeddings = await embedding_service.embed_documents(texts)
        ids = [f'doc{i}' for i in range(100)]

        await chroma_client.add_documents(
            collection_name=collection_name,
            ids=ids,
            embeddings=embeddings,
            documents=texts,
        )

        # Ищем
        import time
        query_embedding = await embedding_service.embed_query('Текст 50')

        start = time.time()
        results = await chroma_client.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            k=5,
        )
        elapsed = time.time() - start

        # Поиск должен быть быстрым (< 1 секунды)
        assert elapsed < 1.0, f"Поиск занял слишком долго: {elapsed:.2f}с"
        assert len(results) == 5
