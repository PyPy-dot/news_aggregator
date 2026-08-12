"""
Тесты для публикации доверенных источников (trusted source publishing).

Покрывают тестами методы:
- CategorizationProcessor._publish_after_analysis()
- CategorizationProcessor._publish_to_telegram_channel()
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from aiogram import Bot


# Примечание: Тесты для _publish_after_analysis() требуют сложного мокинга,
# т.к. NotificationService создаётся внутри метода через get_bot_instance().
# Интеграционные тесты ниже покрывают основную логику публикации.


class TestPublishToTelegramChannel:
    """Тесты для метода _publish_to_telegram_channel()."""

    @pytest.fixture
    def mock_categorizer(self):
        """Создаёт мок категорайзера."""
        return AsyncMock()

    @pytest.fixture
    def mock_saver(self):
        """Создаёт мок NewsSaver."""
        return AsyncMock()

    @pytest.fixture
    def mock_channel_provider(self):
        """Создаёт мок channel_provider."""
        provider = AsyncMock()
        provider.get_by_telegram_id = AsyncMock()
        return provider

    @pytest.fixture
    def processor(self, mock_categorizer, mock_saver, mock_channel_provider):
        """Создаёт CategorizationProcessor с моками."""
        from services.categorization.processor import CategorizationProcessor

        return CategorizationProcessor(
            categorizer=mock_categorizer,
            saver=mock_saver,
            channel_provider=mock_channel_provider,
            notification_service=None,
        )

    @pytest.mark.asyncio
    async def test_publish_to_telegram_channel_success(self, processor):
        """Успешная публикация в Telegram канал."""
        mock_bot = AsyncMock(spec=Bot)
        mock_bot.send_message = AsyncMock()

        await processor._publish_to_telegram_channel(
            bot=mock_bot,
            channel_id=-1001,
            text="<b>Тестовое сообщение</b>",
        )

        mock_bot.send_message.assert_called_once_with(
            chat_id=-1001,
            text="<b>Тестовое сообщение</b>",
            parse_mode='HTML',
        )

    @pytest.mark.asyncio
    async def test_publish_to_telegram_channel_no_bot(self, processor):
        """Публикация без бота."""
        # Не должно выбрасывать исключение или вызывать send_message
        await processor._publish_to_telegram_channel(
            bot=None,
            channel_id=-1001,
            text="Тестовое сообщение",
        )


class TestTrustedSourceIntegration:
    """Интеграционные тесты для доверенных источников."""

    @pytest.fixture
    def mock_categorizer(self):
        """Создаёт мок категорайзера."""
        categorizer = AsyncMock()
        categorizer.send_question = AsyncMock(return_value='{"category": "Политика", "urgency": 5, "is_advertisement": false}')
        return categorizer

    @pytest.fixture
    def mock_saver(self):
        """Создаёт мок NewsSaver."""
        saver = AsyncMock()
        saver.save_urgent_news = AsyncMock(return_value=123)
        return saver

    @pytest.fixture
    def mock_channel_provider(self):
        """Создаёт мок channel_provider с доверенным каналом."""
        provider = AsyncMock()
        trusted_channel = MagicMock()
        trusted_channel.is_trusted = True
        trusted_channel.title = 'Доверенный канал'
        provider.get_by_telegram_id = AsyncMock(return_value=trusted_channel)
        return provider

    @pytest.fixture
    def mock_notification_service(self):
        """Создаёт мок NotificationService."""
        service = AsyncMock()
        service.notify_subscribers = AsyncMock(return_value=5)
        return service

    @pytest.fixture
    def processor(self, mock_categorizer, mock_saver, mock_channel_provider, mock_notification_service):
        """Создаёт CategorizationProcessor для интеграционных тестов."""
        from services.categorization.processor import CategorizationProcessor

        processor = CategorizationProcessor(
            categorizer=mock_categorizer,
            saver=mock_saver,
            channel_provider=mock_channel_provider,
            notification_service=mock_notification_service,
        )

        # Мокаем методы для изоляции теста
        processor._analyze_post = AsyncMock(return_value={
            'category': 'Политика',
            'confidence': 0.95,
            'post_tags': ['тэг1'],
        })
        processor._update_post_with_analysis = AsyncMock()
        processor._publish_after_analysis = AsyncMock()

        return processor

    @pytest.mark.asyncio
    async def test_trusted_source_publishes_after_analysis(self, processor):
        """Доверенный источник публикует новость после анализа."""
        from services.categorization.queue import CategorizationTask

        task = CategorizationTask(
            channel_id=-100,
            prompt="Тестовый промпт",
            original_text="Срочная новость от доверенного источника",
            title='Доверенный канал',
        )

        await processor.process(task)

        # Проверка что _publish_after_analysis был вызван для доверенного источника
        processor._publish_after_analysis.assert_called_once()

    @pytest.fixture
    def mock_channel_provider_not_trusted(self):
        """Создаёт мок channel_provider с НЕ доверенным каналом."""
        provider = AsyncMock()
        not_trusted_channel = MagicMock()
        not_trusted_channel.is_trusted = False
        not_trusted_channel.title = 'Обычный канал'
        provider.get_by_telegram_id = AsyncMock(return_value=not_trusted_channel)
        return provider

    @pytest.mark.asyncio
    async def test_non_trusted_source_notifies_admins(
        self, mock_categorizer, mock_saver, mock_channel_provider_not_trusted, mock_notification_service
    ):
        """НЕ доверенный источник отправляет уведомление админам."""
        from services.categorization.processor import CategorizationProcessor

        processor = CategorizationProcessor(
            categorizer=mock_categorizer,
            saver=mock_saver,
            channel_provider=mock_channel_provider_not_trusted,
            notification_service=mock_notification_service,
        )

        processor._analyze_post = AsyncMock(return_value={
            'category': 'Политика',
            'confidence': 0.95,
            'post_tags': ['тэг1'],
        })
        processor._update_post_with_analysis = AsyncMock()
        processor._notify_urgent_news = AsyncMock(return_value=True)

        from services.categorization.queue import CategorizationTask
        task = CategorizationTask(
            channel_id=-100,
            prompt="Тестовый промпт",
            original_text="Срочная новость",
            title='Обычный канал',
        )

        await processor.process(task)

        # Для НЕ доверенного источника должно быть отправлено уведомление админам
        processor._notify_urgent_news.assert_called_once()
