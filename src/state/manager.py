"""
State manager for task persistence in Redis.
Handles CRUD operations with proper serialization and TTL management.
"""

import json
import logging
from typing import Optional

from .redis_client import RedisClient
from .schemas import TaskState, TaskSummary, TaskStatus, AgentMessage

logger = logging.getLogger(__name__)


class StateManager:
    """Manages task state persistence in Redis."""

    def __init__(
        self,
        redis_client: RedisClient,
        key_prefix: str = "orchestrator:",
        default_ttl: int = 3600,  # 1 hour
    ):
        """
        Initialize state manager.

        Args:
            redis_client: Redis client instance
            key_prefix: Prefix for all Redis keys
            default_ttl: Default TTL in seconds
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl

    def _make_key(self, task_id: str) -> str:
        """Generate Redis key for task."""
        return f"{self.key_prefix}task:{task_id}"

    def _make_messages_key(self, task_id: str) -> str:
        """Generate Redis key for task messages list."""
        return f"{self.key_prefix}messages:{task_id}"

    async def create_task(
        self,
        objective: str,
        user_context: dict | None = None,
        max_iterations: int = 10,
    ) -> TaskState:
        """
        Create a new task.

        Args:
            objective: Task objective/goal
            user_context: Optional user context dict
            max_iterations: Maximum iterations allowed

        Returns:
            Created TaskState

        Raises:
            Exception: If task creation fails
        """
        try:
            state = TaskState(
                objective=objective,
                user_context=user_context or {},
                max_iterations=max_iterations,
                status=TaskStatus.PENDING,
            )

            # Serialize and save
            key = self._make_key(state.task_id)
            serialized = state.model_dump_json()

            success = await self.redis.set(key, serialized, ex=self.default_ttl)
            if not success:
                raise Exception("Failed to save task to Redis")

            logger.info(f"Created task {state.task_id}: {objective[:50]}...")
            return state

        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            raise

    async def get_task(self, task_id: str) -> Optional[TaskState]:
        """
        Get task by ID.

        Args:
            task_id: Task ID

        Returns:
            TaskState or None if not found
        """
        try:
            key = self._make_key(task_id)
            data = await self.redis.get(key)

            if not data:
                logger.warning(f"Task {task_id} not found")
                return None

            state = TaskState.model_validate_json(data)
            return state

        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {e}")
            return None

    async def update_task(self, state: TaskState) -> bool:
        """
        Update existing task.

        Args:
            state: Updated task state

        Returns:
            True if successful

        Raises:
            Exception: If update fails
        """
        try:
            key = self._make_key(state.task_id)

            # Check if task exists
            exists = await self.redis.exists(key)
            if not exists:
                raise ValueError(f"Task {state.task_id} does not exist")

            # Serialize and save
            serialized = state.model_dump_json()
            success = await self.redis.set(key, serialized, ex=self.default_ttl)

            if success:
                logger.debug(f"Updated task {state.task_id}")
                return True
            else:
                raise Exception("Redis SET returned False")

        except Exception as e:
            logger.error(f"Failed to update task {state.task_id}: {e}")
            raise

    async def delete_task(self, task_id: str) -> bool:
        """
        Delete task and associated data.

        Args:
            task_id: Task ID

        Returns:
            True if task was deleted
        """
        try:
            key = self._make_key(task_id)
            messages_key = self._make_messages_key(task_id)

            # Delete both task and messages
            deleted = await self.redis.delete(key, messages_key)

            if deleted > 0:
                logger.info(f"Deleted task {task_id}")
                return True
            else:
                logger.warning(f"Task {task_id} not found for deletion")
                return False

        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {e}")
            return False

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
    ) -> list[TaskSummary]:
        """
        List all tasks, optionally filtered by status.

        Args:
            status: Optional status filter
            limit: Maximum number of tasks to return

        Returns:
            List of task summaries
        """
        try:
            # Get all task keys
            pattern = f"{self.key_prefix}task:*"
            keys = await self.redis.keys(pattern)

            summaries = []
            for key in keys[:limit]:
                data = await self.redis.get(key)
                if data:
                    state = TaskState.model_validate_json(data)

                    # Filter by status if specified
                    if status is None or state.status == status:
                        summary = TaskSummary.from_task_state(state)
                        summaries.append(summary)

            # Sort by updated_at descending
            summaries.sort(key=lambda x: x.updated_at, reverse=True)

            logger.debug(f"Listed {len(summaries)} tasks")
            return summaries

        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return []

    async def add_message(
        self,
        task_id: str,
        message: AgentMessage,
    ) -> bool:
        """
        Add a message to task's message history.

        Args:
            task_id: Task ID
            message: Message to add

        Returns:
            True if successful
        """
        try:
            # Get current state
            state = await self.get_task(task_id)
            if not state:
                raise ValueError(f"Task {task_id} not found")

            # Add message
            state.messages.append(message)

            # Update task
            await self.update_task(state)

            logger.debug(f"Added message to task {task_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to add message to task {task_id}: {e}")
            return False

    async def get_messages(
        self,
        task_id: str,
        limit: Optional[int] = None,
    ) -> list[AgentMessage]:
        """
        Get messages for a task.

        Args:
            task_id: Task ID
            limit: Optional limit on number of messages

        Returns:
            List of messages
        """
        try:
            state = await self.get_task(task_id)
            if not state:
                return []

            messages = state.messages
            if limit:
                messages = messages[-limit:]

            return messages

        except Exception as e:
            logger.error(f"Failed to get messages for task {task_id}: {e}")
            return []

    async def extend_ttl(self, task_id: str, seconds: Optional[int] = None) -> bool:
        """
        Extend TTL for a task.

        Args:
            task_id: Task ID
            seconds: TTL in seconds (uses default if not specified)

        Returns:
            True if successful
        """
        try:
            key = self._make_key(task_id)
            ttl = seconds or self.default_ttl
            success = await self.redis.expire(key, ttl)

            if success:
                logger.debug(f"Extended TTL for task {task_id} to {ttl}s")
            return success

        except Exception as e:
            logger.error(f"Failed to extend TTL for task {task_id}: {e}")
            return False

    async def cleanup_completed(self, older_than_seconds: int = 86400) -> int:
        """
        Clean up completed/failed tasks older than specified time.

        Args:
            older_than_seconds: Delete tasks older than this (default 24h)

        Returns:
            Number of tasks deleted
        """
        try:
            from datetime import datetime, timedelta, timezone

            cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)

            tasks = await self.list_tasks()
            deleted_count = 0

            for task in tasks:
                # Only cleanup completed/failed/cancelled tasks
                if task.status in [
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                ]:
                    if task.updated_at < cutoff:
                        if await self.delete_task(task.task_id):
                            deleted_count += 1

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old tasks")

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup completed tasks: {e}")
            return 0

    async def get_stats(self) -> dict:
        """
        Get statistics about tasks.

        Returns:
            Dict with task statistics
        """
        try:
            tasks = await self.list_tasks()

            stats = {
                "total": len(tasks),
                "by_status": {},
                "with_errors": 0,
                "avg_iteration": 0.0,
            }

            if not tasks:
                return stats

            # Count by status
            for status in TaskStatus:
                count = sum(1 for t in tasks if t.status == status)
                stats["by_status"][status.value] = count

            # Count errors
            stats["with_errors"] = sum(1 for t in tasks if t.has_errors)

            # Average iteration
            total_iterations = sum(t.iteration for t in tasks)
            stats["avg_iteration"] = total_iterations / len(tasks) if tasks else 0.0

            return stats

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}
