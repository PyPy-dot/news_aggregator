"""
Сквозные интеграционные тесты (End-to-End).

Проверяют полный цикл обработки новостей:
1. Получение поста (имитация)
2. Категоризация (Categorizer + Analyst)
3. Генерация новости (Editor + Archivist)
4. Векторный поиск похожих событий
5. Сохранение в БД

Требования:
- Запущенный Ollama сервер
- Запущенный ChromaDB сервер
- SQLite/PostgreSQL для тестов
"""

import os
import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any

# Пропускаем тесты если сервисы не настроены
pytestmark = pytest.mark.skipif(
    not os.environ.get('OLLAMA_HOST') or not os.environ.get('CHROMA_HOST'),
    reason="Требуются Ollama и ChromaDB"
)

from services.ai_agent.agents.categorizer import CategorizerAgent
from services.ai_agent.agents.analyst import AnalystAgent
from services.ai_agent.agents.editor import EditorAgent
from services.ai_agent.agents.archivist import ArchivistAgent
from services.vector_search.search_engine import VectorSearchEngine


# =============================================================================
# Тестовые данные
# =============================================================================

SAMPLE_NEWS_TEXTS = [
    """
    🇷🇺 Президент России провёл встречу с правительством
    Обсуждались вопросы экономического развития и поддержки регионов.
    Особое внимание уделено инфраструктурным проектам.
    """,
    """
    ⚽ Сборная России по футболу победила в товарищеском матче
    Матч прошёл на стадионе «Лужники» в Москве.
    Голы забили: Головин (23'), Миранчук (67').
    """,
    """
    🌡️ Синоптики прогнозируют аномальное потепление на этой неделе
    Температура воздуха превысит норму на 5-7 градусов.
    В некоторых регионах возможны дожди.
    """,
    """
    🚀 Роскосмос запустил спутник связи
    Запуск состоялся с космодрома Восточный.
    Спутник выведен на целевую орбиту.
    """,
]


class TestCategorizationPipeline:
    """Тесты пайплайна категоризации."""

    @pytest.mark.asyncio
    async def test_categorize_news(self):
        """Тест категоризации новости."""
        categorizer = CategorizerAgent()

        text = SAMPLE_NEWS_TEXTS[0]
        result = await categorizer.categorize(
            text=text,
            channel_title='Новости России',
            channel_desc='Официальный новостной канал',
        )

        assert 'category' in result
        assert 'urgency' in result
        assert 'text' in result
        assert isinstance(result['urgency'], int)
        assert 1 <= result['urgency'] <= 5

    @pytest.mark.asyncio
    async def test_analyze_news(self):
        """Тест анализа новости."""
        analyst = AnalystAgent()

        text = SAMPLE_NEWS_TEXTS[1]
        category = 'Спорт'
        urgency = 3

        result = await analyst.analyze(text, category, urgency)

        assert 'tags' in result
        assert isinstance(result['tags'], list)
        assert len(result['tags']) > 0

    @pytest.mark.asyncio
    async def test_full_categorization(self):
        """Тест полной категоризации (Categorizer + Analyst)."""
        categorizer = CategorizerAgent()
        analyst = AnalystAgent()

        text = SAMPLE_NEWS_TEXTS[2]

        # Категоризация
        cat_result = await categorizer.categorize(text, 'Погода')
        assert 'category' in cat_result
        assert 'urgency' in cat_result

        # Анализ
        analysis = await analyst.analyze(
            text=cat_result['text'],
            category=cat_result['category'],
            urgency=cat_result['urgency'],
        )
        assert 'tags' in analysis
        assert 'confidence' in analysis or 'category_confidence' in analysis


class TestNewsGenerationPipeline:
    """Тесты пайплайна генерации новостей."""

    @pytest.mark.asyncio
    async def test_generate_news_single(self):
        """Тест генерации новости из одного контекста."""
        editor = EditorAgent()

        contexts = [
            {
                'text': 'Президент провёл встречу с правительством',
                'source': 'Канал 1',
                'timestamp': datetime.now().isoformat(),
            }
        ]

        news = await editor.generate_news(contexts)

        assert news is not None
        assert len(news) > 50  # Новость должна быть развёрнутой

    @pytest.mark.asyncio
    async def test_generate_news_multiple(self):
        """Тест генерации новости из нескольких контекстов."""
        editor = EditorAgent()

        contexts = [
            {'text': 'Запуск спутника состоялся', 'source': 'Космос', 'timestamp': '10:00'},
            {'text': 'Спутник на орбите', 'source': 'Наука', 'timestamp': '10:30'},
            {'text': 'Связь установлена', 'source': 'Технологии', 'timestamp': '11:00'},
        ]

        news = await editor.generate_news(contexts)

        assert news is not None
        assert len(news) > 100  # Сводная новость должна быть длиннее

    @pytest.mark.asyncio
    async def test_archivist_context(self):
        """Тест создания контекста Архивариусом."""
        archivist = ArchivistAgent()

        contexts = [
            {'text': 'Аномальное потепление', 'source': 'Погода', 'timestamp': '12:00'},
        ]
        news_text = 'Синоптики сообщают о рекордном потеплении'

        result = await archivist.create_context(contexts, news_text)

        assert result is not None
        assert isinstance(result, dict)


class TestVectorSearchIntegration:
    """Тесты интеграции векторного поиска."""

    @pytest.mark.asyncio
    async def test_search_similar_events(self):
        """Тест поиска похожих событий."""
        search_engine = VectorSearchEngine()

        try:
            # Создаём тестовую коллекцию
            collection_name = 'test_e2e_events'
            await search_engine.create_collection(collection_name)

            # Добавляем события
            events = [
                {'id': '1', 'text': 'Встреча президента с правительством', 'metadata': {}},
                {'id': '2', 'text': 'Совещание по экономическим вопросам', 'metadata': {}},
                {'id': '3', 'text': 'Футбольный матч завершился победой', 'metadata': {}},
            ]
            await search_engine.add_documents(collection_name, events)

            # Ищем похожие
            query = 'Правительство обсудило экономику'
            results = await search_engine.search_similar(
                collection_name=collection_name,
                query=query,
                k=2,
            )

            assert len(results) == 2
            # Первый результат должен быть про встречу/совещание
            assert 'правительств' in results[0]['text'].lower() or 'совещани' in results[0]['text'].lower()

        finally:
            await search_engine.close()


class TestEndToEndPipeline:
    """Сквозные тесты полного пайплайна."""

    @pytest.mark.asyncio
    async def test_full_news_cycle(self):
        """
        Тест полного цикла обработки новости.

        Этапы:
        1. Категоризация
        2. Анализ
        3. Генерация новости
        4. Создание контекста
        5. Векторный поиск
        """
        # Инициализируем агентов
        categorizer = CategorizerAgent()
        analyst = AnalystAgent()
        editor = EditorAgent()
        archivist = ArchivistAgent()
        search_engine = VectorSearchEngine()

        try:
            # 1. Категоризация
            original_text = SAMPLE_NEWS_TEXTS[3]
            cat_result = await categorizer.categorize(original_text, 'Космос')

            assert 'category' in cat_result
            assert 'urgency' in cat_result

            # 2. Анализ
            analysis = await analyst.analyze(
                text=cat_result['text'],
                category=cat_result['category'],
                urgency=cat_result['urgency'],
            )

            assert 'tags' in analysis

            # 3. Генерация новости
            contexts = [
                {
                    'text': cat_result['text'],
                    'source': 'Тестовый канал',
                    'timestamp': datetime.now().isoformat(),
                    'tags': analysis.get('tags', []),
                }
            ]

            news = await editor.generate_news(contexts)
            assert len(news) > 50

            # 4. Создание контекста
            archivist_context = await archivist.create_context(contexts, news)
            assert archivist_context is not None

            # 5. Векторный поиск (сохраняем и ищем)
            collection_name = 'test_full_cycle'
            await search_engine.create_collection(collection_name)

            await search_engine.add_documents(
                collection_name,
                [{'id': '1', 'text': news, 'metadata': {'test': True}}],
            )

            results = await search_engine.search_similar(
                collection_name=collection_name,
                query='космос спутник запуск',
                k=1,
            )

            assert len(results) == 1
            assert 'test' in results[0].get('metadata', {})

        finally:
            await search_engine.close()

    @pytest.mark.asyncio
    async def test_parallel_processing(self):
        """Тест параллельной обработки нескольких новостей."""

        async def process_news(text: str) -> Dict[str, Any]:
            """Обработать одну новость."""
            categorizer = CategorizerAgent()
            analyst = AnalystAgent()

            cat = await categorizer.categorize(text, 'Новости')
            analysis = await analyst.analyze(cat['text'], cat['category'], cat['urgency'])

            return {
                'category': cat['category'],
                'urgency': cat['urgency'],
                'tags': analysis.get('tags', []),
            }

        # Обрабатываем все новости параллельно
        tasks = [process_news(text) for text in SAMPLE_NEWS_TEXTS]
        results = await asyncio.gather(*tasks)

        assert len(results) == len(SAMPLE_NEWS_TEXTS)

        for result in results:
            assert 'category' in result
            assert 'urgency' in result
            assert 'tags' in result


class TestAgentQueueIntegration:
    """Тесты интеграции очереди задач."""

    @pytest.mark.asyncio
    async def test_queued_agent_execution(self):
        """Тест выполнения агента через очередь."""
        from services.ai_agent.agent_queue import (
            get_agent_queue,
            start_agent_queue,
            stop_agent_queue,
            is_redis_queue,
        )

        # Проверяем режим работы
        use_redis = is_redis_queue()

        # Получаем очередь
        queue = get_agent_queue()

        # Запускаем
        if use_redis:
            await start_agent_queue(num_workers=2)
        else:
            await start_agent_queue()

        try:
            # Создаём агента
            categorizer = CategorizerAgent()

            # Выполняем через очередь (декоратор @queued должен сработать)
            result = await categorizer.categorize(
                text=SAMPLE_NEWS_TEXTS[0],
                channel_title='Тест',
            )

            assert 'category' in result

        finally:
            # Останавливаем
            await stop_agent_queue()


class TestLLMFallbackIntegration:
    """Тесты интеграции Fallback LLM."""

    @pytest.mark.asyncio
    async def test_fallback_chain(self):
        """Тест цепочки fallback."""
        from services.core.llm_provider import get_llm_provider, FallbackLLMProvider

        provider = get_llm_provider()

        # Если это fallback провайдер
        if isinstance(provider, FallbackLLMProvider):
            # Проверяем что провайдеры настроены
            stats = provider.get_all_stats()
            assert len(stats) > 0

        # Выполняем запрос
        from services.ai_agent.agents.categorizer import CategorizerAgent

        categorizer = CategorizerAgent()
        result = await categorizer.categorize(SAMPLE_NEWS_TEXTS[1])

        assert 'category' in result
        assert result['category'] is not None


class TestPerformanceIntegration:
    """Тесты производительности интеграции."""

    @pytest.mark.asyncio
    async def test_response_time_budget(self):
        """Тест укладывания в бюджет времени."""
        import time

        categorizer = CategorizerAgent()
        analyst = AnalystAgent()

        text = SAMPLE_NEWS_TEXTS[0]

        start = time.time()

        # Категоризация
        cat_result = await categorizer.categorize(text, 'Тест')

        # Анализ
        analysis = await analyst.analyze(
            cat_result['text'],
            cat_result['category'],
            cat_result['urgency'],
        )

        elapsed = time.time() - start

        # Полный цикл должен уложиться в 30 секунд
        assert elapsed < 30, f"Превышен бюджет времени: {elapsed:.2f}с"

        # Проверяем результаты
        assert 'category' in cat_result
        assert 'tags' in analysis

    @pytest.mark.asyncio
    async def test_concurrent_agents(self):
        """Тест параллельной работы агентов."""

        async def categorize(text: str):
            cat = CategorizerAgent()
            return await cat.categorize(text, 'Тест')

        # Запускаем 3 параллельных категоризации
        tasks = [categorize(text) for text in SAMPLE_NEWS_TEXTS[:3]]
        results = await asyncio.gather(*tasks)

        assert len(results) == 3

        for result in results:
            assert 'category' in result
            assert 'urgency' in result
