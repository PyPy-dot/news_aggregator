"""
Tests for Listener Bot Authorization Service.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.listener.auth_service import (
    AuthorizationService,
    get_auth_service,
    init_auth_service,
)


@pytest.fixture
def mock_bot():
    """Mock Telegram bot."""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def auth_service(mock_bot):
    """Create AuthorizationService instance."""
    return AuthorizationService(bot=mock_bot, admin_id=123456)


class TestAuthorizationService:
    """Tests for AuthorizationService."""

    @pytest.mark.asyncio
    async def test_send_code_request(self, auth_service, mock_bot):
        """Test sending code request message."""
        await auth_service.send_code_request('+79991234567')

        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args[1]['chat_id'] == 123456
        assert 'Требуется код авторизации' in call_args[1]['text']
        assert '+79991234567' in call_args[1]['text']

    @pytest.mark.asyncio
    async def test_wait_for_code_timeout(self, auth_service):
        """Test waiting for code with timeout."""
        # Устанавливаем очень короткий таймаут
        code = await auth_service.wait_for_code(timeout=0.1)

        assert code is None

    @pytest.mark.asyncio
    async def test_wait_for_code_success(self, auth_service):
        """Test successfully receiving code."""
        # Устанавливаем код в отдельной задаче
        async def set_code_later():
            await asyncio.sleep(0.1)
            auth_service.set_code('12345')

        asyncio.create_task(set_code_later())

        # Ждём код
        code = await auth_service.wait_for_code(timeout=5.0)

        assert code == '12345'

    @pytest.mark.asyncio
    async def test_set_code(self, auth_service):
        """Test setting code."""
        auth_service.set_code('54321')

        # Проверяем, что событие установлено
        assert auth_service._code_event.is_set()
        assert auth_service._received_code == '54321'

    @pytest.mark.asyncio
    async def test_send_password_request(self, auth_service, mock_bot):
        """Test sending password request message."""
        await auth_service.send_password_request()

        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert call_args[1]['chat_id'] == 123456
        assert 'двухфакторной аутентификации' in call_args[1]['text']

    @pytest.mark.asyncio
    async def test_wait_for_password_timeout(self, auth_service):
        """Test waiting for password with timeout."""
        password = await auth_service.wait_for_password(timeout=0.1)

        assert password is None

    @pytest.mark.asyncio
    async def test_wait_for_password_success(self, auth_service):
        """Test successfully receiving password."""
        async def set_password_later():
            await asyncio.sleep(0.1)
            auth_service.set_password('mypassword')

        asyncio.create_task(set_password_later())

        password = await auth_service.wait_for_password(timeout=5.0)

        assert password == 'mypassword'

    @pytest.mark.asyncio
    async def test_set_password(self, auth_service):
        """Test setting password."""
        auth_service.set_password('secret123')

        assert auth_service._password_event.is_set()
        assert auth_service._received_password == 'secret123'

    @pytest.mark.asyncio
    async def test_reset(self, auth_service):
        """Test resetting service state."""
        # Устанавливаем код и пароль
        auth_service.set_code('12345')
        auth_service.set_password('secret')

        # Сбрасываем
        auth_service.reset()

        # Проверяем, что всё сброшено
        assert not auth_service._code_event.is_set()
        assert not auth_service._password_event.is_set()
        assert auth_service._received_code is None
        assert auth_service._received_password is None

    @pytest.mark.asyncio
    async def test_code_cleared_after_retrieval(self, auth_service):
        """Test that code is cleared after retrieval."""
        auth_service.set_code('12345')
        code = await auth_service.wait_for_code(timeout=1.0)

        assert code == '12345'
        assert auth_service._received_code is None  # Очищено после получения

    @pytest.mark.asyncio
    async def test_password_cleared_after_retrieval(self, auth_service):
        """Test that password is cleared after retrieval."""
        auth_service.set_password('secret')
        password = await auth_service.wait_for_password(timeout=1.0)

        assert password == 'secret'
        assert auth_service._received_password is None  # Очищено после получения


class TestGlobalAuthService:
    """Tests for global auth service functions."""

    def test_init_auth_service(self, mock_bot):
        """Test initializing global auth service."""
        service = init_auth_service(mock_bot, 123456)

        assert service is not None
        assert get_auth_service() is service

    def test_get_auth_service_not_initialized(self):
        """Test getting auth service before initialization."""
        # Сбрасываем глобальный сервис
        import services.listener.auth_service as auth_module
        auth_module._auth_service = None

        service = get_auth_service()
        assert service is None
