"""
Approval system for Human-in-the-Loop (HITL) safety checks.

Defines risk levels, approval requirements, and approval workflows.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class RiskLevel(str, Enum):
    """Risk level classification for operations."""

    LOW = "low"  # No approval needed (read operations)
    MEDIUM = "medium"  # Approval recommended (non-destructive writes)
    HIGH = "high"  # Approval required (destructive operations)
    CRITICAL = "critical"  # Always requires approval (irreversible actions)


class OperationType(str, Enum):
    """Types of operations that may require approval."""

    # Code operations
    CODE_EXECUTION = "code_execution"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"

    # Git operations
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    GIT_FORCE_PUSH = "git_force_push"
    GIT_BRANCH_DELETE = "git_branch_delete"

    # External operations
    API_CALL = "api_call"
    NETWORK_REQUEST = "network_request"

    # Agent operations
    AGENT_CALL = "agent_call"
    PR_CREATE = "pr_create"


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    EXPIRED = "expired"


class ApprovalRequest(BaseModel):
    """Request for human approval of an operation."""

    model_config = ConfigDict()

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Operation details
    operation_type: OperationType
    risk_level: RiskLevel
    description: str
    details: dict[str, Any] = Field(default_factory=dict)

    # Context
    task_id: Optional[str] = None
    agent_name: Optional[str] = None

    # Approval settings
    timeout_seconds: int = 300  # 5 minutes default
    auto_approve: bool = False  # For testing/dev mode

    # Status
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None

    @field_serializer("created_at", "decided_at")
    def serialize_datetimes(self, v: datetime | None) -> str | None:
        return v.isoformat() if v is not None else None


class ApprovalResponse(BaseModel):
    """Response to an approval request."""

    model_config = ConfigDict()

    request_id: str
    approved: bool
    note: Optional[str] = None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_serializer("decided_at")
    def serialize_decided_at(self, v: datetime) -> str:
        return v.isoformat()


class RiskClassifier:
    """Classifies operations by risk level."""

    # Risk level mappings
    RISK_LEVELS = {
        # Low risk - no approval needed
        OperationType.AGENT_CALL: RiskLevel.LOW,

        # Medium risk - approval recommended
        OperationType.FILE_WRITE: RiskLevel.MEDIUM,
        OperationType.GIT_COMMIT: RiskLevel.MEDIUM,
        OperationType.PR_CREATE: RiskLevel.MEDIUM,
        OperationType.API_CALL: RiskLevel.MEDIUM,

        # High risk - approval required
        OperationType.CODE_EXECUTION: RiskLevel.HIGH,
        OperationType.FILE_DELETE: RiskLevel.HIGH,
        OperationType.GIT_PUSH: RiskLevel.HIGH,
        OperationType.NETWORK_REQUEST: RiskLevel.HIGH,

        # Critical risk - always requires approval
        OperationType.GIT_FORCE_PUSH: RiskLevel.CRITICAL,
        OperationType.GIT_BRANCH_DELETE: RiskLevel.CRITICAL,
    }

    @classmethod
    def classify(cls, operation_type: OperationType) -> RiskLevel:
        """
        Classify operation risk level.

        Args:
            operation_type: Type of operation

        Returns:
            Risk level
        """
        return cls.RISK_LEVELS.get(operation_type, RiskLevel.MEDIUM)

    @classmethod
    def requires_approval(cls, risk_level: RiskLevel) -> bool:
        """
        Determine if risk level requires approval.

        Args:
            risk_level: Risk level to check

        Returns:
            True if approval required
        """
        return risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

    @classmethod
    def create_request(
        cls,
        operation_type: OperationType,
        description: str,
        details: Optional[dict] = None,
        task_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Create an approval request with automatic risk classification.

        Args:
            operation_type: Type of operation
            description: Human-readable description
            details: Additional operation details
            task_id: Associated task ID
            agent_name: Agent requesting approval

        Returns:
            ApprovalRequest instance
        """
        risk_level = cls.classify(operation_type)

        return ApprovalRequest(
            operation_type=operation_type,
            risk_level=risk_level,
            description=description,
            details=details or {},
            task_id=task_id,
            agent_name=agent_name,
        )
