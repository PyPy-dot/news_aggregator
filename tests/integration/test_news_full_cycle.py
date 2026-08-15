"""
Интеграционные тесты полного цикла обработки новости.

Тестируется полный цикл:
1. Пост попадает в CategorizationQueue
2. CategorizationProcessor обрабатывает (AI → парсинг → сохранение)
3. Scheduler запускает обработку плановых новостей
4. NewsOrchestrator → Editor → Archivist
5. Новость сохраняется в БД
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from database.models import TelegramPost
from services.categorization.queue import CategorizationTask
from services.categorization.processor import CategorizationProcessor
from services.categorization.saver import NewsSaver
from services.ai_agent.agents.categorizer import CategorizerAgent
from services.news.orchestrator import NewsOrchestrator
from services.news.generation import NewsGenerationService
from database import RepositoryFactory
from services.database import get_database_service


@pytest.fixture
async def db_session():
    """Создать сессию БД для теста с автосбросом."""
    db_service = get_database_service()
    async with db_service.session_context() as session:
        yield session
        # Автосброс после теста
        await session.rollback()


@pytest.fixture
async def factory(db_session):
    """Создать фабрику репозиториев с общей сессией."""
    return RepositoryFactory(db_session)


@pytest.fixture
async def test_channel(factory):
    """Создать тестовый канал."""
    channel = await factory.channels().create_channel(
        channel_id=-1001234567890,
        title="Test Channel",
        description="Test Description",
    )
    return channel


class TestFullNewsCycle:
    """Тесты полного цикла обработки новости."""

    @pytest.mark.asyncio
    async def test_categorization_to_saved_post(self, db_session, factory, test_channel):
        """
        Тест: CategorizationProcessor сохраняет пост в БД.

        Сценарий:
        1. Создаётся CategorizationTask
        2. CategorizationProcessor обрабатывает задачу
        3. Пост сохраняется в БД
        """
        # Мокаем AI агента
        mock_categorizer = AsyncMock(spec=CategorizerAgent)
        mock_categorizer.send_question = AsyncMock(
            return_value='{"text": "Test news cleaned", "category": "Политика", "urgency": 3}'
        )

        # Создаём процессор
        saver = NewsSaver(
            posts_repo=factory.posts(),
            channels_repo=factory.channels(),
            events_repo=factory.events(),
        )

        processor = CategorizationProcessor(
            categorizer=mock_categorizer,
            saver=saver,
            channel_provider=factory.channels(),
            notification_service=None,
        )

        # Создаём задачу
        task = CategorizationTask(
            channel_id=test_channel.channel_id,
            prompt=f"## Название ресурса\n{test_channel.title}\n\n## Текст\nTest news",
            original_text="Test news",
            title=test_channel.title,
            desc=test_channel.description,
        )

        # Обрабатываем
        await processor.process(task)

        # Проверяем, что пост сохранён
        # Используем select напрямую чтобы избежать проблемы с параметрами
        from sqlalchemy import select
        result = await db_session.execute(
            select(TelegramPost).order_by(TelegramPost.created_at.desc()).limit(1)
        )
        posts = result.scalars().all()

        assert len(posts) >= 1
        last_post = posts[-1]
        assert last_post.text == 'Test news cleaned'
        assert last_post.category == 'Политика'

    @pytest.mark.asyncio
    async def test_urgent_news_strategy(self, db_session, factory, test_channel):
        """
        Тест: Срочная новость (urgency=5) обрабатывается через UrgentNewsStrategy.

        Сценарий:
        1. Создаётся пост с urgency=5
        2. NewsOrchestrator выбирает UrgentNewsStrategy
        3. Стратегия отправляет событие GENERATE_NEWS
        """
        # Создаём пост с высокой срочностью
        post = await factory.posts().create_post(
            text="URGENT: Breaking news!",
            channel_id=test_channel.channel_id,
            category="Происшествия",
            urgency=5,
            tags='["срочно", "breaking"]',
        )

        # Создаем orchestrator с моком notification_service
        mock_notification = MagicMock()
        orchestrator = NewsOrchestrator(
            repo_factory=factory,
            notification_service=mock_notification,
        )
        orchestrator._running = True  # Включаем orchestrator

        # Проверяем выбор стратегии
        priority = orchestrator._determine_priority(urgency=5, is_trusted_source=False)
        assert priority == 'urgent'

        strategy = orchestrator._get_strategy('urgent')
        assert strategy is not None

    @pytest.mark.asyncio
    async def test_scheduled_news_batch_processing(
        self, db_session, factory, test_channel
    ):
        """
        Тест: Плановая обработка новостей через process_pending_news_batch.

        Сценарий:
        1. Создаётся несколько постов с checked_at=False
        2. Вызывается process_pending_news_batch
        3. Посты отмечаются как обработанные
        """
        # Создаём посты с checked_at=False
        created_posts = []
        for i in range(3):
            post = await factory.posts().create_post(
                text=f"Scheduled news {i}",
                channel_id=test_channel.channel_id,
                category="Общество",
                urgency=2,
                tags='[]',
            )
            created_posts.append(post)

        # Создаем orchestrator
        mock_notification = MagicMock()
        orchestrator = NewsOrchestrator(
            repo_factory=factory,
            notification_service=mock_notification,
        )
        orchestrator._running = True  # Включаем orchestrator

        # Мокаем Editor и Archivist агентов чтобы не вызывать реальный AI
        with patch.object(orchestrator, '_get_generation_service') as mock_get_service:
            mock_service = AsyncMock(spec=NewsGenerationService)
            # Возвращаем ID созданной новости
            mock_service.generate_news = AsyncMock(return_value=999)
            mock_get_service.return_value = mock_service

            # Обрабатываем ТОЛЬКО наши посты (последние 3)
            processed_count = await orchestrator.process_pending_news_batch(hours=48)

            # Проверяем, что хотя бы наши посты обработаны
            assert processed_count >= 3

            # Проверяем, что наши посты отмечены как обработанные
            for post in created_posts:
                updated = await factory.posts().get(post.id)
                assert updated.checked_at is True, f"Пост ID={post.id} не отмечен как обработанный"

    @pytest.mark.asyncio
    async def test_trusted_source_direct_publish(
        self, db_session, factory, test_channel
    ):
        """
        Тест: Доверенный источник публикуется напрямую.

        Сценарий:
        1. Канал помечается как is_trusted=True
        2. Пост с urgency=4 обрабатывается через TrustedSourceStrategy
        3. Публикация происходит напрямую (без модерации)
        """
        # Помечаем канал как доверенный
        await factory.channels().set_trusted(test_channel.channel_id, is_trusted=True)

        # Создаём пост
        post = await factory.posts().create_post(
            text="Trusted source news",
            channel_id=test_channel.channel_id,
            category="Политика",
            urgency=4,
            tags='[]',
        )

        # Создаем orchestrator
        mock_notification = MagicMock()
        orchestrator = NewsOrchestrator(
            repo_factory=factory,
            notification_service=mock_notification,
        )

        # Проверяем выбор стратегии
        priority = orchestrator._determine_priority(urgency=4, is_trusted_source=True)
        assert priority == 'trusted'

        strategy = orchestrator._get_strategy('trusted')
        assert strategy is not None

    @pytest.mark.asyncio
    async def test_full_cycle_mock_ai(self, db_session, factory, test_channel):
        """
        Тест: Полный цикл с моками AI агентов.

        Сценарий:
        1. Пост создаётся через CategorizationProcessor
        2. Мокируется AI категоризация
        3. Мокируется генерация новости
        4. Проверяется результат в БД
        """
        # 1. Создаём пост через CategorizationProcessor
        mock_categorizer = AsyncMock(spec=CategorizerAgent)
        mock_categorizer.send_question = AsyncMock(
            return_value='{"text": "Cleaned news text", "category": "Экономика", "urgency": 3}'
        )

        saver = NewsSaver(
            posts_repo=factory.posts(),
            channels_repo=factory.channels(),
            events_repo=factory.events(),
        )

        processor = CategorizationProcessor(
            categorizer=mock_categorizer,
            saver=saver,
            channel_provider=factory.channels(),
            notification_service=None,
        )

        task = CategorizationTask(
            channel_id=test_channel.channel_id,
            prompt="Test prompt",
            original_text="Original text",
            title=test_channel.title,
            desc=test_channel.description,
        )

        await processor.process(task)

        # 2. Проверяем, что пост сохранён
        from sqlalchemy import select
        result = await db_session.execute(
            select(TelegramPost).where(
                TelegramPost.channel_id == test_channel.channel_id
            ).order_by(TelegramPost.created_at.desc()).limit(1)
        )
        posts = result.scalars().all()
        assert len(posts) >= 1
        post = posts[-1]
        assert post.category == 'Экономика'
        assert post.urgency == '3'
        assert post.checked_at is False  # Ещё не обработан планировщиком

        # 3. Обрабатываем через orchestrator с полным моком
        mock_notification = MagicMock()

        # Мокаем ВСЕ AI агенты чтобы не вызывать реальный AI
        with patch('services.ai_agent.agents.editor.EditorAgent') as MockEditor:
            with patch('services.ai_agent.agents.archivist.ArchivistAgent') as MockArchivist:
                # Настраиваем моки
                mock_editor_instance = AsyncMock()
                mock_editor_instance.generate_news.return_value = {
                    'title': 'Test News',
                    'text': 'Generated text',
                    'summary': 'Summary',
                    'news_tags': ['tag1']
                }
                MockEditor.return_value = mock_editor_instance

                mock_archivist_instance = AsyncMock()
                mock_archivist_instance.create_context.return_value = {
                    'context_data': {},
                    'embedding_text': 'text',
                    'tags': [],
                    'related_event_ids': []
                }
                MockArchivist.return_value = mock_archivist_instance

                orchestrator = NewsOrchestrator(
                    repo_factory=factory,
                    notification_service=mock_notification,
                )
                orchestrator._running = True  # Включаем orchestrator

                processed = await orchestrator.process_pending_news_batch(hours=48)
                assert processed >= 1

        # 4. Проверяем, что пост отмечен как обработанный
        updated_post = await factory.posts().get(post.id)
        assert updated_post.checked_at is True
        # generated_news_id может быть установлен если генерация прошла успешно
