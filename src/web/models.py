"""
Data models for Command Center web interface.

Defines request/response models for the unified web API.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field

from ..state.schemas import TaskStatus
from ..orchestrator.supervisor import RoutingStrategy


# ═══════════════════════════════════════════════════════════════════════
# Task Models
# ═══════════════════════════════════════════════════════════════════════

class TaskRequest(BaseModel):
    """Request to start a new orchestration task."""

    objective: str = Field(..., min_length=1, description="Task objective")
    user_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for the task"
    )
    max_iterations: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum iterations"
    )
    routing_strategy: RoutingStrategy = Field(
        default=RoutingStrategy.ADAPTIVE,
        description="Routing strategy to use"
    )
    enable_hitl: bool = Field(
        default=True,
        description="Enable HITL approval gates"
    )


class TaskInfo(BaseModel):
    """Information about an orchestration task."""

    task_id: str
    objective: str
    status: TaskStatus
    current_agent: Optional[str] = None
    next_agent: Optional[str] = None
    iteration: int = 0
    max_iterations: int = 10
    routing_strategy: str = "adaptive"
    hitl_enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None


class TaskResponse(BaseModel):
    """Response after creating a task."""

    task_id: str
    objective: str
    status: TaskStatus
    created_at: datetime
    stream_url: str


class TaskListResponse(BaseModel):
    """Response for listing tasks."""

    tasks: List[TaskInfo]
    total: int
    status_filter: Optional[TaskStatus] = None


class TaskDetailResponse(BaseModel):
    """Detailed task information including results."""

    task_id: str
    objective: str
    status: TaskStatus
    current_agent: Optional[str]
    iteration: int
    max_iterations: int
    routing_strategy: str
    hitl_enabled: bool
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    duration_ms: Optional[int]

    # Results
    research_results: Optional[Dict] = None
    context_results: Optional[Dict] = None
    pr_results: Optional[Dict] = None
    final_output: Optional[str] = None

    # Metadata
    messages: List[Dict] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# Progress Event Models
# ═══════════════════════════════════════════════════════════════════════

class ProgressEventType(str, Enum):
    """Types of progress events."""

    TASK_START = "task_start"
    AGENT_START = "agent_start"
    AGENT_PROGRESS = "agent_progress"
    AGENT_COMPLETE = "agent_complete"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_DECIDED = "approval_decided"
    ITERATION = "iteration"
    ROUTING_DECISION = "routing_decision"
    COMPLETE = "complete"
    ERROR = "error"
    KEEPALIVE = "keepalive"


class ProgressEvent(BaseModel):
    """Progress event for SSE streaming."""

    event: ProgressEventType
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: int = 0  # Sequential ID for Last-Event-ID replay tracking


# ═══════════════════════════════════════════════════════════════════════
# Agent Health Models
# ═══════════════════════════════════════════════════════════════════════

class AgentStatus(str, Enum):
    """Agent health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class AgentHealth(BaseModel):
    """Health information for an agent."""

    name: str
    type: str  # "research", "context", "pr", "ollama", "redis"
    status: AgentStatus
    last_check: datetime
    response_time_ms: Optional[int] = None
    error: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class AgentListResponse(BaseModel):
    """Response for listing all agents."""

    agents: List[AgentHealth]
    overall_status: AgentStatus


# ═══════════════════════════════════════════════════════════════════════
# Statistics Models
# ═══════════════════════════════════════════════════════════════════════

class TaskStatistics(BaseModel):
    """Statistics about task execution."""

    total_tasks: int
    completed: int
    failed: int
    running: int
    pending: int
    success_rate: float
    avg_duration_ms: Optional[float] = None
    avg_iterations: float


class AgentStatistics(BaseModel):
    """Statistics about agent usage."""

    agent_name: str
    total_calls: int
    total_duration_ms: int
    avg_duration_ms: float
    success_count: int
    failure_count: int


class RoutingStatistics(BaseModel):
    """Statistics about routing decisions."""

    strategy: str
    count: int
    avg_confidence: float
    agents_chosen: Dict[str, int]  # {agent_name: count}


class OverallStatistics(BaseModel):
    """Overall system statistics."""

    tasks: TaskStatistics
    agents: List[AgentStatistics]
    routing: List[RoutingStatistics]
    approval_stats: Dict[str, Any]  # From ApprovalManager


# ═══════════════════════════════════════════════════════════════════════
# WebSocket Models
# ═══════════════════════════════════════════════════════════════════════

class WSMessageType(str, Enum):
    """WebSocket message types."""

    # Server -> Client
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_DECIDED = "approval_decided"
    TASK_UPDATE = "task_update"
    AGENT_STATUS = "agent_status"

    # Client -> Server
    APPROVE = "approve"
    REJECT = "reject"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


class WSMessage(BaseModel):
    """WebSocket message."""

    type: WSMessageType
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════════════
# Health & System Models
# ═══════════════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    """Overall system health."""

    status: str  # "healthy", "degraded", "down"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agents: Dict[str, AgentStatus]
    details: Dict[str, Any] = Field(default_factory=dict)


class ConfigResponse(BaseModel):
    """System configuration."""

    ollama_base_url: str
    ollama_model: str
    redis_host: str
    redis_port: int
    default_timeout: int
    max_iterations: int
    hitl_enabled_by_default: bool
    research_agent_url: str
