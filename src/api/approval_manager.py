"""
Approval Manager - Manages approval request lifecycle.

Handles creation, tracking, and resolution of approval requests.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List

from .approval import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
    OperationType,
    RiskLevel,
    RiskClassifier,
)

logger = logging.getLogger(__name__)


class ApprovalTimeout(Exception):
    """Raised when approval request times out."""

    pass


class ApprovalManager:
    """
    Manages approval requests and responses.

    Tracks pending requests, handles timeouts, and maintains approval history.
    """

    def __init__(self, default_timeout: int = 300):
        """
        Initialize approval manager.

        Args:
            default_timeout: Default timeout in seconds
        """
        self.default_timeout = default_timeout

        # Active requests {request_id: ApprovalRequest}
        self.pending_requests: Dict[str, ApprovalRequest] = {}

        # Approval history
        self.history: List[ApprovalRequest] = []

        # Event for async waiting
        self._events: Dict[str, asyncio.Event] = {}

        # Callbacks for external notifications (e.g. SSE events)
        # on_request_created(request: ApprovalRequest) - called when a new approval is pending
        # on_request_decided(request: ApprovalRequest) - called when approved/rejected
        self._on_request_created: Optional[callable] = None
        self._on_request_decided: Optional[callable] = None

    def set_callbacks(
        self,
        on_request_created: Optional[callable] = None,
        on_request_decided: Optional[callable] = None,
    ) -> None:
        """
        Set callbacks for approval lifecycle events.

        Args:
            on_request_created: Called when a new approval request is created
            on_request_decided: Called when a request is approved or rejected
        """
        if on_request_created is not None:
            self._on_request_created = on_request_created
        if on_request_decided is not None:
            self._on_request_decided = on_request_decided

    async def request_approval(
        self,
        operation_type: OperationType,
        description: str,
        details: Optional[dict] = None,
        task_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> ApprovalResponse:
        """
        Request approval for an operation.

        Args:
            operation_type: Type of operation
            description: Human-readable description
            details: Additional details
            task_id: Associated task ID
            agent_name: Agent requesting approval
            timeout: Timeout in seconds (uses default if None)

        Returns:
            ApprovalResponse

        Raises:
            ApprovalTimeout: If request times out
        """
        # Create request
        request = RiskClassifier.create_request(
            operation_type=operation_type,
            description=description,
            details=details,
            task_id=task_id,
            agent_name=agent_name,
        )

        request.timeout_seconds = timeout or self.default_timeout

        # Check if approval is actually required
        if not RiskClassifier.requires_approval(request.risk_level):
            logger.info(f"Low risk operation - auto-approving: {description}")
            return ApprovalResponse(
                request_id=request.request_id,
                approved=True,
                note="Auto-approved (low risk)",
            )

        # Add to pending requests
        self.pending_requests[request.request_id] = request

        # Create event for waiting
        self._events[request.request_id] = asyncio.Event()

        logger.info(
            f"Approval requested: {operation_type.value} - {description} "
            f"(risk: {request.risk_level.value}, timeout: {request.timeout_seconds}s)"
        )

        # Notify external listeners (e.g. SSE stream) that approval is needed
        if self._on_request_created:
            try:
                result = self._on_request_created(request)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as cb_err:
                logger.warning(f"on_request_created callback error: {cb_err}")

        try:
            # Wait for approval with timeout
            await asyncio.wait_for(
                self._events[request.request_id].wait(),
                timeout=request.timeout_seconds,
            )

            # Get updated request
            request = self.pending_requests.pop(request.request_id)

            # Move to history
            self.history.append(request)

            logger.info(
                f"Approval {request.status.value}: {description}"
            )

            return ApprovalResponse(
                request_id=request.request_id,
                approved=(request.status == ApprovalStatus.APPROVED),
                note=request.decision_note,
                decided_at=request.decided_at or datetime.now(timezone.utc),
            )

        except asyncio.TimeoutError:
            # Timeout - mark as timeout
            request.status = ApprovalStatus.TIMEOUT
            request.decided_at = datetime.now(timezone.utc)

            self.pending_requests.pop(request.request_id, None)
            self.history.append(request)

            logger.warning(
                f"Approval timeout: {description} "
                f"(waited {request.timeout_seconds}s)"
            )

            # Notify external listeners so the dashboard updates
            if self._on_request_decided:
                try:
                    result = self._on_request_decided(request)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as cb_err:
                    logger.warning(f"on_request_decided callback error (timeout): {cb_err}")

            raise ApprovalTimeout(
                f"Approval request timed out after {request.timeout_seconds}s"
            )

        finally:
            # Cleanup event
            self._events.pop(request.request_id, None)

    async def approve(
        self,
        request_id: str,
        note: Optional[str] = None,
    ) -> bool:
        """
        Approve a pending request.

        Args:
            request_id: Request ID to approve
            note: Optional approval note

        Returns:
            True if approved, False if request not found
        """
        request = self.pending_requests.get(request_id)

        if not request:
            logger.warning(f"Approval request not found: {request_id}")
            return False

        request.status = ApprovalStatus.APPROVED
        request.decided_at = datetime.now(timezone.utc)
        request.decision_note = note

        # Signal waiting coroutine
        if request_id in self._events:
            self._events[request_id].set()

        # Notify external listeners
        if self._on_request_decided:
            try:
                result = self._on_request_decided(request)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as cb_err:
                logger.warning(f"on_request_decided callback error: {cb_err}")

        logger.info(f"Approved request {request_id}")

        return True

    async def reject(
        self,
        request_id: str,
        note: Optional[str] = None,
    ) -> bool:
        """
        Reject a pending request.

        Args:
            request_id: Request ID to reject
            note: Optional rejection note

        Returns:
            True if rejected, False if request not found
        """
        request = self.pending_requests.get(request_id)

        if not request:
            logger.warning(f"Approval request not found: {request_id}")
            return False

        request.status = ApprovalStatus.REJECTED
        request.decided_at = datetime.now(timezone.utc)
        request.decision_note = note

        # Signal waiting coroutine
        if request_id in self._events:
            self._events[request_id].set()

        # Notify external listeners
        if self._on_request_decided:
            try:
                result = self._on_request_decided(request)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as cb_err:
                logger.warning(f"on_request_decided callback error: {cb_err}")

        logger.info(f"Rejected request {request_id}: {note or 'No reason'}")

        return True

    def get_pending_requests(self) -> List[ApprovalRequest]:
        """
        Get all pending approval requests.

        Returns:
            List of pending requests
        """
        return list(self.pending_requests.values())

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """
        Get a specific approval request.

        Args:
            request_id: Request ID

        Returns:
            ApprovalRequest or None
        """
        # Check pending first
        if request_id in self.pending_requests:
            return self.pending_requests[request_id]

        # Check history
        for request in self.history:
            if request.request_id == request_id:
                return request

        return None

    def get_history(
        self,
        limit: Optional[int] = None,
        status: Optional[ApprovalStatus] = None,
    ) -> List[ApprovalRequest]:
        """
        Get approval history.

        Args:
            limit: Maximum number of requests to return
            status: Filter by status

        Returns:
            List of approval requests
        """
        history = self.history

        if status:
            history = [r for r in history if r.status == status]

        # Sort by decided_at descending
        history = sorted(
            history,
            key=lambda r: r.decided_at or datetime.min,
            reverse=True,
        )

        if limit:
            history = history[:limit]

        return history

    def get_stats(self) -> dict:
        """
        Get approval statistics.

        Returns:
            Stats dict
        """
        stats = {
            "pending": len(self.pending_requests),
            "total_history": len(self.history),
            "by_status": {},
            "by_risk_level": {},
            "approval_rate": 0.0,
        }

        # Count by status
        for status in ApprovalStatus:
            count = sum(1 for r in self.history if r.status == status)
            stats["by_status"][status.value] = count

        # Count by risk level
        for risk in RiskLevel:
            count = sum(1 for r in self.history if r.risk_level == risk)
            stats["by_risk_level"][risk.value] = count

        # Calculate approval rate
        total_decided = sum(
            1 for r in self.history
            if r.status in [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]
        )

        if total_decided > 0:
            approved = stats["by_status"].get(ApprovalStatus.APPROVED.value, 0)
            stats["approval_rate"] = approved / total_decided

        return stats

    def clear_history(self, older_than_hours: Optional[int] = None) -> int:
        """
        Clear approval history.

        Args:
            older_than_hours: Only clear requests older than this

        Returns:
            Number of requests cleared
        """
        if older_than_hours is None:
            count = len(self.history)
            self.history.clear()
            logger.info(f"Cleared {count} approval history entries")
            return count

        cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)

        original_count = len(self.history)
        self.history = [
            r for r in self.history
            if (r.decided_at or datetime.now(timezone.utc)) > cutoff
        ]

        cleared = original_count - len(self.history)
        logger.info(f"Cleared {cleared} approval entries older than {older_than_hours}h")

        return cleared


# Singleton instance
_approval_manager: Optional[ApprovalManager] = None


def get_approval_manager(default_timeout: int = 300) -> ApprovalManager:
    """
    Get or create approval manager singleton.

    Args:
        default_timeout: Default timeout in seconds

    Returns:
        ApprovalManager instance
    """
    global _approval_manager
    if _approval_manager is None:
        _approval_manager = ApprovalManager(default_timeout=default_timeout)
    return _approval_manager
