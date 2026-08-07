"""
Listener Bot — мониторинг Telegram каналов.

Использует Telethon для прослушивания каналов.
Корректная инициализация и завершение ресурсов.
"""

import asyncio
import logging
from typing import Optional, Set

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

try:
    from . import config as conf
except ImportError:
    import services.listener.config as conf

from database import RepositoryFactory
from database.repositories.channels import ChannelRepository
from services.core.database import get_database_service
from services.telegram.categorization import CategorizationService, CategorizationTask
from services.telegram.notification import NotificationService
from services.news.orchestrator import NewsOrchestrator
from services.ai_agent.vector_routers import register_vector_search_handlers
from config.settings import settings

logger = logging.getLogger(__name__)


class ListenerBot:
    """
    Бот для мониторинга Telegram каналов.

    Делегирует обработку новостей сервисам:
    - CategorizationService — категоризация
    - NewsOrchestrator — координация обработки
    - NotificationService — уведомления админам
    """

    def __init__(self) -> None:
        """Инициализация бота."""
        # Telegram клиент
        self.client: Optional[TelegramClient] = None
        self._client_initialized = False

        # Сервисы
        self.categorization_service: Optional[CategorizationService] = None
        self.notification_service: Optional[NotificationService] = None
        self.orchestrator: Optional[NewsOrchestrator] = None

        # Кэш обработанных сообщений
        self._processed_messages: Set[str] = set()
        self._messages_lock = asyncio.Lock()

        # Factory для репозиториев
        self._repo_factory: Optional[RepositoryFactory] = None

        # Флаг работы
        self._running = False

        # Задача обработки очереди
        self._queue_task: Optional[asyncio.Task] = None

    @property
    def repo_factory(self) -> RepositoryFactory:
        """Получить фабрику репозиториев."""
        if self._repo_factory is None:
            db_service = get_database_service()
            self._repo_factory = RepositoryFactory(db_service.create_session())
        return self._repo_factory

    async def initialize(self) -> None:
        """
        Инициализировать клиент Telethon.

        Подключается к Telegram, но не запускает обработчики.
        """
        if self._client_initialized:
            logger.debug("Telegram клиент уже инициализирован")
            return

        logger.info("🔌 Инициализация Telegram клиента...")
        logger.debug(f"API_ID: {conf.API_ID}, API_HASH: {conf.API_HASH[:8]}...")

        try:
            self.client = TelegramClient(
                'userbot',
                api_id=conf.API_ID,
                api_hash=conf.API_HASH,
                connection_retries=5,
                retry_delay=2,
                timeout=30,
                use_ipv6=True,
                flood_sleep_threshold=60,
            )

            logger.debug("Подключение к Telegram...")
            await self.client.connect()
            logger.debug("✅ Подключение установлено")
            self._client_initialized = True

            if not await self.client.is_user_authorized():
                logger.warning(
                    "⚠️ Требуется авторизация! Введите код из Telegram в консоль."
                )
                await self.client.send_code_request(conf.PHONE_NUMBER)

                # Неблокирующий ввод кода
                code = await asyncio.get_event_loop().run_in_executor(
                    None, input, 'Enter the code: '
                )
                try:
                    await self.client.sign_in(conf.PHONE_NUMBER, code)
                except SessionPasswordNeededError:
                    password = await asyncio.get_event_loop().run_in_executor(
                        None, input, 'Password: '
                    )
                    await self.client.sign_in(password=password)

            me = await self.client.get_me()
            logger.info(f"✅ UserBot авторизован: @{me.username} (ID: {me.id})")

        except asyncio.CancelledError:
            logger.info("🛑 Инициализация ListenerBot отменена")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Telegram клиента: {type(e).__name__}: {e}", exc_info=True)
            raise

    async def start(self) -> None:
        """
        Запустить бота.

        Инициализирует сервисы, регистрирует обработчики, запускает polling.
        """
        # Инициализируем клиент если нужно
        if not self._client_initialized:
            await self.initialize()

        # Инициализация сервисов
        self._init_services()

        # Получаем каналы из БД
        logger.info("📚 Получение каналов из БД...")
        channel_ids = await self._get_channel_ids()
        logger.info(f"📋 Найдено каналов в БД: {len(channel_ids)}")

        if channel_ids:
            # Регистрируем обработчик для каждого канала
            for channel_id in channel_ids:
                self.client.add_event_handler(
                    self.handle_new_post,
                    events.NewMessage(chats=[channel_id])
                )
            logger.info(
                f"✅ Обработчик событий добавлен для {len(channel_ids)} каналов"
            )
        else:
            logger.warning("⚠️ Нет каналов для мониторинга! Добавьте каналы через бота.")

        # Запускаем обработку очереди категоризации
        if self.categorization_service:
            self._queue_task = asyncio.create_task(
                self.categorization_service.process_queue()
            )
            logger.info("✅ Обработка очереди категоризации запущена")

        # Запускаем шину событий оркестратора
        if self.orchestrator:
            await self.orchestrator.start_event_bus()

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
            logger.error(f"❌ Ошибка UserBot: {type(e).__name__}: {e}")
            raise

    async def stop(self) -> None:
        """
        Корректная остановка бота.

        Последовательность:
        1. Останавливаем флаг работы
        2. Отменяем задачу обработки очереди
        3. Останавливаем оркестратор
        4. Отключаем Telegram клиент
        """
        logger.info("🛑 Остановка ListenerBot...")

        self._running = False

        # 1. Останавливаем обработку очереди
        if self.categorization_service:
            logger.info("⏳ Остановка очереди категоризации...")
            self.categorization_service.stop()

        # 2. Отменяем задачу очереди если есть
        if self._queue_task and not self._queue_task.done():
            logger.info("⏳ Отмена задачи обработки очереди...")
            self._queue_task.cancel()
            try:
                await asyncio.wait_for(self._queue_task, timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # 3. Останавливаем оркестратор
        if self.orchestrator:
            logger.info("⏳ Остановка NewsOrchestrator...")
            await self.orchestrator.stop()

        # 4. Отключаем Telegram клиент
        if self.client:
            try:
                logger.info("🔌 Отключение от Telegram...")
                await self.client.disconnect()
                logger.info("✅ Telegram клиент отключён")
            except Exception as e:
                logger.error(f"❌ Ошибка отключения Telegram клиента: {e}")

        # 5. Очищаем фабрику репозиториев
        self._repo_factory = None

        logger.info("👋 ListenerBot полностью остановлен")

    def _init_services(self) -> None:
        """Инициализация сервисов."""
        # Сервис категоризации
        self.categorization_service = CategorizationService(
            model=settings.agent_model
        )

        # Сервис уведомлений
        self.notification_service = NotificationService()

        # Координатор обработки новостей
        self.orchestrator = NewsOrchestrator(
            repo_factory=self.repo_factory,
            model=settings.agent_model,
            notification_service=self.notification_service,
        )

    async def _get_channel_ids(self) -> list[int]:
        """Получить ID каналов из БД."""
        db_service = get_database_service()
        async with db_service.session_context() as session:
            channels_repo = ChannelRepository(session)
            channels_db = await channels_repo.get_all_channels()
            return [ch.channel_id for ch in channels_db]

    async def handle_new_post(self, event) -> None:
        """
        Обработчик новых постов.

        Args:
            event: Telethon событие
        """
        text = event.message.text
        if not text:
            logger.debug("Игнорируем пост без текста")
            return

        channel_id = event.chat_id
        message_id = event.message.id
        msg_key = f"{channel_id}:{message_id}"

        # Проверяем и добавляем сообщение в обработанные
        async with self._messages_lock:
            if msg_key in self._processed_messages:
                logger.debug(f"Сообщение {msg_key} уже обработано, пропускаем")
                return

            self._processed_messages.add(msg_key)

            # Очищаем старые записи
            if len(self._processed_messages) > settings.processed_messages_cache_max:
                items = list(self._processed_messages)
                self._processed_messages.clear()
                self._processed_messages.update(
                    items[-settings.processed_messages_cache_trim:]
                )

        # Получаем канал через репозиторий
        db_service = get_database_service()
        async with db_service.session_context() as session:
            channels_repo = ChannelRepository(session)
            channel_obj = await channels_repo.get_by_telegram_id(channel_id)

        if channel_obj is None:
            logger.warning(f"Канал {channel_id} не найден в БД, игнорируем")
            return

        title = channel_obj.title
        desc = channel_obj.description

        logger.info(f"📬 Новый пост из: {title}")

        # Формируем промпт для категоризации
        prompt = f'''## Название ресурса
{title}

## Описание ресурса
{desc}

## Текст новости
{text}'''

        # Добавляем задачу в очередь категоризации
        if self.categorization_service:
            task = CategorizationTask(
                channel_id=channel_id,
                prompt=prompt,
                original_text=text,
                title=title,
                desc=desc
            )
            await self.categorization_service.add_task(task)
