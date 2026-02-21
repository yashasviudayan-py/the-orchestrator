"""
Unified FastAPI Server for The Orchestrator Command Center.

Combines task management, HITL approvals, agent monitoring, and analytics
into a single web interface.
"""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from ..config import get_cached_settings
from ..agents import (
    ResearchAgentInterface,
    ContextCoreInterface,
    PRAgentInterface,
    UnavailableAgentStub,
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
from .health_monitor import get_health_monitor
from .analytics import get_analytics_service
from .process_manager import get_process_manager, ServiceNotControllableError
from ..state.schemas import TaskStatus

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Conversational routing helpers
# ═══════════════════════════════════════════════════════════════════════

_CONVERSATIONAL_EXACT = {
    'hi', 'hey', 'hello', 'howdy', 'sup', 'yo', 'hiya',
    'thanks', 'thank you', 'thx', 'ty', 'thank u',
    'bye', 'goodbye', 'cya', 'see you', 'later',
    'ok', 'okay', 'k', 'cool', 'got it', 'nice', 'great',
    'awesome', 'perfect', 'sounds good', 'alright',
    'lol', 'haha', 'hehe', ':)', '👍',
    'good morning', 'good night', 'good evening', 'good afternoon',
    'how are you', 'how r u', "what's up", 'whats up',
    'who are you', 'what are you', 'what can you do',
}
_TASK_WORDS = {
    'fix', 'add', 'create', 'implement', 'build', 'write', 'debug',
    'update', 'delete', 'remove', 'test', 'deploy', 'refactor',
    'install', 'setup', 'configure', 'migrate', 'generate', 'push',
    'commit', 'pr', 'pull', 'merge', 'branch', 'diff', 'review',
    'research', 'find', 'search', 'analyze', 'analyse', 'explain',
    'show', 'list', 'get', 'fetch', 'run', 'execute', 'start',
}


def _is_conversational_msg(text: str) -> bool:
    """Return True if the message is conversational and needs no agents."""
    t = text.strip().lower().rstrip('!?.,')
    if t in _CONVERSATIONAL_EXACT:
        return True
    for p in _CONVERSATIONAL_EXACT:
        if t == p or t.startswith(p + ' '):
            return True
    words = t.split()
    if len(words) <= 3 and not any(w in _TASK_WORDS for w in words):
        return True
    return False


class ChatRequest(BaseModel):
    message: str
    repo_path: Optional[str] = None


# In-memory store for pending chat sessions (chat_id -> message)
# Small enough to not need TTL — entries are consumed on first stream connect
_pending_chats: dict[str, str] = {}


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

    # Initialize agents — use stubs for unavailable agents so the server
    # always starts and tasks fail with a clear message instead of silently.
    settings = get_cached_settings()

    research_agent = ResearchAgentInterface(settings.research_agent_url)

    try:
        context_agent = ContextCoreInterface(settings.context_core_path)
        logger.info("✓ Context Core initialized")
    except Exception as e:
        logger.warning(f"Context Core unavailable — using stub: {e}")
        context_agent = UnavailableAgentStub("context", str(e))

    try:
        pr_agent = PRAgentInterface(settings.pr_agent_path)
        logger.info("✓ PR-Agent initialized")
    except Exception as e:
        logger.warning(f"PR-Agent unavailable — using stub: {e}")
        pr_agent = UnavailableAgentStub("pr", str(e))

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


@app.get("/health", response_class=HTMLResponse)
async def health_page():
    """Health monitoring page."""
    template = _jinja.get_template("health.html")
    return template.render(title="Health")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    """Settings page."""
    template = _jinja.get_template("settings.html")
    return template.render(title="Settings")


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
        research_results=task_state.research_results.model_dump() if task_state.research_results else None,
        context_results=task_state.context_results.model_dump() if task_state.context_results else None,
        pr_results=task_state.pr_results.model_dump() if task_state.pr_results else None,
        final_output=task_state.final_output,
        messages=[msg.model_dump() for msg in task_state.messages],
        errors=task_state.errors,
    )


@app.get("/api/tasks/{task_id}/stream")
async def stream_task_progress(task_id: str, request: Request):
    """
    Stream real-time progress updates for a task via Server-Sent Events.

    Supports Last-Event-ID header so reconnecting clients only receive
    events they haven't seen yet, preventing duplicate display in the UI.
    """
    task_manager = get_task_manager()

    # Verify task exists
    if not task_manager.get_task_info(task_id):
        raise HTTPException(404, "Task not found")

    # Determine which events the client has already received
    last_event_id_header = request.headers.get("Last-Event-ID", "")
    try:
        last_seen_id = int(last_event_id_header)
    except (ValueError, TypeError):
        last_seen_id = -1  # Client hasn't seen any events

    async def event_generator():
        """Generate SSE events, skipping already-seen ones on reconnect."""
        queue = await task_manager.get_event_queue(task_id)

        # Replay only events the client hasn't seen yet
        existing_events = task_manager.get_events(task_id)
        for event in existing_events:
            if event.event_id > last_seen_id:
                data = json.dumps(event.data)
                yield f"id: {event.event_id}\nevent: {event.event.value}\ndata: {data}\n\n"

        # If task already finished, close — no need to stream
        task_info = task_manager.get_task_info(task_id)
        if task_info and task_info.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            return

        # Stream new events as they arrive
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)

                data = json.dumps(event.data)
                yield f"id: {event.event_id}\nevent: {event.event.value}\ndata: {data}\n\n"

                if event.event in [ProgressEventType.COMPLETE, ProgressEventType.ERROR]:
                    break

            except asyncio.TimeoutError:
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
            "details": req.details,
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
    health_monitor = get_health_monitor()

    # Run all health checks
    agents_health = await health_monitor.check_all()

    # Determine overall status
    overall = health_monitor.get_overall_status(agents_health)

    # Build details dictionary with additional info
    details = {
        "timestamp": health_monitor.settings.timestamp() if hasattr(health_monitor.settings, 'timestamp') else None,
        "version": "1.0.0",
    }

    return HealthResponse(
        status=overall,
        agents=agents_health,
        details=details,
    )


# ═══════════════════════════════════════════════════════════════════════
# Analytics API
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/analytics/overview")
async def get_analytics_overview(days: int = Query(7, ge=1, le=30)):
    """
    Get complete analytics overview.

    Args:
        days: Number of days to look back (1-30)
    """
    analytics = get_analytics_service()
    return analytics.get_overview(days=days)


@app.get("/api/analytics/tasks")
async def get_task_analytics(days: int = Query(7, ge=1, le=30)):
    """Get task statistics."""
    analytics = get_analytics_service()
    return analytics.get_task_statistics(days=days)


@app.get("/api/analytics/agents")
async def get_agent_analytics(days: int = Query(7, ge=1, le=30)):
    """Get agent usage statistics."""
    analytics = get_analytics_service()
    return analytics.get_agent_statistics(days=days)


@app.get("/api/analytics/approvals")
async def get_approval_analytics(days: int = Query(7, ge=1, le=30)):
    """Get approval statistics."""
    analytics = get_analytics_service()
    return analytics.get_approval_statistics(days=days)


@app.get("/api/analytics/routing")
async def get_routing_analytics(days: int = Query(7, ge=1, le=30)):
    """Get routing decision statistics."""
    analytics = get_analytics_service()
    return analytics.get_routing_statistics(days=days)


@app.get("/api/analytics/performance")
async def get_performance_analytics(days: int = Query(7, ge=1, le=30)):
    """Get performance metrics."""
    analytics = get_analytics_service()
    return analytics.get_performance_metrics(days=days)


# ═══════════════════════════════════════════════════════════════════════
# Config API
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/config")
async def get_config():
    """Get system configuration (non-sensitive fields only)."""
    s = get_cached_settings()
    return {
        "ollama_model": s.ollama_model,
        "ollama_base_url": s.ollama_base_url,
        "redis_host": s.redis_host,
        "redis_port": s.redis_port,
    }


# ═══════════════════════════════════════════════════════════════════════
# Service Control API
# ═══════════════════════════════════════════════════════════════════════

_VALID_SERVICES = {"ollama", "redis", "research", "context", "pr"}


@app.post("/api/services/{service}/start")
async def start_service(service: str):
    """Start a controllable service (ollama or redis)."""
    if service not in _VALID_SERVICES:
        raise HTTPException(404, f"Unknown service: {service}")
    try:
        success, msg = await get_process_manager().start_service(service)
        return {"success": success, "service": service, "message": msg}
    except ServiceNotControllableError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Failed to start {service}: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to start {service}: {str(e)}")


@app.post("/api/services/{service}/stop")
async def stop_service(service: str):
    """Stop a controllable service (ollama or redis)."""
    if service not in _VALID_SERVICES:
        raise HTTPException(404, f"Unknown service: {service}")
    try:
        success, msg = await get_process_manager().stop_service(service)
        return {"success": success, "service": service, "message": msg}
    except ServiceNotControllableError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Failed to stop {service}: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to stop {service}: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════
# Chat API  (conversational bypass — no task created for simple chat)
# ═══════════════════════════════════════════════════════════════════════

@app.post("/api/chat")
async def chat_route(request: ChatRequest):
    """
    Smart chat router.

    Conversational messages (greetings, short questions) are answered
    directly by Ollama without creating a task.  Agent tasks (fix, build,
    research, etc.) are routed through the normal orchestration pipeline.

    Returns:
        {"type": "chat",  "stream_url": "/api/chat/{id}/stream"}  — direct LLM
        {"type": "task",  "task_id": ..., "stream_url": "/api/tasks/{id}/stream"}
    """
    message = request.message.strip()
    if not message:
        raise HTTPException(400, "Message cannot be empty")

    if _is_conversational_msg(message):
        chat_id = str(uuid.uuid4())
        _pending_chats[chat_id] = message
        logger.info(f"Chat (conversational): {message[:60]}")
        return {"type": "chat", "stream_url": f"/api/chat/{chat_id}/stream"}

    # Agent task → create task as usual
    task_manager = get_task_manager()
    user_context = {}
    if request.repo_path and request.repo_path.strip():
        user_context["repo_path"] = request.repo_path.strip()
    task_request = TaskRequest(
        objective=message,
        user_context=user_context,
        max_iterations=10,
        routing_strategy="adaptive",
        enable_hitl=True,
    )
    try:
        task_state = await task_manager.start_task(task_request)
        logger.info(f"Chat (task): {message[:60]} → {task_state.task_id}")
        return {
            "type": "task",
            "task_id": task_state.task_id,
            "stream_url": f"/api/tasks/{task_state.task_id}/stream",
        }
    except Exception as e:
        logger.error(f"Failed to create task from chat: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to start task: {str(e)}")


@app.get("/api/chat/{chat_id}/stream")
async def chat_stream(chat_id: str):
    """
    Stream a direct Ollama response for a conversational message.
    Emits SSE events:  chat_token  (each token),  chat_complete  (done),  error.
    """
    message = _pending_chats.pop(chat_id, None)
    if message is None:
        raise HTTPException(404, "Chat session not found or already consumed")

    settings = get_cached_settings()

    async def generate():
        try:
            payload = {
                "model": settings.ollama_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are The Orchestrator, a friendly AI assistant "
                            "for software project management. Be concise and helpful. "
                            "For greetings, respond warmly in 1-2 sentences."
                        ),
                    },
                    {"role": "user", "content": message},
                ],
                "stream": True,
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{settings.ollama_base_url}/api/chat",
                    json=payload,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield f"event: chat_token\ndata: {json.dumps({'token': token})}\n\n"
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
            yield f"event: chat_complete\ndata: {{}}\n\n"
        except Exception as e:
            logger.error(f"Chat stream error for {chat_id}: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
