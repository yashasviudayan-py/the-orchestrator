"""
Phase 4 Demo: The Command Center

Demonstrates the full Command Center functionality:
1. Starting the web server (programmatically)
2. Submitting tasks via API
3. Monitoring task progress
4. Checking health status
5. Viewing analytics

Usage:
    python examples/phase4_demo.py
"""

import asyncio
import time
from datetime import datetime

import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

console = Console()

# Server URL (assumes server is running)
BASE_URL = "http://localhost:8080"


async def check_health() -> dict:
    """Check system health status."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/health")
        response.raise_for_status()
        return response.json()


async def submit_task(objective: str) -> dict:
    """Submit a new orchestration task."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/tasks",
            json={
                "objective": objective,
                "max_iterations": 10,
                "routing_strategy": "adaptive",
                "enable_hitl": True,
            },
        )
        response.raise_for_status()
        return response.json()


async def get_task(task_id: str) -> dict:
    """Get task details."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/tasks/{task_id}")
        response.raise_for_status()
        return response.json()


async def list_tasks() -> dict:
    """List all tasks."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/tasks")
        response.raise_for_status()
        return response.json()


async def get_analytics(days: int = 7) -> dict:
    """Get analytics overview."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/analytics/overview?days={days}")
        response.raise_for_status()
        return response.json()


async def get_approvals() -> list:
    """Get pending approvals."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/approvals/pending")
        response.raise_for_status()
        return response.json()


def display_health(health: dict):
    """Display health status."""
    status_colors = {
        "healthy": "green",
        "degraded": "yellow",
        "down": "red",
    }

    agent_colors = {
        "healthy": "✅",
        "degraded": "⚠️",
        "down": "❌",
        "unknown": "❓",
    }

    table = Table(title="System Health Status", show_header=True)
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Icon")

    overall_color = status_colors.get(health['status'], 'white')
    table.add_row(
        "Overall System",
        health['status'].upper(),
        agent_colors.get(health['status'], '❓'),
        style=overall_color,
    )
    table.add_section()

    for agent, status in health['agents'].items():
        icon = agent_colors.get(status, '❓')
        color = status_colors.get(status, 'white')
        table.add_row(
            agent.capitalize(),
            status.upper(),
            icon,
            style=color,
        )

    console.print(table)
    console.print()


def display_task(task: dict):
    """Display task information."""
    table = Table(show_header=True)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Task ID", task.get('task_id', 'N/A'))
    table.add_row("Objective", task.get('objective', 'N/A'))
    table.add_row("Status", task.get('status', 'N/A'))
    table.add_row("Stream URL", task.get('stream_url', 'N/A'))

    console.print(table)
    console.print()


def display_analytics(analytics: dict):
    """Display analytics overview."""
    tasks = analytics.get('tasks', {})
    agents = analytics.get('agents', {})
    approvals = analytics.get('approvals', {})
    performance = analytics.get('performance', {})

    # Task Statistics
    task_table = Table(title="Task Statistics", show_header=True)
    task_table.add_column("Metric", style="cyan")
    task_table.add_column("Value", style="green")

    task_table.add_row("Total Tasks", str(tasks.get('total_tasks', 0)))
    task_table.add_row("Success Rate", f"{tasks.get('success_rate', 0)}%")
    task_table.add_row("Avg Iterations", str(tasks.get('average_iterations', 0)))
    task_table.add_row("Completed", str(tasks.get('completed', 0)))
    task_table.add_row("Failed", str(tasks.get('failed', 0)))

    console.print(task_table)
    console.print()

    # Agent Statistics
    agent_table = Table(title="Agent Usage", show_header=True)
    agent_table.add_column("Agent", style="cyan")
    agent_table.add_column("Total Calls", style="white")
    agent_table.add_column("Success Rate", style="green")

    for agent_name, stats in agents.items():
        agent_table.add_row(
            agent_name.capitalize(),
            str(stats.get('total_calls', 0)),
            f"{stats.get('success_rate', 0)}%",
        )

    console.print(agent_table)
    console.print()

    # Approval Statistics
    approval_table = Table(title="Approval Statistics", show_header=True)
    approval_table.add_column("Metric", style="cyan")
    approval_table.add_column("Value", style="yellow")

    approval_table.add_row("Total Requests", str(approvals.get('total_requests', 0)))
    approval_table.add_row("Approval Rate", f"{approvals.get('approval_rate', 0)}%")
    approval_table.add_row("Avg Response Time", f"{approvals.get('average_response_time', 0)}s")
    approval_table.add_row("Approved", str(approvals.get('approved', 0)))
    approval_table.add_row("Rejected", str(approvals.get('rejected', 0)))

    console.print(approval_table)
    console.print()


async def main():
    """Run the Phase 4 demo."""
    console.print(
        Panel.fit(
            "🚀 Phase 4: The Command Center Demo\n\n"
            "Demonstrating web interface and API functionality",
            title="The Orchestrator",
            border_style="bright_blue",
        )
    )
    console.print()

    try:
        # Step 1: Check Health
        console.print("[bold cyan]Step 1: Checking System Health[/bold cyan]")
        console.print()
        health = await check_health()
        display_health(health)

        # Step 2: Submit a Task
        console.print("[bold cyan]Step 2: Submitting a Task[/bold cyan]")
        console.print()

        objective = "Find best practices for Python async/await error handling"
        console.print(f"Objective: [italic]{objective}[/italic]")
        console.print()

        task = await submit_task(objective)
        display_task(task)

        console.print("[green]✓[/green] Task submitted successfully!")
        console.print(f"[dim]Monitor at: http://localhost:8080/api/tasks/{task['task_id']}/stream[/dim]")
        console.print()

        # Step 3: List Tasks
        console.print("[bold cyan]Step 3: Listing All Tasks[/bold cyan]")
        console.print()

        task_list = await list_tasks()
        console.print(f"Total tasks: {task_list['total']}")
        console.print()

        # Step 4: Check for Approvals
        console.print("[bold cyan]Step 4: Checking for Pending Approvals[/bold cyan]")
        console.print()

        approvals_list = await get_approvals()
        console.print(f"Pending approvals: {len(approvals_list)}")
        console.print()

        if len(approvals_list) > 0:
            console.print("[yellow]⚠️[/yellow] There are pending approvals!")
            console.print("[dim]Visit http://localhost:8080/approvals to review[/dim]")
        else:
            console.print("[green]✓[/green] No pending approvals")
        console.print()

        # Step 5: Get Analytics
        console.print("[bold cyan]Step 5: Fetching Analytics (Last 7 Days)[/bold cyan]")
        console.print()

        analytics = await get_analytics(days=7)
        display_analytics(analytics)

        # Summary
        console.print(
            Panel.fit(
                "✅ Demo Complete!\n\n"
                "Access the Command Center at:\n"
                "• Dashboard:  http://localhost:8080/\n"
                "• Approvals:  http://localhost:8080/approvals\n"
                "• History:    http://localhost:8080/history\n"
                "• Analytics:  http://localhost:8080/analytics",
                title="Success",
                border_style="green",
            )
        )

    except httpx.HTTPError as e:
        console.print(f"[red]❌ HTTP Error: {e}[/red]")
        console.print()
        console.print("[yellow]Make sure the Command Center is running:[/yellow]")
        console.print("[dim]uvicorn src.web.server:app --host 0.0.0.0 --port 8080[/dim]")
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")


if __name__ == "__main__":
    asyncio.run(main())
