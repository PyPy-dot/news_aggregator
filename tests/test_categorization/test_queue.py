"""
Tests for CategorizationQueue.
"""

import pytest
import asyncio
from services.categorization.queue import CategorizationQueue, CategorizationTask


@pytest.fixture
def queue():
    """Фикстура очереди с малым размером."""
    return CategorizationQueue(max_size=5)


@pytest.fixture
def sample_task():
    """Фикстура тестовой задачи."""
    return CategorizationTask(
        channel_id=-1001234567890,
        prompt="Тестовый промпт",
        original_text="Тестовый текст",
        title="Test Channel",
        desc="Test Description"
    )


class TestCategorizationQueue:
    """Тесты для очереди категоризации."""

    def test_init_default_size(self):
        """Тест инициализации с размером по умолчанию."""
        queue = CategorizationQueue()
        assert queue.max_size > 0

    def test_init_custom_size(self):
        """Тест инициализации с кастомным размером."""
        queue = CategorizationQueue(max_size=10)
        assert queue.max_size == 10

    def test_add_task(self, queue, sample_task):
        """Тест добавления задачи."""
        asyncio.run(queue.add(sample_task))
        assert queue.size == 1
        assert not queue.is_empty

    def test_add_multiple_tasks(self, queue, sample_task):
        """Тест добавления нескольких задач."""
        async def add_tasks():
            for i in range(3):
                task = CategorizationTask(
                    channel_id=i,
                    prompt=f"Prompt {i}",
                    original_text=f"Text {i}"
                )
                await queue.add(task)
            return queue.size

        size = asyncio.run(add_tasks())
        assert size == 3

    def test_queue_max_size(self, sample_task):
        """Тест ограничения размера очереди."""
        queue = CategorizationQueue(max_size=2)

        async def add_tasks():
            for i in range(5):
                task = CategorizationTask(
                    channel_id=i,
                    prompt=f"Prompt {i}",
                    original_text=f"Text {i}"
                )
                await queue.add(task)
            return queue.size

        size = asyncio.run(add_tasks())
        assert size == 2  # deque maxlen работает

    def test_get_task(self, queue, sample_task):
        """Тест получения задачи."""
        async def get_task():
            queue.start()  # Запускаем очередь
            await queue.add(sample_task)
            return await queue.get()

        task = asyncio.run(get_task())
        assert task is not None
        assert task.channel_id == sample_task.channel_id
        assert queue.is_empty

    @pytest.mark.asyncio
    async def test_get_task_blocks_when_empty(self, queue):
        """Тест блокировки get на пустой очереди."""
        queue.start()  # Запускаем очередь
        task = asyncio.create_task(queue.get())
        await asyncio.sleep(0.1)
        # Задача не должна завершиться, пока очередь пуста
        assert not task.done()
        await queue.stop()  # Останавливаем для завершения (async!)
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_start_stop(self, queue):
        """Тест запуска и остановки."""
        assert not queue.is_running
        queue.start()
        assert queue.is_running
        await queue.stop()  # async!
        assert not queue.is_running

    @pytest.mark.asyncio
    async def test_get_returns_none_on_stop(self, queue):
        """Тест получения None при остановке."""
        queue.start()
        # Получаем задачу, которая должна вернуть None после stop
        get_task = asyncio.create_task(queue.get())
        await asyncio.sleep(0.05)
        await queue.stop()  # async!
        result = await get_task
        assert result is None
