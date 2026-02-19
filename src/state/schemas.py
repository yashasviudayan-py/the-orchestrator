"""
State schemas for the orchestrator using Pydantic.
Defines all data models for task state and agent communication.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentType(str, Enum):
    """Available agent types."""

    RESEARCH = "research"
    CONTEXT = "context"
    PR = "pr"
    SUPERVISOR = "supervisor"  # Phase 2: Routing decisions


class MessageType(str, Enum):
    """Types of messages between agents."""

    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    INFO = "info"


class AgentMessage(BaseModel):
    """Message exchanged between agents."""

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_name: AgentType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_type: MessageType
    content: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class ResearchResult(BaseModel):
    """Result from Research Agent."""

    topic: str
    report_path: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None  # Full report content in markdown
    urls: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    elapsed_ms: float = 0.0
    errors: dict[str, str] = Field(default_factory=dict)


class ContextResult(BaseModel):
    """Result from Context Core."""

    query: str
    relevant_docs: list[dict[str, Any]] = Field(default_factory=list)
    summary: Optional[str] = None
    has_prior_work: bool = False
    confidence: float = 0.0


class PRResult(BaseModel):
    """Result from PR-Agent."""

    title: str
    pr_url: Optional[str] = None
    branch_name: Optional[str] = None
    files_changed: list[str] = Field(default_factory=list)
    success: bool = False
    error: Optional[str] = None


class TaskState(BaseModel):
    """
    Complete state for an orchestration task.
    This is persisted in Redis and passed through LangGraph.
    """

    # Task identification
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # User input
    objective: str
    user_context: dict[str, Any] = Field(default_factory=dict)

    # Status tracking
    status: TaskStatus = TaskStatus.PENDING
    current_agent: Optional[AgentType] = None
    iteration: int = 0
    max_iterations: int = 10

    # Agent routing
    agents_called: list[AgentType] = Field(default_factory=list)
    next_agent: Optional[AgentType] = None

    # Agent results
    research_results: Optional[ResearchResult] = None
    context_results: Optional[ContextResult] = None
    pr_results: Optional[PRResult] = None

    # Communication
    messages: list[AgentMessage] = Field(default_factory=list)

    # Security
    secrets_detected: bool = False
    secret_patterns: list[str] = Field(default_factory=list)

    # Human-in-the-loop
    requires_approval: bool = False
    approval_requested_at: Optional[datetime] = None
    approved: Optional[bool] = None
    approval_note: Optional[str] = None

    # Error handling
    errors: list[str] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

    # Final output
    final_output: Optional[str] = None
    completed_at: Optional[datetime] = None

    @field_validator("iteration")
    @classmethod
    def check_max_iterations(cls, v, info):
        """Validate iteration doesn't exceed max."""
        max_iter = info.data.get("max_iterations", 10)
        if v > max_iter:
            raise ValueError(f"Iteration {v} exceeds max_iterations {max_iter}")
        return v

    def add_message(
        self,
        agent: AgentType,
        message_type: MessageType,
        content: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a message to the message history."""
        message = AgentMessage(
            agent_name=agent,
            message_type=message_type,
            content=content,
            metadata=metadata or {},
        )
        self.messages.append(message)
        self.updated_at = datetime.utcnow()

    def add_error(self, error: str) -> None:
        """Add an error to the error list."""
        self.errors.append(error)
        self.updated_at = datetime.utcnow()

    def increment_iteration(self) -> None:
        """Increment iteration counter and update timestamp."""
        self.iteration += 1
        self.updated_at = datetime.utcnow()

    def mark_agent_called(self, agent: AgentType) -> None:
        """Mark an agent as called."""
        if agent not in self.agents_called:
            self.agents_called.append(agent)
        self.current_agent = agent
        self.updated_at = datetime.utcnow()

    def request_approval(self, note: str | None = None) -> None:
        """Request human approval."""
        self.requires_approval = True
        self.approval_requested_at = datetime.utcnow()
        self.approval_note = note
        self.status = TaskStatus.WAITING_APPROVAL
        self.updated_at = datetime.utcnow()

    def approve(self) -> None:
        """Approve the task."""
        self.approved = True
        self.requires_approval = False
        self.status = TaskStatus.RUNNING
        self.updated_at = datetime.utcnow()

    def reject(self) -> None:
        """Reject the task."""
        self.approved = False
        self.requires_approval = False
        self.status = TaskStatus.CANCELLED
        self.updated_at = datetime.utcnow()

    def complete(self, output: str) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.final_output = output
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def fail(self, error: str) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.add_error(error)
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }


class TaskSummary(BaseModel):
    """Lightweight summary of a task for listing."""

    task_id: str
    objective: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    current_agent: Optional[AgentType] = None
    iteration: int = 0
    has_errors: bool = False

    @classmethod
    def from_task_state(cls, state: TaskState) -> "TaskSummary":
        """Create summary from full task state."""
        return cls(
            task_id=state.task_id,
            objective=state.objective,
            status=state.status,
            created_at=state.created_at,
            updated_at=state.updated_at,
            current_agent=state.current_agent,
            iteration=state.iteration,
            has_errors=len(state.errors) > 0,
        )
