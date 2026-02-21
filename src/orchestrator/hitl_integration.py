"""
HITL (Human-in-the-Loop) Integration for Orchestrator.

Adds approval gates to risky operations in the orchestrator workflow.
"""

import logging
from typing import Optional, Callable, Any
from functools import wraps

from ..state.schemas import TaskState, AgentType, MessageType, PRResult
from ..api.approval import OperationType, RiskLevel
from ..api.approval_manager import ApprovalManager, ApprovalTimeout, get_approval_manager

logger = logging.getLogger(__name__)


class HITLGate:
    """
    Human-in-the-Loop approval gate for orchestrator operations.

    Wraps agent operations and requires approval before execution.
    """

    def __init__(
        self,
        approval_manager: Optional[ApprovalManager] = None,
        enabled: bool = True,
    ):
        """
        Initialize HITL gate.

        Args:
            approval_manager: Approval manager (uses singleton if None)
            enabled: Whether HITL checks are enabled
        """
        self.manager = approval_manager or get_approval_manager()
        self.enabled = enabled

    async def check_approval(
        self,
        operation_type: OperationType,
        description: str,
        task_state: TaskState,
        details: Optional[dict] = None,
    ) -> bool:
        """
        Check if approval is granted for an operation.

        Args:
            operation_type: Type of operation
            description: Human-readable description
            task_state: Current task state
            details: Additional operation details

        Returns:
            True if approved, False if rejected

        Raises:
            ApprovalTimeout: If approval request times out
        """
        if not self.enabled:
            logger.debug(f"HITL gate disabled - auto-approving: {description}")
            return True

        logger.info(f"Requesting approval for: {description}")

        try:
            response = await self.manager.request_approval(
                operation_type=operation_type,
                description=description,
                details=details,
                task_id=task_state.task_id,
                agent_name=task_state.current_agent,
            )

            # Log decision to task state
            task_state.add_message(
                agent=AgentType.SUPERVISOR,
                message_type=MessageType.INFO,
                content={
                    "hitl_decision": "approved" if response.approved else "rejected",
                    "operation": operation_type.value,
                    "description": description,
                    "note": response.note,
                },
            )

            if response.approved:
                logger.info(f"Operation approved: {description}")
            else:
                logger.warning(f"Operation rejected: {description} - {response.note}")

            return response.approved

        except ApprovalTimeout as e:
            logger.error(f"Approval timeout: {description}")
            task_state.add_error(f"Approval timeout: {str(e)}")
            raise

    def require_approval(
        self,
        operation_type: OperationType,
        description_template: str = "{agent} operation",
    ):
        """
        Decorator to require approval before executing a function.

        Args:
            operation_type: Type of operation
            description_template: Description template (can use {agent}, {task_id})

        Returns:
            Decorator function
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(self, state: dict) -> dict:
                task_state = TaskState(**state)

                # Format description
                description = description_template.format(
                    agent=task_state.current_agent or "unknown",
                    task_id=task_state.task_id,
                    objective=task_state.objective,
                )

                # Check approval
                try:
                    approved = await self.hitl_gate.check_approval(
                        operation_type=operation_type,
                        description=description,
                        task_state=task_state,
                        details={"objective": task_state.objective},
                    )

                    if not approved:
                        # Operation rejected - add error and return
                        task_state.add_error(f"Operation rejected by user: {description}")
                        task_state.next_agent = None  # Stop workflow
                        return task_state.model_dump()

                    # Approved - execute function
                    return await func(self, task_state.model_dump())

                except ApprovalTimeout:
                    # Timeout - add error and stop workflow
                    task_state.add_error(f"Approval timeout: {description}")
                    task_state.next_agent = None
                    return task_state.model_dump()

            return wrapper

        return decorator


class HITLEnhancedNodes:
    """
    Enhanced orchestrator nodes with HITL approval gates.

    Wraps existing OrchestratorNodes to add approval checks.
    """

    def __init__(self, base_nodes: Any, hitl_gate: Optional[HITLGate] = None):
        """
        Initialize HITL-enhanced nodes.

        Args:
            base_nodes: Base OrchestratorNodes instance
            hitl_gate: HITL gate (creates new if None)
        """
        self.base_nodes = base_nodes
        self.hitl_gate = hitl_gate or HITLGate()

    async def call_research_agent(self, state: dict) -> dict:
        """
        Call research agent (low risk - no approval needed).

        Args:
            state: Task state dict

        Returns:
            Updated state dict
        """
        # Research is typically low risk - no approval needed
        logger.debug("Calling research agent (no approval required)")
        return await self.base_nodes.call_research_agent(state)

    async def call_context_agent(self, state: dict) -> dict:
        """
        Call context agent (low risk - no approval needed).

        Args:
            state: Task state dict

        Returns:
            Updated state dict
        """
        # Context retrieval is low risk - no approval needed
        logger.debug("Calling context agent (no approval required)")
        return await self.base_nodes.call_context_agent(state)

    async def call_pr_agent(self, state: dict) -> dict:
        """
        Call PR agent with two-phase flow:
        1. Generate preview (diff) without committing
        2. Show diff to user for approval
        3. On approve: commit, push, create PR
        4. On reject: clean up branch

        Args:
            state: Task state dict

        Returns:
            Updated state dict
        """
        task_state = TaskState(**state)

        # Build PR input from task state
        pr_input = {
            "title": task_state.objective,
            "body": self._build_pr_body(task_state),
            "repo_path": task_state.user_context.get("repo_path", "."),
        }

        # Phase 1: Generate preview (no commit)
        logger.info("PR-Agent Phase 1: Generating preview...")
        pr_agent = self.base_nodes.pr_agent
        preview = await pr_agent.generate_preview(pr_input)

        if not preview.get("success"):
            error_msg = preview.get("error", "Unknown generate error")
            logger.error(f"PR-Agent generate failed: {error_msg}")
            task_state.add_error(f"PR-Agent generate failed: {error_msg}")
            task_state.next_agent = None
            return task_state.model_dump()

        diff_text = preview.get("diff", "")
        branch_name = preview.get("branch_name")
        target_file = preview.get("target_file")
        files_changed = preview.get("files_changed", [])
        repo_path = pr_input["repo_path"]

        # Phase 2: Request approval with diff
        description = f"Review code changes and create pull request for: {task_state.objective}"

        try:
            approved = await self.hitl_gate.check_approval(
                operation_type=OperationType.PR_CREATE,
                description=description,
                task_state=task_state,
                details={
                    "diff": diff_text,
                    "branch_name": branch_name,
                    "target_file": target_file,
                    "files_changed": files_changed,
                    "objective": task_state.objective,
                },
            )

            if not approved:
                logger.warning("PR-Agent diff rejected by user — cleaning up")
                await pr_agent.cleanup_branch(repo_path, branch_name, target_file)
                task_state.add_error("PR changes rejected by user")
                task_state.next_agent = None
                return task_state.model_dump()

        except ApprovalTimeout:
            logger.error("PR-Agent approval timeout — cleaning up")
            await pr_agent.cleanup_branch(repo_path, branch_name, target_file)
            task_state.add_error("PR-Agent approval timeout")
            task_state.next_agent = None
            return task_state.model_dump()

        # Phase 3: Commit and push (approved)
        logger.info("PR-Agent Phase 2: Committing and pushing...")
        try:
            commit_input = {
                **pr_input,
                "branch_name": branch_name,
                "target_file": target_file,
            }
            result = await pr_agent.commit_and_push(commit_input)

            task_state.pr_results = PRResult(**result)

            task_state.add_message(
                AgentType.PR,
                MessageType.RESPONSE,
                content={
                    "result": "PR created" if result.get("success") else "PR failed",
                    "pr_url": result.get("pr_url"),
                    "branch": result.get("branch_name"),
                    "files": result.get("files_changed", []),
                },
            )

            return task_state.model_dump()

        except Exception as e:
            logger.error(f"PR-Agent commit failed: {e}")
            task_state.add_error(f"PR-Agent commit failed: {str(e)}")
            task_state.next_agent = None
            return task_state.model_dump()

    def _build_pr_body(self, task_state: TaskState) -> str:
        """Build PR description from task state."""
        parts = [task_state.objective]
        if task_state.research_results and task_state.research_results.summary:
            parts.append(f"\n## Research\n{task_state.research_results.summary}")
        if task_state.context_results and task_state.context_results.summary:
            parts.append(f"\n## Context\n{task_state.context_results.summary}")
        return "\n".join(parts)

    async def finalize(self, state: dict) -> dict:
        """
        Finalize task (no approval needed).

        Args:
            state: Task state dict

        Returns:
            Updated state dict
        """
        logger.debug("Finalizing task (no approval required)")
        return await self.base_nodes.finalize(state)


def create_hitl_enabled_graph(
    base_graph_class: type,
    enable_hitl: bool = True,
    **graph_kwargs,
):
    """
    Create an orchestrator graph with HITL approval gates enabled.

    Args:
        base_graph_class: Base graph class (OrchestratorGraph or EnhancedOrchestratorGraph)
        enable_hitl: Whether to enable HITL checks
        **graph_kwargs: Arguments to pass to graph constructor

    Returns:
        Graph instance with HITL integration
    """
    # Create base graph
    graph = base_graph_class(**graph_kwargs)

    # Create HITL gate
    hitl_gate = HITLGate(enabled=enable_hitl)

    # Wrap nodes with HITL checks
    original_nodes = graph.nodes
    graph.nodes = HITLEnhancedNodes(
        base_nodes=original_nodes,
        hitl_gate=hitl_gate,
    )

    # Store references for external access
    graph.hitl_gate = hitl_gate
    graph.hitl_enabled = enable_hitl

    logger.info(
        f"HITL integration {'enabled' if enable_hitl else 'disabled'} for graph"
    )

    return graph


# Configuration helper
class HITLConfig:
    """Configuration for HITL approval system."""

    # Default approval requirements by operation type
    APPROVAL_REQUIRED = {
        OperationType.CODE_EXECUTION: True,
        OperationType.FILE_WRITE: True,
        OperationType.FILE_DELETE: True,
        OperationType.GIT_COMMIT: True,
        OperationType.GIT_PUSH: True,
        OperationType.GIT_FORCE_PUSH: True,
        OperationType.GIT_BRANCH_DELETE: True,
        OperationType.API_CALL: False,  # Usually safe
        OperationType.NETWORK_REQUEST: True,
        OperationType.AGENT_CALL: False,  # Research/context are safe
        OperationType.PR_CREATE: True,
    }

    # Default timeout by risk level (seconds)
    TIMEOUT_BY_RISK = {
        RiskLevel.LOW: 60,  # 1 minute
        RiskLevel.MEDIUM: 300,  # 5 minutes
        RiskLevel.HIGH: 600,  # 10 minutes
        RiskLevel.CRITICAL: 900,  # 15 minutes
    }

    @classmethod
    def get_timeout(cls, risk_level: RiskLevel) -> int:
        """Get timeout for risk level."""
        return cls.TIMEOUT_BY_RISK.get(risk_level, 300)

    @classmethod
    def requires_approval(cls, operation_type: OperationType) -> bool:
        """Check if operation requires approval."""
        return cls.APPROVAL_REQUIRED.get(operation_type, True)
