"""
Unified FastAPI Server for The Orchestrator Command Center.

Combines task management, HITL approvals, agent monitoring, and analytics
into a single web interface.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from ..config import get_cached_settings
from ..agents import (
    ResearchAgentInterface,
    ContextCoreInterface,
    PRAgentInterface,
)
from ..api.approval_manager import get_approval_manager
from .models import (
    TaskRequest,
    TaskResponse,
    TaskListResponse,
    TaskDetailResponse,
    HealthResponse,
    AgentStatus,
    ProgressEventType,
)
from .task_manager import get_task_manager
from ..state.schemas import TaskStatus

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════════════════════

_WEB_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _WEB_DIR / "static"
_TEMPLATE_DIR = _WEB_DIR / "templates"

# ═══════════════════════════════════════════════════════════════════════
# Application Lifecycle
# ═══════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Manage application startup and shutdown."""
    logger.info("🚀 The Orchestrator - Command Center starting...")

    # Initialize agents
    settings = get_cached_settings()

    research_agent = ResearchAgentInterface(settings.research_agent_url)
    context_agent = ContextCoreInterface(settings.context_core_path)
    pr_agent = PRAgentInterface(settings.pr_agent_path)

    # Initialize task manager
    get_task_manager(
        research_agent=research_agent,
        context_agent=context_agent,
        pr_agent=pr_agent,
        llm_base_url=settings.ollama_base_url,
        llm_model=settings.ollama_model,
    )

    # Initialize approval manager
    get_approval_manager()

    logger.info("✓ Command Center ready - http://localhost:8080")

    yield

    logger.info("Shutting down Command Center...")


# ═══════════════════════════════════════════════════════════════════════
# FastAPI Application
# ═══════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="The Orchestrator - Command Center",
    description="Unified web interface for multi-agent orchestration",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve static files
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Jinja2 templates
_jinja = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)


# ═══════════════════════════════════════════════════════════════════════
# Pages
# ═══════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard page."""
    template = _jinja.get_template("dashboard.html")
    return template.render(title="Dashboard")


@app.get("/approvals", response_class=HTMLResponse)
async def approvals_page():
    """Approvals management page."""
    template = _jinja.get_template("approvals.html")
    return template.render(title="Approvals")


@app.get("/history", response_class=HTMLResponse)
async def history_page():
    """Task history page."""
    template = _jinja.get_template("history.html")
    return template.render(title="History")


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page():
    """Analytics dashboard page."""
    template = _jinja.get_template("analytics.html")
    return template.render(title="Analytics")


# ═══════════════════════════════════════════════════════════════════════
# Task Management API
# ═══════════════════════════════════════════════════════════════════════

@app.post("/api/tasks", response_model=TaskResponse)
async def create_task(request: TaskRequest):
    """
    Start a new orchestration task.

    The task runs in the background. Use the stream_url to get
    real-time progress updates via Server-Sent Events.
    """
    if not request.objective.strip():
        raise HTTPException(400, "Objective cannot be empty")

    task_manager = get_task_manager()

    logger.info(f"Creating task: {request.objective}")

    try:
        task_state = await task_manager.start_task(request)

        return TaskResponse(
            task_id=task_state.task_id,
            objective=request.objective,
            status=TaskStatus.PENDING,
            created_at=task_state.created_at,
            stream_url=f"/api/tasks/{task_state.task_id}/stream",
        )

    except Exception as e:
        logger.error(f"Failed to create task: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to create task: {str(e)}")


@app.get("/api/tasks", response_model=TaskListResponse)
async def list_tasks(
    status: Optional[TaskStatus] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum tasks to return"),
):
    """List orchestration tasks with optional filtering."""
    task_manager = get_task_manager()

    tasks = task_manager.list_tasks(status=status, limit=limit)

    return TaskListResponse(
        tasks=tasks,
        total=len(tasks),
        status_filter=status,
    )


@app.get("/api/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(task_id: str):
    """Get detailed information about a specific task."""
    task_manager = get_task_manager()

    task_state = task_manager.get_task(task_id)
    task_info = task_manager.get_task_info(task_id)

    if not task_state or not task_info:
        raise HTTPException(404, "Task not found")

    return TaskDetailResponse(
        task_id=task_id,
        objective=task_state.objective,
        status=task_state.status,
        current_agent=task_state.current_agent,
        iteration=task_state.iteration,
        max_iterations=task_state.max_iterations,
        routing_strategy=task_info.routing_strategy,
        hitl_enabled=task_info.hitl_enabled,
        created_at=task_state.created_at,
        updated_at=task_info.updated_at,
        completed_at=task_info.completed_at,
        duration_ms=task_info.duration_ms,
        research_results=task_state.research_results,
        context_results=task_state.context_results,
        pr_results=task_state.pr_results,
        final_output=task_state.final_output,
        messages=[msg.model_dump() for msg in task_state.messages],
        errors=task_state.errors,
    )


@app.get("/api/tasks/{task_id}/stream")
async def stream_task_progress(task_id: str):
    """
    Stream real-time progress updates for a task via Server-Sent Events.

    The client should listen for the following event types:
    - task_start: Task has started
    - agent_start: Agent is starting
    - agent_progress: Agent progress update
    - agent_complete: Agent finished
    - approval_required: Approval needed (HITL)
    - approval_decided: Approval decision made
    - iteration: New iteration started
    - routing_decision: Supervisor routing decision
    - complete: Task completed successfully
    - error: Task failed
    - keepalive: Connection keepalive ping
    """
    task_manager = get_task_manager()

    # Verify task exists
    if not task_manager.get_task_info(task_id):
        raise HTTPException(404, "Task not found")

    async def event_generator():
        """Generate SSE events for task progress."""
        queue = await task_manager.get_event_queue(task_id)

        # Send existing events first
        existing_events = task_manager.get_events(task_id)
        for event in existing_events:
            data = json.dumps(event.data)
            yield f"event: {event.event.value}\ndata: {data}\n\n"

        # Stream new events
        while True:
            try:
                # Wait for next event with timeout
                event = await asyncio.wait_for(queue.get(), timeout=30.0)

                # Send event
                data = json.dumps(event.data)
                yield f"event: {event.event.value}\ndata: {data}\n\n"

                # Stop streaming on completion or error
                if event.event in [ProgressEventType.COMPLETE, ProgressEventType.ERROR]:
                    break

            except asyncio.TimeoutError:
                # Send keepalive to prevent connection from closing
                yield f"event: keepalive\ndata: {{}}\n\n"

            except Exception as e:
                logger.error(f"Error streaming task {task_id}: {e}")
                error_data = json.dumps({"error": str(e)})
                yield f"event: error\ndata: {error_data}\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/api/tasks/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a running task."""
    task_manager = get_task_manager()

    success = await task_manager.cancel_task(task_id)

    if not success:
        raise HTTPException(404, "Task not found or not running")

    return {"cancelled": True, "task_id": task_id}


# ═══════════════════════════════════════════════════════════════════════
# HITL Approvals API (Integration with Phase 3)
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/approvals/pending")
async def get_pending_approvals():
    """Get all pending approval requests."""
    approval_manager = get_approval_manager()
    pending = approval_manager.get_pending_requests()

    return [
        {
            "request_id": req.request_id,
            "created_at": req.created_at.isoformat(),
            "operation_type": req.operation_type.value,
            "risk_level": req.risk_level.value,
            "description": req.description,
            "details": req.details,
            "task_id": req.task_id,
            "agent_name": req.agent_name,
            "timeout_seconds": req.timeout_seconds,
        }
        for req in pending
    ]


@app.post("/api/approvals/{request_id}/approve")
async def approve_request(request_id: str, note: str = ""):
    """Approve a pending approval request."""
    approval_manager = get_approval_manager()

    success = await approval_manager.approve(request_id, note or None)

    if not success:
        raise HTTPException(404, "Approval request not found")

    return {"approved": True, "request_id": request_id}


@app.post("/api/approvals/{request_id}/reject")
async def reject_request(request_id: str, note: str = ""):
    """Reject a pending approval request."""
    approval_manager = get_approval_manager()

    success = await approval_manager.reject(request_id, note or None)

    if not success:
        raise HTTPException(404, "Approval request not found")

    return {"rejected": True, "request_id": request_id}


@app.get("/api/approvals/history")
async def get_approval_history(
    limit: int = Query(50, ge=1, le=100),
):
    """Get approval history."""
    approval_manager = get_approval_manager()
    history = approval_manager.get_history(limit=limit)

    return [
        {
            "request_id": req.request_id,
            "created_at": req.created_at.isoformat(),
            "decided_at": req.decided_at.isoformat() if req.decided_at else None,
            "operation_type": req.operation_type.value,
            "risk_level": req.risk_level.value,
            "description": req.description,
            "status": req.status.value,
            "decision_note": req.decision_note,
        }
        for req in history
    ]


@app.get("/api/approvals/stats")
async def get_approval_stats():
    """Get approval statistics."""
    approval_manager = get_approval_manager()
    return approval_manager.get_stats()


# ═══════════════════════════════════════════════════════════════════════
# Health & System API
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Check overall system health."""
    agents_health = {}

    # TODO: Implement actual health checks for agents
    # For now, return unknown status
    agents_health["research"] = AgentStatus.UNKNOWN
    agents_health["context"] = AgentStatus.UNKNOWN
    agents_health["pr"] = AgentStatus.UNKNOWN
    agents_health["ollama"] = AgentStatus.UNKNOWN
    agents_health["redis"] = AgentStatus.UNKNOWN

    # Determine overall status
    statuses = list(agents_health.values())
    if any(s == AgentStatus.DOWN for s in statuses):
        overall = "down"
    elif any(s == AgentStatus.DEGRADED for s in statuses):
        overall = "degraded"
    else:
        overall = "healthy"

    return HealthResponse(
        status=overall,
        agents=agents_health,
        details={},
    )


# ═══════════════════════════════════════════════════════════════════════
# Run Server
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info",
    )
