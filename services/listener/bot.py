"""
Listener Bot — мониторинг Telegram каналов.

Использует Telethon для прослушивания каналов.
Корректная инициализация и завершение ресурсов.
"""

import asyncio
import logging
from typing import Optional, Set, Any

from telethon import TelegramClient, events

from typing import TYPE_CHECKING

from database import RepositoryFactory
from database.repositories.channels import ChannelRepository
from services.database import get_database_service
# Используем новый модуль categorization напрямую
from services.categorization.queue import CategorizationQueue, CategorizationTask
from services.categorization.processor import CategorizationProcessor
from services.categorization.saver import NewsSaver
from services.categorization.classifier import NewsClassifier
from services.ai_agent.agents.categorizer import CategorizerAgent
from services.telegram.notification import NotificationService
from config.settings import settings

if TYPE_CHECKING:
    from services.core.container import Container

logger = logging.getLogger(__name__)


class ListenerBot:
    """
    Бот для мониторинга Telegram каналов.

    Делегирует обработку новостей сервисам:
    - CategorizationService — категоризация
    - NotificationService — уведомления админам
    """

    def __init__(self, container: Optional['Container'] = None) -> None:
        """
        Инициализация бота.

        Args:
            container: DI контейнер (опционально, для получения сервисов)
        """
        self._container = container

        # Telegram клиент
        self.client: Optional[TelegramClient] = None
        self._client_initialized = False

        # Сервисы
        self.categorization_service: Optional[CategorizationService] = None
        self._notification_service: Optional[NotificationService] = None

        # Кэш обработанных сообщений
        self._processed_messages: Set[str] = set()
        self._messages_lock = asyncio.Lock()

        # Factory для репозиториев
        self._repo_factory: Optional[RepositoryFactory] = None

        # Флаг работы
        self._running = False

        # Задача обработки очереди
        self._queue_task: Optional[asyncio.Task] = None

        # Кэш каналов для динамического добавления/удаления
        self._channel_ids: Set[int] = set()
        self._channels_lock = asyncio.Lock()

        # Хранение обработчиков по ID канала для возможности удаления
        self._event_handlers: dict[int, tuple] = {}  # channel_id -> (handler_func, event_type)
        self._handlers_lock = asyncio.Lock()

        # Задача мониторинга каналов (отслеживает добавления и удаления)
        self._channel_monitor_task: Optional[asyncio.Task] = None

    @property
    def notification_service(self) -> Optional[NotificationService]:
        """Получить NotificationService из контейнера или кэша."""
        if self._notification_service is None and self._container:
            self._notification_service = self._container.get_notification_service()
        return self._notification_service

    async def get_repo_factory(self) -> RepositoryFactory:
        """Получить фабрику репозиториев."""
        if self._repo_factory is None:
            db_service = get_database_service()
            self._db_session = await db_service.create_session()
            self._repo_factory = RepositoryFactory(self._db_session)
        return self._repo_factory

    async def check_session_freshness(self, session_name: str) -> dict:
        """
        Проверить состояние и свежесть сессии.

        Returns:
            dict с информацией о сессии:
            - exists: bool — файл сессии существует
            - authorized: bool — сессия авторизована
            - user_id: int | None — ID пользователя
            - username: str | None — username
            - last_active: datetime | None — последняя активность
            - is_fresh: bool — сессия активна (не старше 7 дней)
        """
        import os
        from datetime import datetime

        session_file = f"{session_name}.session"
        result = {
            'exists': False,
            'authorized': False,
            'user_id': None,
            'username': None,
            'last_active': None,
            'is_fresh': False,
            'session_age_days': None,
        }

        # Проверяем существование файла
        if not os.path.exists(session_file):
            logger.debug(f"📁 Файл сессии {session_file} не найден")
            return result

        result['exists'] = True
        logger.debug(f"📁 Файл сессии {session_file} найден")

        try:
            # Проверяем дату модификации файла
            mtime = os.path.getmtime(session_file)
            last_modified = datetime.fromtimestamp(mtime)
            result['last_active'] = last_modified

            age = datetime.now() - last_modified
            result['session_age_days'] = age.days
            result['is_fresh'] = age.days < 7  # Сессия считается свежей если < 7 дней

            logger.info(f"🕒 Возраст сессии: {age.days} дн. (свежая: {result['is_fresh']})")

        except Exception as e:
            logger.warning(f"⚠️ Не удалось проверить дату сессии: {e}")

        return result

    async def initialize(self) -> None:
        """
        Инициализировать клиент Telethon.

        Подключается к Telegram, но не запускает обработчики.
        """
        if self._client_initialized:
            logger.debug("Telegram клиент уже инициализирован")
            return

        logger.info("🔌 Инициализация Telegram клиента...")
        # Логируем только часть данных для безопасности
        phone_masked = settings.phone_number[:3] + '***' if len(settings.phone_number) > 3 else '***'
        logger.debug(f"API_ID: {settings.api_id}, API_HASH: {settings.api_hash[:8]}..., Phone: {phone_masked}")

        try:
            # Используем файловую сессию для сохранения авторизации между запусками
            session_name = 'userbot'
            session_file = f"{session_name}.session"
            logger.debug(f"📁 Использование сессии: {session_file}")

            # Проверяем, находится ли проект на сетевом диске (Yandex.Disk, Google Drive и т.д.)
            import os
            session_path = os.path.abspath(session_file)
            if 'Yandex.Disk' in session_path or 'Google Drive' in session_path or 'OneDrive' in session_path:
                logger.warning(
                    f"⚠️ Проект находится на сетевом диске ({session_path})!\n"
                    f"   Это может вызвать проблемы с блокировкой файла сессии.\n"
                    f"   Рекомендация: переместите проект в локальную папку."
                )

            # Проверяем состояние сессии перед подключением
            session_info = await self.check_session_freshness(session_name)
            if session_info['exists']:
                if session_info['is_fresh']:
                    logger.info(f"✅ Сессия свежая ({session_info['session_age_days']} дн.)")
                else:
                    logger.warning(f"⚠️ Сессия устарела ({session_info['session_age_days']} дн.) — возможна повторная авторизация")
            else:
                logger.info("📁 Сессия не найдена — потребуется авторизация")

            # Проверка прокси
            proxy_url = getattr(settings, 'telegram_proxy', None)
            mtproto_proxy = getattr(settings, 'telegram_mtproto_proxy', None)
            proxy = None

            # Сначала проверяем MTProto прокси (официальные прокси Telegram)
            if mtproto_proxy:
                logger.info(f"🔑 Использование MTProto прокси: {mtproto_proxy[:50]}...")
                try:
                    # Формат: server:port:secret или https://t.me/proxy?server=...&port=...&secret=...
                    import re
                    if 't.me/proxy' in mtproto_proxy:
                        # Парсим URL
                        match = re.search(r'server=([^&]+)&port=(\d+)&secret=([^\s&]+)', mtproto_proxy)
                        if match:
                            server, port, secret = match.groups()
                            proxy = (server, int(port), secret)
                    elif ':' in mtproto_proxy:
                        # Простой формат server:port:secret
                        parts = mtproto_proxy.strip().split(':')
                        if len(parts) >= 3:
                            proxy = (parts[0], int(parts[1]), parts[2])

                    if proxy:
                        logger.info(f"✅ MTProto прокси настроен: {proxy[0]}:{proxy[1]}")
                    else:
                        logger.warning(f"⚠️ Не удалось распарсить MTProto прокси")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка настройки MTProto прокси: {e}")

            # Если MTProto нет, проверяем обычный прокси
            elif proxy_url:
                logger.info(f"🔑 Использование прокси: {proxy_url}")
                try:
                    import socks
                    import urllib.parse

                    parsed = urllib.parse.urlparse(proxy_url)

                    # Определяем тип прокси
                    if parsed.scheme.lower() == 'socks5':
                        proxy = (socks.SOCKS5, parsed.hostname, parsed.port or 1080)
                    elif parsed.scheme.lower() == 'socks4':
                        proxy = (socks.SOCKS4, parsed.hostname, parsed.port or 1080)
                    elif parsed.scheme.lower() in ('http', 'https'):
                        # HTTP прокси
                        proxy = (socks.HTTP, parsed.hostname, parsed.port or 8080)
                    else:
                        # По умолчанию SOCKS5
                        proxy = (socks.SOCKS5, parsed.hostname, parsed.port or 1080)

                    logger.debug(f"✅ Прокси настроен: {parsed.scheme}://{parsed.hostname}:{parsed.port or 1080}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось настроить прокси: {e}. Подключаемся без прокси.")

            self.client = TelegramClient(
                session_name,
                api_id=settings.api_id,
                api_hash=settings.api_hash,
                connection_retries=10,
                retry_delay=2,
                timeout=60,
                use_ipv6=settings.telegram_use_ipv6,
                flood_sleep_threshold=300,
                auto_reconnect=False,
                proxy=proxy,
                # Указываем устройство как "официальный клиент" для доверия Telegram
                device_model="Telegram Desktop",
                system_version="Windows 10",
                app_version="4.9.2",
                lang_code="en",
                system_lang_code="en-US",
            )

            logger.debug("Подключение к Telegram...")
            try:
                await self.client.connect()
                logger.debug("✅ Подключение установлено")
                self._client_initialized = True

                # Проверяем авторизацию после подключения
                try:
                    is_authorized = await self.client.is_user_authorized()
                except Exception as auth_err:
                    error_str = str(auth_err)
                    # Проверяем на AuthKeyUnregisteredError или ошибку SQLite
                    if ('AuthKeyUnregistered' in type(auth_err).__name__ or
                        'no such table' in error_str or
                        'database disk image is malformed' in error_str):
                        logger.warning(f"⚠️ Сессия повреждена: {error_str}")
                        is_authorized = False
                        # Помечаем для удаления
                        self._client_initialized = False
                        await self.client.disconnect()
                        # Удаляем повреждённую сессию
                        import os
                        session_file = f"{session_name}.session"
                        session_journal = f"{session_name}.session-journal"
                        for f in [session_file, session_journal]:
                            if os.path.exists(f):
                                try:
                                    os.remove(f)
                                    logger.info(f"🗑️ Удалён файл сессии: {f}")
                                except Exception as remove_err:
                                    logger.warning(f"⚠️ Не удалось удалить {f}: {remove_err}")
                        # Переподключаемся с чистой сессией
                        logger.info("🔄 Переподключение с чистой сессией...")
                        self.client = TelegramClient(
                            session_name,
                            api_id=settings.api_id,
                            api_hash=settings.api_hash,
                            connection_retries=3,
                            retry_delay=1,
                            timeout=30,
                            use_ipv6=settings.telegram_use_ipv6,
                            flood_sleep_threshold=60,
                            auto_reconnect=True,
                            proxy=proxy,
                            device_model="Telegram Desktop",
                            system_version="Windows 10",
                            app_version="4.9.2",
                            lang_code="en",
                            system_lang_code="en-US",
                        )
                        await self.client.connect()
                        logger.info("✅ Подключение установлено после очистки сессии")
                        self._client_initialized = True
                        # Проверяем авторизацию ещё раз
                        is_authorized = await self.client.is_user_authorized()
                    else:
                        raise

                if is_authorized:
                    try:
                        me = await self.client.get_me()
                        logger.info(f"✅ Сессия активна: @{me.username} (ID: {me.id})")

                        # Проверяем, не истёк ли токен (попытка получить информацию)
                        try:
                            await self.client.get_me()
                            logger.info("✅ Токен сессии действителен")
                        except Exception as e:
                            logger.warning(f"⚠️ Токен сессии может быть недействителен: {e}")
                            # Помечаем сессию как неавторизованную
                            self._client_initialized = False
                            await self.client.disconnect()
                            raise
                    except Exception as me_err:
                        logger.error(f"❌ Ошибка получения информации о пользователе: {me_err}")
                        # Сессия повреждена - удаляем
                        import os
                        session_file = f"{session_name}.session"
                        if os.path.exists(session_file):
                            os.remove(session_file)
                            logger.info(f"🗑️ Файл сессии {session_file} удалён")
                        self._client_initialized = False
                        await self.client.disconnect()
                        raise

            except Exception as e:
                error_str = str(e)
                logger.error(f"❌ Ошибка подключения к Telegram: {type(e).__name__}: {e}")

                # Проверяем на ошибку SQLite
                if 'no such table' in error_str or 'database disk image is malformed' in error_str:
                    logger.error("🗄️ Обнаружено повреждение базы данных сессии!")
                    logger.error("   Причина: Файл сессии повреждён (возможно, из-за сетевого диска)")

                    # Удаляем все файлы сессии
                    import os
                    session_file = f"{session_name}.session"
                    session_journal = f"{session_name}.session-journal"
                    for f in [session_file, session_journal]:
                        if os.path.exists(f):
                            try:
                                os.remove(f)
                                logger.info(f"🗑️ Удалён файл: {f}")
                            except Exception as remove_err:
                                logger.warning(f"⚠️ Не удалось удалить {f}: {remove_err}")

                    logger.info("🔄 Пересоздание клиента с чистой сессией...")
                    # Пересоздаём клиент
                    self.client = TelegramClient(
                        session_name,
                        api_id=settings.api_id,
                        api_hash=settings.api_hash,
                        connection_retries=3,
                        retry_delay=1,
                        timeout=30,
                        use_ipv6=settings.telegram_use_ipv6,
                        flood_sleep_threshold=60,
                        auto_reconnect=True,
                        proxy=proxy,
                        device_model="Desktop",
                        system_version="10",
                        app_version="1.0.0",
                    )
                    await self.client.connect()
                    logger.info("✅ Подключение установлено после пересоздания сессии")
                    self._client_initialized = True
                else:
                    # Другие ошибки подключения
                    logger.info("🔄 Попытка пересоздать сессию...")
                    await self.client.disconnect()
                    # Удаляем файл сессии
                    import os
                    session_file = f"{session_name}.session"
                    if os.path.exists(session_file):
                        os.remove(session_file)
                        logger.info(f"🗑️ Сессия {session_file} удалена")
                    # Пересоздаём клиент
                    self.client = TelegramClient(
                        session_name,
                        api_id=settings.api_id,
                        api_hash=settings.api_hash,
                        connection_retries=3,
                        retry_delay=1,
                        timeout=30,
                        use_ipv6=settings.telegram_use_ipv6,
                        flood_sleep_threshold=60,
                        auto_reconnect=True,
                        proxy=proxy,
                        device_model="Desktop",
                        system_version="10",
                        app_version="1.0.0",
                    )
                    await self.client.connect()
                    logger.info("✅ Подключение установлено после пересоздания сессии")
                    self._client_initialized = True

            # Проверяем, есть ли строка сессии в окружении (для Docker/production)
            if settings.telegram_session_string:
                logger.info("🔐 Восстановление сессии из TELEGRAM_SESSION_STRING...")
                try:
                    from telethon.sessions import StringSession
                    await self.client.sign_in(StringSession(settings.telegram_session_string))
                    logger.info("✅ Сессия восстановлена из строки")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось восстановить сессию из строки: {e}")

            if not await self.client.is_user_authorized():
                logger.warning("⚠️ Требуется авторизация!")
                logger.info("📝 Для авторизации:")
                logger.info("   1. Откройте веб-админку: http://localhost:8001/console")
                logger.info("   2. Модальное окно появится автоматически")
                logger.info("   3. Введите код из Telegram в модалке или в этой консоли")
                logger.info("")

                # Запускаем единый процесс авторизации (блокирующий)
                # Поддерживает ввод кода из консоли ИЛИ из веб-интерфейса
                from services.web_admin.routes.listener_auth import run_auth_process

                auth_success = await run_auth_process(self)
                if not auth_success:
                    logger.error("❌ Авторизация не удалась — ListenerBot не будет работать")
                    return

                # После успешной авторизации получаем информацию о пользователе
                try:
                    me = await self.client.get_me()
                    if me:
                        logger.info(f"✅ UserBot авторизован: @{me.username} (ID: {me.id})")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось получить информацию о пользователе: {e}")
            else:
                # Уже был авторизован — информация получена выше в блоке is_authorized
                pass

            # Сохраняем строку сессии для будущего использования (опционально)
            # session_str = self.client.session.save()
            # logger.info(f"💾 Session string: {session_str}")

        except asyncio.CancelledError:
            logger.info("🛑 Инициализация ListenerBot отменена")
            raise
        except Exception as e:
            # Специальная обработка FloodWaitError и других ошибок
            import traceback
            error_msg = str(e)

            # FloodWaitError обработка
            if hasattr(e, 'seconds') and hasattr(e, 'message'):
                # Это FloodWaitError от Telethon
                wait_seconds = e.seconds
                wait_minutes = wait_seconds / 60
                wait_hours = wait_minutes / 60

                if wait_hours >= 1:
                    wait_msg = f"{wait_hours:.1f} ч. ({int(wait_minutes)} мин.)"
                elif wait_minutes >= 1:
                    wait_msg = f"{wait_minutes:.1f} мин. ({wait_seconds} сек.)"
                else:
                    wait_msg = f"{wait_seconds} сек."

                logger.error(
                    f"🚫 Telegram ограничивает запросы авторизации!\n"
                    f"   Причина: Слишком много запросов кода подтверждения\n"
                    f"   Время ожидания: {wait_msg}\n"
                    f"   Решение: Используйте другой номер или подождите до {wait_msg}\n"
                    f"   (Ошибка: FloodWaitError: {e.message})"
                )
            # Обработка ошибки доступа к файлу (WinError 1231, сетевая папка)
            elif 'WinError 1231' in error_msg or 'сетевая папка недоступна' in error_msg.lower() or 'Network location unavailable' in error_msg:
                logger.error(
                    f"🚫 Ошибка доступа к файлу сессии!\n"
                    f"   Причина: Проект находится на сетевом диске (Yandex.Disk/Google Drive)\n"
                    f"   Решение:\n"
                    f"   1. Переместите проект в локальную папку (не синхронизируемую)\n"
                    f"   2. Или добавьте '.session' файлы в исключения синхронизации\n"
                    f"   3. Или установите TELEGRAM_SESSION_STRING вместо файловой сессии"
                )
            # Обработка ошибки "database is locked"
            elif 'database is locked' in error_msg:
                logger.error(
                    f"🚫 База данных заблокирована!\n"
                    f"   Причина: Другой процесс использует базу данных\n"
                    f"   Решение:\n"
                    f"   1. Остановите другие экземпляры приложения\n"
                    f"   2. Переместите проект с сетевого диска (Yandex.Disk)\n"
                    f"   3. Используйте PostgreSQL вместо SQLite"
                )
            else:
                logger.error(f"❌ Ошибка инициализации Telegram клиента: {type(e).__name__}: {e}", exc_info=True)
                logger.debug(f"Traceback: {traceback.format_exc()}")

            # Не прерываем работу — ListenerBot может работать без авторизации
            # (будет пропущен при запуске в main.py)
            raise

    async def start(self) -> None:
        """
        Запустить бота.

        Инициализирует сервисы, регистрирует обработчики, запускает polling.
        """
        # Инициализируем клиент если нужно
        if not self._client_initialized:
            await self.initialize()

        # Проверяем, подключен ли клиент (может быть отключен после stop())
        if self.client and not self.client.is_connected():
            logger.info("🔄 Клиент отключен, подключаем заново...")
            await self.client.connect()
            self._client_initialized = True

        # Инициализация сервисов
        self._init_services()

        # Получаем каналы из БД
        logger.info("📚 Получение каналов из БД...")
        channel_ids = await self._get_channel_ids()
        logger.info(f"📋 Найдено каналов в БД: {len(channel_ids)}")

        # Сохраняем каналы в кэш
        async with self._channels_lock:
            self._channel_ids = set(channel_ids)

        if channel_ids:
            # Регистрируем обработчик для каждого канала
            async with self._handlers_lock:
                for channel_id in channel_ids:
                    handler = events.NewMessage(chats=[channel_id])
                    self.client.add_event_handler(
                        self.handle_new_post,
                        handler
                    )
                    self._event_handlers[channel_id] = (self.handle_new_post, handler)
            logger.info(
                f"✅ Обработчик событий добавлен для {len(channel_ids)} каналов"
            )
        else:
            logger.warning("⚠️ Нет каналов для мониторинга! Добавьте каналы через бота.")

        # Запускаем обработку очереди категоризации
        self._queue_task = asyncio.create_task(
            self._process_categorization_queue()
        )
        logger.info("✅ Обработка очереди категоризации запущена")

        # Запускаем мониторинг новых каналов
        self._channel_monitor_task = asyncio.create_task(
            self._monitor_new_channels()
        )
        logger.info("✅ Мониторинг новых каналов запущен")

        # Шина событий оркестратора запускается в Scheduler
        # ListenerBot только добавляет задачи в очередь категоризации

        self._running = True
        logger.info("👂 UserBot слушает события...")

        # Запускаем клиент Telethon в режиме прослушивания событий
        try:
            await self.client.run_until_disconnected()
        except asyncio.CancelledError:
            logger.info("🛑 UserBot получил сигнал отмены")
            raise
        except KeyboardInterrupt:
            logger.info("⌨️ UserBot получил KeyboardInterrupt")
            raise
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__

            # Проверяем на ошибку сессии AuthKeyUnregisteredError
            if 'AuthKeyUnregistered' in error_type or 'AuthKeyUnregistered' in error_msg:
                logger.error("❌ Сессия Telegram недействительна (AuthKeyUnregisteredError)!")
                logger.error("   Причина: Ключ сессии удалён на сервере Telegram")

                # Автоматически удаляем файл сессии
                import os
                session_file = "userbot.session"
                session_file_data = "userbot.session-journal"

                if os.path.exists(session_file):
                    try:
                        os.remove(session_file)
                        logger.info(f"🗑️ Файл сессии {session_file} удалён")
                    except Exception as remove_err:
                        logger.error(f"❌ Не удалось удалить сессию: {remove_err}")

                if os.path.exists(session_file_data):
                    try:
                        os.remove(session_file_data)
                        logger.info(f"🗑️ Файл {session_file_data} удалён")
                    except Exception as remove_err:
                        logger.error(f"❌ Не удалось удалить журнал сессии: {remove_err}")

                logger.error("   Решение: Перезапустите ListenerBot для новой авторизации")
                logger.error("   Откройте веб-админку: http://localhost:8001/console → Telegram")

                # Останавливаем клиент
                try:
                    await self.client.disconnect()
                except Exception:
                    pass

                # Не выбрасываем ошибку дальше - позволяем сервису продолжить работу
                # (без мониторинга каналов до новой авторизации)
                logger.warning("⚠️ ListenerBot остановлен до новой авторизации")
                return

            elif 'session' in error_msg.lower():
                logger.error("❌ Ошибка сессии Telegram!")
                logger.error("   Решение: Удалите файл userbot.session и перезапустите ListenerBot")
            else:
                logger.error(f"❌ Ошибка UserBot: {error_type}: {e}")
            raise

    async def stop(self) -> None:
        """
        Корректная остановка бота.

        Последовательность:
        1. Останавливаем флаг работы
        2. Останавливаем сервис категоризации (с закрытием сессии)
        3. Отменяем задачу обработки очереди
        4. Отменяем задачу мониторинга каналов
        5. Удаляем все обработчики событий
        6. Отключаем Telegram клиент
        7. Очищаем фабрику репозиториев
        """
        logger.info("🛑 Остановка ListenerBot...")

        self._running = False

        # 1. Останавливаем очередь категоризации
        if hasattr(self, 'categorization_queue') and self.categorization_queue:
            logger.info("⏳ Остановка очереди категоризации...")
            await self.categorization_queue.stop()

        # 2. Отменяем задачу очереди если есть
        if self._queue_task and not self._queue_task.done():
            logger.info("⏳ Отмена задачи обработки очереди...")
            self._queue_task.cancel()
            try:
                await asyncio.wait_for(self._queue_task, timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # 3. Отменяем задачу мониторинга каналов
        if self._channel_monitor_task and not self._channel_monitor_task.done():
            logger.info("⏳ Отмена задачи мониторинга каналов...")
            self._channel_monitor_task.cancel()
            try:
                await asyncio.wait_for(self._channel_monitor_task, timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # 4. Удаляем все обработчики событий
        async with self._handlers_lock:
            if self._event_handlers:
                logger.info(f"🗑️ Удаление {len(self._event_handlers)} обработчиков событий...")
                for channel_id, (handler_func, handler) in list(self._event_handlers.items()):
                    try:
                        self.client.remove_event_handler(handler_func, handler)
                    except Exception as e:
                        logger.debug(f"Ошибка удаления обработчика канала {channel_id}: {e}")
                self._event_handlers.clear()
                logger.info("✅ Все обработчики удалены")

        # 5. Отключаем Telegram клиент
        if self.client:
            try:
                logger.info("🔌 Отключение от Telegram...")
                # Синхронизируем сессию перед отключением (важно для сохранения session файла)
                if hasattr(self.client, '_session') and self.client._session:
                    try:
                        await self.client._session.flush()
                        logger.debug("✅ Сессия Telethon синхронизирована")
                    except Exception as flush_err:
                        error_str = str(flush_err)
                        # Игнорируем ошибки SQLite - сессия может быть повреждена
                        if 'no such table' in error_str or 'database disk image is malformed' in error_str:
                            logger.debug(f"⚠️ Сессия повреждена, пропускаем синхронизацию")
                        else:
                            logger.debug(f"⚠️ Ошибка синхронизации сессии Telethon: {flush_err}")

                await self.client.disconnect()
                logger.info("✅ Telegram клиент отключён")
            except Exception as e:
                error_str = str(e)
                # Игнорируем ошибки SQLite - сессия может быть повреждена
                if 'no such table' in error_str or 'database disk image is malformed' in error_str:
                    logger.warning(f"⚠️ Сессия SQLite повреждена - будет пересоздана при следующем запуске")
                    # Удаляем повреждённые файлы сессии
                    import os
                    session_file = "userbot.session"
                    session_journal = "userbot.session-journal"
                    for f in [session_file, session_journal]:
                        if os.path.exists(f):
                            try:
                                os.remove(f)
                                logger.info(f"🗑️ Удалён повреждённый файл: {f}")
                            except Exception as remove_err:
                                logger.warning(f"⚠️ Не удалось удалить {f}: {remove_err}")
                else:
                    logger.error(f"❌ Ошибка отключения Telegram клиента: {e}")

        # 6. Закрываем сессию БД
        if hasattr(self, '_db_session') and self._db_session:
            try:
                await self._db_session.close()
                logger.debug("✅ Сессия БД закрыта")
            except Exception as e:
                logger.debug(f"⚠️ Ошибка закрытия сессии БД: {e}")
            self._db_session = None

        # 7. Очищаем фабрику репозиториев
        self._repo_factory = None

        logger.info("👋 ListenerBot полностью остановлен")

    def _init_services(self) -> None:
        """Инициализация сервисов."""
        # Сервис категоризации — используем новый модуль напрямую
        self.categorization_queue = CategorizationQueue()
        self.categorizer = CategorizerAgent(model=settings.agent_model)
        self.categorization_classifier = NewsClassifier()

        # Процессор будет создан при запуске
        self.categorization_processor = None

        # Сервис уведомлений будет получен из контейнера при первом обращении
        # через свойство notification_service

        # NewsOrchestrator запускается в Scheduler, не создаём здесь
        self.orchestrator = None

    async def _init_categorization_processor(self):
        """Инициализировать процессор категоризации (ленивая инициализация)."""
        if self.categorization_processor:
            return

        db_service = get_database_service()
        session = await db_service.create_session()
        repo_factory = RepositoryFactory(session)

        # Создаём сервис сохранения
        saver = NewsSaver(
            posts_repo=repo_factory.posts(),
            channels_repo=repo_factory.channels(),
            events_repo=repo_factory.events(),
        )

        # Создаём процессор
        self.categorization_processor = CategorizationProcessor(
            categorizer=self.categorizer,
            saver=saver,
            channel_provider=repo_factory.channels(),
            notification_service=self.notification_service,
        )

        logger.info("✅ CategorizationProcessor инициализирован")

    async def _process_categorization_queue(self) -> None:
        """
        Обрабатывать очередь категоризации.

        Запускается как фоновая задача.
        """
        # Инициализируем процессор
        await self._init_categorization_processor()

        # Запускаем единую очередь агентов (если ещё не запущена)
        from services.ai_agent.agent_queue import get_agent_queue
        agent_queue = get_agent_queue()
        if not agent_queue._running:
            await agent_queue.start()
            # Логирование внутри agent_queue.start() — не дублируем

        self.categorization_queue.start()
        logger.info("🔄 Запущена обработка очереди категоризации")

        try:
            while self._running:
                # Получаем задачу из очереди (блокирует до появления)
                task = await self.categorization_queue.get()
                if task is None:
                    # Остановка
                    break

                try:
                    # Делегируем обработку процессору
                    await self.categorization_processor.process(task)
                except Exception as e:
                    logger.error(f"Ошибка обработки задачи категоризации: {e}")

        except asyncio.CancelledError:
            logger.info("🛑 Обработка очереди категоризации отменена")
            # Останавливаем AgentTaskQueue
            await agent_queue.stop()
            raise
        finally:
            await self.categorization_queue.stop()
            # Останавливаем AgentTaskQueue
            await agent_queue.stop()
            logger.info("🛑 Обработка очереди категоризации остановлена")

    async def _get_channel_ids(self) -> list[int]:
        """Получить ID каналов из БД."""
        db_service = get_database_service()
        async with db_service.session_context() as session:
            channels_repo = ChannelRepository(session)
            channels_db = await channels_repo.get_all_channels()
            return [ch.channel_id for ch in channels_db]

    async def _monitor_new_channels(self) -> None:
        """
        Мониторинг новых каналов в БД и динамическое добавление/удаление обработчиков.

        Проверяет БД каждые 10 секунд на наличие новых и удалённых каналов.
        """
        logger.info("🔍 Запуск мониторинга каналов (добавление/удаление)...")

        while self._running:
            try:
                await asyncio.sleep(10)  # Проверка каждые 10 секунд

                # Получаем текущие каналы из БД
                current_channel_ids = set(await self._get_channel_ids())

                # Находим новые и удалённые каналы
                async with self._channels_lock:
                    new_channel_ids = current_channel_ids - self._channel_ids
                    removed_channel_ids = self._channel_ids - current_channel_ids

                # Обработка новых каналов
                if new_channel_ids:
                    logger.info(f"🆕 Обнаружено новых каналов: {len(new_channel_ids)}")

                    async with self._handlers_lock:
                        for channel_id in new_channel_ids:
                            try:
                                handler = events.NewMessage(chats=[channel_id])
                                self.client.add_event_handler(
                                    self.handle_new_post,
                                    handler
                                )
                                self._event_handlers[channel_id] = (self.handle_new_post, handler)
                                logger.info(f"  ✅ Добавлен обработчик для канала ID={channel_id}")
                            except Exception as e:
                                logger.error(
                                    f"  ❌ Ошибка добавления обработчика для канала ID={channel_id}: {e}"
                                )

                    async with self._channels_lock:
                        self._channel_ids.update(new_channel_ids)

                    logger.info(
                        f"✅ Всего каналов для мониторинга: {len(self._channel_ids)}"
                    )

                # Обработка удалённых каналов
                if removed_channel_ids:
                    logger.info(f"🗑️ Обнаружено удалённых каналов: {len(removed_channel_ids)}")

                    async with self._handlers_lock:
                        for channel_id in removed_channel_ids:
                            try:
                                if channel_id in self._event_handlers:
                                    handler_func, handler = self._event_handlers[channel_id]
                                    self.client.remove_event_handler(handler_func, handler)
                                    del self._event_handlers[channel_id]
                                    logger.info(
                                        f"  ✅ Удалён обработчик для канала ID={channel_id}"
                                    )
                                else:
                                    logger.warning(
                                        f"  ⚠️ Обработчик для канала ID={channel_id} не найден в кэше"
                                    )
                            except Exception as e:
                                logger.error(
                                    f"  ❌ Ошибка удаления обработчика для канала ID={channel_id}: {e}"
                                )

                    async with self._channels_lock:
                        self._channel_ids.difference_update(removed_channel_ids)

                    logger.info(
                        f"✅ Осталось каналов для мониторинга: {len(self._channel_ids)}"
                    )

            except asyncio.CancelledError:
                logger.info("🛑 Мониторинг каналов остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка мониторинга каналов: {e}", exc_info=True)

        logger.debug("Мониторинг каналов завершён")

    async def handle_new_post(self, event) -> None:
        """
        Обработчик новых постов.

        Args:
            event: Telethon событие
        """
        channel_id = event.chat_id
        message_id = event.message.id
        msg_key = f"{channel_id}:{message_id}"

        # Проверяем дубликаты и блокируем обработку
        if not await self._check_duplicate_message(msg_key):
            return

        # Получаем текст сообщения
        text = event.message.text
        if not text:
            logger.debug(f"Игнорируем пост без текста (ID={message_id})")
            return

        # Получаем канал из БД
        channel_obj = await self._get_channel(channel_id)
        if channel_obj is None:
            logger.warning(f"Канал {channel_id} не найден в БД, игнорируем")
            return

        logger.info(f"📬 Новый пост из: {channel_obj.title} (ID={message_id}, msg_key={msg_key})")

        # Формируем промпт и добавляем в очередь
        await self._enqueue_categorization_task(
            channel_id=channel_id,
            message_id=message_id,
            text=text,
            channel=channel_obj,
        )

    async def _check_duplicate_message(self, msg_key: str) -> bool:
        """
        Проверить, не было ли сообщение уже обработано.

        Args:
            msg_key: Уникальный ключ сообщения

        Returns:
            True если сообщение новое, False если дубликат
        """
        # Используем отдельный lock для каждого msg_key
        if not hasattr(self, '_msg_locks'):
            self._msg_locks = {}

        if msg_key not in self._msg_locks:
            self._msg_locks[msg_key] = asyncio.Lock()

        async with self._msg_locks[msg_key]:
            async with self._messages_lock:
                if msg_key in self._processed_messages:
                    logger.debug(f"Сообщение {msg_key} уже обработано, пропускаем")
                    self._msg_locks.pop(msg_key, None)
                    return False

                self._processed_messages.add(msg_key)

                # Очищаем старые записи
                if len(self._processed_messages) > settings.processed_messages_cache_max:
                    items = list(self._processed_messages)
                    self._processed_messages.clear()
                    self._processed_messages.update(
                        items[-settings.processed_messages_cache_trim:]
                    )

            self._msg_locks.pop(msg_key, None)
            return True

    async def _get_channel(self, channel_id: int) -> Optional[Any]:
        """
        Получить канал из БД по Telegram ID.

        Args:
            channel_id: Telegram ID канала

        Returns:
            Объект канала или None
        """
        db_service = get_database_service()
        async with db_service.session_context() as session:
            channels_repo = ChannelRepository(session)
            return await channels_repo.get_by_telegram_id(channel_id)

    async def _enqueue_categorization_task(
        self,
        channel_id: int,
        message_id: int,
        text: str,
        channel,
    ) -> None:
        """
        Сформировать промпт и добавить задачу в очередь категоризации.

        Args:
            channel_id: Telegram ID канала
            message_id: ID сообщения
            text: Текст поста
            channel: Объект канала из БД
        """
        prompt = f'''## Название ресурса
{channel.title}

## Описание ресурса
{channel.description}

## Текст новости
{text}'''

        if self.categorization_queue:
            task = CategorizationTask(
                channel_id=channel_id,
                prompt=prompt,
                original_text=text,
                title=channel.title,
                desc=channel.description,
            )
            await self.categorization_queue.add(task)
