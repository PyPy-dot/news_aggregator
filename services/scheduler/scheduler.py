"""
Планировщик задач для обработки новостей и событий.

Архитектура v4.0:
- Все задачи хранятся в таблице `tasks` и создаются через админ-интерфейс
- Планировщик НЕ создаёт задачи самостоятельно — только выполняет их по расписанию
- Задачи указываются через админ-интерфейс, попадают в БД и выполняются по наступлению времени

Логика работы:
1. Новости со срочностью 4-5 обрабатываются немедленно (обходят АРА)
2. Новости со срочностью 1-3 обрабатываются по задачам из таблицы `tasks`
3. События обрабатываются по задачам из таблицы `tasks` (периодическая задача)
4. RSS парсинг работает независимо (каждые 5 минут)

Таблица `tasks` — единственный источник истины для расписания.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from typing import TYPE_CHECKING

from database import RepositoryFactory
from services.news.orchestrator import NewsOrchestrator
from services.database import get_database_service

if TYPE_CHECKING:
    from services.core.container import Container

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Планировщик задач для обработки новостей и событий.

    v4.0: Планировщик только выполняет задачи из таблицы `tasks`.
    Создание задач — через админ-интерфейс.

    Делегирует обработку новостей NewsOrchestrator.
    """

    def __init__(self, container: Optional['Container'] = None) -> None:
        """
        Инициализация планировщика.

        Args:
            container: DI контейнер (опционально, для получения сервисов)
        """
        self._container = container
        self._db_service = get_database_service()
        self._session = None
        self.repo_factory = None

        # Координатор будет создан при запуске
        self.orchestrator: Optional[NewsOrchestrator] = None

        # Задачи планировщика
        self._task_processor_task: Optional[asyncio.Task] = None
        self._event_bus_task: Optional[asyncio.Task] = None
        self._rss_task: Optional[asyncio.Task] = None
        self._expired_cleaner_task: Optional[asyncio.Task] = None

        self._running = False
        self._initialized = False
        self._last_error: Optional[str] = None

    async def _init_components(self) -> None:
        """Инициализировать компоненты (ленивая инициализация)."""
        if self._initialized:
            return

        self._session = await self._db_service.create_session()
        self.repo_factory = RepositoryFactory(self._session)

        # Создаём NewsOrchestrator через контейнер (если доступен) или напрямую
        if self._container:
            self.orchestrator = await self._container.create_orchestrator(self._session)
            logger.debug("✅ NewsOrchestrator создан через контейнер")
        else:
            self.orchestrator = NewsOrchestrator(
                repo_factory=self.repo_factory,
            )
            logger.debug("✅ NewsOrchestrator создан напрямую")

        self._initialized = True
        logger.info("✅ Scheduler компоненты инициализированы")

    async def start(self) -> None:
        """
        Запуск планировщика.

        Запускает фоновые задачи:
        - Обработчик задач из таблицы `tasks` (каждые 10 секунд)
        - Шина событий EventBus
        - RSS парсер (каждые 5 минут)
        - Очистка просроченных задач (каждые 5 минут)
        """
        self._running = True
        self._last_error = None
        logger.info("🕐 Планировщик запущен (архитектура v4.0 — задачи из БД)")

        # Инициализируем компоненты (после установки _running для избежания гонок)
        await self._init_components()

        # Запускаем фоновые задачи
        self._task_processor_task = asyncio.create_task(self._run_task_processor())
        self._event_bus_task = asyncio.create_task(self.orchestrator.start_event_bus())
        self._rss_task = asyncio.create_task(self._run_rss_parser())
        self._expired_cleaner_task = asyncio.create_task(self._run_expired_cleaner())

        logger.info("✅ Все задачи планировщика запущены")
        logger.info("📋 Задачи выполняются из таблицы `tasks` (создаются через админ-интерфейс)")

    def is_alive(self) -> bool:
        """Проверить, действительно ли планировщик работает."""
        if not self._running:
            return False
        if self._task_processor_task is None:
            return False
        return not self._task_processor_task.done()

    async def wait(self) -> None:
        """
        Ждать завершения задач планировщика.

        Блокирует до отмены или завершения любой из основных задач.
        """
        if not self._task_processor_task:
            return

        try:
            await self._task_processor_task
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """
        Корректная остановка планировщика.

        Последовательность:
        1. Останавливаем флаг работы
        2. Отменяем все задачи (включая шину событий)
        3. Останавливаем оркестратор
        4. Закрываем сессию БД
        """
        logger.info("🛑 Остановка планировщика...")

        self._running = False

        # 1. Отменяем задачи (включая шину событий и RSS)
        tasks_to_cancel = [
            (self._task_processor_task, "Обработчик задач"),
            (self._event_bus_task, "Шина событий"),
            (self._rss_task, "RSS парсер"),
            (self._expired_cleaner_task, "Очистка просроченных"),
        ]

        for task, name in tasks_to_cancel:
            if task and not task.done():
                logger.info(f"⏳ Отмена: {name}...")
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=3.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

        # 2. Останавливаем оркестратор
        if self.orchestrator:
            logger.info("⏳ Остановка NewsOrchestrator...")
            await self.orchestrator.stop()

        # 3. Закрываем сессию БД
        if self._session:
            try:
                await self._session.close()
                logger.debug("✅ Сессия БД закрыта")
            except Exception as e:
                logger.error(f"❌ Ошибка закрытия сессии БД: {e}")
            self._session = None
        logger.info("👋 Планировщик полностью остановлен")

    async def _run_task_processor(self) -> None:
        """
        Обработка задач из таблицы `tasks`.

        Цикл проверки каждые 10 секунд:
        1. Проверяем просроченные одноразовые задачи → expired
        2. Берём pending задачи, у которых наступило время → active
        3. Выполняем задачу
        4. Обновляем статус (completed/failed для одноразовых, pending для периодических)
        """
        logger.info("📋 Запуск обработчика задач (проверка каждые 10 секунд)...")

        while self._running:
            try:
                await asyncio.sleep(10)  # Проверка каждые 10 секунд

                if not self._running:
                    break

                await self._process_tasks()

            except asyncio.CancelledError:
                logger.info("🛑 Обработчик задач остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в обработчике задач: {e}", exc_info=True)
                # Продолжаем работу, ошибка не критична

        logger.info("👋 Обработчик задач остановлен")

    async def _run_expired_cleaner(self) -> None:
        """
        Очистка старых просроченных задач.

        Каждые 5 минут удаляет задачи со статусом expired/failed/canceled
        старше 7 дней для предотвращения разрастания таблицы.
        """
        logger.info("🧹 Запуск очистителя просроченных задач (каждые 5 минут)...")

        while self._running:
            try:
                await asyncio.sleep(300)  # 5 минут

                if not self._running:
                    break

                async with self._db_service.session_context() as session:
                    factory = RepositoryFactory(session)
                    task_repo = factory.tasks()

                    # Удаляем старые задачи (старше 7 дней)
                    deleted_count = await task_repo.delete_old_tasks(days_old=7)

                    if deleted_count > 0:
                        logger.info(f"🗑️ Удалено {deleted_count} старых задач")

            except asyncio.CancelledError:
                logger.info("🛑 Очиститель остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в очистителе задач: {e}")

    async def _process_tasks(self) -> None:
        """
        Обработка задач из таблицы tasks с полной логикой статусов.

        Логика:
        1. Берём pending задачи, у которых наступило время (или нет scheduled_at) → active
        2. Выполняем задачу по типу
        3. Для recurring: обновляем время → pending
        4. Для single: completed/failed
        5. Просроченные задачи (одноразовые, время вышло > 1 час) → expired
        """
        try:
            from database import RepositoryFactory

            async with self._db_service.session_context() as session:
                factory = RepositoryFactory(session)
                task_repo = factory.tasks()

                now = datetime.now()

                # 1. Получаем все pending задачи
                pending_tasks = await task_repo.get_pending_tasks(limit=50)

                expired_count = 0
                tasks_to_process = []

                for task in pending_tasks:
                    # Проверяем, просрочена ли задача (одноразовая, время вышло > 1 часа назад)
                    if not task.recurring and task.scheduled_at:
                        time_diff = (now - task.scheduled_at).total_seconds()
                        if time_diff > 3600:  # 1 час
                            await task_repo.mark_expired(task.id)
                            expired_count += 1
                            logger.info(f"⏰ Задача ID={task.id} просрочена (одноразовая, >1ч)")
                            continue
                        elif time_diff > 0:
                            # Время вышло, но < 1 часа — выполняем
                            tasks_to_process.append(task)
                            logger.info(f"✅ Задача ID={task.id} готова к выполнению (время вышло)")
                    elif not task.recurring and task.scheduled_at is None:
                        # Задача без времени — выполняется немедленно
                        tasks_to_process.append(task)
                        logger.info(f"✅ Задача ID={task.id} готова к выполнению (нет scheduled_at)")
                    elif task.recurring:
                        # Периодическая задача — проверяем время
                        if task.scheduled_at is None or task.scheduled_at <= now:
                            tasks_to_process.append(task)
                            logger.info(f"✅ Периодическая задача ID={task.id} готова к выполнению")

                if expired_count > 0:
                    logger.warning(f"📝 Просрочено задач: {expired_count}")

                # 2. Выполняем задачи (не более 10 за цикл)
                for task in tasks_to_process[:10]:
                    try:
                        # 3. Берём в работу
                        await task_repo.mark_active(task.id)
                        logger.info(f"▶️ Задача ID={task.id} взята в работу (active)")

                        # 4. Выполняем задачу по типу
                        await self._execute_task(task, task_repo)

                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки задачи ID={task.id}: {e}", exc_info=True)

                        # Обработка ошибки
                        if task.recurring:
                            # Периодическая — пробуем в следующий раз
                            next_scheduled = (
                                task.scheduled_at + timedelta(days=task.recurrence_pattern or 1)
                                if task.scheduled_at
                                else datetime.now() + timedelta(days=1)
                            )
                            await task_repo.reset_recurring_task(task.id, next_scheduled, 'pending')
                            logger.warning(
                                f"⚠️ Периодическая задача ID={task.id} будет повторена: {next_scheduled}"
                            )
                        else:
                            # Одноразовая — failed
                            await task_repo.mark_failed(task.id)
                            logger.error(f"❌ Задача ID={task.id} завершена с ошибкой (failed)")

        except Exception as e:
            logger.error(f"Ошибка в _process_tasks: {e}", exc_info=True)

    async def _execute_task(self, task, task_repo) -> None:
        """
        Выполнить задачу по типу.

        Args:
            task: Объект задачи
            task_repo: Репозиторий задач
        """
        from datetime import timedelta

        if task.task_type == 'direct_generation':
            # Прямая генерация новости
            logger.info(f"📝 Обработка задачи прямой генерации ID={task.id}")

            description = task.description or ''
            news_id = await self.orchestrator.generate_direct_news(
                description=description,
                publisher_channel_id=task.publisher_channel_id,
            )

            # 5. Обновляем статус в зависимости от результата
            if task.recurring:
                # Периодическая — сбрасываем на следующее выполнение
                next_scheduled = task.scheduled_at + timedelta(days=task.recurrence_pattern or 1)
                if news_id:
                    await task_repo.reset_recurring_task(task.id, next_scheduled, 'pending')
                    logger.info(f"✅ Периодическая задача ID={task.id} выполнена, следующее: {next_scheduled}")
                else:
                    # Ошибка — всё равно переходим к следующему циклу
                    await task_repo.reset_recurring_task(task.id, next_scheduled, 'pending')
                    logger.warning(f"⚠️ Периодическая задача ID={task.id} не выполнена, следующее: {next_scheduled}")
            else:
                # Одноразовая — терминальный статус
                if news_id:
                    await task_repo.mark_completed(task.id)
                    logger.info(f"✅ Задача прямой генерации ID={task.id} выполнена")
                else:
                    await task_repo.mark_failed(task.id)
                    logger.warning(f"❌ Задача прямой генерации ID={task.id} не выполнена")

        elif task.task_type == 'scheduled_processing':
            # Плановая обработка новостей
            logger.info(f"📋 Обработка задачи плановой обработки ID={task.id}")

            if task.news_id:
                # Обработка конкретной новости
                logger.info(f"📝 Обработка новости ID={task.news_id}")
                # Здесь может быть логика обработки конкретной новости
                if task.recurring:
                    next_scheduled = task.scheduled_at + timedelta(days=task.recurrence_pattern or 1)
                    await task_repo.reset_recurring_task(task.id, next_scheduled, 'pending')
                else:
                    await task_repo.mark_completed(task.id)
            else:
                # Обработка всех необработанных новостей
                processed_count = await self.orchestrator.process_pending_news_batch(hours=48)
                logger.info(f"✅ Обработано {processed_count} новостей по задаче ID={task.id}")

                if task.recurring:
                    next_scheduled = task.scheduled_at + timedelta(days=task.recurrence_pattern or 1)
                    await task_repo.reset_recurring_task(task.id, next_scheduled, 'pending')
                else:
                    await task_repo.mark_completed(task.id)

        elif task.task_type == 'event_processing':
            # Обработка событий (векторный поиск, контексты)
            logger.info(f"🔄 Обработка задачи событий ID={task.id}")

            await self.orchestrator.process_news_cycle()

            if task.recurring:
                next_scheduled = task.scheduled_at + timedelta(days=task.recurrence_pattern or 1)
                await task_repo.reset_recurring_task(task.id, next_scheduled, 'pending')
            else:
                await task_repo.mark_completed(task.id)

        elif task.task_type in ('daily_morning', 'daily_evening', 'custom_periodic'):
            # Периодическая задача обработки новостей (создаётся через админ-интерфейс)
            period_name = task.description or task.task_type
            logger.info(f"📋 Обработка периодической задачи '{period_name}' ID={task.id}")

            processed_count = await self.orchestrator.process_pending_news_batch(hours=48)
            logger.info(
                f"✅ Периодическая задача ID={task.id} выполнена, "
                f"обработано {processed_count} новостей"
            )

            if task.recurring:
                next_scheduled = task.scheduled_at + timedelta(days=task.recurrence_pattern or 1)
                await task_repo.reset_recurring_task(task.id, next_scheduled, 'pending')
            else:
                await task_repo.mark_completed(task.id)

        else:
            logger.warning(f"⚠️ Неизвестный тип задачи ID={task.id}: {task.task_type}")
            # Помечаем как выполненную для неизвестных типов
            if not task.recurring:
                await task_repo.mark_completed(task.id)

    async def _run_rss_parser(self) -> None:
        """
        Парсинг RSS лент каждые 5 минут.

        Проверяет активные RSS источники и парсит новые новости.
        """
        from services.rss.processor import get_rss_processor_service

        logger.info("📡 Запуск RSS парсера (каждые 5 минут)...")

        while self._running:
            try:
                # Ждём интервал (5 минут по умолчанию)
                await asyncio.sleep(300)  # 300 секунд = 5 минут

                if not self._running:
                    break

                # Получаем фабрику репозиториев
                async with self._db_service.session_context() as session:
                    from database import RepositoryFactory
                    factory = RepositoryFactory(session)

                    # Создаём RSS процессор
                    rss_processor = get_rss_processor_service(factory)

                    # Обрабатываем все активные источники
                    stats = await rss_processor.process_all_active_sources(limit=20)

                    if stats['sources_processed'] > 0:
                        logger.info(
                            f"📰 RSS: обработано {stats['sources_processed']} источников, "
                            f"получено {stats['total_news']} новостей, "
                            f"добавлено {stats['new_news']} новых"
                        )

                    # Категоризуем и обрабатываем необработанные новости
                    processed = await rss_processor.categorize_and_process_news(limit=50)
                    if processed > 0:
                        logger.info(f"✅ RSS: категоризовано и обработано {processed} новостей")

            except asyncio.CancelledError:
                logger.info("🛑 RSS парсер остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в RSS парсере: {e}")
                # Продолжаем работу, ошибка не критична

        logger.info("👋 RSS парсер остановлен")
