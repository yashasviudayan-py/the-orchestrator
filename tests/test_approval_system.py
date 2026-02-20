"""
Tests for HITL approval system.

Tests approval schemas, manager, and risk classification.
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone

from src.api.approval import (
    RiskLevel,
    OperationType,
    ApprovalStatus,
    ApprovalRequest,
    ApprovalResponse,
    RiskClassifier,
)
from src.api.approval_manager import ApprovalManager, ApprovalTimeout


class TestRiskClassifier:
    """Tests for risk classification."""

    def test_classify_operation_types(self):
        """Test risk classification for different operation types."""
        assert RiskClassifier.classify(OperationType.AGENT_CALL) == RiskLevel.LOW
        assert RiskClassifier.classify(OperationType.FILE_WRITE) == RiskLevel.MEDIUM
        assert RiskClassifier.classify(OperationType.CODE_EXECUTION) == RiskLevel.HIGH
        assert RiskClassifier.classify(OperationType.GIT_FORCE_PUSH) == RiskLevel.CRITICAL

    def test_requires_approval(self):
        """Test approval requirement logic."""
        assert not RiskClassifier.requires_approval(RiskLevel.LOW)
        assert RiskClassifier.requires_approval(RiskLevel.MEDIUM)
        assert RiskClassifier.requires_approval(RiskLevel.HIGH)
        assert RiskClassifier.requires_approval(RiskLevel.CRITICAL)

    def test_create_request(self):
        """Test approval request creation."""
        request = RiskClassifier.create_request(
            operation_type=OperationType.GIT_PUSH,
            description="Push to main branch",
            details={"branch": "main"},
            task_id="task-123",
            agent_name="pr",
        )

        assert request.operation_type == OperationType.GIT_PUSH
        assert request.risk_level == RiskLevel.HIGH
        assert request.description == "Push to main branch"
        assert request.details == {"branch": "main"}
        assert request.task_id == "task-123"
        assert request.agent_name == "pr"
        assert request.status == ApprovalStatus.PENDING


class TestApprovalRequest:
    """Tests for ApprovalRequest model."""

    def test_approval_request_creation(self):
        """Test creating approval request."""
        request = ApprovalRequest(
            operation_type=OperationType.FILE_DELETE,
            risk_level=RiskLevel.HIGH,
            description="Delete important file",
            details={"file": "/path/to/file"},
        )

        assert request.request_id is not None
        assert request.created_at is not None
        assert request.status == ApprovalStatus.PENDING
        assert request.timeout_seconds == 300
        assert request.decided_at is None

    def test_approval_request_serialization(self):
        """Test request serialization to dict."""
        request = ApprovalRequest(
            operation_type=OperationType.API_CALL,
            risk_level=RiskLevel.MEDIUM,
            description="Call external API",
        )

        data = request.model_dump()

        assert data["operation_type"] == OperationType.API_CALL
        assert data["risk_level"] == RiskLevel.MEDIUM
        assert data["status"] == ApprovalStatus.PENDING


class TestApprovalManager:
    """Tests for ApprovalManager."""

    @pytest.fixture
    def manager(self):
        """Create approval manager for testing."""
        return ApprovalManager(default_timeout=2)  # Short timeout for tests

    @pytest.mark.asyncio
    async def test_auto_approve_low_risk(self, manager):
        """Test auto-approval for low risk operations."""
        response = await manager.request_approval(
            operation_type=OperationType.AGENT_CALL,
            description="Call research agent",
        )

        assert response.approved is True
        assert "auto-approved" in response.note.lower()

    @pytest.mark.asyncio
    async def test_approval_flow(self, manager):
        """Test full approval flow."""
        # Create approval request in background
        async def request_approval():
            return await manager.request_approval(
                operation_type=OperationType.GIT_PUSH,
                description="Push to remote",
                timeout=10,
            )

        # Start request
        task = asyncio.create_task(request_approval())

        # Wait a bit for request to be created
        await asyncio.sleep(0.1)

        # Get pending requests
        pending = manager.get_pending_requests()
        assert len(pending) == 1

        request = pending[0]

        # Approve it
        success = await manager.approve(request.request_id, "Looks good")

        # Wait for task to complete
        response = await task

        assert response.approved is True
        assert response.note == "Looks good"
        assert success is True

        # Check it's in history
        history = manager.get_history()
        assert len(history) == 1
        assert history[0].status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_rejection_flow(self, manager):
        """Test rejection flow."""
        # Create approval request in background
        async def request_approval():
            return await manager.request_approval(
                operation_type=OperationType.FILE_DELETE,
                description="Delete all files",
                timeout=10,
            )

        # Start request
        task = asyncio.create_task(request_approval())

        # Wait for request
        await asyncio.sleep(0.1)

        # Get and reject
        pending = manager.get_pending_requests()
        request = pending[0]

        success = await manager.reject(request.request_id, "Too risky")

        # Wait for task
        response = await task

        assert response.approved is False
        assert response.note == "Too risky"
        assert success is True

        # Check history
        history = manager.get_history()
        assert len(history) == 1
        assert history[0].status == ApprovalStatus.REJECTED

    @pytest.mark.asyncio
    async def test_timeout(self, manager):
        """Test approval timeout."""
        with pytest.raises(ApprovalTimeout):
            await manager.request_approval(
                operation_type=OperationType.CODE_EXECUTION,
                description="Execute dangerous code",
                timeout=1,  # 1 second timeout
            )

        # Check history shows timeout
        history = manager.get_history()
        assert len(history) == 1
        assert history[0].status == ApprovalStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_get_request(self, manager):
        """Test getting specific request."""
        # Create request
        async def request_approval():
            return await manager.request_approval(
                operation_type=OperationType.GIT_COMMIT,
                description="Commit changes",
                timeout=10,
            )

        task = asyncio.create_task(request_approval())
        await asyncio.sleep(0.1)

        # Get pending
        pending = manager.get_pending_requests()
        request_id = pending[0].request_id

        # Get by ID
        request = manager.get_request(request_id)
        assert request is not None
        assert request.request_id == request_id

        # Approve to clean up
        await manager.approve(request_id)
        await task

    def test_get_stats(self, manager):
        """Test getting statistics."""
        stats = manager.get_stats()

        assert "pending" in stats
        assert "total_history" in stats
        assert "by_status" in stats
        assert "by_risk_level" in stats
        assert "approval_rate" in stats

    def test_clear_history(self, manager):
        """Test clearing history."""
        # Add some history
        manager.history = [
            ApprovalRequest(
                operation_type=OperationType.FILE_WRITE,
                risk_level=RiskLevel.MEDIUM,
                description="Test",
                status=ApprovalStatus.APPROVED,
                decided_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
        ]

        # Clear all
        cleared = manager.clear_history()
        assert cleared == 1
        assert len(manager.history) == 0

    def test_clear_history_with_filter(self, manager):
        """Test clearing history with time filter."""
        # Add recent and old requests
        manager.history = [
            ApprovalRequest(
                operation_type=OperationType.FILE_WRITE,
                risk_level=RiskLevel.MEDIUM,
                description="Recent",
                status=ApprovalStatus.APPROVED,
                decided_at=datetime.now(timezone.utc),
            ),
            ApprovalRequest(
                operation_type=OperationType.FILE_WRITE,
                risk_level=RiskLevel.MEDIUM,
                description="Old",
                status=ApprovalStatus.APPROVED,
                decided_at=datetime.now(timezone.utc) - timedelta(hours=25),
            ),
        ]

        # Clear old (>24h)
        cleared = manager.clear_history(older_than_hours=24)
        assert cleared == 1
        assert len(manager.history) == 1
        assert manager.history[0].description == "Recent"


class TestApprovalResponse:
    """Tests for ApprovalResponse model."""

    def test_approval_response_creation(self):
        """Test creating approval response."""
        response = ApprovalResponse(
            request_id="req-123",
            approved=True,
            note="Approved by admin",
        )

        assert response.request_id == "req-123"
        assert response.approved is True
        assert response.note == "Approved by admin"
        assert response.decided_at is not None

    def test_approval_response_serialization(self):
        """Test response serialization."""
        response = ApprovalResponse(
            request_id="req-456",
            approved=False,
            note="Rejected",
        )

        data = response.model_dump()

        assert data["request_id"] == "req-456"
        assert data["approved"] is False
        assert data["note"] == "Rejected"
