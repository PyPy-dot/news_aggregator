"""
Web Admin API — управление задачами планировщика.

REST API для создания, просмотра и управления задачами в таблице `tasks`.
Все задачи создаются через этот интерфейс и выполняются планировщиком.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from database import RepositoryFactory
from services.database import get_database_service

router = APIRouter()


# =============================================================================
# Pydantic модели
# =============================================================================

class TaskCreate(BaseModel):
    """Модель для создания задачи."""
    task_type: str = Field(..., description="Тип задачи")
    description: str = Field(default='', description="Описание задачи")
    scheduled_at: Optional[datetime] = Field(default=None, description="Время выполнения")
    recurring: bool = Field(default=False, description="Периодическая задача")
    recurrence_pattern: Optional[int] = Field(default=None, ge=1, le=365, description="Периодичность в днях")
    publisher_channel_id: Optional[int] = Field(default=None, description="ID канала публикации")
    post_id: Optional[int] = Field(default=None, description="ID поста (для прямой генерации)")
    news_id: Optional[int] = Field(default=None, description="ID новости")


class TaskResponse(BaseModel):
    """Модель ответа с задачей."""
    id: int
    task_type: str
    description: str
    post_id: Optional[int]
    news_id: Optional[int]
    scheduled_at: Optional[datetime]
    status: str
    recurring: bool
    recurrence_pattern: Optional[int]
    publisher_channel_id: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """Модель ответа со списком задач."""
    tasks: List[TaskResponse]
    total: int
    # Статистика по статусам
    by_status: dict[str, int]


# =============================================================================
# API эндпоинты
# =============================================================================

@router.get('/')
async def list_tasks(
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    task_type: Optional[str] = Query(None, description="Фильтр по типу задачи"),
    limit: int = Query(100, ge=1, le=500, description="Максимум задач"),
    offset: int = Query(0, ge=0, description="Смещение"),
):
    """
    Получить список задач с фильтрацией и пагинацией.

    - **status**: pending, active, completed, failed, expired, canceled
    - **task_type**: direct_generation, scheduled_processing, event_processing, daily_morning, daily_evening, custom_periodic
    """
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        # Получаем задачи
        tasks = await task_repo.get_tasks_for_admin(
            status=status,
            task_type=task_type,
            limit=limit,
            offset=offset
        )

        # Получаем статистику по статусам
        by_status = await task_repo.get_tasks_count_by_status()

        return {
            'tasks': tasks,
            'total': len(tasks),
            'by_status': by_status,
            'filters': {
                'status': status,
                'task_type': task_type,
            }
        }


@router.get('/stats')
async def get_tasks_stats():
    """
    Получить статистику по задачам.

    Возвращает количество задач по каждому статусу.
    """
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        by_status = await task_repo.get_tasks_count_by_status()

        return {
            'by_status': by_status,
            'total': sum(by_status.values()),
            'pending': by_status.get('pending', 0),
            'active': by_status.get('active', 0),
            'completed': by_status.get('completed', 0),
            'failed': by_status.get('failed', 0),
            'expired': by_status.get('expired', 0),
            'canceled': by_status.get('canceled', 0),
        }


@router.post('/create', response_model=TaskResponse)
async def create_task(task: TaskCreate):
    """
    Создать новую задачу.

    Типы задач:
    - **direct_generation**: Прямая генерация новости по описанию
    - **scheduled_processing**: Плановая обработка новостей
    - **event_processing**: Обработка событий (векторный поиск, контексты)
    - **daily_morning**: Утренняя обработка (периодическая)
    - **daily_evening**: Вечерняя обработка (периодическая)
    - **custom_periodic**: Пользовательская периодическая задача

    Для периодических задач:
    - recurring=True
    - recurrence_pattern: интервал в днях (1=ежедневно, 2=раз в 2 дня, ...)
    """
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        # Валидация времени выполнения
        if task.scheduled_at and task.scheduled_at < datetime.now():
            raise HTTPException(status_code=400, detail="scheduled_at не может быть в прошлом")

        # Автоматически устанавливаем время, если не указано
        if task.scheduled_at is None:
            task.scheduled_at = datetime.now()

        # Создаём задачу
        new_task = await task_repo.create_task(
            task_type=task.task_type,
            description=task.description,
            post_id=task.post_id,
            news_id=task.news_id,
            scheduled_at=task.scheduled_at,
            recurring=task.recurring,
            recurrence_pattern=task.recurrence_pattern,
            publisher_channel_id=task.publisher_channel_id,
        )

        return new_task


@router.post('/create-direct', response_model=TaskResponse)
async def create_direct_generation_task(
    description: str = Query(..., description="Описание новости для генерации"),
    publisher_channel_id: Optional[int] = Query(None, description="ID канала публикации"),
    scheduled_at: Optional[datetime] = Query(None, description="Время выполнения"),
    recurring: bool = Query(False, description="Периодическая задача"),
    recurrence_pattern: Optional[int] = Query(None, ge=1, description="Периодичность в днях"),
):
    """
    Создать задачу на прямую генерацию новости.

    Упрощённый эндпоинт для создания задач прямой генерации.

    - **description**: Описание новости (будет передано AI агенту)
    - **publisher_channel_id**: ID канала для публикации (None = бот, -1 = все каналы)
    - **scheduled_at**: Когда выполнить (по умолчанию немедленно)
    - **recurring**: Периодическая ли задача
    - **recurrence_pattern**: Интервал повторения в днях
    """
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        # Время выполнения
        exec_time = scheduled_at or datetime.now()

        # Создаём задачу
        new_task = await task_repo.create_task(
            task_type='direct_generation',
            description=description,
            post_id=None,
            news_id=None,
            scheduled_at=exec_time,
            recurring=recurring,
            recurrence_pattern=recurrence_pattern if recurring else None,
            publisher_channel_id=publisher_channel_id,
        )

        return new_task


@router.post('/create-periodic', response_model=TaskResponse)
async def create_periodic_task(
    task_type: str = Query(..., description="Тип задачи (custom_periodic, daily_morning, daily_evening)"),
    description: str = Query(..., description="Описание задачи"),
    scheduled_at: datetime = Query(..., description="Время первого выполнения"),
    recurrence_pattern: int = Query(1, ge=1, le=365, description="Периодичность в днях"),
):
    """
    Создать периодическую задачу.

    Периодические задачи выполняются регулярно с указанным интервалом.

    - **task_type**: Тип задачи (custom_periodic, daily_morning, daily_evening)
    - **description**: Описание задачи
    - **scheduled_at**: Время первого выполнения
    - **recurrence_pattern**: Интервал повторения в днях (1=ежедневно, 7=еженедельно)
    """
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        # Валидация времени
        if scheduled_at < datetime.now():
            raise HTTPException(status_code=400, detail="scheduled_at не может быть в прошлом")

        # Создаём периодическую задачу
        new_task = await task_repo.create_task(
            task_type=task_type,
            description=description,
            scheduled_at=scheduled_at,
            recurring=True,
            recurrence_pattern=recurrence_pattern,
        )

        return new_task


@router.get('/{task_id}', response_model=TaskResponse)
async def get_task(task_id: int):
    """Получить задачу по ID."""
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        task = await task_repo.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")

        return task


@router.post('/{task_id}/cancel')
async def cancel_task(task_id: int):
    """
    Отменить задачу.

    Устанавливает статус 'canceled'. Периодические задачи не будут выполнены снова.
    """
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        task = await task_repo.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")

        if task.status in ('completed', 'failed', 'expired', 'canceled'):
            raise HTTPException(status_code=400, detail=f"Нельзя отменить задачу со статусом {task.status}")

        await task_repo.mark_canceled(task_id)

        return {'success': True, 'task_id': task_id, 'new_status': 'canceled'}


@router.post('/{task_id}/reschedule')
async def reschedule_task(task_id: int, scheduled_at: datetime):
    """
    Перенести время выполнения задачи.

    Работает только для задач со статусом pending.
    """
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        task = await task_repo.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")

        if task.status != 'pending':
            raise HTTPException(status_code=400, detail="Можно перенести только задачи со статусом pending")

        if scheduled_at < datetime.now():
            raise HTTPException(status_code=400, detail="scheduled_at не может быть в прошлом")

        await task_repo.update_scheduled_at(task_id, scheduled_at)

        return {
            'success': True,
            'task_id': task_id,
            'new_scheduled_at': scheduled_at,
        }


@router.delete('/{task_id}')
async def delete_task(task_id: int):
    """
    Удалить задачу.

    Можно удалять только задачи со статусами: completed, failed, expired, canceled
    """
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        task = await task_repo.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")

        if task.status not in ('completed', 'failed', 'expired', 'canceled'):
            raise HTTPException(
                status_code=400,
                detail="Можно удалять только завершённые задачи (completed/failed/expired/canceled)"
            )

        await task_repo.delete_task(task_id)

        return {'success': True, 'task_id': task_id, 'deleted': True}


@router.post('/cleanup')
async def cleanup_old_tasks(
    days_old: int = Query(7, ge=1, le=90, description="Возраст задач для удаления (дни)"),
    dry_run: bool = Query(False, description="Режим проверки (без удаления)"),
):
    """
    Очистить старые завершённые задачи.

    Удаляет задачи со статусами expired/failed/canceled старше указанного возраста.

    - **days_old**: Возраст задач в днях для удаления
    - **dry_run**: Если True, показывает сколько задач будет удалено без фактического удаления
    """
    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        if dry_run:
            # Считаем сколько задач будет удалено
            from datetime import timedelta
            from sqlalchemy import select, func
            from database.models import Task

            cutoff_date = datetime.now() - timedelta(days=days_old)

            result = await session.execute(
                select(func.count(Task.id))
                .where(
                    (Task.status.in_(['expired', 'failed', 'canceled'])) &
                    (Task.completed_at < cutoff_date)
                )
            )
            count = result.scalar() or 0

            return {
                'dry_run': True,
                'days_old': days_old,
                'tasks_would_be_deleted': count,
            }

        # Фактическое удаление
        deleted_count = await task_repo.delete_old_tasks(days_old=days_old)

        return {
            'success': True,
            'deleted_count': deleted_count,
            'days_old': days_old,
        }


# =============================================================================
# Типы задач (справочник)
# =============================================================================

@router.get('/meta/task-types')
async def get_task_types():
    """
    Получить доступные типы задач.

    Справочник для создания новых задач.
    """
    return {
        'task_types': [
            {
                'type': 'direct_generation',
                'name': 'Прямая генерация новости',
                'description': 'Генерация новости по описанию через AI агента',
                'requires_description': True,
                'supports_recurring': True,
                'fields': ['description', 'publisher_channel_id'],
            },
            {
                'type': 'scheduled_processing',
                'name': 'Плановая обработка новостей',
                'description': 'Обработка накопившихся новостей (checked_at=false)',
                'requires_description': False,
                'supports_recurring': True,
                'fields': ['news_id'],
            },
            {
                'type': 'event_processing',
                'name': 'Обработка событий',
                'description': 'Векторный поиск и обновление контекстов событий',
                'requires_description': False,
                'supports_recurring': True,
                'fields': [],
            },
            {
                'type': 'daily_morning',
                'name': 'Утренняя обработка',
                'description': 'Ежедневная утренняя обработка новостей',
                'requires_description': False,
                'supports_recurring': True,
                'default_time': '09:00',
            },
            {
                'type': 'daily_evening',
                'name': 'Вечерняя обработка',
                'description': 'Ежедневная вечерняя обработка новостей',
                'requires_description': False,
                'supports_recurring': True,
                'default_time': '21:00',
            },
            {
                'type': 'custom_periodic',
                'name': 'Пользовательская периодическая',
                'description': 'Периодическая задача с настраиваемым расписанием',
                'requires_description': True,
                'supports_recurring': True,
                'fields': ['description'],
            },
        ]
    }


# =============================================================================
# Быстрые действия
# =============================================================================

@router.post('/quick/daily-morning')
async def create_daily_morning_task(time: str = Query('09:00', pattern=r'^\d{2}:\d{2}$')):
    """
    Создать ежедневную утреннюю задачу.

    - **time**: Время выполнения в формате HH:MM (по умолчанию 09:00)
    """
    hour, minute = map(int, time.split(':'))
    scheduled_at = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Если время уже прошло сегодня, ставим на завтра
    if scheduled_at < datetime.now():
        scheduled_at += timedelta(days=1)

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        task = await task_repo.create_or_get_recurring_task(
            task_type='daily_morning',
            description=f'Утренняя обработка новостей ({time})',
            scheduled_at=scheduled_at,
            recurrence_pattern=1,
        )

        return {'success': True, 'task': task, 'action': 'created_or_exists'}


@router.post('/quick/daily-evening')
async def create_daily_evening_task(time: str = Query('21:00', pattern=r'^\d{2}:\d{2}$')):
    """
    Создать ежедневную вечернюю задачу.

    - **time**: Время выполнения в формате HH:MM (по умолчанию 21:00)
    """
    hour, minute = map(int, time.split(':'))
    scheduled_at = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Если время уже прошло сегодня, ставим на завтра
    if scheduled_at < datetime.now():
        scheduled_at += timedelta(days=1)

    async with get_database_service().session_context() as session:
        factory = RepositoryFactory(session)
        task_repo = factory.tasks()

        task = await task_repo.create_or_get_recurring_task(
            task_type='daily_evening',
            description=f'Вечерняя обработка новостей ({time})',
            scheduled_at=scheduled_at,
            recurrence_pattern=1,
        )

        return {'success': True, 'task': task, 'action': 'created_or_exists'}
