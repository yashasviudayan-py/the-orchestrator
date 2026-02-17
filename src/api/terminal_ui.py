"""
Terminal UI for Human-in-the-Loop approval system.

Provides interactive CLI for approving/rejecting operations.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.layout import Layout
from rich import box

from .approval import ApprovalRequest, ApprovalStatus, RiskLevel
from .approval_manager import ApprovalManager, get_approval_manager

logger = logging.getLogger(__name__)
console = Console()


class ApprovalTerminalUI:
    """
    Terminal UI for approval requests.

    Displays pending requests and allows interactive approval/rejection.
    """

    def __init__(self, manager: Optional[ApprovalManager] = None):
        """
        Initialize terminal UI.

        Args:
            manager: Approval manager (uses singleton if None)
        """
        self.manager = manager or get_approval_manager()
        self.console = console

    def _get_risk_color(self, risk_level: RiskLevel) -> str:
        """Get color for risk level."""
        colors = {
            RiskLevel.LOW: "green",
            RiskLevel.MEDIUM: "yellow",
            RiskLevel.HIGH: "orange1",
            RiskLevel.CRITICAL: "red",
        }
        return colors.get(risk_level, "white")

    def _format_request_panel(self, request: ApprovalRequest) -> Panel:
        """Format approval request as rich panel."""
        risk_color = self._get_risk_color(request.risk_level)

        # Build content
        content = f"""[bold]Operation:[/bold] {request.operation_type.value}
[bold]Description:[/bold] {request.description}
[bold]Risk Level:[/bold] [{risk_color}]{request.risk_level.value.upper()}[/{risk_color}]
[bold]Agent:[/bold] {request.agent_name or 'N/A'}
[bold]Task ID:[/bold] {request.task_id or 'N/A'}
[bold]Requested:[/bold] {request.created_at.strftime('%Y-%m-%d %H:%M:%S')}
[bold]Timeout:[/bold] {request.timeout_seconds}s"""

        # Add details if present
        if request.details:
            details_str = "\n".join(
                f"  • {k}: {v}" for k, v in request.details.items()
            )
            content += f"\n\n[bold]Details:[/bold]\n{details_str}"

        return Panel(
            content,
            title=f"[bold]Approval Request[/bold]",
            subtitle=f"[dim]ID: {request.request_id[:8]}...[/dim]",
            border_style=risk_color,
            box=box.ROUNDED,
        )

    def display_pending_requests(self) -> None:
        """Display all pending approval requests in a table."""
        pending = self.manager.get_pending_requests()

        if not pending:
            self.console.print("[yellow]No pending approval requests[/yellow]")
            return

        table = Table(title="Pending Approval Requests", box=box.ROUNDED)

        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Operation", style="magenta")
        table.add_column("Risk", justify="center")
        table.add_column("Description", overflow="fold")
        table.add_column("Agent", style="blue")
        table.add_column("Created", style="green")

        for req in pending:
            risk_color = self._get_risk_color(req.risk_level)
            table.add_row(
                req.request_id[:8] + "...",
                req.operation_type.value,
                f"[{risk_color}]{req.risk_level.value.upper()}[/{risk_color}]",
                req.description[:50] + "..." if len(req.description) > 50 else req.description,
                req.agent_name or "N/A",
                req.created_at.strftime("%H:%M:%S"),
            )

        self.console.print(table)

    async def review_request(self, request: ApprovalRequest) -> bool:
        """
        Review a single approval request interactively.

        Args:
            request: Approval request to review

        Returns:
            True if approved, False if rejected
        """
        self.console.clear()
        self.console.print(self._format_request_panel(request))
        self.console.print()

        # Prompt for decision
        approved = Confirm.ask(
            "[bold]Approve this request?[/bold]",
            default=False,
        )

        # Get optional note
        note = None
        if approved:
            note = Prompt.ask(
                "[green]Approval note (optional)[/green]",
                default="",
            )
        else:
            note = Prompt.ask(
                "[red]Rejection reason (optional)[/red]",
                default="",
            )

        note = note if note else None

        # Submit decision
        if approved:
            success = await self.manager.approve(request.request_id, note)
            if success:
                self.console.print(f"[green]✓ Request approved[/green]")
            else:
                self.console.print(f"[red]✗ Failed to approve request[/red]")
        else:
            success = await self.manager.reject(request.request_id, note)
            if success:
                self.console.print(f"[yellow]✗ Request rejected[/yellow]")
            else:
                self.console.print(f"[red]✗ Failed to reject request[/red]")

        return approved

    async def review_all_pending(self) -> dict:
        """
        Review all pending requests interactively.

        Returns:
            Summary statistics
        """
        pending = self.manager.get_pending_requests()

        if not pending:
            self.console.print("[yellow]No pending approval requests[/yellow]")
            return {"approved": 0, "rejected": 0, "total": 0}

        approved_count = 0
        rejected_count = 0

        self.console.print(
            f"[bold]Found {len(pending)} pending request(s)[/bold]\n"
        )

        for i, request in enumerate(pending, 1):
            self.console.print(
                f"[dim]Request {i} of {len(pending)}[/dim]\n"
            )

            approved = await self.review_request(request)

            if approved:
                approved_count += 1
            else:
                rejected_count += 1

            # Wait before next request
            if i < len(pending):
                self.console.print()
                input("Press Enter to continue to next request...")

        # Summary
        self.console.print(f"\n[bold green]Review Complete[/bold green]")
        self.console.print(f"Approved: {approved_count}")
        self.console.print(f"Rejected: {rejected_count}")
        self.console.print(f"Total: {len(pending)}")

        return {
            "approved": approved_count,
            "rejected": rejected_count,
            "total": len(pending),
        }

    def display_history(self, limit: int = 10) -> None:
        """
        Display approval history.

        Args:
            limit: Maximum number of entries to show
        """
        history = self.manager.get_history(limit=limit)

        if not history:
            self.console.print("[yellow]No approval history[/yellow]")
            return

        table = Table(title=f"Approval History (Last {limit})", box=box.ROUNDED)

        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Operation", style="magenta")
        table.add_column("Status", justify="center")
        table.add_column("Description", overflow="fold")
        table.add_column("Note", overflow="fold")
        table.add_column("Decided", style="green")

        for req in history:
            # Status color
            status_color = "green" if req.status == ApprovalStatus.APPROVED else "red"
            if req.status == ApprovalStatus.TIMEOUT:
                status_color = "yellow"

            table.add_row(
                req.request_id[:8] + "...",
                req.operation_type.value,
                f"[{status_color}]{req.status.value.upper()}[/{status_color}]",
                req.description[:40] + "..." if len(req.description) > 40 else req.description,
                (req.decision_note[:30] + "...") if req.decision_note and len(req.decision_note) > 30 else (req.decision_note or ""),
                req.decided_at.strftime("%H:%M:%S") if req.decided_at else "N/A",
            )

        self.console.print(table)

    def display_stats(self) -> None:
        """Display approval statistics."""
        stats = self.manager.get_stats()

        # Create stats panel
        content = f"""[bold]Pending:[/bold] {stats['pending']}
[bold]Total History:[/bold] {stats['total_history']}
[bold]Approval Rate:[/bold] {stats['approval_rate']:.1%}

[bold]By Status:[/bold]"""

        for status, count in stats["by_status"].items():
            content += f"\n  • {status}: {count}"

        content += "\n\n[bold]By Risk Level:[/bold]"
        for risk, count in stats["by_risk_level"].items():
            content += f"\n  • {risk}: {count}"

        panel = Panel(
            content,
            title="[bold]Approval Statistics[/bold]",
            border_style="blue",
            box=box.ROUNDED,
        )

        self.console.print(panel)

    async def run_interactive_mode(self) -> None:
        """
        Run interactive approval mode.

        Continuously monitors for pending requests and prompts for review.
        """
        self.console.print("[bold green]HITL Approval Terminal[/bold green]")
        self.console.print("[dim]Monitoring for approval requests...[/dim]\n")

        try:
            while True:
                # Check for pending requests
                pending = self.manager.get_pending_requests()

                if pending:
                    self.console.print(
                        f"\n[yellow]⚠ {len(pending)} pending request(s) detected[/yellow]"
                    )

                    # Ask if user wants to review
                    should_review = Confirm.ask(
                        "Review pending requests now?",
                        default=True,
                    )

                    if should_review:
                        await self.review_all_pending()

                # Wait before checking again
                await asyncio.sleep(2)

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Exiting interactive mode[/yellow]")


# CLI functions for standalone usage
async def cli_review_pending():
    """CLI command to review pending approvals."""
    ui = ApprovalTerminalUI()
    await ui.review_all_pending()


def cli_list_pending():
    """CLI command to list pending approvals."""
    ui = ApprovalTerminalUI()
    ui.display_pending_requests()


def cli_show_history(limit: int = 10):
    """CLI command to show approval history."""
    ui = ApprovalTerminalUI()
    ui.display_history(limit=limit)


def cli_show_stats():
    """CLI command to show approval statistics."""
    ui = ApprovalTerminalUI()
    ui.display_stats()


async def cli_interactive():
    """CLI command to run interactive approval mode."""
    ui = ApprovalTerminalUI()
    await ui.run_interactive_mode()


# Main entry point for testing
if __name__ == "__main__":
    import sys

    command = sys.argv[1] if len(sys.argv) > 1 else "interactive"

    if command == "list":
        cli_list_pending()
    elif command == "review":
        asyncio.run(cli_review_pending())
    elif command == "history":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        cli_show_history(limit)
    elif command == "stats":
        cli_show_stats()
    elif command == "interactive":
        asyncio.run(cli_interactive())
    else:
        console.print(f"[red]Unknown command: {command}[/red]")
        console.print("\nAvailable commands:")
        console.print("  list       - List pending requests")
        console.print("  review     - Review pending requests")
        console.print("  history    - Show approval history")
        console.print("  stats      - Show statistics")
        console.print("  interactive - Run interactive mode")
