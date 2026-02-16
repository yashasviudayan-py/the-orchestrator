"""
Unit tests for StateManager.
Demonstrates testing approach for Phase 1 components.
"""

import pytest
from datetime import datetime

from src.state.schemas import TaskState, TaskStatus, AgentType, MessageType
from src.state.manager import StateManager
from src.state.redis_client import RedisClient


@pytest.fixture
async def redis_client():
    """Create Redis client for testing."""
    client = RedisClient(host="localhost", port=6379, db=1)  # Use test DB
    await client.connect()
    yield client
    # Cleanup
    await client.flushdb()
    await client.disconnect()


@pytest.fixture
async def state_manager(redis_client):
    """Create state manager for testing."""
    return StateManager(redis_client, key_prefix="test:", default_ttl=60)


class TestStateManager:
    """Test suite for StateManager."""

    @pytest.mark.asyncio
    async def test_create_task(self, state_manager):
        """Test task creation."""
        objective = "Test objective"
        task = await state_manager.create_task(objective)

        assert task.task_id is not None
        assert task.objective == objective
        assert task.status == TaskStatus.PENDING
        assert task.iteration == 0

    @pytest.mark.asyncio
    async def test_get_task(self, state_manager):
        """Test task retrieval."""
        # Create task
        task = await state_manager.create_task("Test objective")

        # Retrieve task
        retrieved = await state_manager.get_task(task.task_id)

        assert retrieved is not None
        assert retrieved.task_id == task.task_id
        assert retrieved.objective == task.objective

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, state_manager):
        """Test retrieving non-existent task."""
        result = await state_manager.get_task("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_task(self, state_manager):
        """Test task update."""
        # Create task
        task = await state_manager.create_task("Test objective")

        # Update task
        task.status = TaskStatus.RUNNING
        task.iteration = 1
        success = await state_manager.update_task(task)

        assert success

        # Verify update
        updated = await state_manager.get_task(task.task_id)
        assert updated.status == TaskStatus.RUNNING
        assert updated.iteration == 1

    @pytest.mark.asyncio
    async def test_delete_task(self, state_manager):
        """Test task deletion."""
        # Create task
        task = await state_manager.create_task("Test objective")

        # Delete task
        success = await state_manager.delete_task(task.task_id)
        assert success

        # Verify deletion
        retrieved = await state_manager.get_task(task.task_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_list_tasks(self, state_manager):
        """Test listing tasks."""
        # Create multiple tasks
        await state_manager.create_task("Task 1")
        await state_manager.create_task("Task 2")
        await state_manager.create_task("Task 3")

        # List all tasks
        tasks = await state_manager.list_tasks()
        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_list_tasks_by_status(self, state_manager):
        """Test listing tasks filtered by status."""
        # Create tasks with different statuses
        task1 = await state_manager.create_task("Task 1")
        task2 = await state_manager.create_task("Task 2")

        task1.status = TaskStatus.RUNNING
        await state_manager.update_task(task1)

        # List running tasks only
        running = await state_manager.list_tasks(status=TaskStatus.RUNNING)
        assert len(running) == 1
        assert running[0].status == TaskStatus.RUNNING

        # List pending tasks only
        pending = await state_manager.list_tasks(status=TaskStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_add_message(self, state_manager):
        """Test adding messages to task."""
        from src.state.schemas import AgentMessage

        task = await state_manager.create_task("Test objective")

        # Add message
        message = AgentMessage(
            agent_name=AgentType.RESEARCH,
            message_type=MessageType.RESPONSE,
            content={"result": "test"},
        )

        success = await state_manager.add_message(task.task_id, message)
        assert success

        # Verify message added
        updated = await state_manager.get_task(task.task_id)
        assert len(updated.messages) == 1
        assert updated.messages[0].agent_name == AgentType.RESEARCH

    @pytest.mark.asyncio
    async def test_get_messages(self, state_manager):
        """Test retrieving task messages."""
        from src.state.schemas import AgentMessage

        task = await state_manager.create_task("Test objective")

        # Add multiple messages
        for i in range(5):
            message = AgentMessage(
                agent_name=AgentType.RESEARCH,
                message_type=MessageType.INFO,
                content={"index": i},
            )
            await state_manager.add_message(task.task_id, message)

        # Get all messages
        messages = await state_manager.get_messages(task.task_id)
        assert len(messages) == 5

        # Get limited messages
        messages = await state_manager.get_messages(task.task_id, limit=2)
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_get_stats(self, state_manager):
        """Test getting task statistics."""
        # Create tasks with different statuses
        task1 = await state_manager.create_task("Task 1")
        task2 = await state_manager.create_task("Task 2")
        task3 = await state_manager.create_task("Task 3")

        task1.status = TaskStatus.COMPLETED
        task2.status = TaskStatus.FAILED
        task3.status = TaskStatus.RUNNING
        task3.add_error("Test error")

        await state_manager.update_task(task1)
        await state_manager.update_task(task2)
        await state_manager.update_task(task3)

        # Get stats
        stats = await state_manager.get_stats()

        assert stats["total"] == 3
        assert stats["by_status"]["completed"] == 1
        assert stats["by_status"]["failed"] == 1
        assert stats["by_status"]["running"] == 1
        assert stats["with_errors"] == 1

    @pytest.mark.asyncio
    async def test_task_state_helpers(self, state_manager):
        """Test TaskState helper methods."""
        task = await state_manager.create_task("Test objective")

        # Test increment_iteration
        initial_iteration = task.iteration
        task.increment_iteration()
        assert task.iteration == initial_iteration + 1

        # Test add_error
        task.add_error("Test error")
        assert len(task.errors) == 1
        assert task.errors[0] == "Test error"

        # Test add_message
        task.add_message(
            AgentType.RESEARCH,
            MessageType.RESPONSE,
            {"result": "test"},
        )
        assert len(task.messages) == 1

        # Test mark_agent_called
        task.mark_agent_called(AgentType.CONTEXT)
        assert AgentType.CONTEXT in task.agents_called
        assert task.current_agent == AgentType.CONTEXT

        # Test complete
        task.complete("Task completed successfully")
        assert task.status == TaskStatus.COMPLETED
        assert task.final_output == "Task completed successfully"
        assert task.completed_at is not None

        # Test fail
        task2 = await state_manager.create_task("Test task 2")
        task2.fail("Task failed")
        assert task2.status == TaskStatus.FAILED
        assert len(task2.errors) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
