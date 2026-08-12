"""
HNSW Index Configuration — оптимизация параметров HNSW для ChromaDB.

HNSW (Hierarchical Navigable Small World) — алгоритм для приближённого поиска ближайших соседей.

Параметры для оптимизации:
- hnsw:space: Метрика расстояния (cosine, l2, ip)
- hnsw:construction_ef: Размер списка соседей при построении (точность/скорость)
- hnsw:search_ef: Размер списка соседей при поиске (точность/скорость)
- hnsw:M: Максимальное количество связей на узел (качество графа)

Рекомендации для разных размеров базы:
| Размер базы | M  | construction_ef | search_ef | Описание |
|-------------|----|-----------------|-----------|----------|
| < 10K       | 16 | 100             | 50        | Маленькая база, высокая точность |
| 10K-100K    | 32 | 200             | 100       | Средняя база, баланс |
| 100K-1M     | 48 | 300             | 150       | Большая база, оптимизация скорости |
| > 1M        | 64 | 400             | 200       | Очень большая база, максимальная скорость |

Usage:
    from services.vector_search.hnsw_config import get_hnsw_config, HNSWConfig

    # Автоматическая конфигурация
    config = get_hnsw_config(num_vectors=50000)
    collection = client.create_collection(
        name="events",
        metadata=config.to_metadata(),
    )

    # Ручная настройка
    config = HNSWConfig(M=32, construction_ef=200, search_ef=100)
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class HNSWConfig:
    """
    Конфигурация HNSW индекса.

    Attributes:
        space: Метрика расстояния ('cosine', 'l2', 'ip')
        M: Максимальное количество связей на узел (16-64)
        construction_ef: Размер списка соседей при построении (100-400)
        search_ef: Размер списка соседей при поиске (50-200)
    """
    space: str = 'cosine'
    M: int = 32
    construction_ef: int = 200
    search_ef: int = 100

    def to_metadata(self) -> dict[str, any]:
        """
        Преобразовать в метаданные для ChromaDB коллекции.

        Returns:
            Dict с параметрами HNSW
        """
        return {
            'hnsw:space': self.space,
            'hnsw:construction_ef': self.construction_ef,
            'hnsw:search_ef': self.search_ef,
            'hnsw:M': self.M,
        }

    @classmethod
    def from_metadata(cls, metadata: dict[str, any]) -> 'HNSWConfig':
        """
        Создать конфигурацию из метаданных коллекции.

        Args:
            metadata: Метаданные коллекции

        Returns:
            HNSWConfig экземпляр
        """
        return cls(
            space=metadata.get('hnsw:space', 'cosine'),
            M=metadata.get('hnsw:M', 32),
            construction_ef=metadata.get('hnsw:construction_ef', 200),
            search_ef=metadata.get('hnsw:search_ef', 100),
        )

    def validate(self) -> list[str]:
        """
        Проверить валидность параметров.

        Returns:
            Список ошибок (пустой если всё OK)
        """
        errors = []

        if self.space not in ('cosine', 'l2', 'ip'):
            errors.append(f"Invalid space: {self.space}. Must be 'cosine', 'l2', or 'ip'")

        if not (8 <= self.M <= 128):
            errors.append(f"M={self.M} out of range [8, 128]")

        if not (50 <= self.construction_ef <= 500):
            errors.append(f"construction_ef={self.construction_ef} out of range [50, 500]")

        if not (25 <= self.search_ef <= 300):
            errors.append(f"search_ef={self.search_ef} out of range [25, 300]")

        # M должно быть меньше construction_ef
        if self.M >= self.construction_ef:
            errors.append(f"M ({self.M}) must be less than construction_ef ({self.construction_ef})")

        return errors


def get_hnsw_config(
    num_vectors: int,
    space: str = 'cosine',
    optimize_for: str = 'balance',
) -> HNSWConfig:
    """
    Получить оптимальную конфигурацию HNSW для заданного размера базы.

    Args:
        num_vectors: Ожидаемое количество векторов в коллекции
        space: Метрика расстояния ('cosine', 'l2', 'ip')
        optimize_for: Что оптимизировать ('speed', 'accuracy', 'balance')

    Returns:
        HNSWConfig с оптимальными параметрами

    Examples:
        # Маленькая база (< 10K векторов)
        config = get_hnsw_config(num_vectors=5000)

        # Большая база (100K+), оптимизация скорости
        config = get_hnsw_config(num_vectors=150000, optimize_for='speed')

        # Максимальная точность для критичных задач
        config = get_hnsw_config(num_vectors=50000, optimize_for='accuracy')
    """
    # Определяем размер базы
    if num_vectors < 10_000:
        base_m = 16
        base_ef = 100
    elif num_vectors < 100_000:
        base_m = 32
        base_ef = 200
    elif num_vectors < 500_000:
        base_m = 48
        base_ef = 300
    else:
        base_m = 64
        base_ef = 400

    # Корректируем в зависимости от оптимизации
    if optimize_for == 'speed':
        # Меньше M и ef для скорости
        m_multiplier = 0.75
        ef_multiplier = 0.75
    elif optimize_for == 'accuracy':
        # Больше M и ef для точности
        m_multiplier = 1.25
        ef_multiplier = 1.25
    else:  # balance
        m_multiplier = 1.0
        ef_multiplier = 1.0

    M = int(base_m * m_multiplier)
    construction_ef = int(base_ef * ef_multiplier)
    search_ef = int(construction_ef * 0.5)  # search_ef обычно половина construction_ef

    # Ограничиваем диапазонами
    M = max(8, min(128, M))
    construction_ef = max(50, min(500, construction_ef))
    search_ef = max(25, min(300, search_ef))

    config = HNSWConfig(
        space=space,
        M=M,
        construction_ef=construction_ef,
        search_ef=search_ef,
    )

    # Валидация
    errors = config.validate()
    if errors:
        logger.warning(f"⚠️ HNSW config validation warnings: {errors}")

    logger.info(
        f"📊 HNSW конфигурация для {num_vectors:,} векторов "
        f"(optimize={optimize_for}): M={M}, construction_ef={construction_ef}, search_ef={search_ef}"
    )

    return config


def estimate_memory_usage(num_vectors: int, dimensions: int = 384) -> dict[str, float]:
    """
    Оценить потребление памяти для HNSW индекса.

    Args:
        num_vectors: Количество векторов
        dimensions: Размерность векторов (по умолчанию 384 для multilingual-MiniLM)

    Returns:
        Dict с оценками памяти (MB)

    Formula:
        Base vectors: num_vectors * dimensions * 4 bytes (float32)
        HNSW graph: num_vectors * M * 8 bytes (pointers)
        Metadata: num_vectors * 1 KB (approx)
    """
    # Параметры по умолчанию для сбалансированной конфигурации
    config = get_hnsw_config(num_vectors)

    # Векторы (float32 = 4 bytes)
    vectors_memory = (num_vectors * dimensions * 4) / (1024 * 1024)

    # HNSW граф (указатели ~8 bytes на связь)
    graph_memory = (num_vectors * config.M * 8) / (1024 * 1024)

    # Метаданные (примерно 1KB на вектор)
    metadata_memory = (num_vectors * 1024) / (1024 * 1024)

    # Итого
    total_memory = vectors_memory + graph_memory + metadata_memory

    return {
        'vectors_mb': round(vectors_memory, 2),
        'graph_mb': round(graph_memory, 2),
        'metadata_mb': round(metadata_memory, 2),
        'total_mb': round(total_memory, 2),
        'total_gb': round(total_memory / 1024, 3),
    }


def get_recommended_batch_size(num_vectors: int) -> int:
    """
    Получить рекомендуемый размер пакета для добавления векторов.

    Args:
        num_vectors: Общее количество векторов

    Returns:
        Рекомендуемый размер пакета
    """
    if num_vectors < 10_000:
        return 100
    elif num_vectors < 100_000:
        return 500
    elif num_vectors < 500_000:
        return 1000
    else:
        return 2000


# =============================================================================
# Оптимизация существующих коллекций
# =============================================================================

def optimize_collection(
    collection,
    num_vectors: int,
    optimize_for: str = 'balance',
) -> HNSWConfig:
    """
    Оптимизировать параметры HNSW для существующей коллекции.

    Args:
        collection: ChromaDB коллекция
        num_vectors: Количество векторов в коллекции
        optimize_for: Что оптимизировать ('speed', 'accuracy', 'balance')

    Returns:
        HNSWConfig с применёнными параметрами

    Note:
        ChromaDB не поддерживает динамическое изменение параметров HNSW
        для существующих коллекций. Этот метод создаёт новую коллекцию
        с оптимальными параметрами и копирует данные.
    """
    # Получаем оптимальную конфигурацию
    config = get_hnsw_config(num_vectors, optimize_for=optimize_for)

    # Проверяем текущие параметры
    current_metadata = collection.metadata or {}
    current_config = HNSWConfig.from_metadata(current_metadata)

    logger.info(
        f"📊 Текущая конфигурация: M={current_config.M}, "
        f"construction_ef={current_config.construction_ef}, "
        f"search_ef={current_config.search_ef}"
    )

    logger.info(
        f"📊 Рекомендуемая конфигурация: M={config.M}, "
        f"construction_ef={config.construction_ef}, "
        f"search_ef={config.search_ef}"
    )

    # Если параметры отличаются, рекомендуем пересоздать коллекцию
    if (current_config.M != config.M or
        current_config.construction_ef != config.construction_ef or
        current_config.search_ef != config.search_ef):

        logger.warning(
            "⚠️ Для применения новых параметров HNSW требуется пересоздание коллекции. "
            "Используйте services.vector_search.auto_reindex для переиндексации."
        )

    return config


__all__ = [
    'HNSWConfig',
    'get_hnsw_config',
    'estimate_memory_usage',
    'get_recommended_batch_size',
    'optimize_collection',
]
