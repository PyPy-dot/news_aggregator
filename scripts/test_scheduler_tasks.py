#!/usr/bin/env python3
"""
Тестовый скрипт для проверки обработки задач планировщиком.

Использование:
    python scripts/test_scheduler_tasks.py

Скрипт:
1. Создаёт тестовую задачу прямой генерации
2. Запускает обработку задач
3. Показывает результат
"""

import asyncio
import logging
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


async def test_scheduler():
    """Тестирование обработки задач."""
    logger.info("=" * 60)
    logger.info("🧪 Тестирование обработки задач планировщиком")
    logger.info("=" * 60)

    # Импортируем зависимости
    from services.database import get_database_service
    from database import RepositoryFactory

    # Инициализация БД
    db_service = get_database_service()
    await db_service.connect()
    logger.info(f"✅ БД подключена: {db_service.db_type.name}")

    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        # 1. Показываем текущие задачи
        logger.info("\n📋 Текущие задачи:")
        all_tasks = await task_repo.get_all_tasks(limit=10)
        for task in all_tasks:
            logger.info(
                f"  ID={task.id} type={task.task_type} status={task.status} "
                f"recurring={task.recurring} scheduled_at={task.scheduled_at}"
            )

        # 2. Создаём тестовую задачу (запуск через 5 секунд)
        scheduled_at = datetime.now() + timedelta(seconds=5)
        test_task = await task_repo.create_task(
            task_type='direct_generation',
            description='Тестовая задача для проверки планировщика',
            scheduled_at=scheduled_at,
            publisher_channel_id=None,
        )
        logger.info(f"\n✅ Создана тестовая задача ID={test_task.id}")
        logger.info(f"   scheduled_at={scheduled_at}")

        # 3. Ждём пока задача должна выполниться
        logger.info(f"\n⏳ Ожидание выполнения задачи (5 сек)...")
        await asyncio.sleep(6)

        # 4. Проверяем статус задачи
        task = await task_repo.get(test_task.id)
        logger.info(f"\n📊 Статус задачи после ожидания:")
        logger.info(
            f"   ID={task.id} status={task.status} completed_at={task.completed_at}"
        )

        # 5. Пробуем обработать задачи вручную
        logger.info("\n🔄 Ручная обработка задач...")
        from services.scheduler.scheduler import Scheduler
        from services.core.container import Container

        container = Container()
        await container.init()

        scheduler = Scheduler(container)
        await scheduler._init_components()

        # Выполняем один цикл обработки
        await scheduler._process_tasks()

        # 6. Проверяем статус после обработки
        task = await task_repo.get(test_task.id)
        logger.info(f"\n📊 Статус задачи после обработки:")
        logger.info(
            f"   ID={task.id} status={task.status} completed_at={task.completed_at}"
        )

        # 7. Показываем все задачи снова
        logger.info("\n📋 Все задачи после обработки:")
        all_tasks = await task_repo.get_all_tasks(limit=10)
        for t in all_tasks:
            logger.info(
                f"  ID={t.id} type={t.task_type} status={t.status} "
                f"recurring={t.recurring} completed_at={t.completed_at}"
            )

        # 8. Очистка (удаляем тестовую задачу)
        if task.status not in ('completed', 'failed'):
            logger.info(f"\n🗑️ Очистка: удаляем тестовую задачу ID={test_task.id}")
            await task_repo.delete_task(test_task.id)

        await container.dispose()

    await db_service.disconnect()
    logger.info("\n✅ Тестирование завершено")


if __name__ == "__main__":
    asyncio.run(test_scheduler())
