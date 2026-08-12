"""
ChromaDB Vector Store — хранение и поиск векторов.

Оптимизация HNSW:
- Автоматическая настройка параметров на основе размера коллекции
- Поддержка различных метрик (cosine, l2, ip)
- Батчинг для эффективного добавления векторов
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Any

# Отключаем телеметрию ChromaDB ДО импорта chromadb
os.environ['ANONYMIZED_TELEMETRY'] = 'false'
os.environ['CHROMA_TELEMETRY_ENABLED'] = 'false'

import chromadb
from chromadb.config import Settings as ChromaSettings

from services.logging_config import get_logger

logger = get_logger(__name__)

# Отключаем логирование телеметрии на уровне logging
logging.getLogger('chromadb.telemetry').setLevel(logging.CRITICAL)
logging.getLogger('chromadb.telemetry.product').setLevel(logging.CRITICAL)
logging.getLogger('chromadb.telemetry.product.posthog').setLevel(logging.CRITICAL)

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
        # Телеметрия отключена через переменные окружения (в начале файла)
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
        Получает или создаёт коллекцию с оптимизированными параметрами HNSW.

        Args:
            name: Имя коллекции (events, news, posts)

        Returns:
            ChromaDB коллекция
        """
        if name not in self._collections:
            # Определяем оптимальные параметры HNSW на основе предполагаемого размера
            # Для разных типов коллекций разные ожидания по размеру
            size_estimates = {
                COLLECTION_EVENTS: 50_000,    # Средняя коллекция событий
                COLLECTION_NEWS: 10_000,      # Меньше сгенерированных новостей
                COLLECTION_POSTS: 100_000,    # Большая коллекция постов
            }
            estimated_size = size_estimates.get(name, 50_000)

            # Получаем оптимальную конфигурацию
            from services.vector_search.hnsw_config import get_hnsw_config
            config = get_hnsw_config(
                num_vectors=estimated_size,
                space='cosine',
                optimize_for='balance',
            )

            # Получаем или создаём коллекцию с параметрами HNSW
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata=config.to_metadata(),
            )
            logger.info(
                f"📦 Коллекция '{name}' инициализирована с HNSW: "
                f"M={config.M}, construction_ef={config.construction_ef}, "
                f"search_ef={config.search_ef}"
            )

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

        # Конвертируем простой фильтр в формат ChromaDB с операторами
        where_filter = None
        if filter_metadata:
            where_filter = {
                key: {'$eq': value} for key, value in filter_metadata.items()
            }

        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where_filter,
                include=['metadatas', 'distances'],
            )
            # Не логируем keys() — это может вызвать ошибку для именованных кортежей
            logger.debug(f"ChromaDB query результат тип: {type(results)}")
        except Exception as e:
            logger.error(f"Ошибка query к ChromaDB: {e}", exc_info=True)
            return []

        # Форматируем результаты с защитой от отсутствующих ключей
        formatted = []

        try:
            # Проверяем, что результаты не пустые
            # ChromaDB может возвращать dict или именованный кортеж
            if isinstance(results, dict):
                ids_list = results.get('ids')
                metadatas_list = results.get('metadatas', [{}])
                distances_list = results.get('distances', [{}])
            elif hasattr(results, 'ids'):
                # Именованный кортеж/объект (ChromaDB 0.5.x)
                ids_list = results.ids
                metadatas_list = results.metadatas if hasattr(results, 'metadatas') else [{}]
                distances_list = results.distances if hasattr(results, 'distances') else [{}]
            else:
                logger.warning(f"Неизвестный формат результатов ChromaDB: {type(results)}")
                return formatted

            # ids_list[0] может быть пустым списком
            if not ids_list or len(ids_list) == 0:
                logger.debug("ChromaDB вернул пустой ids_list")
                return formatted

            if not ids_list[0] or len(ids_list[0]) == 0:
                logger.debug("ChromaDB вернул пустой ids_list[0]")
                return formatted

            for i, id in enumerate(ids_list[0]):
                # Извлекаем metadata с защитой от разных форматов
                metadata_raw = None
                if metadatas_list and len(metadatas_list) > 0 and i < len(metadatas_list[0]):
                    metadata_raw = metadatas_list[0][i]

                # Конвертируем именованный кортеж/объект в dict если нужно
                if metadata_raw and hasattr(metadata_raw, '_asdict'):
                    metadata = metadata_raw._asdict()
                elif isinstance(metadata_raw, dict):
                    metadata = metadata_raw
                else:
                    metadata = {}

                # Извлекаем distance
                distance = 0
                if distances_list and len(distances_list) > 0 and i < len(distances_list[0]):
                    distance = distances_list[0][i]

                formatted.append({
                    'id': id,
                    'text': metadata.get('text', '') if metadata else '',
                    'metadata': metadata if metadata else {},
                    'distance': distance,
                    'score': 1 - distance,  # Косинусное сходство (distance ∈ [0, 1])
                })

            logger.debug(
                f"🔍 Найдено {len(formatted)} результатов в '{collection_name}'"
            )

        except Exception as e:
            logger.error(f"Ошибка форматирования результатов ChromaDB: {e}", exc_info=True)
            return []

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

    def get_hnsw_config(self, collection_name: str) -> Optional[dict[str, Any]]:
        """
        Получить текущую конфигурацию HNSW коллекции.

        Args:
            collection_name: Имя коллекции

        Returns:
            Dict с параметрами HNSW или None
        """
        collection = self.get_collection(collection_name)
        metadata = collection.metadata or {}

        if not any(k.startswith('hnsw:') for k in metadata.keys()):
            logger.warning(f"⚠️ Коллекция '{collection_name}' не имеет параметров HNSW")
            return None

        return {
            'space': metadata.get('hnsw:space', 'cosine'),
            'M': metadata.get('hnsw:M', 32),
            'construction_ef': metadata.get('hnsw:construction_ef', 200),
            'search_ef': metadata.get('hnsw:search_ef', 100),
        }

    def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """
        Получить расширенную статистику коллекции.

        Args:
            collection_name: Имя коллекции

        Returns:
            Dict со статистикой
        """
        from services.vector_search.hnsw_config import estimate_memory_usage

        collection = self.get_collection(collection_name)
        count = collection.count()

        # Получаем конфигурацию HNSW
        hnsw_config = self.get_hnsw_config(collection_name)

        # Оцениваем потребление памяти (предполагаем 384 измерения для multilingual-MiniLM)
        memory_estimate = estimate_memory_usage(count, dimensions=384)

        return {
            'name': collection_name,
            'count': count,
            'hnsw_config': hnsw_config,
            'memory_estimate': memory_estimate,
        }
