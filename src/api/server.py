"""
FastAPI server for Human-in-the-Loop approval system.

Provides REST endpoints for managing approval requests and responses.
"""

import logging
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .approval import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
    OperationType,
    RiskLevel,
)
from .approval_manager import ApprovalManager, get_approval_manager

logger = logging.getLogger(__name__)


# Request/Response Models
class CreateApprovalRequest(BaseModel):
    """Request to create an approval."""

    operation_type: OperationType
    description: str
    details: Optional[dict] = None
    task_id: Optional[str] = None
    agent_name: Optional[str] = None
    timeout: Optional[int] = None


class ApprovalDecision(BaseModel):
    """Decision on an approval request."""

    request_id: str
    note: Optional[str] = None


class ApprovalStats(BaseModel):
    """Statistics about approvals."""

    pending: int
    total_history: int
    by_status: dict
    by_risk_level: dict
    approval_rate: float


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    logger.info("Starting HITL Approval Server")
    yield
    logger.info("Shutting down HITL Approval Server")


# Create FastAPI app
app = FastAPI(
    title="The Orchestrator - HITL Approval API",
    description="Human-in-the-Loop approval system for risky operations",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency to get approval manager
def get_manager() -> ApprovalManager:
    """Get approval manager singleton."""
    return get_approval_manager()


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "hitl-approval-server",
    }


# Approval request endpoints
@app.post("/approvals", response_model=dict)
async def create_approval_request(
    request: CreateApprovalRequest,
    manager: ApprovalManager = Depends(get_approval_manager),
):
    """
    Create a new approval request.

    This endpoint is typically called by agents when they need approval.
    It will block until approval is granted/rejected or timeout occurs.

    Args:
        request: Approval request details

    Returns:
        Approval response with decision
    """
    logger.info(
        f"Creating approval request: {request.operation_type} - {request.description}"
    )

    try:
        response = await manager.request_approval(
            operation_type=request.operation_type,
            description=request.description,
            details=request.details,
            task_id=request.task_id,
            agent_name=request.agent_name,
            timeout=request.timeout,
        )

        return {
            "request_id": response.request_id,
            "approved": response.approved,
            "note": response.note,
            "decided_at": response.decided_at.isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to create approval request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/approvals/pending", response_model=List[dict])
async def get_pending_requests(manager: ApprovalManager = Depends(get_approval_manager)):
    """
    Get all pending approval requests.

    Returns:
        List of pending approval requests
    """
    pending = manager.get_pending_requests()

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
            "status": req.status.value,
        }
        for req in pending
    ]


@app.get("/approvals/{request_id}", response_model=dict)
async def get_approval_request(
    request_id: str,
    manager: ApprovalManager = Depends(get_approval_manager),
):
    """
    Get a specific approval request by ID.

    Args:
        request_id: Request ID

    Returns:
        Approval request details
    """
    request = manager.get_request(request_id)

    if not request:
        raise HTTPException(status_code=404, detail="Approval request not found")

    return {
        "request_id": request.request_id,
        "created_at": request.created_at.isoformat(),
        "operation_type": request.operation_type.value,
        "risk_level": request.risk_level.value,
        "description": request.description,
        "details": request.details,
        "task_id": request.task_id,
        "agent_name": request.agent_name,
        "timeout_seconds": request.timeout_seconds,
        "status": request.status.value,
        "decided_at": request.decided_at.isoformat() if request.decided_at else None,
        "decision_note": request.decision_note,
    }


@app.post("/approvals/{request_id}/approve", response_model=dict)
async def approve_request(
    request_id: str,
    decision: Optional[ApprovalDecision] = None,
    manager: ApprovalManager = Depends(get_approval_manager),
):
    """
    Approve a pending approval request.

    Args:
        request_id: Request ID to approve
        decision: Optional approval decision with note

    Returns:
        Success status
    """
    note = decision.note if decision else None

    success = await manager.approve(request_id, note)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found or already decided",
        )

    logger.info(f"Approved request {request_id}: {note or 'No note'}")

    return {
        "success": True,
        "request_id": request_id,
        "action": "approved",
        "note": note,
    }


@app.post("/approvals/{request_id}/reject", response_model=dict)
async def reject_request(
    request_id: str,
    decision: Optional[ApprovalDecision] = None,
    manager: ApprovalManager = Depends(get_approval_manager),
):
    """
    Reject a pending approval request.

    Args:
        request_id: Request ID to reject
        decision: Optional rejection decision with note

    Returns:
        Success status
    """
    note = decision.note if decision else None

    success = await manager.reject(request_id, note)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found or already decided",
        )

    logger.info(f"Rejected request {request_id}: {note or 'No reason'}")

    return {
        "success": True,
        "request_id": request_id,
        "action": "rejected",
        "note": note,
    }


@app.get("/approvals/history", response_model=List[dict])
async def get_approval_history(
    limit: Optional[int] = Query(None, ge=1, le=100),
    status: Optional[ApprovalStatus] = None,
    manager: ApprovalManager = Depends(get_approval_manager),
):
    """
    Get approval history.

    Args:
        limit: Maximum number of requests to return (1-100)
        status: Filter by status

    Returns:
        List of historical approval requests
    """
    history = manager.get_history(limit=limit, status=status)

    return [
        {
            "request_id": req.request_id,
            "created_at": req.created_at.isoformat(),
            "operation_type": req.operation_type.value,
            "risk_level": req.risk_level.value,
            "description": req.description,
            "task_id": req.task_id,
            "agent_name": req.agent_name,
            "status": req.status.value,
            "decided_at": req.decided_at.isoformat() if req.decided_at else None,
            "decision_note": req.decision_note,
        }
        for req in history
    ]


@app.get("/approvals/stats", response_model=ApprovalStats)
async def get_approval_stats(manager: ApprovalManager = Depends(get_approval_manager)):
    """
    Get approval statistics.

    Returns:
        Statistics about approvals
    """
    stats = manager.get_stats()

    return ApprovalStats(**stats)


@app.delete("/approvals/history", response_model=dict)
async def clear_approval_history(
    older_than_hours: Optional[int] = Query(None, ge=1),
    manager: ApprovalManager = Depends(get_approval_manager),
):
    """
    Clear approval history.

    Args:
        older_than_hours: Only clear requests older than this (hours)

    Returns:
        Number of requests cleared
    """
    cleared = manager.clear_history(older_than_hours=older_than_hours)

    logger.info(f"Cleared {cleared} approval history entries")

    return {
        "success": True,
        "cleared": cleared,
        "older_than_hours": older_than_hours,
    }


# Run server (for development)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
    )
