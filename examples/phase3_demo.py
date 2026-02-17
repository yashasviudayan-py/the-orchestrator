"""
Phase 3 Demo: HITL (Human-in-the-Loop) Approval System

Demonstrates:
1. Approval request creation and management
2. Risk classification
3. Approval/rejection flow
4. Timeout handling
5. Statistics and history
6. Terminal UI for interactive approvals
"""

import asyncio
import logging
from rich.console import Console
from rich.panel import Panel

from src.api.approval import (
    OperationType,
    RiskLevel,
    ApprovalStatus,
    RiskClassifier,
)
from src.api.approval_manager import ApprovalManager, ApprovalTimeout
from src.api.terminal_ui import ApprovalTerminalUI
from src.state.schemas import TaskState, TaskStatus

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()


async def demo_risk_classification():
    """Demonstrate risk classification system."""
    console.print(Panel.fit(
        "[bold cyan]Demo 1: Risk Classification System[/bold cyan]",
        border_style="cyan"
    ))

    operations = [
        OperationType.AGENT_CALL,
        OperationType.FILE_WRITE,
        OperationType.CODE_EXECUTION,
        OperationType.GIT_FORCE_PUSH,
    ]

    for op in operations:
        risk = RiskClassifier.classify(op)
        requires = RiskClassifier.requires_approval(risk)

        console.print(
            f"[bold]{op.value}[/bold] → "
            f"[{_get_risk_color(risk)}]{risk.value.upper()}[/{_get_risk_color(risk)}] "
            f"({'Approval Required' if requires else 'Auto-Approved'})"
        )

    console.print()


async def demo_auto_approval():
    """Demonstrate auto-approval for low risk operations."""
    console.print(Panel.fit(
        "[bold cyan]Demo 2: Auto-Approval (Low Risk)[/bold cyan]",
        border_style="cyan"
    ))

    manager = ApprovalManager(default_timeout=5)

    # Low risk operation - should auto-approve
    response = await manager.request_approval(
        operation_type=OperationType.AGENT_CALL,
        description="Call research agent to find best practices",
        task_id="demo-task-1",
        agent_name="research",
    )

    if response.approved:
        console.print("[green]✓ Auto-approved (low risk operation)[/green]")
        console.print(f"Note: {response.note}")
    else:
        console.print("[red]✗ Unexpected rejection[/red]")

    console.print()


async def demo_approval_flow():
    """Demonstrate manual approval flow."""
    console.print(Panel.fit(
        "[bold cyan]Demo 3: Manual Approval Flow[/bold cyan]",
        border_style="cyan"
    ))

    manager = ApprovalManager(default_timeout=10)

    # Create approval request in background
    async def request_approval():
        console.print("[yellow]Requesting approval for GIT PUSH operation...[/yellow]")

        response = await manager.request_approval(
            operation_type=OperationType.GIT_PUSH,
            description="Push changes to main branch",
            details={"branch": "main", "commits": 3},
            task_id="demo-task-2",
            agent_name="pr",
        )

        if response.approved:
            console.print(f"[green]✓ Operation approved: {response.note}[/green]")
        else:
            console.print(f"[red]✗ Operation rejected: {response.note}[/red]")

        return response

    # Start request in background
    task = asyncio.create_task(request_approval())

    # Wait for request to be created
    await asyncio.sleep(0.5)

    # Show pending requests
    pending = manager.get_pending_requests()
    console.print(f"[cyan]Pending requests: {len(pending)}[/cyan]")

    if pending:
        request = pending[0]
        console.print(f"  Request ID: {request.request_id[:8]}...")
        console.print(f"  Operation: {request.operation_type.value}")
        console.print(f"  Risk: {request.risk_level.value}")
        console.print(f"  Description: {request.description}")

        # Approve it
        console.print("\n[green]Approving request...[/green]")
        await manager.approve(request.request_id, "Demo approval - looks good!")

    # Wait for task to complete
    await task

    console.print()


async def demo_rejection_flow():
    """Demonstrate rejection flow."""
    console.print(Panel.fit(
        "[bold cyan]Demo 4: Rejection Flow[/bold cyan]",
        border_style="cyan"
    ))

    manager = ApprovalManager(default_timeout=10)

    # Create approval request
    async def request_approval():
        console.print("[yellow]Requesting approval for FILE DELETE operation...[/yellow]")

        response = await manager.request_approval(
            operation_type=OperationType.FILE_DELETE,
            description="Delete production database",
            details={"files": ["prod.db", "prod_backup.db"]},
            task_id="demo-task-3",
            agent_name="pr",
        )

        if response.approved:
            console.print(f"[green]✓ Operation approved: {response.note}[/green]")
        else:
            console.print(f"[red]✗ Operation rejected: {response.note}[/red]")

        return response

    # Start request
    task = asyncio.create_task(request_approval())
    await asyncio.sleep(0.5)

    # Get and reject
    pending = manager.get_pending_requests()
    if pending:
        request = pending[0]
        console.print(f"[cyan]Found risky operation: {request.description}[/cyan]")

        # Reject it
        console.print("[red]Rejecting request (too risky)...[/red]")
        await manager.reject(
            request.request_id,
            "Too risky - production database should not be deleted"
        )

    await task

    console.print()


async def demo_timeout():
    """Demonstrate timeout handling."""
    console.print(Panel.fit(
        "[bold cyan]Demo 5: Timeout Handling[/bold cyan]",
        border_style="cyan"
    ))

    manager = ApprovalManager(default_timeout=2)  # Short timeout for demo

    console.print("[yellow]Requesting approval with 2s timeout...[/yellow]")
    console.print("[dim](Not approving - will timeout)[/dim]\n")

    try:
        await manager.request_approval(
            operation_type=OperationType.CODE_EXECUTION,
            description="Execute untrusted code from external source",
            timeout=2,
        )
    except ApprovalTimeout as e:
        console.print(f"[red]✗ Approval timeout: {str(e)}[/red]")

        # Check it's in history with timeout status
        history = manager.get_history(limit=1)
        if history and history[0].status == ApprovalStatus.TIMEOUT:
            console.print("[yellow]Request recorded in history with TIMEOUT status[/yellow]")

    console.print()


async def demo_statistics():
    """Demonstrate statistics and history."""
    console.print(Panel.fit(
        "[bold cyan]Demo 6: Statistics and History[/bold cyan]",
        border_style="cyan"
    ))

    manager = ApprovalManager(default_timeout=5)

    # Create some requests
    console.print("[yellow]Creating sample approval history...[/yellow]\n")

    # Approve some
    for i in range(3):
        task = asyncio.create_task(
            manager.request_approval(
                operation_type=OperationType.FILE_WRITE,
                description=f"Write file {i}",
            )
        )
        await asyncio.sleep(0.1)

        pending = manager.get_pending_requests()
        if pending:
            await manager.approve(pending[0].request_id, f"Approval {i}")

        try:
            await task
        except:
            pass

    # Reject some
    for i in range(2):
        task = asyncio.create_task(
            manager.request_approval(
                operation_type=OperationType.GIT_PUSH,
                description=f"Push {i}",
            )
        )
        await asyncio.sleep(0.1)

        pending = manager.get_pending_requests()
        if pending:
            await manager.reject(pending[0].request_id, f"Rejection {i}")

        try:
            await task
        except:
            pass

    # Show statistics
    stats = manager.get_stats()

    console.print("[bold]Approval Statistics:[/bold]")
    console.print(f"  Total History: {stats['total_history']}")
    console.print(f"  Approval Rate: {stats['approval_rate']:.1%}")
    console.print(f"\n  By Status:")
    for status, count in stats['by_status'].items():
        console.print(f"    {status}: {count}")
    console.print(f"\n  By Risk Level:")
    for risk, count in stats['by_risk_level'].items():
        console.print(f"    {risk}: {count}")

    console.print()


async def demo_terminal_ui():
    """Demonstrate terminal UI for approvals."""
    console.print(Panel.fit(
        "[bold cyan]Demo 7: Terminal UI[/bold cyan]",
        border_style="cyan"
    ))

    manager = ApprovalManager(default_timeout=10)
    ui = ApprovalTerminalUI(manager)

    # Create some pending requests
    console.print("[yellow]Creating pending requests...[/yellow]\n")

    tasks = []
    for i in range(2):
        task = asyncio.create_task(
            manager.request_approval(
                operation_type=OperationType.PR_CREATE,
                description=f"Create PR for feature {i}",
                details={"feature": f"feature-{i}"},
            )
        )
        tasks.append(task)
        await asyncio.sleep(0.1)

    # Display pending requests in table
    ui.display_pending_requests()

    console.print("\n[dim]In a real scenario, you would review these interactively[/dim]")
    console.print("[dim]Run: python -m src.api.terminal_ui review[/dim]\n")

    # Auto-approve for demo
    pending = manager.get_pending_requests()
    for req in pending:
        await manager.approve(req.request_id, "Demo auto-approval")

    # Wait for tasks
    await asyncio.gather(*tasks, return_exceptions=True)

    # Show history
    console.print("\n[bold]Approval History:[/bold]")
    ui.display_history(limit=5)

    console.print()


async def demo_hitl_integration():
    """Demonstrate HITL integration with orchestrator."""
    console.print(Panel.fit(
        "[bold cyan]Demo 8: HITL Integration with Orchestrator[/bold cyan]",
        border_style="cyan"
    ))

    from src.orchestrator.hitl_integration import HITLGate

    # Create task state
    task_state = TaskState(
        task_id="demo-task-orchestrator",
        objective="Add authentication feature",
        status=TaskStatus.RUNNING,
        current_agent="pr",
    )

    # Create HITL gate
    hitl_gate = HITLGate(enabled=True)
    manager = hitl_gate.manager

    console.print("[yellow]Checking approval for PR creation...[/yellow]")

    # Request approval in background
    async def request_with_hitl():
        approved = await hitl_gate.check_approval(
            operation_type=OperationType.PR_CREATE,
            description="Create PR with authentication feature",
            task_state=task_state,
            details={"files_changed": 5, "lines_added": 200},
        )
        return approved

    task = asyncio.create_task(request_with_hitl())
    await asyncio.sleep(0.5)

    # Auto-approve for demo
    pending = manager.get_pending_requests()
    if pending:
        console.print(f"[cyan]HITL gate requested approval[/cyan]")
        console.print(f"  Operation: {pending[0].operation_type.value}")
        console.print(f"  Risk: {pending[0].risk_level.value}")

        await manager.approve(pending[0].request_id, "HITL demo approval")

    approved = await task

    if approved:
        console.print("[green]✓ PR creation approved - proceeding with operation[/green]")

        # Check message added to task state
        if task_state.messages:
            console.print(f"[dim]HITL decision logged in task state[/dim]")
    else:
        console.print("[red]✗ PR creation rejected - operation cancelled[/red]")

    console.print()


def _get_risk_color(risk_level: RiskLevel) -> str:
    """Get color for risk level."""
    colors = {
        RiskLevel.LOW: "green",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.HIGH: "orange1",
        RiskLevel.CRITICAL: "red",
    }
    return colors.get(risk_level, "white")


async def main():
    """Run all Phase 3 demos."""
    console.print("\n[bold green]═══ Phase 3: HITL Approval System Demo ═══[/bold green]\n")

    try:
        await demo_risk_classification()
        await demo_auto_approval()
        await demo_approval_flow()
        await demo_rejection_flow()
        await demo_timeout()
        await demo_statistics()
        await demo_terminal_ui()
        await demo_hitl_integration()

        console.print(Panel.fit(
            "[bold green]✓ All Phase 3 demos completed successfully![/bold green]\n\n"
            "Next steps:\n"
            "  1. Start approval server: python -m src.api.server\n"
            "  2. Run terminal UI: python -m src.api.terminal_ui interactive\n"
            "  3. Test with full orchestrator\n"
            "  4. Review docs/PHASE_3_GUIDE.md",
            border_style="green",
            title="[bold]Demo Complete[/bold]"
        ))

    except Exception as e:
        console.print(f"\n[red]Error during demo: {str(e)}[/red]")
        logger.exception("Demo failed")
        raise


if __name__ == "__main__":
    asyncio.run(main())
