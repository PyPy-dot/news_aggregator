"""
ChromaDB Vector Store — хранение и поиск векторов.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from services.logging_config import get_logger

logger = get_logger(__name__)

# Типы коллекций
COLLECTION_EVENTS = 'events'
COLLECTION_NEWS = 'news'
COLLECTION_POSTS = 'posts'


class ChromaVectorStore:
    """
    Векторное хранилище на базе ChromaDB.

    Поддерживает:
    - Постоянное хранение (persist_directory)
    - Несколько коллекций (events, news, posts)
    - Поиск по косинусному сходству
    - Фильтрацию по метаданным

    Attributes:
        persist_directory: Путь к директории для постоянного хранения
    """

    def __init__(
        self,
        persist_directory: Optional[Path] = None,
    ) -> None:
        """
        Инициализация ChromaDB хранилища.

        Args:
            persist_directory: Директория для хранения (по умолчанию: ./vector_store)
        """
        if persist_directory is None:
            persist_directory = Path(__file__).parent.parent.parent / 'vector_store'

        self.persist_directory = persist_directory
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        logger.info(f"📁 ChromaDB хранилище: {self.persist_directory}")

        # Инициализация клиента с постоянным хранением
        self._client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=False,
            ),
        )

        # Кэш коллекций
        self._collections: dict[str, chromadb.Collection] = {}

        logger.info("✅ ChromaDB клиент инициализирован")

    def get_collection(self, name: str) -> chromadb.Collection:
        """
        Получает или создаёт коллекцию.

        Args:
            name: Имя коллекции (events, news, posts)

        Returns:
            ChromaDB коллекция
        """
        if name not in self._collections:
            # Получаем или создаём коллекцию
            # distance_function=cosine по умолчанию для нормализованных векторов
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={'hnsw:space': 'cosine'},
            )
            logger.debug(f"📦 Коллекция '{name}' инициализирована")

        return self._collections[name]

    def add(
        self,
        collection_name: str,
        id: str,
        text: str,
        embedding: list[float],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Добавляет вектор в коллекцию.

        Args:
            collection_name: Имя коллекции
            id: Уникальный идентификатор
            text: Исходный текст (для референса)
            embedding: Векторный эмбеддинг
            metadata: Дополнительные метаданные
        """
        collection = self.get_collection(collection_name)

        # Подготавливаем метаданные
        full_metadata = metadata or {}
        full_metadata['text'] = text  # Сохраняем текст для референса

        collection.upsert(
            ids=[id],
            embeddings=[embedding],
            metadatas=[full_metadata],
        )

        logger.debug(f"➕ Добавлен вектор ID={id} в коллекцию '{collection_name}'")

    def add_batch(
        self,
        collection_name: str,
        items: list[dict[str, Any]],
    ) -> None:
        """
        Добавляет пакет векторов в коллекцию.

        Args:
            collection_name: Имя коллекции
            items: Список dict с полями {id, text, embedding, metadata}
        """
        collection = self.get_collection(collection_name)

        ids = [item['id'] for item in items]
        embeddings = [item['embedding'] for item in items]
        metadatas = [
            {**(item.get('metadata') or {}), 'text': item['text']}
            for item in items
        ]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info(
            f"✅ Добавлено {len(items)} векторов в коллекцию '{collection_name}'"
        )

    def search(
        self,
        collection_name: str,
        query_embedding: list[float],
        limit: int = 5,
        filter_metadata: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Поиск похожих векторов.

        Args:
            collection_name: Имя коллекции
            query_embedding: Вектор запроса
            limit: Количество результатов
            filter_metadata: Фильтр по метаданным (например, {'category': 'politics'})

        Returns:
            Список результатов с полями {id, text, metadata, distance, score}
        """
        collection = self.get_collection(collection_name)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=filter_metadata,
            include=['metadatas', 'distances'],
        )

        # Форматируем результаты с защитой от отсутствующих ключей
        formatted = []
        if results['ids'] and results['ids'][0]:
            for i, id in enumerate(results['ids'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                distance = results['distances'][0][i] if results['distances'] else 0

                formatted.append({
                    'id': id,
                    'text': metadata.get('text', ''),
                    'metadata': metadata,
                    'distance': distance,
                    'score': 1 - distance,  # Косинусное сходство (distance ∈ [0, 1])
                })

        logger.debug(
            f"🔍 Найдено {len(formatted)} результатов в '{collection_name}'"
        )

        return formatted

    def delete(self, collection_name: str, id: str) -> None:
        """
        Удаляет вектор из коллекции.

        Args:
            collection_name: Имя коллекции
            id: Идентификатор для удаления
        """
        collection = self.get_collection(collection_name)
        collection.delete(ids=[id])
        logger.debug(f"🗑️ Удалён вектор ID={id} из '{collection_name}'")

    def count(self, collection_name: str) -> int:
        """
        Возвращает количество векторов в коллекции.

        Args:
            collection_name: Имя коллекции

        Returns:
            Количество векторов
        """
        collection = self.get_collection(collection_name)
        return collection.count()

    def reset(self) -> None:
        """Очищает все коллекции (для тестов)."""
        self._collections.clear()
        # ChromaDB не поддерживает reset для PersistentClient без пересоздания
        logger.warning("⚠️ Сброс хранилища требует пересоздания клиента")
