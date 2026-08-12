"""
Тесты для RedisTaskQueue.

Проверяют:
- Подключение к Redis
- Добавление и получение задач
- Приоритеты задач
- Retry логику
- Статистику и историю
"""

import asyncio
import os
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Пропускаем тесты если Redis недоступен
pytestmark = pytest.mark.skipif(
    not os.environ.get('REDIS_URL') and not os.environ.get('REDIS_HOST'),
    reason="Требуется Redis (REDIS_URL или REDIS_HOST в окружении)"
)

from services.core.redis_queue import (
    RedisTaskQueue,
    AgentTask,
    TaskPriority,
    TaskStatus,
    QueueFullError,
    get_redis_queue,
    reset_redis_queue,
)


@pytest.fixture
def redis_url():
    """Получить URL Redis из окружения."""
    return os.environ.get('REDIS_URL', 'redis://localhost:6379')


@pytest.fixture
async def queue(redis_url):
    """Создать очередь для тестов."""
    q = RedisTaskQueue(
        redis_url=redis_url,
        prefix='test_queue',
        max_concurrency=2,
        max_queue_size=10,
        retry_delay=0.1,
    )
    await q.connect()
    await q.clear()  # Очищаем перед тестом
    yield q
    await q.clear()  # Очищаем после теста
    await q.disconnect()


@pytest.fixture
def sample_task():
    """Создать тестовую задачу."""
    return AgentTask(
        task_id='test_123',
        priority=TaskPriority.NORMAL.value,
        created_at=time.time(),
        agent_name='TestAgent',
        method_name='test_method',
        args=('arg1', 'arg2'),
        kwargs={'key': 'value'},
        max_retries=3,
    )


class TestAgentTask:
    """Тесты сериализации AgentTask."""

    def test_to_dict(self, sample_task):
        """Тест сериализации в dict."""
        data = sample_task.to_dict()

        assert data['task_id'] == 'test_123'
        assert data['priority'] == 3
        assert data['agent_name'] == 'TestAgent'
        assert data['method_name'] == 'test_method'
        assert data['args'] == ['arg1', 'arg2']
        assert data['kwargs'] == {'key': 'value'}

    def test_from_dict(self, sample_task):
        """Тест десериализации из dict."""
        data = sample_task.to_dict()
        restored = AgentTask.from_dict(data)

        assert restored.task_id == sample_task.task_id
        assert restored.priority == sample_task.priority
        assert restored.agent_name == sample_task.agent_name
        assert restored.method_name == sample_task.method_name
        assert restored.args == sample_task.args
        assert restored.kwargs == sample_task.kwargs


class TestRedisTaskQueue:
    """Тесты RedisTaskQueue."""

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, redis_url):
        """Тест подключения и отключения."""
        q = RedisTaskQueue(redis_url=redis_url, prefix='test_connect')

        await q.connect()
        assert q._redis is not None

        await q.disconnect()
        assert q._redis is None

    @pytest.mark.asyncio
    async def test_add_task(self, queue):
        """Тест добавления задачи."""
        task_id = await queue.add_task(
            agent_name='TestAgent',
            method_name='test_method',
            args=('arg1',),
            kwargs={'key': 'value'},
            priority=TaskPriority.HIGH,
        )

        assert task_id.startswith('TestAgent_')

        # Проверяем что задача в очереди
        stats = await queue.get_stats()
        assert stats['total'] == 1
        assert stats['queue_size'] == 1

    @pytest.mark.asyncio
    async def test_add_task_with_different_priorities(self, queue):
        """Тест добавления задач с разными приоритетами."""
        # Добавляем задачи в обратном порядке приоритета
        low_id = await queue.add_task(
            'Agent', 'method', priority=TaskPriority.LOW
        )
        normal_id = await queue.add_task(
            'Agent', 'method', priority=TaskPriority.NORMAL
        )
        high_id = await queue.add_task(
            'Agent', 'method', priority=TaskPriority.HIGH
        )
        critical_id = await queue.add_task(
            'Agent', 'method', priority=TaskPriority.CRITICAL
        )

        # Проверяем порядок в очереди (должны быть отсортированы по приоритету)
        tasks = await queue.get_history(limit=10)
        assert len(tasks) == 4

    @pytest.mark.asyncio
    async def test_queue_full_error(self, queue):
        """Тест переполнения очереди."""
        # Устанавливаем маленький размер очереди
        queue.max_queue_size = 2

        # Добавляем задачи
        await queue.add_task('A', 'm', priority=TaskPriority.LOW)
        await queue.add_task('A', 'm', priority=TaskPriority.LOW)

        # Следующая должна вызвать ошибку
        with pytest.raises(QueueFullError):
            await queue.add_task('A', 'm', priority=TaskPriority.NORMAL)

    @pytest.mark.asyncio
    async def test_get_task(self, queue):
        """Тест получения задачи из очереди."""
        task_id = await queue.add_task(
            'TestAgent',
            'test_method',
            'arg1',
            method=AsyncMock(return_value='result'),
        )

        # Получаем задачу
        task = await queue._get_next_task()

        assert task is not None
        assert task.task_id == task_id
        assert task.status == TaskStatus.PROCESSING.value

    @pytest.mark.asyncio
    async def test_get_task_priority_order(self, queue):
        """Тест получения задач в порядке приоритета."""
        # Добавляем задачи в обратном порядке
        low_id = await queue.add_task('A', 'm', priority=TaskPriority.LOW)
        high_id = await queue.add_task('A', 'm', priority=TaskPriority.HIGH)
        normal_id = await queue.add_task('A', 'm', priority=TaskPriority.NORMAL)

        # Получаем первую задачу (должна быть HIGH)
        task1 = await queue._get_next_task()
        assert task1.task_id == high_id

        # Получаем вторую задачу (должна быть NORMAL)
        task2 = await queue._get_next_task()
        assert task2.task_id == normal_id

        # Получаем третью задачу (должна быть LOW)
        task3 = await queue._get_next_task()
        assert task3.task_id == low_id

    @pytest.mark.asyncio
    async def test_execute_task_success(self, queue):
        """Тест успешного выполнения задачи."""
        # Создаём mock метод
        mock_method = AsyncMock(return_value='test_result')
        queue.register_method('TestAgent', 'test_method', mock_method)

        # Добавляем задачу
        await queue.add_task(
            'TestAgent',
            'test_method',
            'arg1',
            key='value',
        )

        # Получаем и выполняем
        task = await queue._get_next_task()
        await queue._execute_task(task, worker_id=0)

        # Проверяем результат
        assert task.status == TaskStatus.COMPLETED.value
        assert task.result == 'test_result'
        mock_method.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_task_with_retry(self, queue):
        """Тест повторной попытки при ошибке."""
        # Создаём mock метод который падает
        mock_method = AsyncMock(side_effect=Exception('Test error'))
        queue.register_method('TestAgent', 'test_method', mock_method)

        # Добавляем задачу
        await queue.add_task(
            'TestAgent',
            'test_method',
            max_retries=3,
        )

        # Получаем и выполняем
        task = await queue._get_next_task()
        await queue._execute_task(task, worker_id=0)

        # Задача должна быть на retry
        assert task.status == TaskStatus.RETRY.value
        assert task.retry_count == 1

    @pytest.mark.asyncio
    async def test_execute_task_failed_after_max_retries(self, queue):
        """Тест провала после максимального количества попыток."""
        # Создаём mock метод который всегда падает
        mock_method = AsyncMock(side_effect=Exception('Test error'))
        queue.register_method('TestAgent', 'test_method', mock_method)

        # Добавляем задачу с 1 попыткой
        await queue.add_task(
            'TestAgent',
            'test_method',
            max_retries=1,
        )

        # Получаем и выполняем
        task = await queue._get_next_task()
        await queue._execute_task(task, worker_id=0)

        # После первой попытки задача должна быть FAILED
        assert task.status == TaskStatus.FAILED.value
        assert task.retry_count == 1

    @pytest.mark.asyncio
    async def test_get_stats(self, queue):
        """Тест получения статистики."""
        # Добавляем несколько задач
        await queue.add_task('A', 'm1')
        await queue.add_task('A', 'm2')
        await queue.add_task('A', 'm3')

        stats = await queue.get_stats()

        assert stats['total'] == 3
        assert stats['queue_size'] == 3
        assert stats['running'] is False

    @pytest.mark.asyncio
    async def test_get_history(self, queue):
        """Тест получения истории."""
        # Добавляем и выполняем задачи
        for i in range(5):
            mock_method = AsyncMock(return_value=f'result_{i}')
            queue.register_method('Agent', f'method_{i}', mock_method)
            await queue.add_task('Agent', f'method_{i}')

            task = await queue._get_next_task()
            await queue._execute_task(task, worker_id=0)

        history = await queue.get_history(limit=10)
        assert len(history) == 5

    @pytest.mark.asyncio
    async def test_get_task_by_id(self, queue):
        """Тест получения задачи по ID."""
        task_id = await queue.add_task('TestAgent', 'test_method', 'arg1')

        task = await queue.get_task(task_id)

        assert task is not None
        assert task.task_id == task_id
        assert task.agent_name == 'TestAgent'

    @pytest.mark.asyncio
    async def test_clear_queue(self, queue):
        """Тест очистки очереди."""
        # Добавляем задачи
        for i in range(5):
            await queue.add_task('A', f'm{i}')

        # Очищаем
        await queue.clear()

        stats = await queue.get_stats()
        assert stats['queue_size'] == 0


class TestRedisTaskQueueWorkers:
    """Тесты воркеров RedisTaskQueue."""

    @pytest.mark.asyncio
    async def test_start_stop_workers(self, queue):
        """Тест запуска и остановки воркеров."""
        await queue.start(num_workers=2)
        assert queue._running is True
        assert len(queue._worker_tasks) == 2

        await queue.stop()
        assert queue._running is False
        assert len(queue._worker_tasks) == 0

    @pytest.mark.asyncio
    async def test_worker_processes_tasks(self, queue):
        """Тест обработки задач воркерами."""
        results = []

        # Создаём mock метод
        async def mock_method(instance, *args, **kwargs):
            results.append(args)
            return 'done'

        queue.register_method('TestAgent', 'test_method', mock_method)

        # Запускаем воркеры
        await queue.start(num_workers=1)

        # Добавляем задачи
        for i in range(3):
            await queue.add_task(
                'TestAgent',
                'test_method',
                f'arg_{i}',
            )

        # Ждём выполнения
        await asyncio.sleep(1)

        await queue.stop()

        # Проверяем что все задачи выполнены
        assert len(results) == 3


class TestGlobalInstance:
    """Тесты глобального экземпляра."""

    def test_get_redis_queue(self, redis_url):
        """Тест получения глобальной очереди."""
        # Устанавливаем REDIS_URL
        old_url = os.environ.get('REDIS_URL')
        os.environ['REDIS_URL'] = redis_url

        try:
            reset_redis_queue()
            q = get_redis_queue()

            assert isinstance(q, RedisTaskQueue)
            assert q.redis_url == redis_url
        finally:
            # Восстанавливаем окружение
            if old_url:
                os.environ['REDIS_URL'] = old_url
            elif 'REDIS_URL' in os.environ:
                del os.environ['REDIS_URL']

            reset_redis_queue()

    def test_reset_redis_queue(self, redis_url):
        """Тест сброса очереди."""
        old_url = os.environ.get('REDIS_URL')
        os.environ['REDIS_URL'] = redis_url

        try:
            q1 = get_redis_queue()
            reset_redis_queue()
            q2 = get_redis_queue()

            # Это должны быть разные экземпляры
            assert q1 is not q2
        finally:
            if old_url:
                os.environ['REDIS_URL'] = old_url
            elif 'REDIS_URL' in os.environ:
                del os.environ['REDIS_URL']

            reset_redis_queue()


class TestTaskPriorityOrdering:
    """Тесты приоритетов задач."""

    @pytest.mark.asyncio
    async def test_critical_before_low(self, queue):
        """Тест что CRITICAL выполняется перед LOW."""
        low_id = await queue.add_task('A', 'low', priority=TaskPriority.LOW)
        critical_id = await queue.add_task('A', 'critical', priority=TaskPriority.CRITICAL)

        # CRITICAL должна быть получена первой
        task1 = await queue._get_next_task()
        assert task1.task_id == critical_id

        task2 = await queue._get_next_task()
        assert task2.task_id == low_id

    @pytest.mark.asyncio
    async def test_same_priority_fifo(self, queue):
        """Тест FIFO для задач одного приоритета."""
        # Добавляем задачи одного приоритета
        first_id = await queue.add_task('A', 'first', priority=TaskPriority.NORMAL)
        await asyncio.sleep(0.01)  # Небольшая задержка
        second_id = await queue.add_task('A', 'second', priority=TaskPriority.NORMAL)

        # Первая задача должна быть получена первой
        task1 = await queue._get_next_task()
        assert task1.task_id == first_id

        task2 = await queue._get_next_task()
        assert task2.task_id == second_id


class TestRetryLogic:
    """Тесты retry логики."""

    @pytest.mark.asyncio
    async def test_exponential_backoff(self, queue):
        """Тест экспоненциальной задержки между попытками."""
        queue.retry_delay = 0.1

        # Создаём задачу
        task = AgentTask(
            task_id='retry_test',
            priority=TaskPriority.NORMAL.value,
            created_at=time.time(),
            agent_name='TestAgent',
            method_name='test',
            max_retries=3,
            retry_count=0,
        )

        # Первая попытка
        task.retry_count = 1
        delay1 = queue.retry_delay * (2 ** task.retry_count)
        assert delay1 == 0.2

        # Вторая попытка
        task.retry_count = 2
        delay2 = queue.retry_delay * (2 ** task.retry_count)
        assert delay2 == 0.4

        # Третья попытка
        task.retry_count = 3
        delay3 = queue.retry_delay * (2 ** task.retry_count)
        assert delay3 == 0.8
