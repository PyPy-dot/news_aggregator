"""
Tests for NotificationService.
"""

import asyncio
import pytest
import logging
from unittest.mock import AsyncMock, patch, MagicMock

from services.telegram.notification import NotificationService

# Настраиваем логирование для тестов
logging.basicConfig(level=logging.INFO)


class TestNotificationService:
    """Тесты для NotificationService."""

    def test_init(self):
        """Тест инициализации сервиса."""
        service = NotificationService()
        # Сервис не хранит admin_chat_id — получает админов из БД
        assert service._bot is None

    @pytest.mark.asyncio
    async def test_notify_urgent_news_no_admins(self, caplog):
        """Тест уведомления о срочной новости без админов."""
        caplog.set_level(logging.WARNING)
        service = NotificationService()

        # Мок для _get_admin_ids — возвращаем пустой список
        with patch.object(service, '_get_admin_ids', return_value=[]):
            await service.notify_urgent_news(
                post_id=42,
                text="Breaking News",
                category="Политика",
                urgency=5,
                channel_title="Test Channel"
            )

        # Проверяем логирование
        assert "Нет админов" in caplog.text

    @pytest.mark.asyncio
    async def test_notify_urgent_news_with_admins(self, caplog):
        """Тест уведомления о срочной новости с админами."""
        caplog.set_level(logging.INFO)

        # Мок для бота
        mock_bot = AsyncMock()
        service = NotificationService(bot=mock_bot)

        # Мок для _get_admin_ids
        with patch.object(service, '_get_admin_ids', return_value=[123456]):
            await service.notify_urgent_news(
                post_id=42,
                text="Breaking News",
                category="Политика",
                urgency=5,
                channel_title="Test Channel"
            )

        # Проверяем вызов бота
        mock_bot.send_message.assert_called_once()
        assert "СРОЧНАЯ" in mock_bot.send_message.call_args[0][1]

    @pytest.mark.asyncio
    async def test_notify_pending_news_no_admins(self, caplog):
        """Тест уведомления о плановой новости без админов."""
        caplog.set_level(logging.WARNING)
        service = NotificationService()

        with patch.object(service, '_get_admin_ids', return_value=[]):
            await service.notify_pending_news(
                post_id=100,
                text="Regular News",
                category="Экономика",
                channel_title="Test Channel"
            )

        assert "Нет админов" in caplog.text

    @pytest.mark.asyncio
    async def test_notify_pending_news_with_admins(self, caplog):
        """Тест уведомления о плановой новости с админами."""
        caplog.set_level(logging.INFO)

        mock_bot = AsyncMock()
        service = NotificationService(bot=mock_bot)

        with patch.object(service, '_get_admin_ids', return_value=[123456]):
            await service.notify_pending_news(
                post_id=100,
                text="Regular News",
                category="Экономика",
                channel_title="Test Channel"
            )

        mock_bot.send_message.assert_called_once()
        assert "модерации" in mock_bot.send_message.call_args[0][1]

    @pytest.mark.asyncio
    async def test_notify_direct_publish(self, caplog):
        """Тест уведомления о прямой публикации."""
        caplog.set_level(logging.INFO)

        mock_bot = AsyncMock()
        service = NotificationService(bot=mock_bot)

        with patch.object(service, '_get_admin_ids', return_value=[123456]):
            await service.notify_direct_publish(
                post_id=55,
                channel_title="Trusted Channel",
                category="Важное",
                text="Direct publish text"
            )

        mock_bot.send_message.assert_called_once()
        assert "ОПУБЛИКОВАНО НАПРЯМУЮ" in mock_bot.send_message.call_args[0][1]

    @pytest.mark.asyncio
    async def test_notify_no_bot(self, caplog):
        """Тест уведомления без инициализированного бота."""
        caplog.set_level(logging.WARNING)
        service = NotificationService()

        # Бот не установлен
        assert service._bot is None

        with patch.object(service, '_get_admin_ids', return_value=[123456]):
            await service.notify_urgent_news(
                post_id=42,
                text="Test",
                category="Тест",
                urgency=5,
                channel_title="Test"
            )

        assert "Бот не инициализирован" in caplog.text


class TestNotificationServiceRetry:
    """Тесты для retry логики при отправке уведомлений."""

    @pytest.mark.asyncio
    async def test_send_with_timeout_retry_success(self, caplog):
        """Тест успешной отправки после таймаута."""
        caplog.set_level(logging.WARNING)
        mock_bot = AsyncMock()

        # Первая попытка — таймаут, вторая — успех
        mock_bot.send_message.side_effect = [
            asyncio.TimeoutError("Request timeout"),
            None  # Успех
        ]

        service = NotificationService(bot=mock_bot)

        # Мок для _get_admin_ids
        with patch.object(service, '_get_admin_ids', return_value=[123456]):
            await service.notify_urgent_news(
                post_id=42,
                text="Test",
                category="Тест",
                urgency=5,
                channel_title="Test"
            )

        # Проверяем что было 2 вызова (первый с таймаутом, второй успешный)
        assert mock_bot.send_message.call_count == 2
        assert "Таймаут отправки" in caplog.text

    @pytest.mark.asyncio
    async def test_notify_urgent_news_timeout_with_retry(self, caplog):
        """Тест что notify_urgent_news делает retry при таймауте."""
        caplog.set_level(logging.WARNING)
        mock_bot = AsyncMock()

        # Все 3 попытки — таймаут
        mock_bot.send_message.side_effect = [
            asyncio.TimeoutError("Timeout 1"),
            asyncio.TimeoutError("Timeout 2"),
            asyncio.TimeoutError("Timeout 3")
        ]

        service = NotificationService(bot=mock_bot)

        with patch.object(service, '_get_admin_ids', return_value=[123456]):
            await service.notify_urgent_news(
                post_id=42,
                text="Test",
                category="Тест",
                urgency=5,
                channel_title="Test"
            )

        # Проверяем что было 3 вызова (retry логика)
        assert mock_bot.send_message.call_count == 3
        assert "Таймаут отправки" in caplog.text
        assert "Ошибка отправки уведомления админу" in caplog.text

    @pytest.mark.asyncio
    async def test_notify_urgent_news_non_timeout_error(self, caplog):
        """Тест что не временные ошибки логируются корректно."""
        caplog.set_level(logging.ERROR)
        mock_bot = AsyncMock()

        # Ошибка не связана с таймаутом — retry не должно быть
        mock_bot.send_message.side_effect = Exception("API Error")

        service = NotificationService(bot=mock_bot)

        with patch.object(service, '_get_admin_ids', return_value=[123456]):
            await service.notify_urgent_news(
                post_id=42,
                text="Test",
                category="Тест",
                urgency=5,
                channel_title="Test"
            )

        # Проверяем что был только 1 вызов (без retry для не временных ошибок)
        assert mock_bot.send_message.call_count == 1
        assert "Ошибка отправки уведомления админу" in caplog.text
