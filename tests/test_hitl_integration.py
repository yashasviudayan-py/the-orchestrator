"""
Tests for HITL integration with orchestrator.

Tests HITL gate, enhanced nodes, and integration.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.orchestrator.hitl_integration import (
    HITLGate,
    HITLEnhancedNodes,
    HITLConfig,
)
from src.api.approval import OperationType, RiskLevel, ApprovalStatus
from src.api.approval_manager import ApprovalManager, ApprovalTimeout
from src.state.schemas import TaskState, TaskStatus, AgentType


class TestHITLConfig:
    """Tests for HITL configuration."""

    def test_approval_required(self):
        """Test approval requirements."""
        assert HITLConfig.requires_approval(OperationType.CODE_EXECUTION) is True
        assert HITLConfig.requires_approval(OperationType.GIT_PUSH) is True
        assert HITLConfig.requires_approval(OperationType.AGENT_CALL) is False

    def test_get_timeout(self):
        """Test timeout by risk level."""
        assert HITLConfig.get_timeout(RiskLevel.LOW) == 60
        assert HITLConfig.get_timeout(RiskLevel.MEDIUM) == 300
        assert HITLConfig.get_timeout(RiskLevel.HIGH) == 600
        assert HITLConfig.get_timeout(RiskLevel.CRITICAL) == 900


class TestHITLGate:
    """Tests for HITL gate."""

    @pytest.fixture
    def mock_manager(self):
        """Create mock approval manager."""
        manager = Mock(spec=ApprovalManager)
        manager.request_approval = AsyncMock()
        return manager

    @pytest.fixture
    def hitl_gate(self, mock_manager):
        """Create HITL gate with mock manager."""
        return HITLGate(approval_manager=mock_manager, enabled=True)

    @pytest.fixture
    def task_state(self):
        """Create sample task state."""
        return TaskState(
            task_id="test-task-123",
            objective="Test objective",
            status=TaskStatus.RUNNING,
            current_agent="pr",
        )

    @pytest.mark.asyncio
    async def test_check_approval_approved(self, hitl_gate, mock_manager, task_state):
        """Test approval check when approved."""
        from src.api.approval import ApprovalResponse

        # Mock approval response
        mock_manager.request_approval.return_value = ApprovalResponse(
            request_id="req-123",
            approved=True,
            note="Looks good",
        )

        # Check approval
        approved = await hitl_gate.check_approval(
            operation_type=OperationType.GIT_PUSH,
            description="Push to remote",
            task_state=task_state,
        )

        assert approved is True
        mock_manager.request_approval.assert_called_once()

        # Check message added to state
        assert len(task_state.messages) == 1
        msg = task_state.messages[0]
        assert msg.content["hitl_decision"] == "approved"

    @pytest.mark.asyncio
    async def test_check_approval_rejected(self, hitl_gate, mock_manager, task_state):
        """Test approval check when rejected."""
        from src.api.approval import ApprovalResponse

        # Mock rejection response
        mock_manager.request_approval.return_value = ApprovalResponse(
            request_id="req-123",
            approved=False,
            note="Too risky",
        )

        # Check approval
        approved = await hitl_gate.check_approval(
            operation_type=OperationType.FILE_DELETE,
            description="Delete all files",
            task_state=task_state,
        )

        assert approved is False

        # Check message added
        assert len(task_state.messages) == 1
        msg = task_state.messages[0]
        assert msg.content["hitl_decision"] == "rejected"

    @pytest.mark.asyncio
    async def test_check_approval_timeout(self, hitl_gate, mock_manager, task_state):
        """Test approval timeout."""
        # Mock timeout
        mock_manager.request_approval.side_effect = ApprovalTimeout("Timeout")

        # Should raise timeout
        with pytest.raises(ApprovalTimeout):
            await hitl_gate.check_approval(
                operation_type=OperationType.CODE_EXECUTION,
                description="Execute code",
                task_state=task_state,
            )

        # Check error added
        assert len(task_state.errors) == 1
        assert "timeout" in task_state.errors[0].lower()

    @pytest.mark.asyncio
    async def test_check_approval_disabled(self, mock_manager, task_state):
        """Test approval check when HITL is disabled."""
        gate = HITLGate(approval_manager=mock_manager, enabled=False)

        # Should auto-approve
        approved = await gate.check_approval(
            operation_type=OperationType.GIT_PUSH,
            description="Push to remote",
            task_state=task_state,
        )

        assert approved is True
        mock_manager.request_approval.assert_not_called()


class TestHITLEnhancedNodes:
    """Tests for HITL-enhanced orchestrator nodes."""

    @pytest.fixture
    def mock_base_nodes(self):
        """Create mock base nodes."""
        nodes = Mock()
        nodes.call_research_agent = AsyncMock()
        nodes.call_context_agent = AsyncMock()
        nodes.call_pr_agent = AsyncMock()
        nodes.finalize = AsyncMock()
        return nodes

    @pytest.fixture
    def mock_hitl_gate(self):
        """Create mock HITL gate."""
        gate = Mock(spec=HITLGate)
        gate.check_approval = AsyncMock()
        return gate

    @pytest.fixture
    def enhanced_nodes(self, mock_base_nodes, mock_hitl_gate):
        """Create enhanced nodes."""
        return HITLEnhancedNodes(
            base_nodes=mock_base_nodes,
            hitl_gate=mock_hitl_gate,
        )

    @pytest.fixture
    def task_state_dict(self):
        """Create task state dict."""
        state = TaskState(
            task_id="test-123",
            objective="Test objective",
            status=TaskStatus.RUNNING,
        )
        return state.model_dump()

    @pytest.mark.asyncio
    async def test_call_research_agent_no_approval(
        self, enhanced_nodes, mock_base_nodes, mock_hitl_gate, task_state_dict
    ):
        """Test research agent doesn't require approval."""
        mock_base_nodes.call_research_agent.return_value = task_state_dict

        result = await enhanced_nodes.call_research_agent(task_state_dict)

        assert result == task_state_dict
        mock_base_nodes.call_research_agent.assert_called_once()
        mock_hitl_gate.check_approval.assert_not_called()

    @pytest.mark.asyncio
    async def test_call_context_agent_no_approval(
        self, enhanced_nodes, mock_base_nodes, mock_hitl_gate, task_state_dict
    ):
        """Test context agent doesn't require approval."""
        mock_base_nodes.call_context_agent.return_value = task_state_dict

        result = await enhanced_nodes.call_context_agent(task_state_dict)

        assert result == task_state_dict
        mock_base_nodes.call_context_agent.assert_called_once()
        mock_hitl_gate.check_approval.assert_not_called()

    @pytest.mark.asyncio
    async def test_call_pr_agent_approved(
        self, enhanced_nodes, mock_base_nodes, mock_hitl_gate, task_state_dict
    ):
        """Test PR agent with approval."""
        # Mock approval
        mock_hitl_gate.check_approval.return_value = True
        mock_base_nodes.call_pr_agent.return_value = task_state_dict

        result = await enhanced_nodes.call_pr_agent(task_state_dict)

        assert result == task_state_dict
        mock_hitl_gate.check_approval.assert_called_once()
        mock_base_nodes.call_pr_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_pr_agent_rejected(
        self, enhanced_nodes, mock_base_nodes, mock_hitl_gate, task_state_dict
    ):
        """Test PR agent with rejection."""
        # Mock rejection
        mock_hitl_gate.check_approval.return_value = False

        result = await enhanced_nodes.call_pr_agent(task_state_dict)

        # Should not call PR agent
        mock_base_nodes.call_pr_agent.assert_not_called()

        # Check error added and workflow stopped
        result_state = TaskState(**result)
        assert len(result_state.errors) > 0
        assert result_state.next_agent is None

    @pytest.mark.asyncio
    async def test_call_pr_agent_timeout(
        self, enhanced_nodes, mock_base_nodes, mock_hitl_gate, task_state_dict
    ):
        """Test PR agent with approval timeout."""
        # Mock timeout
        mock_hitl_gate.check_approval.side_effect = ApprovalTimeout("Timeout")

        result = await enhanced_nodes.call_pr_agent(task_state_dict)

        # Should not call PR agent
        mock_base_nodes.call_pr_agent.assert_not_called()

        # Check error and stopped workflow
        result_state = TaskState(**result)
        assert len(result_state.errors) > 0
        assert "timeout" in result_state.errors[0].lower()
        assert result_state.next_agent is None

    @pytest.mark.asyncio
    async def test_finalize_no_approval(
        self, enhanced_nodes, mock_base_nodes, mock_hitl_gate, task_state_dict
    ):
        """Test finalize doesn't require approval."""
        mock_base_nodes.finalize.return_value = task_state_dict

        result = await enhanced_nodes.finalize(task_state_dict)

        assert result == task_state_dict
        mock_base_nodes.finalize.assert_called_once()
        mock_hitl_gate.check_approval.assert_not_called()


class TestCreateHITLEnabledGraph:
    """Tests for creating HITL-enabled graphs."""

    def test_create_with_hitl_enabled(self):
        """Test creating graph with HITL enabled."""
        # This would require full graph setup
        # Skipping for unit tests - covered in integration tests
        pass

    def test_create_with_hitl_disabled(self):
        """Test creating graph with HITL disabled."""
        # This would require full graph setup
        # Skipping for unit tests - covered in integration tests
        pass
