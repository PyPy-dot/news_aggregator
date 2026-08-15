"""
Task repository для работы с задачами.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Task
from database.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    """
    Репозиторий для работы с задачами.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Task)

    async def create_task(
        self,
        task_type: str,
        description: str = '',
        post_id: Optional[int] = None,
        news_id: Optional[int] = None,
        scheduled_at: Optional[datetime] = None,
        recurring: bool = False,
        recurrence_pattern: Optional[int] = None,
        publisher_channel_id: Optional[int] = None,
    ) -> Task:
        """
        Создать новую задачу.

        Args:
            task_type: Тип задачи ('direct_generation', 'scheduled_processing', 'daily_morning', 'daily_evening')
            description: Описание задачи
            post_id: ID поста (для прямой генерации)
            news_id: ID новости (для плановой обработки)
            scheduled_at: Дата/время выполнения
            recurring: Флаг периодической задачи
            recurrence_pattern: Периодичность в днях (1=ежедневно, 2=раз в 2 дня, и т.д.)
            publisher_channel_id: ID канала публикации (для прямой генерации)

        Returns:
            Созданная задача
        """
        task = Task(
            task_type=task_type,
            description=description,
            post_id=post_id,
            news_id=news_id,
            scheduled_at=scheduled_at or datetime.now(),
            status='pending',
            recurring=recurring,
            recurrence_pattern=recurrence_pattern,
            publisher_channel_id=publisher_channel_id,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def get_recurring_tasks(self, task_type: str) -> list[Task]:
        """
        Получить периодические задачи по типу.

        Args:
            task_type: Тип задачи ('daily_morning', 'daily_evening')

        Returns:
            Список периодических задач
        """
        result = await self.session.execute(
            select(Task)
            .where(
                (Task.task_type == task_type) &
                (Task.recurring == True) &
                (Task.status == 'pending')
            )
            .order_by(Task.scheduled_at)
        )
        return list(result.scalars().all())

    async def create_or_get_recurring_task(
        self,
        task_type: str,
        description: str = '',
        scheduled_at: Optional[datetime] = None,
        recurrence_pattern: int = 1,
    ) -> Task:
        """
        Создать или получить существующую периодическую задачу.

        Args:
            task_type: Тип задачи ('daily_morning', 'daily_evening')
            description: Описание задачи
            scheduled_at: Дата/время выполнения
            recurrence_pattern: Периодичность в днях (1=ежедневно, 2=раз в 2 дня, и т.д.)

        Returns:
            Существующая или созданная задача
        """
        # Проверяем, есть ли уже невыполненная задача этого типа за сегодня
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start.replace(hour=23, minute=59, second=59)

        result = await self.session.execute(
            select(Task)
            .where(
                (Task.task_type == task_type) &
                (Task.recurring == True) &
                (Task.scheduled_at >= today_start) &
                (Task.scheduled_at <= today_end)
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            return existing

        # Создаём новую задачу
        return await self.create_task(
            task_type=task_type,
            description=description,
            scheduled_at=scheduled_at,
            recurring=True,
            recurrence_pattern=recurrence_pattern,
        )

    async def create_or_get_daily_task(
        self,
        task_type: str,
        description: str = '',
        scheduled_at: Optional[datetime] = None,
    ) -> Task:
        """
        Создать или получить существующую ежедневную задачу (утренняя/вечерняя обработка).

        В отличие от create_or_get_recurring_task, создаёт разовую ежедневную задачу
        (не периодическую), которая выполняется один раз в день.

        Args:
            task_type: Тип задачи ('daily_morning', 'daily_evening')
            description: Описание задачи
            scheduled_at: Дата/время выполнения

        Returns:
            Существующая или созданная задача
        """
        # Проверяем, есть ли уже задача этого типа за сегодня
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start.replace(hour=23, minute=59, second=59)

        result = await self.session.execute(
            select(Task)
            .where(
                (Task.task_type == task_type) &
                (Task.scheduled_at >= today_start) &
                (Task.scheduled_at <= today_end)
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            return existing

        # Создаём новую ежедневную задачу (recurring=False, так как это разовая задача на день)
        return await self.create_task(
            task_type=task_type,
            description=description,
            scheduled_at=scheduled_at or datetime.now(),
            recurring=False,
            recurrence_pattern=None,
        )

    async def get_pending_tasks(self, limit: int = 100) -> List[Task]:
        """
        Получить ожидающие задачи.

        Args:
            limit: Максимальное количество задач

        Returns:
            Список задач со статусом 'pending'
        """
        result = await self.session.execute(
            select(Task)
            .where(Task.status == 'pending')
            .order_by(Task.scheduled_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_active_tasks(self, limit: int = 100) -> List[Task]:
        """
        Получить активные задачи (pending и processing).

        Args:
            limit: Максимальное количество задач

        Returns:
            Список активных задач
        """
        result = await self.session.execute(
            select(Task)
            .where(
                (Task.status == 'pending') | (Task.status == 'processing')
            )
            .order_by(Task.scheduled_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_active(self, task_id: int) -> bool:
        """
        Отметить задачу как выполняемую (active).

        Args:
            task_id: ID задачи

        Returns:
            True если обновлена, False если не найдена
        """
        task = await self.get(task_id)
        if task:
            task.status = 'active'
            await self.session.commit()
            return True
        return False

    async def mark_expired(self, task_id: int) -> bool:
        """
        Отметить задачу как просроченную.

        Args:
            task_id: ID задачи

        Returns:
            True если обновлена, False если не найдена
        """
        task = await self.get(task_id)
        if task:
            task.status = 'expired'
            task.completed_at = datetime.now()
            await self.session.commit()
            return True
        return False

    async def mark_canceled(self, task_id: int) -> bool:
        """
        Отметить задачу как отмененную.

        Args:
            task_id: ID задачи

        Returns:
            True если обновлена, False если не найдена
        """
        task = await self.get(task_id)
        if task:
            task.status = 'canceled'
            task.recurring = False
            task.completed_at = datetime.now()
            await self.session.commit()
            return True
        return False

    async def reset_recurring_task(
        self,
        task_id: int,
        next_scheduled_at: datetime,
        status: str = 'pending'
    ) -> bool:
        """
        Сбросить периодическую задачу на следующее выполнение.

        Args:
            task_id: ID задачи
            next_scheduled_at: Время следующего выполнения
            status: Статус (по умолчанию 'pending')

        Returns:
            True если обновлена, False если не найдена
        """
        task = await self.get(task_id)
        if task:
            task.scheduled_at = next_scheduled_at
            task.status = status
            task.completed_at = None
            await self.session.commit()
            return True
        return False

    async def get_expired_tasks(self, limit: int = 100) -> List[Task]:
        """
        Получить просроченные задачи.

        Args:
            limit: Максимальное количество задач

        Returns:
            Список задач со статусом 'expired'
        """
        result = await self.session.execute(
            select(Task)
            .where(Task.status == 'expired')
            .order_by(Task.scheduled_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_pending_and_active_tasks(self, limit: int = 100) -> List[Task]:
        """
        Получить задачи со статусами pending и active.

        Args:
            limit: Максимальное количество задач

        Returns:
            Список задач со статусами pending и active
        """
        result = await self.session.execute(
            select(Task)
            .where(
                (Task.status == 'pending') | (Task.status == 'active')
            )
            .order_by(Task.scheduled_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_scheduled_at(self, task_id: int, scheduled_at: datetime) -> bool:
        """
        Обновить время выполнения задачи.

        Args:
            task_id: ID задачи
            scheduled_at: Новое время выполнения

        Returns:
            True если обновлена, False если не найдена
        """
        task = await self.get(task_id)
        if task:
            task.scheduled_at = scheduled_at
            await self.session.commit()
            return True
        return False

    async def mark_processing(self, task_id: int) -> bool:
        """
        Отметить задачу как выполняемую.

        Args:
            task_id: ID задачи

        Returns:
            True если обновлена, False если не найдена
        """
        task = await self.get(task_id)
        if task:
            task.status = 'processing'
            await self.session.commit()
            return True
        return False

    async def mark_completed(self, task_id: int) -> bool:
        """
        Отметить задачу как выполненную.

        Args:
            task_id: ID задачи

        Returns:
            True если обновлена, False если не найдена
        """
        task = await self.get(task_id)
        if task:
            task.status = 'completed'
            task.completed_at = datetime.now()
            await self.session.commit()
            return True
        return False

    async def mark_failed(self, task_id: int) -> bool:
        """
        Отметить задачу как неудачную.

        Args:
            task_id: ID задачи

        Returns:
            True если обновлена, False если не найдена
        """
        task = await self.get(task_id)
        if task:
            task.status = 'failed'
            task.completed_at = datetime.now()
            await self.session.commit()
            return True
        return False

    async def get_by_id(self, task_id: int) -> Optional[Task]:
        """
        Получить задачу по ID.

        Args:
            task_id: ID задачи

        Returns:
            Задача или None
        """
        return await self.get(task_id)

    async def get_tasks_by_type(
        self,
        task_type: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Task]:
        """
        Получить задачи по типу.

        Args:
            task_type: Тип задачи
            status: Статус (опционально)
            limit: Максимальное количество задач

        Returns:
            Список задач
        """
        query = select(Task).where(Task.task_type == task_type)
        if status:
            query = query.where(Task.status == status)

        query = query.order_by(desc(Task.created_at)).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_task(
        self,
        task_id: int,
        task_type: Optional[str] = None,
        description: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
        recurring: Optional[bool] = None,
        recurrence_pattern: Optional[int] = None,
        publisher_channel_id: Optional[int] = None,
    ) -> bool:
        """
        Обновить задачу.

        Args:
            task_id: ID задачи
            task_type: Тип задачи (опционально)
            description: Описание (опционально)
            scheduled_at: Дата/время выполнения (опционально)
            recurring: Флаг периодической задачи (опционально)
            recurrence_pattern: Периодичность в днях (опционально)
            publisher_channel_id: ID канала публикации (опционально)

        Returns:
            True если обновлена, False если не найдена
        """
        task = await self.get(task_id)
        if task:
            if task_type is not None:
                task.task_type = task_type
            if description is not None:
                task.description = description
            if scheduled_at is not None:
                task.scheduled_at = scheduled_at
            if recurring is not None:
                task.recurring = recurring
            if recurrence_pattern is not None:
                task.recurrence_pattern = recurrence_pattern
            if publisher_channel_id is not None:
                task.publisher_channel_id = publisher_channel_id
            await self.session.commit()
            return True
        return False

    async def delete_task(self, task_id: int) -> bool:
        """
        Удалить задачу.

        Args:
            task_id: ID задачи

        Returns:
            True если удалена, False если не найдена
        """
        task = await self.get(task_id)
        if task:
            await self.session.delete(task)
            await self.session.commit()
            return True
        return False

    async def get_all_tasks(self, limit: int = 100) -> List[Task]:
        """
        Получить все задачи.

        Args:
            limit: Максимальное количество задач

        Returns:
            Список задач
        """
        result = await self.session.execute(
            select(Task)
            .order_by(desc(Task.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_old_tasks(self, days_old: int = 7) -> int:
        """
        Удалить старые завершённые задачи (expired/failed/canceled).

        Args:
            days_old: Возраст задач в днях для удаления

        Returns:
            Количество удалённых задач
        """
        from datetime import timedelta
        from sqlalchemy import delete

        cutoff_date = datetime.now() - timedelta(days=days_old)

        # Удаляем старые задачи с терминальными статусами
        stmt = (
            delete(Task)
            .where(
                (Task.status.in_(['expired', 'failed', 'canceled'])) &
                (Task.completed_at < cutoff_date)
            )
        )

        result = await self.session.execute(stmt)
        await self.session.commit()

        deleted_count = result.rowcount
        return deleted_count if deleted_count else 0

    async def get_tasks_for_admin(
        self,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Task]:
        """
        Получить задачи для админ-интерфейса.

        Args:
            status: Фильтр по статусу (опционально)
            task_type: Фильтр по типу задачи (опционально)
            limit: Максимальное количество задач
            offset: Смещение для пагинации

        Returns:
            Список задач
        """
        query = select(Task)

        if status:
            query = query.where(Task.status == status)
        if task_type:
            query = query.where(Task.task_type == task_type)

        query = query.order_by(desc(Task.created_at)).offset(offset).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_tasks_count_by_status(self) -> dict[str, int]:
        """
        Получить количество задач по статусам.

        Returns:
            Dict со статусами и количеством задач
        """
        from sqlalchemy import func

        result = await self.session.execute(
            select(Task.status, func.count(Task.id))
            .group_by(Task.status)
        )

        return {row.status: row.count for row in result.all()}
