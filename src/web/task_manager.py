"""
Task Manager for Command Center.

Manages background execution of orchestration tasks and progress tracking.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List
from collections import defaultdict

from ..state.schemas import TaskState, TaskStatus
from ..orchestrator import EnhancedOrchestratorGraph, create_hitl_enabled_graph, RoutingStrategy
from ..agents import ResearchAgentInterface, ContextCoreInterface, PRAgentInterface
from .models import TaskRequest, TaskInfo, ProgressEvent, ProgressEventType

logger = logging.getLogger(__name__)


class TaskManager:
    """
    Manages orchestration tasks and progress events.

    Handles:
    - Background task execution
    - Progress event streaming
    - Task state tracking
    - Event broadcasting
    """

    def __init__(
        self,
        research_agent: ResearchAgentInterface,
        context_agent: ContextCoreInterface,
        pr_agent: PRAgentInterface,
        llm_base_url: str = "http://localhost:11434",
        llm_model: str = "llama3.1:8b-instruct-q8_0",
    ):
        """
        Initialize task manager.

        Args:
            research_agent: Research agent interface
            context_agent: Context Core interface
            pr_agent: PR-Agent interface
            llm_base_url: Ollama base URL
            llm_model: Ollama model name
        """
        self.research_agent = research_agent
        self.context_agent = context_agent
        self.pr_agent = pr_agent
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model

        # Storage path for task history
        self.storage_path = Path.home() / ".orchestrator" / "task_history.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Active tasks {task_id: TaskState}
        self.tasks: Dict[str, TaskState] = {}

        # Task metadata {task_id: TaskInfo}
        self.task_info: Dict[str, TaskInfo] = {}

        # Progress events {task_id: [ProgressEvent]}
        self.events: Dict[str, List[ProgressEvent]] = defaultdict(list)

        # Event queues for SSE {task_id: asyncio.Queue}
        self.event_queues: Dict[str, asyncio.Queue] = {}

        # Background task handles {task_id: asyncio.Task}
        self.background_tasks: Dict[str, asyncio.Task] = {}

        # Load task history from disk
        self._load_tasks()

    async def start_task(self, request: TaskRequest) -> TaskState:
        """
        Start a new orchestration task in the background.

        Args:
            request: Task request

        Returns:
            Initial TaskState
        """
        # Create initial task state
        task_state = TaskState(
            objective=request.objective,
            user_context=request.user_context,
            max_iterations=request.max_iterations,
        )

        task_id = task_state.task_id

        # Store task
        self.tasks[task_id] = task_state

        # Create task info
        self.task_info[task_id] = TaskInfo(
            task_id=task_id,
            objective=request.objective,
            status=TaskStatus.PENDING,
            current_agent=None,
            iteration=0,
            max_iterations=request.max_iterations,
            routing_strategy=request.routing_strategy.value,
            hitl_enabled=request.enable_hitl,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Create event queue for SSE
        self.event_queues[task_id] = asyncio.Queue()

        # Send initial event
        await self._emit_event(
            task_id,
            ProgressEventType.TASK_START,
            {
                "task_id": task_id,
                "objective": request.objective,
                "max_iterations": request.max_iterations,
            },
        )

        # Start background execution
        bg_task = asyncio.ensure_future(
            self._run_orchestration(task_id, request)
        )
        self.background_tasks[task_id] = bg_task

        # Add callback to log if task fails
        def task_done_callback(future):
            try:
                future.result()
            except Exception as e:
                logger.error(f"Background task {task_id} raised exception: {e}", exc_info=True)

        bg_task.add_done_callback(task_done_callback)

        logger.info(f"Started background task {task_id}: {request.objective}")

        return task_state

    async def _run_orchestration(
        self,
        task_id: str,
        request: TaskRequest,
    ) -> None:
        """
        Run orchestration in background and emit progress events.

        Args:
            task_id: Task ID
            request: Task request
        """
        logger.info(f"🚀 BACKGROUND TASK STARTED for {task_id}")
        try:
            logger.info(f"Creating orchestrator for {task_id}")
            # Create orchestrator with HITL if enabled
            orchestrator = create_hitl_enabled_graph(
                base_graph_class=EnhancedOrchestratorGraph,
                enable_hitl=request.enable_hitl,
                research_agent=self.research_agent,
                context_agent=self.context_agent,
                pr_agent=self.pr_agent,
                llm_base_url=self.llm_base_url,
                llm_model=self.llm_model,
                routing_strategy=request.routing_strategy,
            )

            # Run orchestration
            logger.info(f"Running orchestration for task {task_id}")

            # Update status
            self._update_task_info(task_id, status=TaskStatus.RUNNING)

            # Progress callback to emit events during execution
            async def progress_callback(state_dict: dict):
                """Called on each node update during orchestration."""
                try:
                    # Extract state info
                    current_agent = state_dict.get("current_agent")
                    iteration = state_dict.get("iteration", 0)
                    status = state_dict.get("status")

                    # Update task info
                    self._update_task_info(
                        task_id,
                        current_agent=current_agent,
                        iteration=iteration,
                    )

                    # Emit progress event
                    await self._emit_event(
                        task_id,
                        ProgressEventType.AGENT_PROGRESS,
                        {
                            "task_id": task_id,
                            "current_agent": current_agent,
                            "iteration": iteration,
                            "status": status,
                        },
                    )
                except Exception as e:
                    logger.warning(f"Progress callback error: {e}")

            result = await orchestrator.run(
                objective=request.objective,
                user_context=request.user_context,
                max_iterations=request.max_iterations,
                routing_strategy=request.routing_strategy,
                progress_callback=progress_callback,
            )

            # Store result
            self.tasks[task_id] = result

            # Update task info
            self._update_task_info(
                task_id,
                status=result.status,
                current_agent=result.current_agent,
                iteration=result.iteration,
            )

            # Save to disk
            self._save_tasks()

            # Emit completion event
            await self._emit_event(
                task_id,
                ProgressEventType.COMPLETE,
                {
                    "task_id": task_id,
                    "status": result.status.value,
                    "iterations": result.iteration,
                    "final_output": result.final_output,
                },
            )

            logger.info(f"Task {task_id} completed with status: {result.status}")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)

            # Update status
            self._update_task_info(task_id, status=TaskStatus.FAILED)

            # Save to disk
            self._save_tasks()

            # Emit error event
            await self._emit_event(
                task_id,
                ProgressEventType.ERROR,
                {
                    "task_id": task_id,
                    "error": str(e),
                },
            )

        finally:
            # Cleanup
            self.background_tasks.pop(task_id, None)

    async def _emit_event(
        self,
        task_id: str,
        event_type: ProgressEventType,
        data: dict,
    ) -> None:
        """
        Emit progress event for a task.

        Args:
            task_id: Task ID
            event_type: Event type
            data: Event data
        """
        event = ProgressEvent(
            event=event_type,
            data=data,
        )

        # Store event
        self.events[task_id].append(event)

        # Send to queue for SSE
        if task_id in self.event_queues:
            await self.event_queues[task_id].put(event)

    def _update_task_info(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        current_agent: Optional[str] = None,
        iteration: Optional[int] = None,
    ) -> None:
        """Update task info metadata."""
        if task_id not in self.task_info:
            return

        info = self.task_info[task_id]

        if status is not None:
            info.status = status

        if current_agent is not None:
            info.current_agent = current_agent

        if iteration is not None:
            info.iteration = iteration

        info.updated_at = datetime.utcnow()

        # Set completion time
        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            info.completed_at = datetime.utcnow()
            info.duration_ms = int(
                (info.completed_at - info.created_at).total_seconds() * 1000
            )

    def get_task(self, task_id: str) -> Optional[TaskState]:
        """Get task state by ID."""
        return self.tasks.get(task_id)

    def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        """Get task info by ID."""
        return self.task_info.get(task_id)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: Optional[int] = None,
    ) -> List[TaskInfo]:
        """
        List tasks with optional filtering.

        Args:
            status: Filter by status
            limit: Maximum number of tasks

        Returns:
            List of task info
        """
        tasks = list(self.task_info.values())

        # Filter by status
        if status:
            tasks = [t for t in tasks if t.status == status]

        # Sort by created_at descending
        tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)

        # Apply limit
        if limit:
            tasks = tasks[:limit]

        return tasks

    def get_events(self, task_id: str) -> List[ProgressEvent]:
        """Get all events for a task."""
        return self.events.get(task_id, [])

    async def get_event_queue(self, task_id: str) -> asyncio.Queue:
        """Get event queue for SSE streaming."""
        if task_id not in self.event_queues:
            self.event_queues[task_id] = asyncio.Queue()
        return self.event_queues[task_id]

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.

        Args:
            task_id: Task ID

        Returns:
            True if cancelled, False if not found
        """
        if task_id in self.background_tasks:
            self.background_tasks[task_id].cancel()
            self._update_task_info(task_id, status=TaskStatus.FAILED)

            await self._emit_event(
                task_id,
                ProgressEventType.ERROR,
                {"task_id": task_id, "error": "Task cancelled by user"},
            )

            logger.info(f"Cancelled task {task_id}")
            return True

        return False

    def _load_tasks(self):
        """Load task history from JSON file."""
        if not self.storage_path.exists():
            logger.info("No task history file found - starting fresh")
            return

        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)

            # Load tasks
            for task_dict in data.get('tasks', []):
                try:
                    task_state = TaskState(**task_dict)
                    self.tasks[task_state.task_id] = task_state
                except Exception as e:
                    logger.warning(f"Failed to load task {task_dict.get('task_id')}: {e}")

            # Load task info
            for info_dict in data.get('task_info', []):
                try:
                    task_info = TaskInfo(**info_dict)
                    self.task_info[task_info.task_id] = task_info
                except Exception as e:
                    logger.warning(f"Failed to load task info {info_dict.get('task_id')}: {e}")

            logger.info(f"Loaded {len(self.tasks)} tasks from history")

        except Exception as e:
            logger.error(f"Failed to load task history: {e}")

    def _save_tasks(self):
        """Save task history to JSON file."""
        try:
            # Convert tasks and task_info to JSON-serializable dicts
            tasks_data = []
            for task in self.tasks.values():
                # Only save completed or failed tasks
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    tasks_data.append(task.model_dump(mode='json'))

            task_info_data = []
            for info in self.task_info.values():
                if info.task_id in [t['task_id'] for t in tasks_data]:
                    task_info_data.append(info.model_dump(mode='json'))

            data = {
                'tasks': tasks_data,
                'task_info': task_info_data,
                'saved_at': datetime.now().isoformat(),
            }

            # Write to file
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(tasks_data)} tasks to history")

        except Exception as e:
            logger.error(f"Failed to save task history: {e}")


# Singleton instance
_task_manager: Optional[TaskManager] = None


def get_task_manager(
    research_agent: Optional[ResearchAgentInterface] = None,
    context_agent: Optional[ContextCoreInterface] = None,
    pr_agent: Optional[PRAgentInterface] = None,
    **kwargs,
) -> TaskManager:
    """
    Get or create task manager singleton.

    Args:
        research_agent: Research agent (required on first call)
        context_agent: Context agent (required on first call)
        pr_agent: PR agent (required on first call)
        **kwargs: Additional arguments

    Returns:
        TaskManager instance
    """
    global _task_manager

    if _task_manager is None:
        if not all([research_agent, context_agent, pr_agent]):
            raise ValueError(
                "research_agent, context_agent, and pr_agent required on first call"
            )

        _task_manager = TaskManager(
            research_agent=research_agent,
            context_agent=context_agent,
            pr_agent=pr_agent,
            **kwargs,
        )

    return _task_manager
