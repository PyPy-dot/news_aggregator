#!/usr/bin/env python3
"""
Диагностический скрипт для проверки задач в БД.

Использование:
    python scripts/check_tasks.py
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

# Добавляем корень проекта в PATH
sys.path.insert(0, str(Path(__file__).parent.parent))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


async def check_tasks():
    """Проверка задач в БД."""
    from services.database import get_database_service
    from database import RepositoryFactory

    db_service = get_database_service()
    await db_service.connect()

    async with db_service.session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        now = datetime.now()
        logger.info(f"📊 Проверка задач на {now}")
        logger.info("=" * 70)

        # Все задачи
        all_tasks = await task_repo.get_all_tasks(limit=50)
        logger.info(f"\n📋 Все задачи ({len(all_tasks)}):")

        for task in all_tasks:
            time_info = ""
            if task.scheduled_at:
                time_diff = (now - task.scheduled_at).total_seconds()
                if time_diff > 0:
                    time_info = f"(прошло {time_diff:.0f}с)"
                else:
                    time_info = f"(через {-time_diff:.0f}с)"

            status_icon = {
                'pending': '⏳',
                'active': '▶️',
                'completed': '✅',
                'failed': '❌',
                'expired': '⏰',
                'canceled': '🚫'
            }.get(task.status, '❓')

            logger.info(
                f"  {status_icon} ID={task.id:5d} | {task.task_type:<20} | "
                f"{task.status:<10} | rec={task.recurring} | "
                f"scheduled={task.scheduled_at} {time_info}"
            )

        # Статистика по статусам
        logger.info("\n" + "=" * 70)
        logger.info("📊 Статистика по статусам:")
        stats = await task_repo.get_tasks_count_by_status()
        for status, count in sorted(stats.items()):
            logger.info(f"  {status}: {count}")

        # Pending задачи
        pending_tasks = await task_repo.get_pending_tasks(limit=20)
        if pending_tasks:
            logger.info("\n" + "=" * 70)
            logger.info(f"📋 Pending задачи ({len(pending_tasks)}):")

            for task in pending_tasks:
                if task.scheduled_at:
                    time_diff = (now - task.scheduled_at).total_seconds()
                    if time_diff > 0:
                        ready = "✅ ГОТОВА" if time_diff > 0 else "⏳ ещё не время"
                    else:
                        ready = "⏳ ещё не время"
                else:
                    ready = "✅ НЕМЕДЛЕННО"

                logger.info(
                    f"  {ready} ID={task.id} type={task.task_type} "
                    f"scheduled={task.scheduled_at}"
                )

    await db_service.disconnect()
    logger.info("\n✅ Проверка завершена")


if __name__ == "__main__":
    asyncio.run(check_tasks())
