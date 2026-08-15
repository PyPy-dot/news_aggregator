"""
Web Admin Service — сервис для запуска админ-панели.

Интегрируется с основным приложением и запускает FastAPI сервер
для администрирования системы.
"""

import asyncio
import logging
import uvicorn
from typing import Optional

logger = logging.getLogger(__name__)


class UvicornCancelledErrorFilter(logging.Filter):
    """Фильтр для подавления CancelledError traceback от uvicorn lifespan.

    При graceful shutdown uvicorn логирует CancelledError как ERROR с traceback
    (lifespan/on.py:97). Это ожидаемое поведение — приложение завершается.
    """

    def filter(self, record):
        try:
            msg = record.getMessage()
            if "CancelledError" in msg and "lifespan" in msg:
                return False
        except Exception:
            pass
        # Также проверяем exc_info напрямую
        if record.exc_info and isinstance(record.exc_info[1], asyncio.CancelledError):
            return False
        return True


class WebAdminService:
    """
    Сервис для запуска Web Admin панели.

    Usage:
        service = WebAdminService(host="0.0.0.0", port=8001)
        await service.start()
        # ... работает в фоне ...
        await service.stop()
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8001,
        reload: bool = False,
        log_level: str = "info",
    ):
        """
        Инициализировать сервис.

        Args:
            host: Хост для прослушивания
            port: Порт для прослушивания
            reload: Перезагрузка при изменении кода (для разработки)
            log_level: Уровень логирования
        """
        self.host = host
        self.port = port
        self.reload = reload
        self.log_level = log_level

        self._server: Optional[uvicorn.Server] = None
        self._config: Optional[uvicorn.Config] = None
        self._running = False

    async def start(self) -> None:
        """
        Запустить Web Admin сервер.

        Запускает FastAPI приложение в фоновом режиме.
        """
        if self._running:
            logger.warning("Web Admin уже запущен")
            return

        # Проверяем и создаём учётные данные если нужно
        await self._ensure_credentials()

        logger.info(f"🚀 Запуск Web Admin сервера на {self.host}:{self.port}...")

        # Импортируем приложение
        from services.web_admin.api.app import app

        # Создаём конфигурацию uvicorn
        self._config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            reload=self.reload,
            log_level=self.log_level,
            access_log=True,
            lifespan="auto",
        )

        # Подавляем CancelledError traceback от uvicorn lifespan при
        # graceful shutdown (lifespan/on.py:97 — logger.error(exc_info=exc)).
        # Приложение корректно завершается, это косметический шум.
        logging.getLogger("uvicorn.error").addFilter(
            UvicornCancelledErrorFilter()
        )

        # Создаём сервер
        self._server = uvicorn.Server(self._config)

        # Запускаем в фоне
        self._running = True
        await self._server.serve()

    async def _ensure_credentials(self) -> None:
        """
        Проверить и создать учётные данные если не существуют.

        Запрашивает логин и пароль через консоль при первом запуске.
        """
        from services.web_admin.session_manager import get_session_manager

        manager = get_session_manager()

        if manager.credentials_exist():
            logger.info("✅ Учётные данные Web Admin найдены")
            return

        # Запрашиваем учётные данные через консоль
        print("\n" + "=" * 60)
        print("🔐 ПЕРВЫЙ ЗАПУСК WEB ADMIN — СОЗДАНИЕ УЧЁТНОЙ ЗАПИСИ")
        print("=" * 60)
        print()
        print("Введите данные для входа в админ-панель:")
        print()

        # Ввод логина
        while True:
            username = input("  Логин (мин. 3 символа): ").strip()
            if len(username) >= 3:
                break
            print("  ❌ Логин должен быть не менее 3 символов")

        # Ввод пароля
        while True:
            password = input("  Пароль (мин. 6 символов): ").strip()
            if len(password) >= 6:
                break
            print("  ❌ Пароль должен быть не менее 6 символов")

        # Подтверждение пароля
        while True:
            password_confirm = input("  Подтвердите пароль: ").strip()
            if password == password_confirm:
                break
            print("  ❌ Пароли не совпадают")

        print()
        print("🔧 Создание учётной записи...")

        try:
            manager.create_credentials(username, password)
            print(f"✅ Учётная запись '{username}' успешно создана!")
            print()
            print("Теперь вы можете войти в админ-панель:")
            print(f"   URL: http://localhost:{self.port}")
            print(f"   Логин: {username}")
            print()
        except Exception as e:
            print(f"❌ Ошибка создания учётной записи: {e}")
            raise

        print("=" * 60)
        print()

    async def stop(self) -> None:
        """
        Остановить Web Admin сервер.
        """
        if not self._running:
            return

        logger.info("🛑 Остановка Web Admin сервера...")

        if self._server:
            self._server.should_exit = True

        self._running = False
        logger.info("✅ Web Admin сервер остановлен")

    @property
    def is_running(self) -> bool:
        """Проверить, запущен ли сервер."""
        return self._running

    @property
    def url(self) -> str:
        """Получить URL админ-панели."""
        return f"http://localhost:{self.port}"
