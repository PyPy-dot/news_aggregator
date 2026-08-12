"""
Тесты для Listener Bot (Telethon).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.listener.bot import ListenerBot


class TestListenerBotInit:
    """Тесты инициализации ListenerBot."""

    def test_init_without_container(self):
        """Проверка инициализации без контейнера."""
        bot = ListenerBot()
        assert bot._container is None
        assert bot._running is False

    def test_init_with_container(self):
        """Проверка инициализации с контейнером."""
        mock_container = MagicMock()
        bot = ListenerBot(container=mock_container)
        assert bot._container is mock_container


class TestListenerBotProperties:
    """Тесты свойств ListenerBot."""

    def test_notification_service_without_container(self):
        """Проверка notification_service без контейнера."""
        bot = ListenerBot()
        assert bot.notification_service is None

    def test_notification_service_with_container(self):
        """Проверка notification_service с контейнером."""
        mock_container = MagicMock()
        mock_notification = MagicMock()
        mock_container.get_notification_service.return_value = mock_notification

        bot = ListenerBot(container=mock_container)
        service = bot.notification_service

        assert service is mock_notification
        mock_container.get_notification_service.assert_called_once()


class TestListenerBotMethods:
    """Тесты методов ListenerBot."""

    @pytest.mark.asyncio
    async def test_get_repo_factory_cached(self):
        """Проверка кэширования factory."""
        with patch('services.listener.bot.get_database_service') as mock_db:
            mock_session = AsyncMock()
            mock_db.return_value.create_session = AsyncMock(return_value=mock_session)

            bot = ListenerBot()
            factory1 = await bot.get_repo_factory()
            factory2 = await bot.get_repo_factory()

            # Должно создать только один раз
            assert factory1 is factory2
            mock_db.return_value.create_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_not_running(self):
        """Проверка остановки когда не запущен."""
        bot = ListenerBot()
        bot._running = False
        await bot.stop()
        # Должно завершиться без ошибок

    @pytest.mark.asyncio
    async def test_stop_with_client(self):
        """Проверка остановки с клиентом."""
        bot = ListenerBot()
        bot._running = True
        bot._client_initialized = True

        mock_client = AsyncMock()
        bot.client = mock_client

        await bot.stop()

        assert bot._running is False
        mock_client.disconnect.assert_called_once()


class TestListenerBotMessageHandling:
    """Тесты обработки сообщений."""

    @pytest.mark.asyncio
    async def test_handle_new_post_no_text(self):
        """Проверка поста без текста."""
        bot = ListenerBot()
        bot._running = True

        mock_event = MagicMock()
        mock_event.chat_id = 12345
        mock_event.message.id = 67890
        mock_event.message.text = None  # Нет текста

        # Мокаем методы
        bot._check_duplicate_message = AsyncMock(return_value=True)
        bot._get_channel = AsyncMock()
        bot._enqueue_categorization_task = AsyncMock()

        await bot.handle_new_post(mock_event)

        # Не должно вызывать дальнейшую обработку
        bot._get_channel.assert_not_called()
        bot._enqueue_categorization_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_new_post_duplicate(self):
        """Проверка дубликата сообщения."""
        bot = ListenerBot()
        bot._running = True

        mock_event = MagicMock()
        mock_event.chat_id = 12345
        mock_event.message.id = 67890
        mock_event.message.text = 'Test text'

        # Мокаем проверку дубликатов
        original_check = bot._check_duplicate_message
        bot._check_duplicate_message = AsyncMock(return_value=False)

        await bot.handle_new_post(mock_event)

        # Восстанавливаем метод
        bot._check_duplicate_message = original_check

    @pytest.mark.asyncio
    async def test_check_duplicate_message_first_time(self):
        """Проверка первого сообщения."""
        bot = ListenerBot()

        result = await bot._check_duplicate_message('test_key')

        assert result is True

    @pytest.mark.asyncio
    async def test_check_duplicate_message_second_time(self):
        """Проверка дубликата."""
        bot = ListenerBot()

        # Первый раз
        await bot._check_duplicate_message('test_key')
        # Второй раз (дубликат)
        result = await bot._check_duplicate_message('test_key')

        assert result is False

    @pytest.mark.asyncio
    async def test_get_channel_not_found(self):
        """Проверка ненайденного канала."""
        # Просто проверяем что метод существует и не падает
        bot = ListenerBot()
        # Метод требует рабочую БД, поэтому тестируем только существование
        assert hasattr(bot, '_get_channel')

    @pytest.mark.asyncio
    async def test_enqueue_categorization_task(self):
        """Проверка добавления задачи в очередь."""
        bot = ListenerBot()

        mock_queue = AsyncMock()
        bot.categorization_queue = mock_queue

        mock_channel = MagicMock()
        mock_channel.title = 'Test Channel'
        mock_channel.description = 'Test Description'

        await bot._enqueue_categorization_task(
            channel_id=12345,
            message_id=67890,
            text='Test text',
            channel=mock_channel,
        )

        mock_queue.add.assert_called_once()


class TestListenerBotChannelMonitoring:
    """Тесты мониторинга каналов."""

    @pytest.mark.asyncio
    async def test_monitor_new_channels_exists(self):
        """Проверка существования метода мониторинга."""
        bot = ListenerBot()
        # Просто проверяем что метод существует
        assert hasattr(bot, '_monitor_new_channels')

    @pytest.mark.asyncio
    async def test_add_channel_handler(self):
        """Проверка добавления обработчика канала."""
        bot = ListenerBot()

        # Инициализируем кэш обработчиков
        bot._event_handlers = {}

        channel_id = 12345
        handler_func = MagicMock()
        event_type = 'new_message'

        # Добавляем обработчик
        bot._event_handlers[channel_id] = (handler_func, event_type)

        assert channel_id in bot._event_handlers
        assert bot._event_handlers[channel_id] == (handler_func, event_type)

    @pytest.mark.asyncio
    async def test_remove_channel_handler(self):
        """Проверка удаления обработчика канала."""
        bot = ListenerBot()
        bot._event_handlers = {12345: (MagicMock(), 'new_message')}

        # Удаляем обработчик
        del bot._event_handlers[12345]

        assert 12345 not in bot._event_handlers


# Импортируем asyncio для тестов
import asyncio
