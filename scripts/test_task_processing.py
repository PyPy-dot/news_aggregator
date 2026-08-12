#!/usr/bin/env python3
"""
Скрипт для тестирования обработки задач планировщиком.

Использование:
    python scripts/test_task_processing.py
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Добавляем корень проекта в PATH
sys.path.insert(0, str(Path(__file__).parent.parent))

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


async def test_task_processing():
    """Тестирование обработки задач."""
    from services.database import get_database_service
    from database import RepositoryFactory
    from services.scheduler.scheduler import Scheduler
    from services.core.container import Container

    db_service = get_database_service()
    await db_service.connect()

    # Создаём тестовую задачу на выполнение "сейчас"
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        scheduled_at = datetime.now() - timedelta(seconds=5)  # 5 секунд назад
        task = await task_repo.create_task(
            task_type='scheduled_processing',
            description='Тест обработки задач (немедленное выполнение)',
            scheduled_at=scheduled_at,
            recurring=False,
        )
        logger.info(f"✅ Создана задача ID={task.id} scheduled_at={scheduled_at}")

    # Инициализируем планировщик
    container = Container()
    await container.init()

    scheduler = Scheduler(container)
    await scheduler._init_components()

    logger.info(f"\n🔄 Запуск обработки задач...")
    logger.info(f"   Задача ID={task.id} должна выполниться")

    # Выполняем один цикл обработки
    await scheduler._process_tasks()

    # Проверяем результат
    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        task = await task_repo.get(task.id)
        logger.info(f"\n📊 Результат:")
        logger.info(f"   ID={task.id}")
        logger.info(f"   Статус: {task.status}")
        logger.info(f"   Completed at: {task.completed_at}")

        if task.status == 'completed':
            logger.info(f"\n✅ Задача успешно выполнена!")
        elif task.status == 'failed':
            logger.info(f"\n❌ Задача завершена с ошибкой")
        elif task.status == 'active':
            logger.info(f"\n⚠️ Задача всё ещё в работе (active)")
        elif task.status == 'pending':
            logger.info(f"\n⚠️ Задача всё ещё ожидает (pending) - возможно, не прошла проверку времени")
        elif task.status == 'expired':
            logger.info(f"\n⏰ Задача просрочена (expired)")

    await container.dispose()
    await db_service.disconnect()


if __name__ == "__main__":
    asyncio.run(test_task_processing())
