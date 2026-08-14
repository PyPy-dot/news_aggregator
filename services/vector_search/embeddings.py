"""
Embedding Service — генерация векторных эмбеддингов через sentence-transformers.
"""

import asyncio
import logging
import warnings
from functools import lru_cache
from typing import Optional

from sentence_transformers import SentenceTransformer

from services.logging_config import get_logger

logger = get_logger(__name__)

# Подавляем предупреждение transformers о clean_up_tokenization_spaces
warnings.filterwarnings(
    'ignore',
    message='.*clean_up_tokenization_spaces.*',
    category=FutureWarning,
    module='transformers'
)

# Модель для русскоязычных текстов (paraphrase-multilingual работает с русским)
DEFAULT_MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'


class EmbeddingService:
    """
    Сервис для генерации векторных эмбеддингов текстов.

    Использует предобученную модель sentence-transformers.
    Эмбеддинги кэшируются для производительности.

    Attributes:
        model_name: Название модели
        embedding_dim: Размерность вектора (зависит от модели)
    """

    _instance: Optional['EmbeddingService'] = None
    _model: Optional[SentenceTransformer] = None

    def __new__(cls, model_name: str = DEFAULT_MODEL_NAME) -> 'EmbeddingService':
        """Singleton pattern — модель загружается один раз."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        """
        Инициализация сервиса.

        Args:
            model_name: Название модели sentence-transformers
        """
        if self._initialized:
            return

        self.model_name = model_name
        self._model = None
        self._embedding_dim: Optional[int] = None
        self._initialized = True

        logger.info(f"🧠 EmbeddingService инициализирован (модель: {model_name})")

    @property
    def model(self) -> SentenceTransformer:
        """Ленивая загрузка модели."""
        if self._model is None:
            logger.info(f"📥 Загрузка модели {self.model_name}...")
            self._model = SentenceTransformer(self.model_name)
            self._embedding_dim = self._model.get_sentence_embedding_dimension()
            logger.info(
                f"✅ Модель загружена (размерность: {self._embedding_dim})"
            )
        return self._model

    @property
    def embedding_dim(self) -> int:
        """Размерность вектора эмбеддинга."""
        if self._embedding_dim is None:
            _ = self.model  # Загружаем модель
        return self._embedding_dim  # type: ignore[return-value]

    # Кэш для часто используемых текстов (максимум 1000 записей)
    @lru_cache(maxsize=1000)
    def _embed_cached(self, text: str) -> list[float]:
        """
        Генерирует эмбеддинг с кэшированием.

        Args:
            text: Текст для эмбеддинга

        Returns:
            Вектор эмбеддинга
        """
        import numpy as np
        result = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        # Конвертируем numpy array в список
        if isinstance(result, np.ndarray):
            return result.tolist()
        return result

    async def embed(self, text: str) -> list[float]:
        """
        Генерирует векторный эмбеддинг для текста (асинхронно).

        Использует кэш для часто используемых текстов.
        Выполняется в background thread для неблокирующего выполнения.

        Args:
            text: Текст для эмбеддинга

        Returns:
            Вектор эмбеддинга (список float)
        """
        import time
        start = time.time()

        # Выполняем в background thread для неблокирующего выполнения
        embedding = await asyncio.to_thread(
            self._embed_cached, text
        )

        elapsed_ms = (time.time() - start) * 1000
        logger.debug(f"⏱ Эмбеддинг сгенерирован за {elapsed_ms:.0f} мс")

        return embedding

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> list[list[float]]:
        """
        Генерирует эмбеддинги для пакета текстов.

        Args:
            texts: Список текстов
            batch_size: Размер батча для обработки
            show_progress: Показывать прогресс-бар

        Returns:
            Список векторных эмбеддингов
        """
        import time
        import numpy as np
        start = time.time()

        result = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=batch_size,
            show_progress_bar=show_progress,
        )

        # Конвертируем numpy array в список списков
        if isinstance(result, np.ndarray):
            embeddings = result.tolist()
        else:
            embeddings = result

        elapsed_ms = (time.time() - start) * 1000
        logger.info(
            f"✅ Сгенерировано {len(embeddings)} эмбеддингов за {elapsed_ms:.0f} мс"
        )

        return embeddings

    def clear_cache(self) -> None:
        """Очищает кэш модели (для освобождения памяти)."""
        if self._model is not None:
            del self._model
            self._model = None
            self._embedding_dim = None
            logger.info("🗑️ Кэш эмбеддингов очищен")
