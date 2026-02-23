"""
Task Manager for Command Center.

Manages background execution of orchestration tasks and progress tracking.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List
from collections import defaultdict

from ..state.schemas import TaskState, TaskStatus
from ..orchestrator import EnhancedOrchestratorGraph, create_hitl_enabled_graph
from ..agents import ResearchAgentInterface, ContextCoreInterface, PRAgentInterface
from ..api.approval_manager import get_approval_manager
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

        # Mapping from internal graph task_ids to TaskManager task_ids
        # Populated by progress_callback so approval routing is accurate
        self._graph_to_manager_task: Dict[str, str] = {}

        # Build the orchestrator once and reuse across tasks (LangGraph
        # compilation is expensive; the graph is stateless between runs).
        self._orchestrator = create_hitl_enabled_graph(
            base_graph_class=EnhancedOrchestratorGraph,
            enable_hitl=True,
            research_agent=self.research_agent,
            context_agent=self.context_agent,
            pr_agent=self.pr_agent,
            llm_base_url=self.llm_base_url,
            llm_model=self.llm_model,
        )
        logger.info("Orchestrator graph compiled and ready")

        # Wire approval callbacks to emit SSE events for the dashboard
        self._setup_approval_callbacks()

        # Load task history from disk
        self._load_tasks()

    def _setup_approval_callbacks(self) -> None:
        """Wire ApprovalManager callbacks to emit SSE events."""
        approval_manager = get_approval_manager()

        async def on_approval_requested(request):
            """Emit APPROVAL_REQUIRED event to the task's SSE stream."""
            # The graph creates its own TaskState with a different task_id than
            # the one TaskManager uses for SSE queues.  Resolve to whichever
            # active queue exists — try the request's task_id first, then fall
            # back to the currently running task.
            target_task_id = self._resolve_sse_task_id(request.task_id)
            if not target_task_id:
                logger.warning(
                    f"Cannot emit APPROVAL_REQUIRED — no matching SSE queue "
                    f"(request task_id={request.task_id}, queues={list(self.event_queues.keys())})"
                )
                return

            logger.info(f"Emitting APPROVAL_REQUIRED SSE event for task {target_task_id}")
            await self._emit_event(
                target_task_id,
                ProgressEventType.APPROVAL_REQUIRED,
                {
                    "task_id": target_task_id,
                    "request_id": request.request_id,
                    "operation_type": request.operation_type.value,
                    "risk_level": request.risk_level.value,
                    "description": request.description,
                    "details": request.details or {},
                    "agent_name": request.agent_name,
                    "timeout_seconds": request.timeout_seconds,
                },
            )

        async def on_approval_decided(request):
            """Emit APPROVAL_DECIDED or APPROVAL_TIMEOUT event to the task's SSE stream."""
            target_task_id = self._resolve_sse_task_id(request.task_id)
            if not target_task_id:
                return

            # Choose event type based on status
            status_value = getattr(request.status, 'value', None) if request.status else None
            is_timeout = status_value == "timeout"
            event_type = (
                ProgressEventType.APPROVAL_TIMEOUT if is_timeout
                else ProgressEventType.APPROVAL_DECIDED
            )

            logger.info(
                f"Emitting {event_type.value} SSE event for task {target_task_id}: "
                f"{status_value}"
            )
            await self._emit_event(
                target_task_id,
                event_type,
                {
                    "task_id": target_task_id,
                    "request_id": request.request_id,
                    "approved": request.status.value == "approved",
                    "status": request.status.value,
                    "note": request.decision_note,
                },
            )

        approval_manager.set_callbacks(
            on_request_created=on_approval_requested,
            on_request_decided=on_approval_decided,
        )
        logger.info("Approval callbacks wired for SSE event emission")

    def _resolve_sse_task_id(self, internal_task_id: Optional[str]) -> Optional[str]:
        """
        Resolve the correct SSE queue task_id.

        The orchestrator graph creates its own TaskState with a fresh UUID,
        which differs from the task_id used by TaskManager for SSE queues.
        This method maps back to the correct queue:
        1. Try the provided task_id directly
        2. Check the graph-to-manager mapping
        3. Fall back to the single currently-running background task (only if exactly one)
        """
        # Direct match
        if internal_task_id and internal_task_id in self.event_queues:
            return internal_task_id

        # Check the explicit mapping populated by progress_callback
        if internal_task_id and internal_task_id in self._graph_to_manager_task:
            mapped = self._graph_to_manager_task[internal_task_id]
            if mapped in self.event_queues:
                return mapped

        # Fall back only if exactly one active background task (avoid misrouting)
        active = [tid for tid in self.background_tasks if tid in self.event_queues]
        if len(active) == 1:
            return active[0]

        return None

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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
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
            # Reuse the shared orchestrator — toggle HITL per request
            orchestrator = self._orchestrator
            orchestrator.hitl_gate.enabled = request.enable_hitl

            # Run orchestration
            logger.info(f"Running orchestration for task {task_id}")

            # Update status
            self._update_task_info(task_id, status=TaskStatus.RUNNING)

            # Track previous state for detecting transitions
            _prev_agent = [None]   # mutable container for closure
            _prev_iteration = [0]

            # Progress callback to emit events during execution
            async def progress_callback(state_dict: dict):
                """Called on each node update during orchestration."""
                try:
                    # Extract state info
                    current_agent = state_dict.get("current_agent")
                    next_agent = state_dict.get("next_agent")
                    iteration = state_dict.get("iteration", 0)
                    status = state_dict.get("status")

                    # Register graph task_id → manager task_id mapping
                    graph_task_id = state_dict.get("task_id")
                    if graph_task_id and graph_task_id != task_id:
                        self._graph_to_manager_task[graph_task_id] = task_id

                    # Update task info
                    self._update_task_info(
                        task_id,
                        current_agent=current_agent,
                        iteration=iteration,
                    )

                    # Detect agent transitions and emit richer events
                    prev = _prev_agent[0]

                    # Agent started (transition from different/no agent)
                    if current_agent and current_agent != prev:
                        # Previous agent completed
                        if prev:
                            await self._emit_event(
                                task_id,
                                ProgressEventType.AGENT_COMPLETE,
                                {
                                    "task_id": task_id,
                                    "agent": prev,
                                    "iteration": iteration,
                                },
                            )
                        # New agent starting
                        await self._emit_event(
                            task_id,
                            ProgressEventType.AGENT_START,
                            {
                                "task_id": task_id,
                                "agent": current_agent,
                                "iteration": iteration,
                            },
                        )

                    # Routing decision made
                    if next_agent and next_agent != current_agent:
                        await self._emit_event(
                            task_id,
                            ProgressEventType.ROUTING_DECISION,
                            {
                                "task_id": task_id,
                                "from_agent": current_agent,
                                "next_agent": next_agent,
                                "iteration": iteration,
                            },
                        )

                    # Iteration advanced
                    if iteration > _prev_iteration[0]:
                        await self._emit_event(
                            task_id,
                            ProgressEventType.ITERATION,
                            {
                                "task_id": task_id,
                                "iteration": iteration,
                                "current_agent": current_agent,
                            },
                        )
                        _prev_iteration[0] = iteration

                    _prev_agent[0] = current_agent

                    # Always emit generic progress event
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
        event_id = len(self.events[task_id])  # 0-based sequential index
        event = ProgressEvent(
            event=event_type,
            data=data,
            event_id=event_id,
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
        """Update task info metadata and keep task_state in sync."""
        if task_id not in self.task_info:
            return

        info = self.task_info[task_id]

        if status is not None:
            info.status = status
            # Keep tasks dict in sync so the REST API reflects live status
            if task_id in self.tasks:
                self.tasks[task_id].status = status

        if current_agent is not None:
            info.current_agent = current_agent
            if task_id in self.tasks:
                try:
                    from ..state.schemas import AgentType
                    self.tasks[task_id].current_agent = AgentType(current_agent)
                except (ValueError, TypeError):
                    pass

        if iteration is not None:
            info.iteration = iteration
            if task_id in self.tasks:
                self.tasks[task_id].iteration = iteration

        info.updated_at = datetime.now(timezone.utc)

        # Set completion time
        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            info.completed_at = datetime.now(timezone.utc)
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
