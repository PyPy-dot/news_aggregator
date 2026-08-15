"""
Tests for AgentTaskQueue Prometheus metrics.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch

from services.ai_agent.agent_queue import AgentTaskQueue, TaskPriority, AgentTask, TaskStatus


@pytest.fixture
def mock_metrics():
    """Mock Prometheus metrics for testing."""
    with patch('services.ai_agent.agent_queue.agent_queue_size') as mock_queue_size, \
         patch('services.ai_agent.agent_queue.agent_queue_active_tasks') as mock_active, \
         patch('services.ai_agent.agent_queue.agent_tasks_total') as mock_total, \
         patch('services.ai_agent.agent_queue.agent_task_duration') as mock_duration, \
         patch('services.ai_agent.agent_queue.agent_queue_pending_by_priority') as mock_priority:

        # Setup mocks
        mock_queue_size.set = MagicMock()
        mock_active.labels = MagicMock(return_value=MagicMock(set=MagicMock()))
        mock_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
        mock_duration.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))
        mock_priority.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

        yield {
            'queue_size': mock_queue_size,
            'active': mock_active,
            'total': mock_total,
            'duration': mock_duration,
            'priority': mock_priority,
        }


class TestAgentQueueMetrics:
    """Tests for AgentTaskQueue metrics."""

    @pytest.mark.asyncio
    async def test_add_task_updates_metrics(self, mock_metrics):
        """Test that adding a task updates queue size and priority metrics."""
        queue = AgentTaskQueue(max_concurrency=2)

        async def dummy_method(self):
            return "result"

        await queue.add_task(
            agent_name="TestAgent",
            method_name="test_method",
            method=dummy_method,
            priority=TaskPriority.HIGH,
        )

        # Проверяем, что метрики были обновлены
        mock_metrics['queue_size'].set.assert_called()
        mock_metrics['priority'].labels.assert_called_with(priority='HIGH')
        mock_metrics['priority'].labels.return_value.inc.assert_called()

    @pytest.mark.asyncio
    async def test_execute_task_updates_metrics(self, mock_metrics):
        """Test that executing a task updates active and duration metrics."""
        queue = AgentTaskQueue(max_concurrency=2)

        async def dummy_method(self):
            await asyncio.sleep(0.01)
            return "result"

        # Создаём задачу
        task = AgentTask(
            priority=TaskPriority.NORMAL.value,
            created_at=asyncio.get_event_loop().time(),
            task_id="test_1",
            agent_name="TestAgent",
            method_name="test_method",
            args=(MagicMock(),),  # self как первый аргумент
            kwargs={},
        )
        task.method = dummy_method

        # Выполняем задачу
        await queue._execute_task(task, dummy_method)

        # Проверяем метрики
        assert mock_metrics['active'].labels.called
        assert mock_metrics['total'].labels.called
        assert mock_metrics['duration'].labels.called

        # Проверяем, что статус COMPLETED
        assert task.status.value == TaskStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_execute_task_failed_updates_metrics(self, mock_metrics):
        """Test that failed task updates failed metrics."""
        queue = AgentTaskQueue(max_concurrency=2)

        async def failing_method(self):
            raise Exception("Test error")

        task = AgentTask(
            priority=TaskPriority.NORMAL.value,
            created_at=asyncio.get_event_loop().time(),
            task_id="test_1",
            agent_name="TestAgent",
            method_name="test_method",
            args=(MagicMock(),),
            kwargs={},
            max_retries=0,  # Не повторять
        )
        task.method = failing_method

        await queue._execute_task(task, failing_method)

        # Проверяем, что метрика failed была вызвана
        mock_metrics['total'].labels.assert_any_call(
            agent_name="TestAgent",
            status='failed'
        )
        mock_metrics['total'].labels.return_value.inc.assert_called()

        # Статус должен быть FAILED
        assert task.status.value == TaskStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_execute_task_retry_updates_metrics(self, mock_metrics):
        """Test that retried task updates retry metrics."""
        queue = AgentTaskQueue(max_concurrency=2)

        async def failing_method(self):
            raise Exception("Test error")

        task = AgentTask(
            priority=TaskPriority.NORMAL.value,
            created_at=asyncio.get_event_loop().time(),
            task_id="test_1",
            agent_name="TestAgent",
            method_name="test_method",
            args=(MagicMock(),),
            kwargs={},
            max_retries=3,
        )
        task.method = failing_method

        await queue._execute_task(task, failing_method)

        # Проверяем, что метрика retried была вызвана
        mock_metrics['total'].labels.assert_any_call(
            agent_name="TestAgent",
            status='retried'
        )

        # Статус должен быть RETRY
        assert task.status.value == TaskStatus.RETRY.value

    @pytest.mark.asyncio
    async def test_get_stats_updates_queue_size(self, mock_metrics):
        """Test that get_stats updates queue size metric."""
        queue = AgentTaskQueue(max_concurrency=2)

        async def dummy_method(self):
            return "result"

        # Добавляем задачу
        await queue.add_task(
            agent_name="TestAgent",
            method_name="test_method",
            method=dummy_method,
        )

        # Получаем статистику
        stats = queue.get_stats()

        # Проверяем, что метрика queue_size была обновлена
        mock_metrics['queue_size'].set.assert_called()

        # Проверяем, что статистика содержит правильные данные
        assert 'queue_size' in stats
        assert stats['queue_size'] >= 1

    @pytest.mark.asyncio
    async def test_active_tasks_by_agent(self, mock_metrics):
        """Test that active tasks are tracked by agent name."""
        queue = AgentTaskQueue(max_concurrency=5)

        async def slow_method(self):
            await asyncio.sleep(0.1)
            return "result"

        # Добавляем несколько задач для разных агентов
        tasks = []
        for agent_name in ["Analyst", "Editor", "Archivist"]:
            task = AgentTask(
                priority=TaskPriority.NORMAL.value,
                created_at=asyncio.get_event_loop().time(),
                task_id=f"test_{agent_name}",
                agent_name=agent_name,
                method_name="process",
                args=(MagicMock(),),
                kwargs={},
            )
            task.method = slow_method
            tasks.append(task)

        # Запускаем все задачи параллельно
        await asyncio.gather(*[
            queue._execute_task(task, slow_method) for task in tasks
        ])

        # Проверяем, что метрики для каждого агента были обновлены
        assert mock_metrics['active'].labels.call_count >= 3
