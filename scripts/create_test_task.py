#!/usr/bin/env python3
"""
Скрипт для создания тестовой задачи и проверки её выполнения.

Использование:
    python scripts/create_test_task.py
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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


async def create_test_task():
    """Создание тестовой задачи."""
    from services.database import get_database_service
    from database import RepositoryFactory

    db_service = get_database_service()
    await db_service.connect()

    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        # Создаём задачу на выполнение через 30 секунд (чтобы успеть запустить планировщик)
        scheduled_at = datetime.now() + timedelta(seconds=30)
        task = await task_repo.create_task(
            task_type='scheduled_processing',
            description='Тестовая задача обработки новостей',
            scheduled_at=scheduled_at,
            recurring=False,
        )

        logger.info(f"✅ Создана тестовая задача ID={task.id}")
        logger.info(f"   Тип: {task.task_type}")
        logger.info(f"   scheduled_at: {scheduled_at}")
        logger.info(f"   Статус: {task.status}")
        logger.info(f"\n⏳ Задача будет выполнена через 30 секунд")
        logger.info(f"   Запустите приложение и следите за логами планировщика")

    await db_service.disconnect()


if __name__ == "__main__":
    asyncio.run(create_test_task())
