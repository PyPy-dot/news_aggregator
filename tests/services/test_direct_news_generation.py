"""
Тесты для прямой генерации новостей (direct news generation).

Покрывают тестами методы:
- NewsOrchestrator.generate_direct_news()
- NewsOrchestrator._publish_direct_to_bot()
- NewsOrchestrator._publish_direct_to_all_channels()
- NewsOrchestrator._publish_direct_to_channel()
- NotificationService.notify_all_subscribers()
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import Bot

from services.news.orchestrator import NewsOrchestrator
from services.telegram.notification import NotificationService
from database import RepositoryFactory


class TestGenerateDirectNews:
    """Тесты для метода generate_direct_news()."""

    @pytest.fixture
    def mock_repo_factory(self):
        """Создаёт мок фабрики репозиториев."""
        factory = MagicMock(spec=RepositoryFactory)

        # Моки репозиториев
        factory.posts = MagicMock(return_value=AsyncMock())
        factory.events = MagicMock(return_value=AsyncMock())
        factory.news = MagicMock(return_value=AsyncMock())
        factory.publishers = MagicMock(return_value=AsyncMock())
        factory.channels = MagicMock(return_value=AsyncMock())

        return factory

    @pytest.fixture
    def mock_notification_service(self):
        """Создаёт мок сервиса уведомлений."""
        return AsyncMock(spec=NotificationService)

    @pytest.fixture
    def orchestrator(self, mock_repo_factory, mock_notification_service):
        """Создаёт NewsOrchestrator с моками."""
        orch = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=mock_notification_service,
        )
        orch._running = True  # Оркестратор запущен
        return orch

    @pytest.mark.asyncio
    async def test_generate_direct_news_to_bot(self, orchestrator, mock_notification_service):
        """Генерация новости с публикацией через бота."""
        # Мокаем методы оркестратора и агентов
        with patch.object(orchestrator, '_publish_direct_to_bot', new_callable=AsyncMock) as mock_publish_bot, \
             patch('services.news.orchestrator.DirectNewsEditorAgent') as MockEditor, \
             patch('services.news.orchestrator.ArchivistAgent') as MockArchivist, \
             patch('services.news.orchestrator.add_generated_news') as mock_add:

            # Настройка моков
            mock_editor = AsyncMock()
            mock_editor.generate_from_description.return_value = {
                'text': 'Тестовая новость',
                'news_tags': ['тэг1', 'тэг2'],
            }
            MockEditor.return_value = mock_editor

            mock_archivist = AsyncMock()
            mock_archivist.create_context.return_value = {
                'context_data': {'key': 'value'},
                'tags': ['тэг1'],
            }
            MockArchivist.return_value = mock_archivist

            mock_add.return_value = 123  # ID новости

            # Вызов метода
            result = await orchestrator.generate_direct_news(
                description="Тестовое описание",
                publisher_channel_id=None,  # Публикация через бота
            )

            # Проверки
            assert result == 123
            mock_editor.generate_from_description.assert_called_once()
            mock_archivist.create_context.assert_called_once()
            mock_add.assert_called_once()

            # Проверка вызова публикации через бота
            mock_publish_bot.assert_called_once_with(123, 'Тестовая новость')

    @pytest.mark.asyncio
    async def test_generate_direct_news_to_all_channels(self, orchestrator):
        """Генерация новости с публикацией во все каналы."""
        with patch.object(orchestrator, '_publish_direct_to_all_channels', new_callable=AsyncMock) as mock_publish_channels, \
             patch('services.news.orchestrator.DirectNewsEditorAgent') as MockEditor, \
             patch('services.news.orchestrator.ArchivistAgent') as MockArchivist, \
             patch('services.news.orchestrator.add_generated_news') as mock_add:

            mock_editor = AsyncMock()
            mock_editor.generate_from_description.return_value = {
                'text': 'Тестовая новость для каналов',
                'news_tags': ['тэг1'],
            }
            MockEditor.return_value = mock_editor

            mock_archivist = AsyncMock()
            mock_archivist.create_context.return_value = {
                'context_data': {},
                'tags': [],
            }
            MockArchivist.return_value = mock_archivist

            mock_add.return_value = 456

            # Вызов метода
            result = await orchestrator.generate_direct_news(
                description="Тестовое описание для каналов",
                publisher_channel_id=-1,  # Публикация во все каналы
            )

            # Проверки
            assert result == 456
            mock_publish_channels.assert_called_once_with(
                456, 'Тестовая новость для каналов'
            )

    @pytest.mark.asyncio
    async def test_generate_direct_news_to_specific_channel(self, orchestrator):
        """Генерация новости с публикацией в конкретный канал."""
        with patch.object(orchestrator, '_publish_direct_to_channel', new_callable=AsyncMock) as mock_publish_channel, \
             patch('services.news.orchestrator.DirectNewsEditorAgent') as MockEditor, \
             patch('services.news.orchestrator.ArchivistAgent') as MockArchivist, \
             patch('services.news.orchestrator.add_generated_news') as mock_add:

            mock_editor = AsyncMock()
            mock_editor.generate_from_description.return_value = {
                'text': 'Тестовая новость в канал',
                'news_tags': [],
            }
            MockEditor.return_value = mock_editor

            mock_archivist = AsyncMock()
            mock_archivist.create_context.return_value = {
                'context_data': {},
                'tags': [],
            }
            MockArchivist.return_value = mock_archivist

            mock_add.return_value = 789

            # Вызов метода
            result = await orchestrator.generate_direct_news(
                description="Тестовое описание",
                publisher_channel_id=100,  # Конкретный канал
            )

            # Проверки
            assert result == 789
            mock_publish_channel.assert_called_once_with(
                789, 'Тестовая новость в канал', 100
            )

    @pytest.mark.asyncio
    async def test_generate_direct_news_error_handling(self, orchestrator):
        """Обработка ошибок при генерации новости."""
        with patch('services.news.orchestrator.DirectNewsEditorAgent') as MockEditor:
            mock_editor = AsyncMock()
            mock_editor.generate_from_description.side_effect = Exception("Ошибка генерации")
            MockEditor.return_value = mock_editor

            # Вызов метода
            result = await orchestrator.generate_direct_news(
                description="Тестовое описание",
            )

            # Проверка
            assert result is None


class TestPublishDirectToBot:
    """Тесты для метода _publish_direct_to_bot()."""

    @pytest.fixture
    def mock_repo_factory(self):
        """Создаёт мок фабрики репозиториев."""
        factory = MagicMock(spec=RepositoryFactory)
        factory.posts = MagicMock(return_value=AsyncMock())
        factory.events = MagicMock(return_value=AsyncMock())
        factory.news = MagicMock(return_value=AsyncMock())
        factory.publishers = MagicMock(return_value=AsyncMock())
        return factory

    @pytest.fixture
    def mock_notification_service(self):
        """Создаёт мок сервиса уведомлений."""
        service = AsyncMock(spec=NotificationService)
        service.notify_all_subscribers = AsyncMock(return_value=50)
        return service

    @pytest.fixture
    def orchestrator(self, mock_repo_factory, mock_notification_service):
        """Создаёт NewsOrchestrator с моками."""
        orch = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=mock_notification_service,
        )
        orch._running = True
        return orch

    @pytest.mark.asyncio
    async def test_publish_direct_to_bot_success(self, orchestrator, mock_notification_service):
        """Успешная публикация через бота."""
        await orchestrator._publish_direct_to_bot(123, "Текст новости")

        mock_notification_service.notify_all_subscribers.assert_called_once_with(
            news_text="Текст новости",
            news_id=123,
            ignore_preferences=True,
        )

    @pytest.mark.asyncio
    async def test_publish_direct_to_bot_no_notification_service(self, mock_repo_factory):
        """Публикация без NotificationService."""
        orch = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=None,
        )
        orch._running = True

        # Не должно выбрасывать исключение
        await orch._publish_direct_to_bot(123, "Текст новости")


class TestPublishDirectToAllChannels:
    """Тесты для метода _publish_direct_to_all_channels()."""

    @pytest.fixture
    def mock_repo_factory(self):
        """Создаёт мок фабрики репозиториев."""
        factory = MagicMock(spec=RepositoryFactory)
        factory.posts = MagicMock(return_value=AsyncMock())
        factory.events = MagicMock(return_value=AsyncMock())
        factory.news = MagicMock(return_value=AsyncMock())

        # Мок publishers_repo
        publishers_repo = AsyncMock()
        publishers_repo.get_all = AsyncMock(return_value=[
            MagicMock(channel_id=-1001, title="Канал 1"),
            MagicMock(channel_id=-1002, title="Канал 2"),
        ])
        factory.publishers = MagicMock(return_value=publishers_repo)

        return factory

    @pytest.fixture
    def orchestrator(self, mock_repo_factory):
        """Создаёт NewsOrchestrator с моками."""
        orch = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=None,
        )
        orch._running = True
        return orch

    @pytest.mark.asyncio
    async def test_publish_direct_to_all_channels_success(self, orchestrator, mock_repo_factory):
        """Успешная публикация во все каналы."""
        with patch.object(orchestrator, '_publish_to_telegram_channel', new_callable=AsyncMock) as mock_publish:
            await orchestrator._publish_direct_to_all_channels(123, "Текст новости")

            # Должно вызвать публикацию в каждый канал
            assert mock_publish.call_count == 2
            mock_publish.assert_any_call(-1001, "Текст новости")
            mock_publish.assert_any_call(-1002, "Текст новости")

            # Проверка вызова mark_published
            news_repo = mock_repo_factory.news.return_value
            news_repo.mark_published.assert_called_once_with(123)


class TestPublishDirectToChannel:
    """Тесты для метода _publish_direct_to_channel()."""

    @pytest.fixture
    def mock_repo_factory(self):
        """Создаёт мок фабрики репозиториев."""
        factory = MagicMock(spec=RepositoryFactory)
        factory.posts = MagicMock(return_value=AsyncMock())
        factory.events = MagicMock(return_value=AsyncMock())
        factory.news = MagicMock(return_value=AsyncMock())

        # Настраиваем publishers mock с правильным return value для get_by_id
        publishers_repo_mock = AsyncMock()
        mock_publisher = MagicMock()
        mock_publisher.channel_id = -1001
        mock_publisher.title = 'Test Channel'
        publishers_repo_mock.get_by_id = AsyncMock(return_value=mock_publisher)
        factory.publishers = MagicMock(return_value=publishers_repo_mock)
        return factory

    @pytest.fixture
    def orchestrator(self, mock_repo_factory):
        """Создаёт NewsOrchestrator с моками."""
        orch = NewsOrchestrator(
            repo_factory=mock_repo_factory,
            notification_service=None,
        )
        orch._running = True
        return orch

    @pytest.mark.asyncio
    async def test_publish_direct_to_channel_success(self, orchestrator, mock_repo_factory):
        """Успешная публикация в конкретный канал."""
        with patch.object(orchestrator, '_publish_to_telegram_channel', new_callable=AsyncMock) as mock_publish:
            await orchestrator._publish_direct_to_channel(123, "Текст новости", -1001)

            mock_publish.assert_called_once_with(-1001, "Текст новости")

            # Проверка вызова mark_published
            news_repo = mock_repo_factory.news.return_value
            news_repo.mark_published.assert_called_once_with(123)


class TestNotifyAllSubscribers:
    """Тесты для метода notify_all_subscribers()."""

    @pytest.fixture
    def mock_bot(self):
        """Создаёт мок бота."""
        bot = AsyncMock(spec=Bot)
        bot.send_message = AsyncMock()
        return bot

    @pytest.fixture
    def notification_service(self, mock_bot):
        """Создаёт NotificationService с моком бота."""
        return NotificationService(bot=mock_bot)

    @pytest.mark.asyncio
    async def test_notify_all_subscribers_ignore_preferences(self, notification_service, mock_bot):
        """Рассылка всем подписчикам с игнорированием предпочтений."""
        # Мокаем базу данных
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.user_id_encrypted = 'encrypted_id'
        mock_user.role = 'user'
        mock_user.has_subscription = True

        with patch('services.telegram.notification.get_database_service') as mock_db, \
             patch('services.telegram.notification.decrypt_user_id', return_value=12345), \
             patch('services.telegram.notification.select') as mock_select:

            # Настройка мока сессии
            mock_session = AsyncMock()
            mock_session.refresh = AsyncMock()
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_context.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_user]
            mock_session.execute.return_value = mock_result

            mock_db.return_value.session_context.return_value = mock_context
            mock_select.return_value.where.return_value = MagicMock()

            # Вызов метода
            result = await notification_service.notify_all_subscribers(
                news_text="Тестовая новость",
                news_id=123,
                ignore_preferences=True,
            )

            # Проверка
            assert result >= 0
            mock_bot.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_notify_all_subscribers_skip_admins(self, notification_service, mock_bot):
        """Админы пропускаются при рассылке."""
        mock_admin = MagicMock()
        mock_admin.id = 1
        mock_admin.user_id_encrypted = 'encrypted_id'
        mock_admin.role = 'admin'  # Админ
        mock_admin.has_subscription = True

        with patch('services.telegram.notification.get_database_service') as mock_db, \
             patch('services.telegram.notification.select') as mock_select:

            mock_session = AsyncMock()
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_context.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_admin]
            mock_session.execute.return_value = mock_result

            mock_db.return_value.session_context.return_value = mock_context
            mock_select.return_value.where.return_value = MagicMock()

            # Вызов метода
            await notification_service.notify_all_subscribers(
                news_text="Тестовая новость",
                news_id=123,
                ignore_preferences=True,
            )

            # Бот не должен отправлять сообщения админу
            mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_all_subscribers_no_bot(self):
        """Рассылка без инициализированного бота."""
        service = NotificationService(bot=None)

        mock_user = MagicMock()
        mock_user.role = 'user'
        mock_user.has_subscription = True

        with patch('services.telegram.notification.get_database_service') as mock_db, \
             patch('services.telegram.notification.select') as mock_select:

            mock_session = AsyncMock()
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_context.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_user]
            mock_session.execute.return_value = mock_result

            mock_db.return_value.session_context.return_value = mock_context
            mock_select.return_value.where.return_value = MagicMock()

            # Вызов метода
            result = await service.notify_all_subscribers(
                news_text="Тестовая новость",
                news_id=123,
                ignore_preferences=True,
            )

            # Должно вернуть 0 отправленных
            assert result == 0
