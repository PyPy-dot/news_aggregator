"""
Тесты для HNSW конфигурации векторного поиска.

Проверяют:
- HNSWConfig dataclass
- get_hnsw_config функция
- estimate_memory_usage функция
- Валидация параметров
"""

import pytest

from services.vector_search.hnsw_config import (
    HNSWConfig,
    get_hnsw_config,
    estimate_memory_usage,
    get_recommended_batch_size,
)


# =============================================================================
# Тесты HNSWConfig
# =============================================================================

class TestHNSWConfig:
    """Тесты для HNSWConfig."""

    def test_default_values(self):
        """Тест: значения по умолчанию."""
        config = HNSWConfig()

        assert config.space == 'cosine'
        assert config.M == 32
        assert config.construction_ef == 200
        assert config.search_ef == 100

    def test_custom_values(self):
        """Тест: кастомные значения."""
        config = HNSWConfig(
            space='l2',
            M=48,
            construction_ef=300,
            search_ef=150,
        )

        assert config.space == 'l2'
        assert config.M == 48
        assert config.construction_ef == 300
        assert config.search_ef == 150

    def test_to_metadata(self):
        """Тест: преобразование в метаданные."""
        config = HNSWConfig(
            space='cosine',
            M=32,
            construction_ef=200,
            search_ef=100,
        )

        metadata = config.to_metadata()

        assert metadata['hnsw:space'] == 'cosine'
        assert metadata['hnsw:M'] == 32
        assert metadata['hnsw:construction_ef'] == 200
        assert metadata['hnsw:search_ef'] == 100

    def test_from_metadata(self):
        """Тест: создание из метаданных."""
        metadata = {
            'hnsw:space': 'l2',
            'hnsw:M': 48,
            'hnsw:construction_ef': 300,
            'hnsw:search_ef': 150,
        }

        config = HNSWConfig.from_metadata(metadata)

        assert config.space == 'l2'
        assert config.M == 48
        assert config.construction_ef == 300
        assert config.search_ef == 150

    def test_validate_valid(self):
        """Тест: валидация валидной конфигурации."""
        config = HNSWConfig(
            space='cosine',
            M=32,
            construction_ef=200,
            search_ef=100,
        )

        errors = config.validate()
        assert len(errors) == 0

    def test_validate_invalid_space(self):
        """Тест: валидация неверного space."""
        config = HNSWConfig(space='invalid')
        errors = config.validate()

        assert any('space' in e for e in errors)

    def test_validate_m_out_of_range(self):
        """Тест: валидация M вне диапазона."""
        config = HNSWConfig(M=5)  # < 8
        errors = config.validate()

        assert any('M=' in e for e in errors)

        config = HNSWConfig(M=150)  # > 128
        errors = config.validate()

        assert any('M=' in e for e in errors)

    def test_validate_m_greater_than_construction_ef(self):
        """Тест: валидация M > construction_ef."""
        config = HNSWConfig(M=100, construction_ef=50)
        errors = config.validate()

        assert any('must be less than' in e for e in errors)


# =============================================================================
# Тесты get_hnsw_config
# =============================================================================

class TestGetHnswConfig:
    """Тесты для get_hnsw_config."""

    def test_small_database(self):
        """Тест: маленькая база (< 10K)."""
        config = get_hnsw_config(num_vectors=5000)

        assert config.M <= 32
        assert config.construction_ef <= 200

    def test_medium_database(self):
        """Тест: средняя база (10K-100K)."""
        config = get_hnsw_config(num_vectors=50000)

        assert config.M >= 32
        assert config.M <= 48
        assert config.construction_ef >= 200

    def test_large_database(self):
        """Тест: большая база (100K-500K)."""
        config = get_hnsw_config(num_vectors=200000)

        assert config.M >= 48
        assert config.construction_ef >= 300

    def test_very_large_database(self):
        """Тест: очень большая база (> 500K)."""
        config = get_hnsw_config(num_vectors=1000000)

        assert config.M >= 64
        assert config.construction_ef >= 400

    def test_optimize_for_speed(self):
        """Тест: оптимизация для скорости."""
        config = get_hnsw_config(num_vectors=50000, optimize_for='speed')

        # Для скорости M и ef должны быть меньше
        assert config.M < 32 or config.construction_ef < 200

    def test_optimize_for_accuracy(self):
        """Тест: оптимизация для точности."""
        config = get_hnsw_config(num_vectors=50000, optimize_for='accuracy')

        # Для точности M и ef должны быть больше
        assert config.M > 32 or config.construction_ef > 200

    def test_custom_space(self):
        """Тест: кастомная метрика."""
        config = get_hnsw_config(num_vectors=50000, space='l2')

        assert config.space == 'l2'


# =============================================================================
# Тесты estimate_memory_usage
# =============================================================================

class TestEstimateMemoryUsage:
    """Тесты для estimate_memory_usage."""

    def test_small_collection(self):
        """Тест: оценка для маленькой коллекции."""
        result = estimate_memory_usage(num_vectors=10000, dimensions=384)

        assert result['vectors_mb'] > 0
        assert result['graph_mb'] > 0
        assert result['metadata_mb'] > 0
        assert result['total_mb'] > 0
        assert result['total_gb'] > 0

        # Проверка что total = sum компонентов
        assert abs(result['total_mb'] - (
            result['vectors_mb'] + result['graph_mb'] + result['metadata_mb']
        )) < 0.1

    def test_large_collection(self):
        """Тест: оценка для большой коллекции."""
        result = estimate_memory_usage(num_vectors=100000, dimensions=384)

        # Для 100K векторов с 384 измерениями
        # vectors: 100000 * 384 * 4 / 1024 / 1024 ≈ 146 MB
        assert result['vectors_mb'] > 100

    def test_dimensions_impact(self):
        """Тест: влияние размерности на память."""
        result_384 = estimate_memory_usage(num_vectors=10000, dimensions=384)
        result_768 = estimate_memory_usage(num_vectors=10000, dimensions=768)

        # 768 измерений должно занимать примерно в 2 раза больше
        assert result_768['vectors_mb'] > result_384['vectors_mb'] * 1.5


# =============================================================================
# Тесты get_recommended_batch_size
# =============================================================================

class TestGetRecommendedBatchSize:
    """Тесты для get_recommended_batch_size."""

    def test_small_database(self):
        """Тест: маленькая база."""
        batch_size = get_recommended_batch_size(num_vectors=5000)
        assert batch_size == 100

    def test_medium_database(self):
        """Тест: средняя база."""
        batch_size = get_recommended_batch_size(num_vectors=50000)
        assert batch_size == 500

    def test_large_database(self):
        """Тест: большая база."""
        batch_size = get_recommended_batch_size(num_vectors=200000)
        assert batch_size == 1000

    def test_very_large_database(self):
        """Тест: очень большая база."""
        batch_size = get_recommended_batch_size(num_vectors=1000000)
        assert batch_size == 2000


# =============================================================================
# Интеграционные тесты
# =============================================================================

class TestIntegration:
    """Интеграционные тесты."""

    def test_config_roundtrip(self):
        """Тест: конвертация туда-обратно."""
        original = HNSWConfig(
            space='cosine',
            M=48,
            construction_ef=300,
            search_ef=150,
        )

        metadata = original.to_metadata()
        restored = HNSWConfig.from_metadata(metadata)

        assert restored.space == original.space
        assert restored.M == original.M
        assert restored.construction_ef == original.construction_ef
        assert restored.search_ef == original.search_ef

    def test_get_hnsw_config_validation(self):
        """Тест: get_hnsw_config возвращает валидную конфигурацию."""
        for num_vectors in [1000, 10000, 100000, 500000]:
            for optimize_for in ['speed', 'accuracy', 'balance']:
                config = get_hnsw_config(
                    num_vectors=num_vectors,
                    optimize_for=optimize_for,
                )

                errors = config.validate()
                assert len(errors) == 0, f"Config for {num_vectors} vectors has errors: {errors}"

    def test_memory_estimate_scaling(self):
        """Тест: масштабирование оценки памяти."""
        result_10k = estimate_memory_usage(num_vectors=10000, dimensions=384)
        result_100k = estimate_memory_usage(num_vectors=100000, dimensions=384)

        # 100K должно быть примерно в 10 раз больше 10K
        assert result_100k['total_mb'] > result_10k['total_mb'] * 8
        assert result_100k['total_mb'] < result_10k['total_mb'] * 12
